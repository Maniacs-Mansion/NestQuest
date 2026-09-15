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

Migration 1 was rewritten pre-release (D-007): nothing was ever
shipped, so the v1 DDL now creates the ``quest_*`` tables directly
instead of the legacy ``task_*`` spellings, and no compatibility shim
exists.  Dev machines that already hold a version-1 database with
``task_*`` tables are handled by migration 2, which detects the legacy
table names and ``ALTER TABLE ... RENAME TO``s them to their current
names before anything else assumes the new model.  The rename step runs
inside the same transaction as its version stamp, so a crash mid-rename
rolls both back together.

Migration entries are either an ordered sequence of SQL statements or
an async callable taking the open database.  Callables exist for steps
whose SQL depends on the database's current state (the legacy rename
only fires when a legacy table is actually present) and run under the
same per-migration transaction as statement lists.

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

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Union

from .db import NestQuestDatabase
from .schema import SCHEMA_V1_STATEMENTS

LOGGER = logging.getLogger(__name__)

#: One migration entry: either an ordered sequence of SQL statements or
#: an async callable run under the entry's migration transaction.
MigrationStep = Union[Sequence[str], Callable[[NestQuestDatabase], Awaitable[None]]]

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

#: Legacy (pre-D-007) table name -> current table name.  Order matters:
#: the parent table renames first so the child's foreign key reference
#: is rewritten while its parent's new name is already in place.
LEGACY_TASK_TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("task_definitions", "quest_definitions"),
    ("task_instances", "quest_instances"),
)


async def _rename_legacy_task_tables(database: NestQuestDatabase) -> None:
    """Rename any surviving ``task_*`` tables to their ``quest_*`` names.

    Dev-machines-only path (D-007): a database stamped version 1 by the
    pre-rename runner holds ``task_definitions``/``task_instances``.
    Each legacy name still present is renamed; fresh databases find
    nothing and this step is a no-op.  Modern SQLite rewrites foreign
    key clauses in other tables to follow the rename, so the renamed
    schema is indistinguishable from a freshly created one apart from
    internal autoindex names.  Runs inside the migration transaction,
    so the renames and the version stamp commit or roll back together.
    """
    for legacy_name, current_name in LEGACY_TASK_TABLE_RENAMES:
        row = await database.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = ?",
            (legacy_name,),
        )
        if row is not None:
            await database.execute(
                f'ALTER TABLE "{legacy_name}" RENAME TO "{current_name}"'
            )
            LOGGER.info(
                "Renamed legacy table %s to %s", legacy_name, current_name
            )


#: The ordered migration list.  Append-only: never edit an applied
#: entry, add the next one instead.  (Migration 1's content was
#: rewritten pre-release per D-007 — no version 1 database shipped.)
MIGRATIONS: Sequence[MigrationStep] = [
    MIGRATION_1_V1_DDL,
    _rename_legacy_task_tables,
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


#: One asyncio.Lock per connection wrapper, created lazily and bound to
#: the running loop, serializing whole apply_migrations runs so two
#: concurrent callers on one connection queue instead of colliding on
#: the wrapper's single-transaction rule.
_MIGRATION_LOCKS: dict[int, asyncio.Lock] = {}


def _migration_lock(database: NestQuestDatabase) -> asyncio.Lock:
    """Return the migration lock bound to ``database``'s running loop."""
    loop = asyncio.get_running_loop()
    key = (id(database), id(loop))
    lock = _MIGRATION_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _MIGRATION_LOCKS[key] = lock
    return lock


async def apply_migrations(
    database: NestQuestDatabase,
    migrations: Sequence[MigrationStep] = MIGRATIONS,
) -> int:
    """Bring the database schema up to the latest version.

    Reads the current version, applies every pending migration in order
    — each inside one transaction that also stamps the new version —
    and returns the resulting version.  Applying zero pending
    migrations (database already current) is a no-op that logs at debug
    level and opens no write transaction.

    The version is re-read inside each migration transaction before
    deciding to apply it: the outer read is advisory only (loop bounds,
    no-op fast path), and on one shared connection two interleaved
    runners would otherwise both read the same version and both apply
    a non-idempotent migration.  Under the transaction's lock the
    second runner sees the first runner's stamp and skips.

    Runners on one connection are serialized by an asyncio lock held
    for the whole decide-and-apply span: NestQuestDatabase rejects a
    second transaction while one is active (RuntimeError), so
    concurrent callers must queue, and the lock makes that queueing
    explicit.  The loser of the race re-reads the version once it
    acquires the lock, sees the winner's stamp, and applies nothing.

    Raises whatever the failing migration raised, with the database
    rolled back to its prior version and prior rows untouched.
    """
    async with _migration_lock(database):
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
                "NestQuest schema already at version %d; "
                "no migrations to apply",
                current,
            )
            return current

        for target in range(current + 1, latest + 1):
            applied = False
            async with database.transaction():
                # Re-read the version INSIDE the write transaction: the
                # outer read was advisory, and the wrapper serializes
                # individual statements, not the read-decide-apply
                # decision.  Under the transaction's lock the version
                # cannot change between the read and the stamp, and the
                # loser of an interleaved race (a queued second caller
                # re-running apply_migrations after the winner already
                # migrated) re-reads here, sees the winner's stamp, and
                # skips instead of re-applying a non-idempotent
                # migration with a stale version.
                in_tx_version = await read_schema_version(database)
                if in_tx_version > latest:
                    raise RuntimeError(
                        f"Database schema version {in_tx_version} is newer "
                        f"than this integration understands (latest known: "
                        f"{latest}); downgrades are not supported"
                    )
                if in_tx_version < target:
                    step = migrations[target - 1]
                    if callable(step):
                        await step(database)
                        applied_statements = 0
                    else:
                        for sql in step:
                            await database.execute(sql)
                        applied_statements = len(step)
                    # INSERT keyed on the singleton row (id = 1): a
                    # fresh file has no row yet, and migration 1 is the
                    # only migration a version-0 database can run, so
                    # the row is seeded by the same statement batch
                    # when needed.  UPDATE alone would silently match
                    # zero rows there.
                    await database.execute(
                        f"INSERT INTO {VERSION_TABLE} (id, version) "
                        "VALUES (1, ?) "
                        "ON CONFLICT (id) DO UPDATE SET version = "
                        "excluded.version",
                        (target,),
                    )
                    applied = True
            if applied:
                if applied_statements == 0:
                    LOGGER.info(
                        "NestQuest schema migrated to version %d",
                        target,
                    )
                else:
                    LOGGER.info(
                        "NestQuest schema migrated to version %d "
                        "(%d statement%s)",
                        target,
                        applied_statements,
                        "s" if applied_statements != 1 else "",
                    )

        return latest