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
names before anything else assumes the new model.  Migration 3 brings
pre-D-008 databases to the multi-assignee model: it creates
``quest_definition_assignees`` and, when ``quest_definitions`` still
carries a single ``child_id`` column, rebuilds the table without it,
copying each definition's assignee across.  Each callable migration
runs inside its own transaction together with its version stamp, so a
crash mid-step rolls the statements and the stamp back together.

Migration entries are either an ordered sequence of SQL statements or
an async callable taking ``(database, target_version)``.  Callables
exist for steps whose SQL depends on the database's current state (a
legacy rename only fires when a legacy table is present; a rebuild only
when the old column shape is present) and own their transaction so they
can bracket it with connection pragmas the runner's uniform transaction
cannot express.

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
from .schema import (
    QUEST_DEFINITIONS_TABLE_SQL,
    SCHEMA_V1_STATEMENTS,
    SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL,
    SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL,
)

LOGGER = logging.getLogger(__name__)

#: One migration entry: either an ordered sequence of SQL statements or
#: an async callable taking ``(database, target_version)`` that manages
#: its own transaction and stamps via :func:`stamp_schema_version`.
MigrationStep = Union[
    Sequence[str],
    Callable[[NestQuestDatabase, int], Awaitable[None]],
]

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

#: The assignees table DDL, shared with migration 1 via the schema
#: module so a rebuilt and a freshly created table cannot drift.
_ASSIGNEES_TABLE_DDL: str = SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL[0]

#: Legacy (pre-D-007) table name -> current table name.  Order matters:
#: the parent table renames first so the child's foreign key reference
#: is rewritten while its parent's new name is already in place.
LEGACY_TASK_TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("task_definitions", "quest_definitions"),
    ("task_instances", "quest_instances"),
)


async def stamp_schema_version(
    database: NestQuestDatabase, version: int
) -> None:
    """Write the schema version stamp (inside the caller's transaction).

    INSERT keyed on the singleton row (id = 1) with an upsert: a fresh
    file has no row yet, so UPDATE alone would silently match zero rows
    there and leave a migrated-but-unstamped database.
    """
    await database.execute(
        f"INSERT INTO {VERSION_TABLE} (id, version) "
        "VALUES (1, ?) "
        "ON CONFLICT (id) DO UPDATE SET version = excluded.version",
        (version,),
    )


async def _table_has_column(
    database: NestQuestDatabase, table: str, column: str
) -> bool:
    """Return True when ``table`` currently carries ``column``."""
    rows = await database.fetch_all(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in rows)


async def _rename_legacy_task_tables(
    database: NestQuestDatabase, target_version: int
) -> None:
    """Rename any surviving ``task_*`` tables to their ``quest_*`` names.

    Dev-machines-only path (D-007): a database stamped version 1 by the
    pre-rename runner holds ``task_definitions``/``task_instances``.
    Each legacy name still present is renamed; fresh databases find
    nothing and this step is a no-op.  Modern SQLite rewrites foreign
    key clauses in other tables to follow the rename, so the renamed
    schema is indistinguishable from a freshly created one apart from
    internal autoindex names.  Runs in its own transaction together
    with the version stamp, so a crash rolls both back.
    """
    async with database.transaction():
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
                    "Renamed legacy table %s to %s",
                    legacy_name,
                    current_name,
                )
        await stamp_schema_version(database, target_version)


