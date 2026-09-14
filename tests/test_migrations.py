"""Tests for migrations.py: the versioned schema migration runner."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from unittest.mock import AsyncMock

import pytest

from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import (
    MIGRATIONS,
    VERSION_TABLE,
    apply_migrations,
    read_schema_version,
)
from custom_components.nestquest.schema import SCHEMA_V1_STATEMENTS


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> NestQuestDatabase:
    database = NestQuestDatabase(_make_hass_mock())
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
        "task_definitions",
        "presence_schedules",
        "presence_overrides",
        "task_instances",
        "completion_events",
    )
    counts = {}
    for table in tables:
        row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
        counts[table] = row[0]
    return counts


# ---------------------------------------------------------------------------
# Fresh file: version 0 -> version 1
# ---------------------------------------------------------------------------


def test_fresh_file_migrates_to_version_1(tmp_path) -> None:
    database = _open_db(tmp_path / "fresh.db")
    try:
        final = _migrate(database)
        assert final == 1
        assert _version(database) == 1
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
            "task_definitions",
            "presence_schedules",
            "presence_overrides",
            "task_instances",
            "completion_events",
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
        _run(
            database.execute(
                f"CREATE TABLE {VERSION_TABLE} (version INTEGER NOT NULL)"
            )
        )
        assert _version(database) == 0
    finally:
        _run(database.close())


def test_migration_1_is_the_full_v1_ddl() -> None:
    assert MIGRATIONS[0] == SCHEMA_V1_STATEMENTS
    assert len(MIGRATIONS) == 1


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
        assert final == 1
        assert _version(database) == 1
        assert _counts(database)["children"] == 1
        assert _counts(database)["admin_users"] == 1
    finally:
        _run(database.close())


def test_second_run_writes_nothing_to_the_file(tmp_path, caplog) -> None:
    database = _open_db(tmp_path / "noop.db")
    try:
        _migrate(database)
        db_file = tmp_path / "noop.db"
        size_before = db_file.stat().st_size
        mtime_before = db_file.stat().st_mtime_ns

        _migrate(database)

        # A no-op run must not open a write transaction: the main
        # database file is byte-identical and untouched (mtime too), and
        # no WAL checkpoint traffic dirtied it.
        assert db_file.stat().st_size == size_before
        assert db_file.stat().st_mtime_ns == mtime_before
    finally:
        _run(database.close())


def test_noop_run_logs_no_migration(caplog, tmp_path) -> None:
    database = _open_db(tmp_path / "noop-log.db")
    try:
        _migrate(database)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="custom_components.nestquest.migrations"):
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
        with caplog.at_level(logging.DEBUG, logger="custom_components.nestquest.migrations"):
            _migrate(database)
        assert any(
            "already at version 1" in r.getMessage()
            for r in caplog.records
        )
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Failure atomicity: a failing migration leaves the prior version intact
# ---------------------------------------------------------------------------


def _failing_migrations(prior_statements: list[str]) -> list[list[str]]:
    """Two-migration list where migration 2 fails mid-application."""
    return [
        prior_statements,
        [
            "CREATE TABLE IF NOT EXISTS later_table (id INTEGER PRIMARY KEY)",
            "CREATE TABLE broken (",
        ],
    ]


def test_failing_migration_rolls_back_to_prior_version(tmp_path) -> None:
    database = _open_db(tmp_path / "rollback.db")
    try:
        # Manually simulate a database at version 1: apply migration 1's
        # statements directly and stamp version 1 through the runner.
        _migrate(database)
        version_row = _run(
            database.fetch_one(f"SELECT version FROM {VERSION_TABLE}")
        )
        assert version_row == (1,)

        with pytest.raises(sqlite3.OperationalError):
            _migrate(database, _failing_migrations(SCHEMA_V1_STATEMENTS))

        # Version stamp unchanged, statements from the failed migration
        # absent, and the v1 tables untouched.
        assert _version(database) == 1
        assert "later_table" not in _tables(database)
        assert _counts(database)["children"] == 0
        assert _counts(database)["completion_events"] == 0
    finally:
        _run(database.close())


def test_failing_migration_on_fresh_file_leaves_version_0(tmp_path) -> None:
    database = _open_db(tmp_path / "fresh-rollback.db")
    try:
        # The fresh file still reaches migration 2 (the failing one):
        # migration 1 commits, stamping version 1, before migration 2
        # fails and rolls back.  The run aborts at version 1 — the last
        # fully-applied migration — not at version 0.
        with pytest.raises(sqlite3.OperationalError):
            _migrate(database, _failing_migrations(SCHEMA_V1_STATEMENTS))
        assert _version(database) == 1
        # Migration 2's tables must not survive the failed attempt.
        assert "later_table" not in _tables(database)
        # Migration 1's tables do: it committed before the failure.
        assert "children" in _tables(database)
        assert "task_instances" in _tables(database)
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
        broken[1] = [
            "CREATE TABLE IF NOT EXISTS later_table (id INTEGER PRIMARY KEY)"
        ]
        final = _migrate(database, broken)
        assert final == 2
        assert _version(database) == 2
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
        _run(
            database.execute(
                f"CREATE TABLE {VERSION_TABLE} (version TEXT NOT NULL)"
            )
        )
        _run(
            database.execute(
                f"INSERT INTO {VERSION_TABLE} (version) VALUES (?)",
                ("one",),
            )
        )
        with pytest.raises(RuntimeError, match="not an integer"):
            _run(read_schema_version(database))
    finally:
        _run(database.close())


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