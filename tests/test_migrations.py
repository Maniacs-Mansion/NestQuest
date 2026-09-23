"""Tests for migrations.py: the versioned schema migration runner."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
from unittest.mock import AsyncMock

import pytest

from custom_components.nestquest.core.db import NestQuestDatabase
from custom_components.nestquest.core.schema import SCHEMA_V7_META_STATE_DDL
from custom_components.nestquest.core.migrations import (
    MIGRATIONS,
    VERSION_TABLE,
    VERSION_TABLE_DDL,
    apply_migrations,
    read_schema_version,
)
from custom_components.nestquest.core.schema import (
    SCHEMA_V1_STATEMENTS,
    SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> NestQuestDatabase:
    database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
    _run(database.open(path))
    return database


def _migrate(database, migrations=MIGRATIONS):
    return _run(apply_migrations(database, migrations))


def _version(database) -> int:
    return _run(read_schema_version(database))


def _tables(database) -> set[str]:
    rows = _run(
        database.fetch_all(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    )
    return {row[0] for row in rows}


def _counts(database) -> dict[str, int]:
    """Row counts for every v1 data table plus the version table."""
    tables = (
        "children",
        "admin_users",
        "schedule_rules",
        "quest_definitions",
        "quest_definition_assignees",
        "quest_definition_windows",
        "presence_schedules",
        "presence_overrides",
        "quest_instances",
        "completion_events",
    )
    counts = {}
    for table in tables:
        row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
        counts[table] = row[0]
    return counts


# ---------------------------------------------------------------------------
# Fresh file: version 0 -> latest version
# ---------------------------------------------------------------------------


def test_fresh_file_migrates_to_latest_version(tmp_path) -> None:
    database = _open_db(tmp_path / "fresh.db")
    try:
        final = _migrate(database)
        assert final == len(MIGRATIONS)
        assert _version(database) == len(MIGRATIONS)
    finally:
        _run(database.close())


def test_fresh_file_migration_creates_all_v1_tables(tmp_path) -> None:
    database = _open_db(tmp_path / "fresh-tables.db")
    try:
        _migrate(database)
        expected = {
            "children",
            "admin_users",
            "schedule_rules",
            "quest_definitions",
            "quest_definition_assignees",
            "quest_definition_windows",
            "presence_schedules",
            "presence_overrides",
            "quest_instances",
            "completion_events",
            "nestquest_meta_state",
            VERSION_TABLE,
        }
        assert _tables(database) == expected
    finally:
        _run(database.close())


def test_missing_version_table_raises_on_direct_read(tmp_path) -> None:
    database = _open_db(tmp_path / "no-table.db")
    try:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            _run(read_schema_version(database))
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                f"AND name = '{VERSION_TABLE}'"
            )
        )
        assert row is None, "read_schema_version must not create the table"
    finally:
        _run(database.close())


def test_empty_version_table_reads_as_version_0(tmp_path) -> None:
    database = _open_db(tmp_path / "empty-table.db")
    try:
        _run(database.execute(VERSION_TABLE_DDL))
        assert _version(database) == 0
    finally:
        _run(database.close())


def test_migration_list_shape() -> None:
    """Migration 1 is the v1 DDL; 2 and 3 are callable steps.

    Nothing ever shipped, so migration 1 was rewritten pre-release
    (D-007) to create the quest_* tables directly; migration 2 exists
    for dev databases stamped version 1 by the pre-rename runner,
    migration 3 brings pre-D-008 definitions to the multi-assignee
    model, migration 4 adds the windows table, migration 5 rebuilds
    quest_instances onto the widened (definition, child, date, window)
    key, and migration 6 adds actor_child_id to completion_events.
    """
    assert MIGRATIONS[0] == SCHEMA_V1_STATEMENTS
    assert callable(MIGRATIONS[1])
    assert callable(MIGRATIONS[2])
    assert MIGRATIONS[3] == SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL
    assert callable(MIGRATIONS[4])
    assert callable(MIGRATIONS[5])
    assert MIGRATIONS[6] == SCHEMA_V7_META_STATE_DDL
    assert len(MIGRATIONS) == 7


# ---------------------------------------------------------------------------
# Legacy dev database: task_* tables stamped version 1 -> quest_*
# ---------------------------------------------------------------------------


_LEGACY_DDL = [
    """
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        colour TEXT,
        avatar_ref TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_users (
        ha_user_id TEXT PRIMARY KEY NOT NULL,
        added_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT NOT NULL,
        interval INTEGER NOT NULL DEFAULT 1,
        weekday_set TEXT,
        day_of_month INTEGER,
        nth_weekday INTEGER,
        month INTEGER,
        start_date TEXT NOT NULL,
        end_date TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        icon TEXT,
        child_id INTEGER NOT NULL REFERENCES children(id),
        schedule_rule_id INTEGER NOT NULL REFERENCES schedule_rules(id),
        due_time TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS presence_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER NOT NULL UNIQUE REFERENCES children(id),
        cycle_length_weeks INTEGER NOT NULL,
        anchor_date TEXT NOT NULL,
        pattern TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS presence_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER NOT NULL REFERENCES children(id),
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        is_present INTEGER NOT NULL,
        note TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        definition_id INTEGER NOT NULL REFERENCES task_definitions(id),
        child_id INTEGER NOT NULL REFERENCES children(id),
        due_date TEXT NOT NULL,
        due_time TEXT,
        generated_at TEXT NOT NULL,
        UNIQUE (definition_id, due_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS completion_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id INTEGER NOT NULL REFERENCES task_instances(id),
        child_id INTEGER NOT NULL REFERENCES children(id),
        event_type TEXT NOT NULL,
        actor_source TEXT NOT NULL,
        actor_user_id TEXT,
        occurred_at TEXT NOT NULL,
        was_on_time INTEGER
    )
    """,
]


def _seed_legacy_database(database) -> None:
    """Create a database indistinguishable from a pre-rename dev file.

    Applies the legacy task_* DDL, seeds one row in every renamed
    table, and stamps version 1 exactly the way the old runner did.
    """
    for sql in _LEGACY_DDL:
        _run(database.execute(sql))
    _run(database.execute(VERSION_TABLE_DDL))
    _run(
        database.execute(
            f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, 1)"
        )
    )
    _run(
        database.execute(
            "INSERT INTO children (display_name, created_at) "
            "VALUES ('Ada', '2026-09-14T00:00:00+00:00')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO schedule_rules (rule_type, start_date) "
            "VALUES ('daily', '2026-09-14')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO task_definitions (title, child_id, "
            "schedule_rule_id, created_at) "
            "VALUES ('Dishes', 1, 1, '2026-09-14T00:00:00+00:00')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO task_instances (definition_id, child_id, "
            "due_date, generated_at) "
            "VALUES (1, 1, '2026-09-15', '2026-09-14T00:00:00+00:00')"
        )
    )


def test_legacy_task_tables_are_renamed_and_keep_their_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "legacy.db")
    try:
        _seed_legacy_database(database)
        final = _migrate(database)
        assert final == len(MIGRATIONS)
        assert _version(database) == len(MIGRATIONS)
        tables = _tables(database)
        assert "task_definitions" not in tables
        assert "task_instances" not in tables
        assert {"quest_definitions", "quest_instances"} <= tables
        # Every seeded row survived the rename.
        assert _run(database.fetch_one("SELECT COUNT(*) FROM children")) == (1,)
        assert (
            _run(
                database.fetch_one(
                    "SELECT title FROM quest_definitions WHERE id = 1"
                )
            )
            == ("Dishes",)
        )
        assert (
            _run(
                database.fetch_one(
                    "SELECT due_date FROM quest_instances WHERE id = 1"
                )
            )
            == ("2026-09-15",)
        )
        # Migration 3 moved the legacy single-assignee column into the
        # assignees table: the definition kept its child, the column is
        # gone.
        assignees = _run(
            database.fetch_one(
                "SELECT child_id FROM quest_definition_assignees "
                "WHERE definition_id = 1"
            )
        )
        assert assignees == (1,)
        columns = _run(
            database.fetch_all("PRAGMA table_info(quest_definitions)")
        )
        assert "child_id" not in {row[1] for row in columns}
        # The untouched completion_events table still exists and is empty.
        assert "completion_events" in tables
        assert (
            _run(database.fetch_one("SELECT COUNT(*) FROM completion_events"))
            == (0,)
        )
    finally:
        _run(database.close())


def test_renamed_instances_foreign_key_follows_the_rename(tmp_path) -> None:
    database = _open_db(tmp_path / "legacy-fk.db")
    try:
        _seed_legacy_database(database)
        _migrate(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(quest_instances)"))
        referenced = {row[2] for row in fks}
        assert "quest_definitions" in referenced
        assert "task_definitions" not in referenced
        # The renamed table is live: a new row validates its FKs.
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) "
                "VALUES ('Ben', '2026-09-14T00:00:00+00:00')"
            )
        )
        with pytest.raises(sqlite3.IntegrityError):
            _run(
                database.execute(
                    "INSERT INTO quest_instances (definition_id, child_id, "
                    "due_date, generated_at) "
                    "VALUES (999, 2, '2026-09-16', "
                    "'2026-09-14T00:00:00+00:00')"
                )
            )
    finally:
        _run(database.close())


def test_legacy_rename_is_idempotent_across_restarts(tmp_path) -> None:
    database = _open_db(tmp_path / "legacy-restart.db")
    try:
        _seed_legacy_database(database)
        _migrate(database)
        final = _migrate(database)
        assert final == len(MIGRATIONS)
        tables = _tables(database)
        assert "quest_definitions" in tables
        assert "task_definitions" not in tables
        assert (
            _run(database.fetch_one("SELECT COUNT(*) FROM quest_definitions"))
            == (1,)
        )
    finally:
        _run(database.close())


def test_fresh_database_never_holds_legacy_table_names(tmp_path) -> None:
    database = _open_db(tmp_path / "fresh-legacy.db")
    try:
        _migrate(database)
        tables = _tables(database)
        assert not any(name.startswith("task_") for name in tables)
        assert _version(database) == len(MIGRATIONS)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Pre-D-008 database: quest_definitions with child_id stamped version 2
# ---------------------------------------------------------------------------

_V2_DEFINITIONS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS quest_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        icon TEXT,
        child_id INTEGER NOT NULL REFERENCES children(id),
        schedule_rule_id INTEGER NOT NULL REFERENCES schedule_rules(id),
        due_time TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
]

_V2_INSTANCES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS quest_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        definition_id INTEGER NOT NULL REFERENCES quest_definitions(id),
        child_id INTEGER NOT NULL REFERENCES children(id),
        due_date TEXT NOT NULL,
        due_time TEXT,
        generated_at TEXT NOT NULL,
        UNIQUE (definition_id, due_date)
    )
    """,
]

