"""Tests for schema.py: v1 DDL for children and admin_users tables."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.schema import (
    SCHEMA_V1_ADMIN_USERS_DDL,
    SCHEMA_V1_CHILDREN_DDL,
    SCHEMA_V1_STATEMENTS,
    async_apply_ddl,
)


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


def _apply(database) -> None:
    _run(async_apply_ddl(database, SCHEMA_V1_STATEMENTS))


# ---------------------------------------------------------------------------
# DDL constants
# ---------------------------------------------------------------------------


def test_schema_v1_statements_compose_the_two_tables() -> None:
    assert SCHEMA_V1_STATEMENTS == [
        *SCHEMA_V1_CHILDREN_DDL,
        *SCHEMA_V1_ADMIN_USERS_DDL,
    ]


def test_every_statement_is_create_if_not_exists() -> None:
    for sql in SCHEMA_V1_STATEMENTS:
        assert sql.lstrip().upper().startswith("CREATE TABLE IF NOT EXISTS")


# ---------------------------------------------------------------------------
# Tables after applying DDL
# ---------------------------------------------------------------------------


def test_children_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "children.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'children'"
            )
        )
        assert row is not None and row[0] == "children"
    finally:
        _run(database.close())


def test_admin_users_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "admins.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'admin_users'"
            )
        )
        assert row is not None and row[0] == "admin_users"
    finally:
        _run(database.close())


def test_children_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "children-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(children)"))
        # cid, name, type, notnull, dflt_value, pk
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("display_name", "TEXT", 1, None, 0),
            ("colour", "TEXT", 0, None, 0),
            ("avatar_ref", "TEXT", 0, None, 0),
            ("sort_order", "INTEGER", 1, "0", 0),
            ("is_active", "INTEGER", 1, "1", 0),
            ("created_at", "TEXT", 1, None, 0),
        ]
    finally:
        _run(database.close())


def test_admin_users_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "admins-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(admin_users)"))
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("ha_user_id", "TEXT", 1, None, 1),
            ("added_at", "TEXT", 1, None, 0),
        ]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Constraint enforcement
# ---------------------------------------------------------------------------


def test_children_display_name_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "display-name.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _run(
                database.execute(
                    "INSERT INTO children (display_name, created_at) "
                    "VALUES (NULL, ?)",
                    ("2026-09-13T00:00:00+00:00",),
                )
            )
    finally:
        _run(database.close())


def test_children_is_active_check_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "is-active.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _run(
                database.execute(
                    "INSERT INTO children (display_name, is_active, created_at) "
                    "VALUES (?, ?, ?)",
                    ("Ada", 2, "2026-09-13T00:00:00+00:00"),
                )
            )
    finally:
        _run(database.close())


def test_children_created_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "created-at.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _run(
                database.execute(
                    "INSERT INTO children (display_name, created_at) "
                    "VALUES (?, NULL)",
                    ("Ada",),
                )
            )
    finally:
        _run(database.close())


def test_admin_users_primary_key_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "pk.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO admin_users (ha_user_id, added_at) VALUES (?, ?)",
                ("user-1", "2026-09-13T00:00:00+00:00"),
            )
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            _run(
                database.execute(
                    "INSERT INTO admin_users (ha_user_id, added_at) VALUES (?, ?)",
                    ("user-1", "2026-09-13T00:00:01+00:00"),
                )
            )
    finally:
        _run(database.close())


def test_admin_users_added_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "added-at.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _run(
                database.execute(
                    "INSERT INTO admin_users (ha_user_id, added_at) "
                    "VALUES (?, NULL)",
                    ("user-1",),
                )
            )
    finally:
        _run(database.close())


def test_children_defaults_apply_on_insert(tmp_path) -> None:
    database = _open_db(tmp_path / "defaults.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        row = _run(
            database.fetch_one(
                "SELECT sort_order, is_active FROM children "
                "WHERE display_name = 'Ada'"
            )
        )
        assert row == (0, 1)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Idempotence and transactional application
# ---------------------------------------------------------------------------


def test_applying_ddl_twice_succeeds_and_keeps_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "idempotent.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _apply(database)
        row = _run(
            database.fetch_one("SELECT COUNT(*) FROM children")
        )
        assert row == (1,)
    finally:
        _run(database.close())


def test_failed_statement_rolls_back_whole_application(tmp_path) -> None:
    from unittest.mock import AsyncMock

    database = _open_db(tmp_path / "rollback.db")
    try:
        bad_statements = [
            "CREATE TABLE IF NOT EXISTS children (id INTEGER PRIMARY KEY)",
            "CREATE TABLE nope (",
        ]
        original = database.execute

        async def _failing_execute(sql, parameters=()):
            if "CREATE TABLE nope" in sql:
                raise sqlite3.OperationalError("near \"(\": syntax error")
            return await original(sql, parameters)

        database.execute = AsyncMock(side_effect=_failing_execute)
        with pytest.raises(sqlite3.OperationalError):
            _run(async_apply_ddl(database, bad_statements))
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'children'"
            )
        )
        assert row is None, "partial DDL must not survive a failed application"
    finally:
        _run(database.close())