async def _add_definition_assignees(
    database: NestQuestDatabase, target_version: int
) -> None:
    """Bring definitions to the multi-assignee model (D-008).

    Two shapes arrive here:

    - Fresh or renamed databases whose ``quest_definitions`` already
      matches the current canonical DDL (no ``child_id`` column): only
      the assignees table needs creating (``IF NOT EXISTS`` is a no-op
      when migration 1 already made it).
    - Databases stamped at version 2 whose ``quest_definitions`` still
      carries the single ``child_id`` column: the table is rebuilt via
      SQLite's canonical procedure — create the new table, copy rows,
      move each definition's assignee into
      ``quest_definition_assignees``, drop the old table, rename — so
      ``DROP COLUMN``'s foreign-key restriction never applies and no
      definition or instance row is lost.

    The copy runs with ``foreign_keys = OFF`` because dropping the old
    table under enforcement would fire the implicit DELETE and violate
    the ``quest_instances`` foreign key; ``PRAGMA foreign_key_check``
    runs inside the same transaction before the stamp, so a corrupt
    copy aborts the whole migration instead of persisting.  The pragma
    is a connection-level no-op inside a transaction, hence the
    off/transaction/on bracket.
    """
    legacy_child_id = await _table_has_column(
        database, "quest_definitions", "child_id"
    )
    await database.execute("PRAGMA foreign_keys = OFF")
    try:
        async with database.transaction():
            await database.execute(_ASSIGNEES_TABLE_DDL)
            if legacy_child_id:
                await database.execute(
                    "CREATE TABLE quest_definitions_rebuilt "
                    f"{QUEST_DEFINITIONS_TABLE_SQL}"
                )
                await database.execute(
                    "INSERT INTO quest_definitions_rebuilt "
                    "(id, title, description, icon, schedule_rule_id, "
                    "due_time, is_active, created_at) "
                    "SELECT id, title, description, icon, "
                    "schedule_rule_id, due_time, is_active, created_at "
                    "FROM quest_definitions ORDER BY id"
                )
                await database.execute(
                    "INSERT OR IGNORE INTO quest_definition_assignees "
                    "(definition_id, child_id) "
                    "SELECT id, child_id FROM quest_definitions"
                )
                await database.execute("DROP TABLE quest_definitions")
                await database.execute(
                    "ALTER TABLE quest_definitions_rebuilt "
                    "RENAME TO quest_definitions"
                )
                violations = await database.fetch_all(
                    "PRAGMA foreign_key_check"
                )
                if violations:
                    raise RuntimeError(
                        "definition rebuild produced foreign-key "
                        f"violations: {violations!r}"
                    )
            await stamp_schema_version(database, target_version)
    finally:
        await database.execute("PRAGMA foreign_keys = ON")


#: The ordered migration list.  Append-only: never edit an applied
#: entry, add the next one instead.  (Migration 1's content was
#: rewritten pre-release per D-007 — no version 1 database shipped.)
MIGRATIONS: Sequence[MigrationStep] = [
    MIGRATION_1_V1_DDL,
    _rename_legacy_task_tables,
    _add_definition_assignees,
    # Migration 4 (D-008): the windows table is a plain new table — a
    # CREATE IF NOT EXISTS suffices for both fresh databases (which
    # already made it in migration 1) and pre-window databases.
    list(SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL),
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
            step = migrations[target - 1]
            if callable(step):
                # Callable migrations own their transaction: some steps
                # (table rebuilds) must run connection pragmas such as
                # ``foreign_keys = OFF`` BEFORE opening one, which the
                # runner's uniform transaction cannot express, and they
                # stamp inside their own transaction so a failure rolls
                # the statements and the version stamp back together.
                # The version is re-read here under the migration lock:
                # runners on one connection are serialized by it, so
                # the version cannot change between this read and the
                # callable's commit.
                in_tx_version = await read_schema_version(database)
                if in_tx_version > latest:
                    raise RuntimeError(
                        f"Database schema version {in_tx_version} is newer "
                        f"than this integration understands (latest known: "
                        f"{latest}); downgrades are not supported"
                    )
                if in_tx_version < target:
                    await step(database, target)
                    applied = True
            else:
                async with database.transaction():
                    # Re-read the version INSIDE the write transaction:
                    # the outer read was advisory, and the wrapper
                    # serializes individual statements, not the
                    # read-decide-apply decision.  Under the
                    # transaction's lock the version cannot change
                    # between the read and the stamp, and the loser of
                    # an interleaved race (a queued second caller
                    # re-running apply_migrations after the winner
                    # already migrated) re-reads here, sees the
                    # winner's stamp, and skips instead of re-applying
                    # a non-idempotent migration with a stale version.
                    in_tx_version = await read_schema_version(database)
                    if in_tx_version > latest:
                        raise RuntimeError(
                            f"Database schema version {in_tx_version} is "
                            f"newer than this integration understands "
                            f"(latest known: {latest}); downgrades are "
                            f"not supported"
                        )
                    if in_tx_version < target:
                        for sql in step:
                            await database.execute(sql)
                        await stamp_schema_version(database, target)
                        applied = True
                        applied_statements = len(step)
            if applied:
                LOGGER.info(
                    "NestQuest schema migrated to version %d",
                    target,
                )

        return latest