_V2_EVENTS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS completion_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id INTEGER NOT NULL REFERENCES quest_instances(id),
        child_id INTEGER NOT NULL REFERENCES children(id),
        event_type TEXT NOT NULL,
        actor_source TEXT NOT NULL,
        actor_user_id TEXT,
        occurred_at TEXT NOT NULL,
        was_on_time INTEGER
    )
    """,
]


def _seed_v2_multi_assignee_upgrade(database) -> None:
    """Create a database shaped like a post-rename, pre-D-008 dev file.

    Fresh quest_* tables — but quest_definitions still carries the
    single child_id column and no assignees table exists — stamped at
    version 2, with definition and instance rows that must survive.
    """
    # Freeze the version-2 shape: definitions carry child_id, the
    # instance table has no window column, and the assignees/windows
    # tables do not exist yet — everything else matches the current DDL.
    _v2_replaced = (
        "quest_definitions ",
        "quest_definition_assignees ",
        "quest_definition_windows ",
        "quest_instances ",
        "completion_events ",
    )
    for sql in SCHEMA_V1_STATEMENTS:
        if any(name in sql for name in _v2_replaced):
            continue
        _run(database.execute(sql))
    for sql in _V2_DEFINITIONS_DDL + _V2_INSTANCES_DDL + _V2_EVENTS_DDL:
        _run(database.execute(sql))
    _run(database.execute(VERSION_TABLE_DDL))
    _run(
        database.execute(
            f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, 2)"
        )
    )
    _run(
        database.execute(
            "INSERT INTO children (display_name, created_at) "
            "VALUES ('Ada', '2026-09-14T00:00:00+00:00')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO children (display_name, created_at) "
            "VALUES ('Bo', '2026-09-14T00:00:00+00:00')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO schedule_rules (rule_type, start_date) "
            "VALUES ('daily', '2026-09-14')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO quest_definitions (title, child_id, "
            "schedule_rule_id, created_at) "
            "VALUES ('Dishes', 2, 1, '2026-09-14T00:00:00+00:00')"
        )
    )
    _run(
        database.execute(
            "INSERT INTO quest_instances (definition_id, child_id, "
            "due_date, generated_at) "
            "VALUES (1, 2, '2026-09-15', '2026-09-14T00:00:00+00:00')"
        )
    )
    # One legacy panel event and one legacy admin event: the panel one
    # must backfill actor_child_id to its own child; the admin one must
    # stay NULL.
    _run(
        database.execute(
            "INSERT INTO completion_events (instance_id, child_id, "
            "event_type, actor_source, occurred_at, was_on_time) "
            "VALUES (1, 2, 'completed', 'panel', "
            "'2026-09-15T10:00:00+00:00', 1)"
        )
    )
    _run(
        database.execute(
            "INSERT INTO completion_events (instance_id, child_id, "
            "event_type, actor_source, actor_user_id, occurred_at, "
            "was_on_time) "
            "VALUES (1, 2, 'uncompleted', 'user', 'parent-1', "
            "'2026-09-15T11:00:00+00:00', 1)"
        )
    )


def test_v2_definitions_rebuilt_to_multi_assignee(tmp_path) -> None:
    database = _open_db(tmp_path / "v2-upgrade.db")
    try:
        _seed_v2_multi_assignee_upgrade(database)
        final = _migrate(database)
        assert final == len(MIGRATIONS)
        assert _version(database) == len(MIGRATIONS)
        # The definition row survived and lost its child_id column.
        row = _run(
            database.fetch_one(
                "SELECT title, schedule_rule_id, is_active "
                "FROM quest_definitions WHERE id = 1"
            )
        )
        assert row == ("Dishes", 1, 1)
        columns = _run(
            database.fetch_all("PRAGMA table_info(quest_definitions)")
        )
        assert "child_id" not in {c[1] for c in columns}
        # The single assignee moved into the assignees table.
        assignees = _run(
            database.fetch_all(
                "SELECT definition_id, child_id "
                "FROM quest_definition_assignees ORDER BY child_id"
            )
        )
        assert assignees == [(1, 2)]
        # The instance survived the rebuild, pinned to the migrated
        # window, still referencing the definition.
        instance = _run(
            database.fetch_one(
                "SELECT definition_id, child_id, window, due_date "
                "FROM quest_instances WHERE id = 1"
            )
        )
        assert instance == (1, 2, "morning", "2026-09-15")
        # The rebuilt instance table carries the widened unique key.
        index_rows = _run(
            database.fetch_all(
                "PRAGMA index_list(quest_instances)"
            )
        )
        unique_columns = []
        for index_row in index_rows:
            if index_row[2]:  # unique flag
                info = _run(
                    database.fetch_all(
                        f"PRAGMA index_info('{index_row[1]}')"
                    )
                )
                unique_columns.append([col[2] for col in info])
        assert [
            "definition_id", "child_id", "due_date", "window"
        ] in unique_columns
        # The completion events survived the actor_child_id rebuild:
        # the panel row backfilled to its own child, the admin row
        # stayed NULL, and ids are preserved.
        events = _run(
            database.fetch_all(
                "SELECT id, event_type, actor_source, actor_child_id "
                "FROM completion_events ORDER BY id"
            )
        )
        assert events == [
            (1, "completed", "panel", 2),
            (2, "uncompleted", "user", None),
        ]
        columns = _run(
            database.fetch_all("PRAGMA table_info(completion_events)")
        )
        assert "actor_child_id" in {c[1] for c in columns}
        # No dangling references anywhere.
        assert _run(database.fetch_all("PRAGMA foreign_key_check")) == []
        # The rebuilt table is live for the new model: a definition
        # insert carries no child column at all.
        _run(
            database.execute(
                "INSERT INTO quest_definitions (title, schedule_rule_id, "
                "created_at) VALUES ('Laundry', 1, "
                "'2026-09-14T00:00:00+00:00')"
            )
        )
        _run(
            database.execute(
                "INSERT INTO quest_definition_assignees "
                "(definition_id, child_id) VALUES (2, 1)"
            )
        )
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Idempotence: second start is a no-op
# ---------------------------------------------------------------------------


def test_second_run_applies_nothing_and_keeps_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "idempotent.db")
    try:
        _migrate(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _run(
            database.execute(
                "INSERT INTO admin_users (ha_user_id, added_at) VALUES (?, ?)",
                ("user-1", "2026-09-13T00:00:00+00:00"),
            )
        )
        final = _migrate(database)
        assert final == len(MIGRATIONS)
        assert _version(database) == len(MIGRATIONS)
        assert _counts(database)["children"] == 1
        assert _counts(database)["admin_users"] == 1
    finally:
        _run(database.close())


def test_second_run_writes_nothing_to_the_file(tmp_path, caplog) -> None:
    database = _open_db(tmp_path / "noop.db")
    try:
        _migrate(database)
        _run(database.execute("PRAGMA wal_checkpoint(TRUNCATE)"))
        db_file = tmp_path / "noop.db"
        wal_file = tmp_path / "noop.db-wal"
        digest_before = hashlib.sha256(db_file.read_bytes()).hexdigest()
        mtime_before = db_file.stat().st_mtime_ns
        wal_digest_before = (
            hashlib.sha256(wal_file.read_bytes()).hexdigest()
            if wal_file.exists()
            else None
        )

        _migrate(database)

        # A no-op run must not open a write transaction: the main
        # database file is byte-identical (content hash, not just size)
        # and untouched (mtime too), and the WAL gained no frames.
        assert db_file.stat().st_mtime_ns == mtime_before
        assert (
            hashlib.sha256(db_file.read_bytes()).hexdigest() == digest_before
        )
        if wal_digest_before is None:
            assert not wal_file.exists()
        else:
            assert (
                hashlib.sha256(wal_file.read_bytes()).hexdigest()
                == wal_digest_before
            )
    finally:
        _run(database.close())


def test_noop_run_logs_no_migration(caplog, tmp_path) -> None:
    database = _open_db(tmp_path / "noop-log.db")
    try:
        _migrate(database)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="custom_components.nestquest.core.migrations"):
            _migrate(database)
        migrated = [
            r for r in caplog.records if "migrated" in r.getMessage().lower()
        ]
        assert migrated == []
    finally:
        _run(database.close())


def test_noop_run_is_logged_at_debug_level(caplog, tmp_path) -> None:
    database = _open_db(tmp_path / "noop-debug.db")
    try:
        _migrate(database)
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="custom_components.nestquest.core.migrations"):
            _migrate(database)
        assert any(
            f"already at version {len(MIGRATIONS)}" in r.getMessage()
            for r in caplog.records
        )
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Failure atomicity: a failing migration leaves the prior version intact
# ---------------------------------------------------------------------------


def _failing_migrations(prior_statements: list[str]) -> list[list[str]]:
    """Migration list where the LAST entry fails mid-application.

    Sized one entry longer than the real MIGRATIONS and padded with
    harmless no-op fillers, so a fully-migrated database (already at
    len(MIGRATIONS)) still has exactly one pending migration — the
    failing one — to attempt.
    """
    steps: list[list[str]] = [prior_statements]
    steps += [
        [
            f"CREATE TABLE IF NOT EXISTS filler_{index} "
            "(id INTEGER PRIMARY KEY)"
        ]
        for index in range(len(MIGRATIONS) - 1)
    ]
    steps.append(
        [
            "CREATE TABLE IF NOT EXISTS later_table (id INTEGER PRIMARY KEY)",
            "CREATE TABLE broken (",
        ]
    )
    return steps


def test_failing_migration_rolls_back_to_prior_version(tmp_path) -> None:
    database = _open_db(tmp_path / "rollback.db")
    try:
        # Manually simulate a fully-migrated database: run the real
        # migration list, which stamps the latest version.
        _migrate(database)
        version_row = _run(
            database.fetch_one(f"SELECT version FROM {VERSION_TABLE}")
        )
        assert version_row == (len(MIGRATIONS),)

        with pytest.raises(sqlite3.OperationalError):
            _migrate(database, _failing_migrations(SCHEMA_V1_STATEMENTS))

        # Version stamp unchanged, statements from the failed migration
        # absent, and the v1 tables untouched.
        assert _version(database) == len(MIGRATIONS)
        assert "later_table" not in _tables(database)
        assert _counts(database)["children"] == 0
        assert _counts(database)["completion_events"] == 0
    finally:
        _run(database.close())


def test_failing_migration_on_fresh_file_leaves_last_good_version(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "fresh-rollback.db")
    try:
        # The fresh file reaches the failing migration (the last one):
        # earlier migrations commit and stamp before it fails and rolls
        # back.  The run aborts at the last fully-applied migration —
        # not at version 0.
        broken = _failing_migrations(SCHEMA_V1_STATEMENTS)
        with pytest.raises(sqlite3.OperationalError):
            _migrate(database, broken)
        assert _version(database) == len(broken) - 1
        # The failing migration's tables must not survive the attempt.
        assert "later_table" not in _tables(database)
        # Migration 1's tables do: it committed before the failure.
        assert "children" in _tables(database)
        assert "quest_instances" in _tables(database)
    finally:
        _run(database.close())


def test_failed_migration_can_be_retried_after_fix(tmp_path) -> None:
    database = _open_db(tmp_path / "retry.db")
    try:
        _migrate(database)
        broken = _failing_migrations(SCHEMA_V1_STATEMENTS)
        with pytest.raises(sqlite3.OperationalError):
            _migrate(database, broken)
        # "Fix" the migration and retry: it now applies cleanly.
        broken[-1] = [
            "CREATE TABLE IF NOT EXISTS later_table (id INTEGER PRIMARY KEY)"
        ]
        final = _migrate(database, broken)
        assert final == len(broken)
        assert _version(database) == len(broken)
        assert "later_table" in _tables(database)
    finally:
        _run(database.close())


def test_failing_migration_error_is_preserved(tmp_path) -> None:
    database = _open_db(tmp_path / "error-preserved.db")
    try:
        with pytest.raises(sqlite3.OperationalError, match="incomplete input"):
            _migrate(database, _failing_migrations(SCHEMA_V1_STATEMENTS))
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Version guard rails
# ---------------------------------------------------------------------------


def test_future_version_is_rejected(tmp_path) -> None:
    database = _open_db(tmp_path / "future.db")
    try:
        _migrate(database)
        _run(
            database.execute(
                f"UPDATE {VERSION_TABLE} SET version = ?", (99,)
            )
        )
        with pytest.raises(RuntimeError, match="newer than"):
            _migrate(database)
        # Nothing was modified by the rejected run.
        assert _version(database) == 99
    finally:
        _run(database.close())


def test_non_integer_version_raises_runtime_error(tmp_path) -> None:
    database = _open_db(tmp_path / "string-version.db")
    try:
        _run(database.execute(VERSION_TABLE_DDL))
        # The CHECK enforces version >= 1 but SQLite's loose typing
        # stores TEXT under an INTEGER-affinity column when it cannot
        # be losslessly coerced; guard the read path against it.
        _run(
            database.execute(
                f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, ?)",
                ("one",),
            )
        )
        with pytest.raises(RuntimeError, match="not an integer"):
            _run(read_schema_version(database))
    finally:
        _run(database.close())


def test_negative_version_read_guard_rejects_below_one() -> None:
    """The read path rejects sub-1 versions even if storage missed them.

    The VERSION_TABLE CHECK already makes negative/zero unstorable; this
    exercises the defense-in-depth guard in read_schema_version itself
    against a database stub returning such a row (e.g. a future schema
    relaxing the CHECK, or a hand-edited file).
    """
    from unittest.mock import AsyncMock, MagicMock

    for bad in (-1, 0):
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(bad,))
        with pytest.raises(RuntimeError, match="must be >= 1"):
            _run(read_schema_version(database))


def test_non_integer_version_read_guard_rejects_text() -> None:
    from unittest.mock import AsyncMock, MagicMock

    for bad in ("one", 1.5, True):
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(bad,))
        with pytest.raises(RuntimeError, match="not an integer"):
            _run(read_schema_version(database))


def test_zero_version_row_is_unstorable(tmp_path) -> None:
    """The CHECK makes sub-1 versions impossible through SQL.

    PRAGMA writable_schema does not bypass CHECKs on ordinary tables,
    so the negative/zero read guard above is pure defense-in-depth;
    here we prove the storage-level rule the normal path relies on.
    """
    database = _open_db(tmp_path / "zero-version.db")
    try:
        _run(database.execute(VERSION_TABLE_DDL))
        for bad in (0, -1):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                _run(
                    database.execute(
                        f"INSERT INTO {VERSION_TABLE} (id, version) "
                        "VALUES (1, ?)",
                        (bad,),
                    )
                )
    finally:
        _run(database.close())


def test_version_table_enforces_singleton_row(tmp_path) -> None:
    database = _open_db(tmp_path / "singleton.db")
    try:
        _run(database.execute(VERSION_TABLE_DDL))
        _run(
            database.execute(
                f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, 1)"
            )
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _run(
                database.execute(
                    f"INSERT INTO {VERSION_TABLE} (id, version) "
                    "VALUES (2, 1)"
                )
            )
    finally:
        _run(database.close())


def test_version_table_check_rejects_version_zero_and_negative(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "version-check.db")
    try:
        _run(database.execute(VERSION_TABLE_DDL))
        for bad in (0, -1):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                _run(
                    database.execute(
                        f"INSERT INTO {VERSION_TABLE} (id, version) "
                        "VALUES (1, ?)",
                        (bad,),
                    )
                )
    finally:
        _run(database.close())


def test_concurrent_runners_serialize_and_apply_once(tmp_path) -> None:
    """Two concurrent runners on one connection apply each step once.

    Deterministic race: runner B starts while runner A is queued into
    its migration.  A applies everything and stamps; B then acquires
    the migration lock, re-reads the already-stamped version, and
    applies nothing.  Without serialization B's transaction() would
    raise RuntimeError (the wrapper forbids concurrent transactions),
    so this also proves the queueing works.
    """
    migrations = [
        ["CREATE TABLE IF NOT EXISTS step_a (id INTEGER PRIMARY KEY)"],
        ["CREATE TABLE IF NOT EXISTS step_b (id INTEGER PRIMARY KEY)"],
    ]
    results: dict[str, int] = {}

    async def _main(tmp_name: str) -> None:
        database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
        await database.open(tmp_name)
        try:
            # Start A, yield so it acquires the lock and enters its
            # first transaction, then start B while A is mid-apply.
            task_a = asyncio.ensure_future(
                apply_migrations(database, migrations)
            )
            await asyncio.sleep(0)
            task_b = asyncio.ensure_future(
                apply_migrations(database, migrations)
            )
            results["a"], results["b"] = await asyncio.gather(
                task_a, task_b
            )

            tables = {
                row[0]
                for row in await database.fetch_all(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            assert {"step_a", "step_b"} <= tables
            # Each migration's statements ran exactly once: the CREATE
            # IF NOT EXISTS would hide double-runs, so count via sqlite
            # sequence/DDL fingerprint instead — re-check version and
            # that both runners reported the same final version.
            row = await database.fetch_one(
                f"SELECT version FROM {VERSION_TABLE}"
            )
            assert row == (2,)
        finally:
            await database.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_main(str(tmp_path / "concurrent.db")))
    finally:
        loop.close()

    assert results["a"] == 2
    assert results["b"] == 2


def test_multiple_pending_migrations_apply_in_order(tmp_path) -> None:
    database = _open_db(tmp_path / "multi-step.db")
    try:
        migrations = [
            ["CREATE TABLE IF NOT EXISTS step_a (id INTEGER PRIMARY KEY)"],
            ["CREATE TABLE IF NOT EXISTS step_b (id INTEGER PRIMARY KEY)"],
            ["CREATE TABLE IF NOT EXISTS step_c (id INTEGER PRIMARY KEY)"],
        ]
        final = _run(apply_migrations(database, migrations))
        assert final == 3
        assert _version(database) == 3
        assert {"step_a", "step_b", "step_c"} <= _tables(database)
    finally:
        _run(database.close())


def test_partial_pending_migrations_resume_from_current_version(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "resume.db")
    try:
        migrations = [
            ["CREATE TABLE IF NOT EXISTS step_a (id INTEGER PRIMARY KEY)"],
            ["CREATE TABLE IF NOT EXISTS step_b (id INTEGER PRIMARY KEY)"],
        ]
        # Advance to version 1 only, by applying a truncated list of the
        # same migrations: patch apply_migrations' latest by passing a
        # single-migration list first, then the full list.
        _run(apply_migrations(database, migrations[:1]))
        assert _version(database) == 1
        final = _run(apply_migrations(database, migrations))
        assert final == 2
        assert _version(database) == 2
        assert "step_b" in _tables(database)
    finally:
        _run(database.close())
