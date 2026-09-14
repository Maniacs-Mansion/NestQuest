"""Versioned schema migration runner for the NestQuest SQLite database.

The runner owns one metadata table, ``nestquest_schema_version``, holding
a single row with the schema version the database file currently
reflects.  Migrations are declared as an ordered list: entry ``n``
upgrades version ``n-1`` to version ``n``.  Applying a migration means
running its DDL inside one transaction and stamping the new version in
that same transaction, so a database never persists a half-applied
migration: any failure rolls the statements and the version stamp back
together, leaving the file at its prior version.

Version 0 means "the file exists but carries no NestQuest schema yet"
— a fresh file, or a file this integration has never written.  Starting
the runner against version 0 applies migration 1, which applies the
full v1 DDL from :mod:`.schema` and stamps version 1.

Each migration's statements and its version stamp run inside ONE
transaction, and the stamp is written as DELETE + INSERT rather than
UPDATE because a version-0 database has no version row to update yet.
An UPDATE form would silently match zero rows there and leave the
database migrated but unstamped — reporting version 0 forever, and
re-applying migration 1 on every startup.  The DELETE+INSERT shape is
also what makes the stamp a replace, so the row never duplicates.

Idempotence across restarts: a database already at the latest version
has no pending migrations, so the runner opens a read-only check, finds
nothing to do, and leaves the file byte-untouched (no write transaction
is opened, so no WAL churn).

Migration list policy: entries are append-only.  Once shipped, a
migration's SQL must never be edited — an old database applying it for
the first time and a fresh database would then diverge.  Fix-forward
with a new migration instead.  The version stamp lives in the same
SQLite file as the data it describes, so restoring a backup restores
its matching schema version with it.

Corrupt or missing files are not this module's concern: startup
handling of those cases is task d5bca74b, which decides whether to
open fresh or raise ConfigEntryNotReady.  This runner assumes it is
handed an open, working connection.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from .db import NestQuestDatabase
from .schema import SCHEMA_V1_STATEMENTS

LOGGER = logging.getLogger(__name__)

#: Metadata table holding the applied schema version.  Prefixed with the
#: integration domain so a config directory shared with other tools can
#: never collide with a foreign ``schema_version`` table.
VERSION_TABLE = "nestquest_schema_version"

#: DDL for the version metadata table.  The singleton-row invariant is
#: enforced by the schema itself: ``id`` is fixed at 1 by CHECK, keyed
#: PRIMARY KEY, so the table can never hold a second row, and the
#: stamp write is an UPDATE (no DELETE+INSERT needed).  ``version`` is
#: a positive integer: version 0 means "no row" and is never stored,
#: so a negative or zero stored value is corruption, not a state the
#: runner can act on.
VERSION_TABLE_DDL = f"""
    CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
        id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
        version INTEGER NOT NULL CHECK (version >= 1)
    )
"""

#: One-based index into :data:`MIGRATIONS`: entry ``n`` upgrades
#: version ``n-1`` to version ``n``.
MIGRATION_1_V1_DDL: list[str] = list(SCHEMA_V1_STATEMENTS)

#: The ordered migration list.  Append-only: never edit an applied
#: entry, add the next one instead.
MIGRATIONS: Sequence[Sequence[str]] = [
    MIGRATION_1_V1_DDL,
]


async def _create_version_table(database: NestQuestDatabase) -> None:
    """Create the version metadata table if it does not exist.

    The table is created before any version check: it is the runner's
    own bookkeeping, and creating it is idempotent.  The DDL enforces
    the singleton-row invariant (``id`` fixed at 1) and a positive
    integer version at the database level.
    """
    await database.execute(VERSION_TABLE_DDL)


async def read_schema_version(database: NestQuestDatabase) -> int:
    """Return the schema version recorded in the database.

    Returns 0 when the version table or its row is missing — the
    "fresh file" case.  A stored version higher than the runner knows
    is surfaced as-is; the caller decides how to treat a future version.

    Reading is deliberately passive: a missing table raises, it is not
    swallowed into 0, because :func:`apply_migrations` always creates
    the table before reading and a direct reader hitting "no such
    table" is a caller bug worth surfacing, not a fresh file.
    """
    row = await database.fetch_one(
        f"SELECT version FROM {VERSION_TABLE} LIMIT 1"
    )
    if row is None:
        return 0
    version = row[0]
    if not isinstance(version, int) or isinstance(version, bool):
        raise RuntimeError(
            f"Schema version metadata is not an integer: {version!r}"
        )
    if version < 1:
        raise RuntimeError(
            f"Schema version metadata is invalid (must be >= 1): {version!r}"
        )
    return version


async def apply_migrations(
    database: NestQuestDatabase,
    migrations: Sequence[Sequence[str]] = MIGRATIONS,
) -> int:
    """Bring the database schema up to the latest version.

    Reads the current version, applies every pending migration in order
    — each inside one transaction that also stamps the new version —
    and returns the resulting version.  Applying zero pending
    migrations (database already current) is a no-op that logs at debug
    level and opens no write transaction.

    Raises whatever the failing migration raised, with the database
    rolled back to its prior version and prior rows untouched.
    """
    await _create_version_table(database)
    current = await read_schema_version(database)
    latest = len(migrations)

    if current > latest:
        raise RuntimeError(
            f"Database schema version {current} is newer than this "
            f"integration understands (latest known: {latest}); "
            "downgrades are not supported"
        )

    if current == latest:
        LOGGER.debug(
            "NestQuest schema already at version %d; no migrations to apply",
            current,
        )
        return current

    for target in range(current + 1, latest + 1):
        statements = migrations[target - 1]
        async with database.transaction():
            for sql in statements:
                await database.execute(sql)
            # UPDATE keyed on the singleton row (id = 1): a fresh file
            # has no row yet, but migration 1 is the only migration a
            # version-0 database can run, so the row is seeded by the
            # same statement batch when needed.  UPDATE alone would
            # silently match zero rows there, so seed-if-absent first.
            await database.execute(
                f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, ?) "
                "ON CONFLICT (id) DO UPDATE SET version = excluded.version",
                (target,),
            )
        LOGGER.info(
            "NestQuest schema migrated to version %d (%d statement%s)",
            target,
            len(statements),
            "s" if len(statements) != 1 else "",
        )

    return latest