"""Tests for schema.py: v1 DDL for children and admin_users tables."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.schema import (
    SCHEMA_V1_ADMIN_USERS_DDL,
    SCHEMA_V1_CHILDREN_DDL,
    SCHEMA_V1_PRESENCE_OVERRIDES_DDL,
    SCHEMA_V1_PRESENCE_SCHEDULES_DDL,
    SCHEMA_V1_SCHEDULE_RULES_DDL,
    SCHEMA_V1_STATEMENTS,
    SCHEMA_V1_TASK_DEFINITIONS_DDL,
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


# Sentinel used by the insert helpers: omit the column from the INSERT so
# its DDL DEFAULT applies (explicit NULL would not trigger a DEFAULT).
_OMIT = object()


def _insert_rule(database, **overrides):
    """Insert one valid schedule_rule, returning the rule id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "rule_type": "weekly",
        "weekday_set": "0,2,4",
        "start_date": "2026-09-13",
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO schedule_rules ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _insert_definition(database, child_id=1, rule_id=1, **overrides):
    """Insert one valid task_definition, returning the definition id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "title": "Brush teeth",
        "child_id": child_id,
        "schedule_rule_id": rule_id,
        "created_at": "2026-09-13T00:00:00+00:00",
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO task_definitions ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _insert_schedule(database, child_id, **overrides):
    """Insert one valid presence_schedule, returning the schedule id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "child_id": child_id,
        "cycle_length_weeks": 2,
        "anchor_date": "2026-09-13",
        "pattern": "0,2,4|1,3",
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO presence_schedules ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _insert_override(database, child_id, **overrides):
    """Insert one valid presence_override, returning the override id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "child_id": child_id,
        "start_date": "2026-09-13",
        "end_date": "2026-09-13",
        "is_present": 1,
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO presence_overrides ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


# ---------------------------------------------------------------------------
# DDL constants
# ---------------------------------------------------------------------------


def test_schema_v1_statements_compose_the_six_tables() -> None:
    assert SCHEMA_V1_STATEMENTS == [
        *SCHEMA_V1_CHILDREN_DDL,
        *SCHEMA_V1_ADMIN_USERS_DDL,
        *SCHEMA_V1_SCHEDULE_RULES_DDL,
        *SCHEMA_V1_TASK_DEFINITIONS_DDL,
        *SCHEMA_V1_PRESENCE_SCHEDULES_DDL,
        *SCHEMA_V1_PRESENCE_OVERRIDES_DDL,
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


def test_schedule_rules_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "rules.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'schedule_rules'"
            )
        )
        assert row is not None and row[0] == "schedule_rules"
    finally:
        _run(database.close())


def test_task_definitions_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'task_definitions'"
            )
        )
        assert row is not None and row[0] == "task_definitions"
    finally:
        _run(database.close())


def test_schedule_rules_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "rules-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(schedule_rules)"))
        # cid, name, type, notnull, dflt_value, pk
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("rule_type", "TEXT", 1, None, 0),
            ("interval", "INTEGER", 1, "1", 0),
            ("weekday_set", "TEXT", 0, None, 0),
            ("day_of_month", "INTEGER", 0, None, 0),
            ("nth_weekday", "INTEGER", 0, None, 0),
            ("month", "INTEGER", 0, None, 0),
            ("start_date", "TEXT", 1, None, 0),
            ("end_date", "TEXT", 0, None, 0),
        ]
    finally:
        _run(database.close())


def test_task_definitions_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(task_definitions)"))
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("title", "TEXT", 1, None, 0),
            ("description", "TEXT", 0, None, 0),
            ("icon", "TEXT", 0, None, 0),
            ("child_id", "INTEGER", 1, None, 0),
            ("schedule_rule_id", "INTEGER", 1, None, 0),
            ("due_time", "TEXT", 0, None, 0),
            ("is_active", "INTEGER", 1, "1", 0),
            ("created_at", "TEXT", 1, None, 0),
        ]
    finally:
        _run(database.close())


def test_task_definitions_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(task_definitions)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("children", "child_id", "id"),
            ("schedule_rules", "schedule_rule_id", "id"),
        }
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


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("sort_order", "abc"),
        ("sort_order", 1.5),
        ("is_active", "abc"),
        ("is_active", 1.5),
    ],
)
def test_children_integer_columns_reject_text_and_fraction(
    tmp_path, column, bad_value
) -> None:
    database = _open_db(tmp_path / f"children-{column}-typeof.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _run(
                database.execute(
                    f"INSERT INTO children (display_name, {column}, created_at) "
                    "VALUES (?, ?, ?)",
                    ("Ada", bad_value, "2026-09-13T00:00:00+00:00"),
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


# ---------------------------------------------------------------------------
# schedule_rules and task_definitions constraint enforcement
# ---------------------------------------------------------------------------


def test_schedule_rules_valid_insert_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "valid-rule.db")
    try:
        _apply(database)
        rule_id = _insert_rule(database)
        row = _run(
            database.fetch_one(
                "SELECT rule_type, interval, weekday_set, start_date "
                "FROM schedule_rules WHERE id = ?",
                (rule_id,),
            )
        )
        assert row == ("weekly", 1, "0,2,4", "2026-09-13")
    finally:
        _run(database.close())


def test_schedule_rules_interval_default_applies(tmp_path) -> None:
    database = _open_db(tmp_path / "interval-default.db")
    try:
        _apply(database)
        rule_id = _insert_rule(database, interval=_OMIT)
        row = _run(
            database.fetch_one(
                "SELECT interval FROM schedule_rules WHERE id = ?", (rule_id,)
            )
        )
        assert row == (1,)
    finally:
        _run(database.close())


def test_schedule_rules_rule_type_check_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "rule-type.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, rule_type="biweekly", weekday_set=None)
    finally:
        _run(database.close())


def test_schedule_rules_interval_zero_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "interval-zero.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, interval=0)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_interval", ["abc", 1.5])
def test_schedule_rules_interval_non_integer_fails(
    tmp_path, bad_interval
) -> None:
    database = _open_db(tmp_path / f"interval-{type(bad_interval).__name__}.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, interval=bad_interval)
    finally:
        _run(database.close())


def test_schedule_rules_interval_integer_one_succeeds(tmp_path) -> None:
    database = _open_db(tmp_path / "interval-one.db")
    try:
        _apply(database)
        rule_id = _insert_rule(database, interval=1)
        row = _run(
            database.fetch_one(
                "SELECT interval FROM schedule_rules WHERE id = ?", (rule_id,)
            )
        )
        assert row == (1,)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("day_of_month", "abc"),
        ("day_of_month", 1.5),
        ("nth_weekday", "abc"),
        ("nth_weekday", 1.5),
        ("month", "abc"),
        ("month", 1.5),
    ],
)
def test_schedule_rules_integer_columns_reject_text_and_fraction(
    tmp_path, column, bad_value
) -> None:
    database = _open_db(tmp_path / f"{column}-typeof.db")
    try:
        _apply(database)
        overrides: dict[str, object] = {"rule_type": "monthly", "weekday_set": None}
        overrides[column] = bad_value
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, **overrides)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    "bad_weekday_set",
    ["", "x", "7", "0,x", "0,8", "0,", "0,1,2,3,4,5,6,0"],
)
def test_schedule_rules_weekday_set_invalid_csv_fails(
    tmp_path, bad_weekday_set
) -> None:
    database = _open_db(tmp_path / "weekday-set-invalid.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, weekday_set=bad_weekday_set)
    finally:
        _run(database.close())


@pytest.mark.parametrize("weekday_set", ["0", "6", "0,1,2,3,4,5,6"])
def test_schedule_rules_weekday_set_valid_csv_succeeds(
    tmp_path, weekday_set
) -> None:
    database = _open_db(tmp_path / "weekday-set-valid.db")
    try:
        _apply(database)
        rule_id = _insert_rule(database, weekday_set=weekday_set)
        row = _run(
            database.fetch_one(
                "SELECT weekday_set FROM schedule_rules WHERE id = ?", (rule_id,)
            )
        )
        assert row == (weekday_set,)
    finally:
        _run(database.close())


def test_schedule_rules_day_of_month_out_of_range_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "day-of-month.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(
                database,
                rule_type="monthly",
                weekday_set=None,
                day_of_month=32,
            )
    finally:
        _run(database.close())


def test_schedule_rules_nth_weekday_zero_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "nth-weekday.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(
                database,
                rule_type="monthly",
                weekday_set=None,
                day_of_month=None,
                nth_weekday=0,
            )
    finally:
        _run(database.close())


def test_schedule_rules_nth_weekday_minus_one_last_week_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "nth-weekday-last.db")
    try:
        _apply(database)
        rule_id = _insert_rule(
            database,
            rule_type="monthly",
            weekday_set=None,
            day_of_month=None,
            nth_weekday=-1,
        )
        row = _run(
            database.fetch_one(
                "SELECT nth_weekday FROM schedule_rules WHERE id = ?", (rule_id,)
            )
        )
        assert row == (-1,)
    finally:
        _run(database.close())


def test_schedule_rules_month_out_of_range_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "month.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(
                database, rule_type="yearly", weekday_set=None, month=13
            )
    finally:
        _run(database.close())


def test_schedule_rules_weekly_without_weekday_set_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "weekly-no-weekdays.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, rule_type="weekly", weekday_set=None)
    finally:
        _run(database.close())


def test_schedule_rules_monthly_without_day_or_nth_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "monthly-no-fields.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(
                database,
                rule_type="monthly",
                weekday_set=None,
                day_of_month=None,
                nth_weekday=None,
            )
    finally:
        _run(database.close())


def test_schedule_rules_yearly_without_month_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "yearly-no-month.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(
                database,
                rule_type="yearly",
                weekday_set=None,
                day_of_month=None,
                month=None,
            )
    finally:
        _run(database.close())


def test_schedule_rules_daily_with_month_fields_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "daily-month-fields.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, rule_type="daily", month=3)
    finally:
        _run(database.close())


def test_schedule_rules_end_date_before_start_date_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "end-before-start.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_rule(database, end_date="2026-09-12")
    finally:
        _run(database.close())


def test_schedule_rules_end_date_equal_to_start_date_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "end-equals-start.db")
    try:
        _apply(database)
        rule_id = _insert_rule(database, end_date="2026-09-13")
        row = _run(
            database.fetch_one(
                "SELECT end_date FROM schedule_rules WHERE id = ?", (rule_id,)
            )
        )
        assert row == ("2026-09-13",)
    finally:
        _run(database.close())


def test_schedule_rules_start_date_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "start-date-null.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_rule(database, start_date=None)
    finally:
        _run(database.close())


def test_task_definitions_insert_requires_existing_child_and_rule(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "definitions-fk-unknown.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        rule_id = _insert_rule(database)
        definition_id = _insert_definition(
            database, child_id=1, rule_id=rule_id
        )
        row = _run(
            database.fetch_one(
                "SELECT title, child_id, schedule_rule_id FROM task_definitions "
                "WHERE id = ?",
                (definition_id,),
            )
        )
        assert row == ("Brush teeth", 1, rule_id)
    finally:
        _run(database.close())


def test_task_definitions_unknown_child_id_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-bad-child.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_definition(database, child_id=999)
    finally:
        _run(database.close())


def test_task_definitions_unknown_schedule_rule_id_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-bad-rule.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_definition(database, child_id=1, rule_id=999)
    finally:
        _run(database.close())


def test_task_definitions_is_active_check_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-is-active.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_definition(database, child_id=1, rule_id=1, is_active=2)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_is_active", ["abc", 1.5])
def test_task_definitions_is_active_non_integer_fails(
    tmp_path, bad_is_active
) -> None:
    database = _open_db(tmp_path / "definitions-is-active-typeof.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_definition(
                database, child_id=1, rule_id=1, is_active=bad_is_active
            )
    finally:
        _run(database.close())


def test_task_definitions_title_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-title.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_definition(database, child_id=1, rule_id=1, title=None)
    finally:
        _run(database.close())


def test_task_definitions_created_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-created-at.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_definition(
                database, child_id=1, rule_id=1, created_at=None
            )
    finally:
        _run(database.close())


def test_task_definitions_defaults_apply_on_insert(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-defaults.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_rule(database)
        definition_id = _insert_definition(
            database, child_id=1, rule_id=1, is_active=_OMIT
        )
        row = _run(
            database.fetch_one(
                "SELECT is_active, due_time FROM task_definitions WHERE id = ?",
                (definition_id,),
            )
        )
        assert row == (1, None)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Idempotence across the extended v1 list
# ---------------------------------------------------------------------------


def test_applying_extended_ddl_twice_keeps_new_table_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "idempotent-extended.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_rule(database)
        _insert_definition(database, child_id=1, rule_id=1)
        _apply(database)
        counts = []
        for table in ("children", "schedule_rules", "task_definitions"):
            row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
            counts.append(row[0])
        assert counts == [1, 1, 1]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# presence_schedules and presence_overrides constraint enforcement
# ---------------------------------------------------------------------------


def _child(database, name="Ada") -> int:
    _run(
        database.execute(
            "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
            (name, "2026-09-13T00:00:00+00:00"),
        )
    )
    return 1


def test_presence_schedules_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'presence_schedules'"
            )
        )
        assert row is not None and row[0] == "presence_schedules"
    finally:
        _run(database.close())


def test_presence_overrides_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'presence_overrides'"
            )
        )
        assert row is not None and row[0] == "presence_overrides"
    finally:
        _run(database.close())


def test_presence_schedules_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(presence_schedules)"))
        # cid, name, type, notnull, dflt_value, pk
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("child_id", "INTEGER", 1, None, 0),
            ("cycle_length_weeks", "INTEGER", 1, None, 0),
            ("anchor_date", "TEXT", 1, None, 0),
            ("pattern", "TEXT", 1, None, 0),
        ]
    finally:
        _run(database.close())


def test_presence_overrides_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(presence_overrides)"))
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("child_id", "INTEGER", 1, None, 0),
            ("start_date", "TEXT", 1, None, 0),
            ("end_date", "TEXT", 1, None, 0),
            ("is_present", "INTEGER", 1, None, 0),
            ("note", "TEXT", 0, None, 0),
        ]
    finally:
        _run(database.close())


def test_presence_schedules_foreign_key_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(presence_schedules)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {("children", "child_id", "id")}
    finally:
        _run(database.close())


def test_presence_overrides_foreign_key_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(presence_overrides)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {("children", "child_id", "id")}
    finally:
        _run(database.close())


def test_presence_schedules_valid_insert_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-valid.db")
    try:
        _apply(database)
        _child(database)
        schedule_id = _insert_schedule(database, child_id=1)
        row = _run(
            database.fetch_one(
                "SELECT child_id, cycle_length_weeks, anchor_date, pattern "
                "FROM presence_schedules WHERE id = ?",
                (schedule_id,),
            )
        )
        assert row == (1, 2, "2026-09-13", "0,2,4|1,3")
    finally:
        _run(database.close())


def test_presence_schedules_second_schedule_for_same_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-unique.db")
    try:
        _apply(database)
        _child(database)
        _insert_schedule(database, child_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            _insert_schedule(database, child_id=1)
    finally:
        _run(database.close())


def test_presence_schedules_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-bad-child.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_schedule(database, child_id=999)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_cycle", [0, 5, "abc", 1.5])
def test_presence_schedules_cycle_length_out_of_range_or_type_fails(
    tmp_path, bad_cycle
) -> None:
    database = _open_db(tmp_path / f"cycle-{type(bad_cycle).__name__}.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_schedule(database, child_id=1, cycle_length_weeks=bad_cycle)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    ("cycle", "pattern"),
    [
        (1, ""),
        (1, "0"),
        (1, "0,2,4"),
        (2, "0,2,4|1,3"),
        (2, "|0"),
        (2, "0|"),
        (2, "0,1,2,3,4,5,6|"),
        (3, "0||1"),
        (4, "|||"),
        (4, "0|1|2|3"),
        (4, "0,1|0,1|0,1|0,1"),
    ],
)
def test_presence_schedules_valid_patterns_succeed(tmp_path, cycle, pattern) -> None:
    database = _open_db(tmp_path / "presence-schedules-patterns-valid.db")
    try:
        _apply(database)
        _child(database)
        schedule_id = _insert_schedule(
            database, child_id=1, cycle_length_weeks=cycle, pattern=pattern
        )
        row = _run(
            database.fetch_one(
                "SELECT pattern FROM presence_schedules WHERE id = ?",
                (schedule_id,),
            )
        )
        assert row == (pattern,)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    ("cycle", "pattern"),
    [
        (2, "0,2,4"),  # too few segments
        (1, "0|1"),  # too many segments
        (4, "0|1|2"),  # too few segments
        (2, "0,2,4||1,3"),  # empty middle segment is only valid if empty everywhere
        (2, "x|1"),
        (2, "7|1"),
        (2, "0,8|1"),
        (2, "0,|1"),
        (2, "0|,1"),
        (2, "0|1,"),
        (2, ",0|1"),
        (2, "0,,1|2"),
        (2, "00,1|2"),
        (2, "0;1|2"),
        (2, "0 1|2"),
        (2, "0,2,4|1,7"),
        (2, "0,2,4|10,3"),
        (1, "0,1,2,3,4,5,6,0"),  # more than 7 elements
    ],
)
def test_presence_schedules_invalid_patterns_fail(tmp_path, cycle, pattern) -> None:
    database = _open_db(tmp_path / "presence-schedules-patterns-invalid.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_schedule(
                database, child_id=1, cycle_length_weeks=cycle, pattern=pattern
            )
    finally:
        _run(database.close())


def test_presence_schedules_cycle_length_bounds_pass(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-schedules-cycle-bounds.db")
    try:
        _apply(database)
        _child(database)
        _insert_schedule(database, child_id=1, cycle_length_weeks=1, pattern="0")
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Bo", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_schedule(database, child_id=2, cycle_length_weeks=4, pattern="|||")
    finally:
        _run(database.close())


def test_presence_overrides_valid_insert_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-valid.db")
    try:
        _apply(database)
        _child(database)
        override_id = _insert_override(
            database,
            child_id=1,
            note="Grandma's birthday",
        )
        row = _run(
            database.fetch_one(
                "SELECT child_id, start_date, end_date, is_present, note "
                "FROM presence_overrides WHERE id = ?",
                (override_id,),
            )
        )
        assert row == (1, "2026-09-13", "2026-09-13", 1, "Grandma's birthday")
    finally:
        _run(database.close())


def test_presence_overrides_range_and_absent_round_trip(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-range.db")
    try:
        _apply(database)
        _child(database)
        override_id = _insert_override(
            database,
            child_id=1,
            start_date="2026-12-21",
            end_date="2027-01-04",
            is_present=0,
        )
        row = _run(
            database.fetch_one(
                "SELECT start_date, end_date, is_present, note "
                "FROM presence_overrides WHERE id = ?",
                (override_id,),
            )
        )
        assert row == ("2026-12-21", "2027-01-04", 0, None)
    finally:
        _run(database.close())


def test_presence_overrides_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-bad-child.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_override(database, child_id=999)
    finally:
        _run(database.close())


def test_presence_overrides_is_present_check_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-is-present.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_override(database, child_id=1, is_present=2)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    "bad_is_present",
    ["abc", 1.5, 2.5],
)
def test_presence_overrides_is_present_non_integer_fails(
    tmp_path, bad_is_present
) -> None:
    database = _open_db(tmp_path / "presence-overrides-is-present-typeof.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_override(database, child_id=1, is_present=bad_is_present)
    finally:
        _run(database.close())


def test_presence_overrides_end_date_before_start_date_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-end-before-start.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_override(
                database, child_id=1, start_date="2026-09-13", end_date="2026-09-12"
            )
    finally:
        _run(database.close())


def test_presence_overrides_end_date_equal_to_start_date_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-end-equals-start.db")
    try:
        _apply(database)
        _child(database)
        override_id = _insert_override(
            database, child_id=1, start_date="2026-09-13", end_date="2026-09-13"
        )
        row = _run(
            database.fetch_one(
                "SELECT end_date FROM presence_overrides WHERE id = ?",
                (override_id,),
            )
        )
        assert row == ("2026-09-13",)
    finally:
        _run(database.close())


def test_presence_overrides_start_date_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-start-null.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_override(database, child_id=1, start_date=None)
    finally:
        _run(database.close())


def test_presence_overrides_end_date_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-end-null.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_override(database, child_id=1, end_date=None)
    finally:
        _run(database.close())


def test_presence_overrides_is_present_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-is-present-null.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_override(database, child_id=1, is_present=None)
    finally:
        _run(database.close())


def test_presence_overrides_multiple_children_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-overrides-multi-child.db")
    try:
        _apply(database)
        _child(database, "Ada")
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Bo", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_override(database, child_id=1)
        _insert_override(database, child_id=2)
        row = _run(database.fetch_one("SELECT COUNT(*) FROM presence_overrides"))
        assert row == (2,)
    finally:
        _run(database.close())


def test_applying_presence_ddl_twice_keeps_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-idempotent.db")
    try:
        _apply(database)
        _child(database)
        _insert_schedule(database, child_id=1)
        _insert_override(database, child_id=1)
        _apply(database)
        counts = []
        for table in ("presence_schedules", "presence_overrides"):
            row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
            counts.append(row[0])
        assert counts == [1, 1]
    finally:
        _run(database.close())