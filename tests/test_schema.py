"""Tests for schema.py: v1 DDL for children and admin_users tables."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.core.db import NestQuestDatabase
from custom_components.nestquest.core.schema import (
    SCHEMA_V1_ADMIN_USERS_DDL,
    SCHEMA_V1_CHILDREN_DDL,
    SCHEMA_V1_COMPLETION_EVENTS_DDL,
    SCHEMA_V7_META_STATE_DDL,
    SCHEMA_V1_PRESENCE_OVERRIDES_DDL,
    SCHEMA_V9_PRESENCE_PATTERNS_DDL,
    SCHEMA_V1_SCHEDULE_RULES_DDL,
    SCHEMA_V1_STATEMENTS,
    SCHEMA_V1_QUEST_DEFINITIONS_DDL,
    SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL,
    SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL,
    SCHEMA_V1_QUEST_INSTANCES_DDL,
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
    database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
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


def _insert_definition(database, rule_id=1, assignees=(1,), **overrides):
    """Insert one valid quest_definition, returning the definition id.

    ``assignees`` rows are written to ``quest_definition_assignees``
    after the definition insert (the definition itself carries no
    child).  Pass ``assignees=None`` for an unassigned definition.
    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "title": "Brush teeth",
        "schedule_rule_id": rule_id,
        "created_at": "2026-09-13T00:00:00+00:00",
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO quest_definitions ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    for child_id in assignees or ():
        _run(
            database.execute(
                "INSERT INTO quest_definition_assignees "
                "(definition_id, child_id) VALUES (?, ?)",
                (result.lastrowid, child_id),
            )
        )
    return result.lastrowid


def _insert_pattern(database, child_id, **overrides):
    """Insert one valid presence_pattern, returning the pattern id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "child_id": child_id,
        "name": "Home schedule",
        "kind": "home",
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
            f"INSERT INTO presence_patterns ({columns}) VALUES ({placeholders})",
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


def test_schema_v1_statements_compose_the_nine_tables() -> None:
    assert SCHEMA_V1_STATEMENTS == [
        *SCHEMA_V1_CHILDREN_DDL,
        *SCHEMA_V1_ADMIN_USERS_DDL,
        *SCHEMA_V1_SCHEDULE_RULES_DDL,
        *SCHEMA_V1_QUEST_DEFINITIONS_DDL,
        *SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL,
        *SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL,
        *SCHEMA_V9_PRESENCE_PATTERNS_DDL,
        *SCHEMA_V1_PRESENCE_OVERRIDES_DDL,
        *SCHEMA_V1_QUEST_INSTANCES_DDL,
        *SCHEMA_V1_COMPLETION_EVENTS_DDL,
        *SCHEMA_V7_META_STATE_DDL,
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


def test_quest_definitions_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'quest_definitions'"
            )
        )
        assert row is not None and row[0] == "quest_definitions"
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


def test_quest_definitions_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(quest_definitions)"))
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("title", "TEXT", 1, None, 0),
            ("description", "TEXT", 0, None, 0),
            ("icon", "TEXT", 0, None, 0),
            ("schedule_rule_id", "INTEGER", 1, None, 0),
            ("due_time", "TEXT", 0, None, 0),
            ("is_active", "INTEGER", 1, "1", 0),
            ("created_at", "TEXT", 1, None, 0),
            ("skip_on_away", "INTEGER", 1, "1", 0),
        ]
    finally:
        _run(database.close())


def test_quest_definitions_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(quest_definitions)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("schedule_rules", "schedule_rule_id", "id"),
        }
    finally:
        _run(database.close())


def test_quest_definition_assignees_table_exists_after_applying_ddl(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "assignees.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'quest_definition_assignees'"
            )
        )
        assert row is not None and row[0] == "quest_definition_assignees"
    finally:
        _run(database.close())


def test_quest_definition_assignees_columns_types_and_constraints(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "assignees-columns.db")
    try:
        _apply(database)
        columns = _run(
            database.fetch_all("PRAGMA table_info(quest_definition_assignees)")
        )
        # cid, name, type, notnull, dflt_value, pk — both columns are
        # the two-part primary key, so pk is 1 and 2.
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("definition_id", "INTEGER", 1, None, 1),
            ("child_id", "INTEGER", 1, None, 2),
        ]
    finally:
        _run(database.close())


def test_quest_definition_assignees_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "assignees-fks.db")
    try:
        _apply(database)
        fks = _run(
            database.fetch_all(
                "PRAGMA foreign_key_list(quest_definition_assignees)"
            )
        )
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("quest_definitions", "definition_id", "id"),
            ("children", "child_id", "id"),
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
# schedule_rules and quest_definitions constraint enforcement
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


@pytest.mark.parametrize("bad_flag", [2, -1])
def test_quest_definitions_skip_on_away_check_enforced(
    tmp_path, bad_flag
) -> None:
    database = _open_db(tmp_path / f"skip-on-away-{bad_flag}.db")
    try:
        _apply(database)
        _child(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_definition(database, skip_on_away=bad_flag)
        definition_id = _insert_definition(database, skip_on_away=0)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _run(
                database.execute(
                    "UPDATE quest_definitions SET skip_on_away = ? "
                    "WHERE id = ?",
                    (bad_flag, definition_id),
                )
            )
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


def test_quest_definitions_insert_requires_existing_child_and_rule(
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
        definition_id = _insert_definition(database, rule_id=rule_id)
        row = _run(
            database.fetch_one(
                "SELECT title, schedule_rule_id FROM quest_definitions "
                "WHERE id = ?",
                (definition_id,),
            )
        )
        assert row == ("Brush teeth", rule_id)
        assignee = _run(
            database.fetch_one(
                "SELECT child_id FROM quest_definition_assignees "
                "WHERE definition_id = ?",
                (definition_id,),
            )
        )
        assert assignee == (1,)
    finally:
        _run(database.close())


def test_quest_definition_assignees_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "assignees-bad-child.db")
    try:
        _apply(database)
        _insert_rule(database)
        definition_id = _insert_definition(database, assignees=None)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_assignees "
                    "(definition_id, child_id) VALUES (?, 999)",
                    (definition_id,),
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_assignees_unknown_definition_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "assignees-bad-definition.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_assignees "
                    "(definition_id, child_id) VALUES (999, 1)"
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_assignees_duplicate_pair_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "assignees-duplicate.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_rule(database)
        definition_id = _insert_definition(database)
        with pytest.raises(sqlite3.IntegrityError):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_assignees "
                    "(definition_id, child_id) VALUES (?, 1)",
                    (definition_id,),
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_windows_table_exists_after_applying_ddl(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "windows.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'quest_definition_windows'"
            )
        )
        assert row is not None and row[0] == "quest_definition_windows"
    finally:
        _run(database.close())


def test_quest_definition_windows_columns_types_and_constraints(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "windows-columns.db")
    try:
        _apply(database)
        columns = _run(
            database.fetch_all("PRAGMA table_info(quest_definition_windows)")
        )
        # cid, name, type, notnull, dflt_value, pk — the composite
        # primary key spans definition_id and window.
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("definition_id", "INTEGER", 1, None, 1),
            ("window", "TEXT", 1, None, 2),
            ("due_time", "TEXT", 0, None, 0),
        ]
    finally:
        _run(database.close())


def test_quest_definition_windows_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "windows-fks.db")
    try:
        _apply(database)
        fks = _run(
            database.fetch_all(
                "PRAGMA foreign_key_list(quest_definition_windows)"
            )
        )
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("quest_definitions", "definition_id", "id"),
        }
    finally:
        _run(database.close())


def test_quest_definition_windows_valid_rows_round_trip(tmp_path) -> None:
    database = _open_db(tmp_path / "windows-roundtrip.db")
    try:
        _apply(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Ada", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_rule(database)
        definition_id = _insert_definition(database, assignees=None)
        for window, due in (
            ("morning", "09:00"),
            ("afternoon", None),
            ("evening", "19:30"),
        ):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_windows "
                    "(definition_id, window, due_time) VALUES (?, ?, ?)",
                    (definition_id, window, due),
                )
            )
        rows = _run(
            database.fetch_all(
                "SELECT window, due_time FROM quest_definition_windows "
                "WHERE definition_id = ? ORDER BY window",
                (definition_id,),
            )
        )
        assert rows == [
            ("afternoon", None),
            ("evening", "19:30"),
            ("morning", "09:00"),
        ]
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    "window", ["Midnight", "MORNING", "noon", "", "evenings"]
)
def test_quest_definition_windows_window_check_enforced(
    tmp_path, window
) -> None:
    database = _open_db(tmp_path / "windows-check.db")
    try:
        _apply(database)
        _insert_rule(database)
        definition_id = _insert_definition(database, assignees=None)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_windows "
                    "(definition_id, window, due_time) VALUES (?, ?, NULL)",
                    (definition_id, window),
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_windows_duplicate_window_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "windows-duplicate.db")
    try:
        _apply(database)
        _insert_rule(database)
        definition_id = _insert_definition(database, assignees=None)
        _run(
            database.execute(
                "INSERT INTO quest_definition_windows "
                "(definition_id, window, due_time) "
                "VALUES (?, 'morning', NULL)",
                (definition_id,),
            )
        )
        with pytest.raises(sqlite3.IntegrityError):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_windows "
                    "(definition_id, window, due_time) "
                    "VALUES (?, 'morning', '09:00')",
                    (definition_id,),
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_windows_unknown_definition_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "windows-bad-definition.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _run(
                database.execute(
                    "INSERT INTO quest_definition_windows "
                    "(definition_id, window, due_time) "
                    "VALUES (999, 'morning', NULL)"
                )
            )
    finally:
        _run(database.close())


def test_quest_definition_assignees_multiple_children_allowed(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "assignees-multi.db")
    try:
        _apply(database)
        for name in ("Ada", "Ben", "Cleo"):
            _run(
                database.execute(
                    "INSERT INTO children (display_name, created_at) "
                    "VALUES (?, ?)",
                    (name, "2026-09-13T00:00:00+00:00"),
                )
            )
        _insert_rule(database)
        definition_id = _insert_definition(database, assignees=(1, 2, 3))
        rows = _run(
            database.fetch_all(
                "SELECT child_id FROM quest_definition_assignees "
                "WHERE definition_id = ? ORDER BY child_id",
                (definition_id,),
            )
        )
        assert [row[0] for row in rows] == [1, 2, 3]
    finally:
        _run(database.close())


def test_quest_definitions_unknown_schedule_rule_id_fails(tmp_path) -> None:
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
            _insert_definition(database, rule_id=999)
    finally:
        _run(database.close())


def test_quest_definitions_is_active_check_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-is-active.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_definition(database, rule_id=1, is_active=2)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_is_active", ["abc", 1.5])
def test_quest_definitions_is_active_non_integer_fails(
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
                database, rule_id=1, is_active=bad_is_active
            )
    finally:
        _run(database.close())


def test_quest_definitions_title_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-title.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_definition(database, rule_id=1, title=None)
    finally:
        _run(database.close())


def test_quest_definitions_created_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "definitions-created-at.db")
    try:
        _apply(database)
        _insert_rule(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_definition(
                database, rule_id=1, created_at=None
            )
    finally:
        _run(database.close())


def test_quest_definitions_defaults_apply_on_insert(tmp_path) -> None:
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
            database, rule_id=1, is_active=_OMIT
        )
        row = _run(
            database.fetch_one(
                "SELECT is_active, due_time FROM quest_definitions WHERE id = ?",
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
        _insert_definition(database, rule_id=1)
        _apply(database)
        counts = []
        for table in ("children", "schedule_rules", "quest_definitions"):
            row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
            counts.append(row[0])
        assert counts == [1, 1, 1]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# presence_patterns and presence_overrides constraint enforcement
# ---------------------------------------------------------------------------


def _child(database, name="Ada") -> int:
    _run(
        database.execute(
            "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
            (name, "2026-09-13T00:00:00+00:00"),
        )
    )
    return 1


def test_presence_patterns_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'presence_patterns'"
            )
        )
        assert row is not None and row[0] == "presence_patterns"
        # Schema 9 replaced the one-per-child presence_schedules table;
        # the current-schema DDL must not create it.
        gone = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'presence_schedules'"
            )
        )
        assert gone is None
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


def test_presence_patterns_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(presence_patterns)"))
        # cid, name, type, notnull, dflt_value, pk
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("child_id", "INTEGER", 1, None, 0),
            ("name", "TEXT", 1, None, 0),
            ("kind", "TEXT", 1, None, 0),
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


def test_presence_patterns_foreign_key_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(presence_patterns)"))
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


def test_presence_patterns_valid_insert_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-valid.db")
    try:
        _apply(database)
        _child(database)
        pattern_id = _insert_pattern(database, child_id=1)
        row = _run(
            database.fetch_one(
                "SELECT child_id, name, kind, cycle_length_weeks, anchor_date, "
                "pattern FROM presence_patterns WHERE id = ?",
                (pattern_id,),
            )
        )
        assert row == (1, "Home schedule", "home", 2, "2026-09-13", "0,2,4|1,3")
    finally:
        _run(database.close())


def test_presence_patterns_allow_several_patterns_per_child(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-many.db")
    try:
        _apply(database)
        _child(database)
        first = _insert_pattern(database, child_id=1)
        second = _insert_pattern(
            database, child_id=1, name="Weekend away", kind="away",
            cycle_length_weeks=1, pattern="5,6",
        )
        third = _insert_pattern(database, child_id=1)  # identical row is fine
        rows = _run(
            database.fetch_all(
                "SELECT id, name, kind FROM presence_patterns "
                "WHERE child_id = 1 ORDER BY id"
            )
        )
        assert rows == [
            (first, "Home schedule", "home"),
            (second, "Weekend away", "away"),
            (third, "Home schedule", "home"),
        ]
    finally:
        _run(database.close())


def test_presence_patterns_declare_no_unique_index(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-no-unique.db")
    try:
        _apply(database)
        indexes = _run(database.fetch_all("PRAGMA index_list(presence_patterns)"))
        assert [row for row in indexes if row[2]] == []
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_kind", ["", "HOME", "Away", "present", "absent", 1])
def test_presence_patterns_kind_check_enforced(tmp_path, bad_kind) -> None:
    database = _open_db(tmp_path / "presence-patterns-kind.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_pattern(database, child_id=1, kind=bad_kind)
    finally:
        _run(database.close())


@pytest.mark.parametrize("kind", ["home", "away"])
def test_presence_patterns_both_kinds_accepted(tmp_path, kind) -> None:
    database = _open_db(tmp_path / f"presence-patterns-kind-{kind}.db")
    try:
        _apply(database)
        _child(database)
        pattern_id = _insert_pattern(database, child_id=1, kind=kind)
        row = _run(
            database.fetch_one(
                "SELECT kind FROM presence_patterns WHERE id = ?", (pattern_id,)
            )
        )
        assert row == (kind,)
    finally:
        _run(database.close())


@pytest.mark.parametrize("column", ["name", "kind"])
def test_presence_patterns_name_and_kind_not_null(tmp_path, column) -> None:
    database = _open_db(tmp_path / f"presence-patterns-null-{column}.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_pattern(database, child_id=1, **{column: None})
    finally:
        _run(database.close())


def test_presence_schedules_absent_from_current_schema_ddl() -> None:
    assert not any(
        "presence_schedules" in sql for sql in SCHEMA_V1_STATEMENTS
    )


def test_presence_patterns_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-bad-child.db")
    try:
        _apply(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_pattern(database, child_id=999)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_cycle", [0, 5, "abc", 1.5])
def test_presence_patterns_cycle_length_out_of_range_or_type_fails(
    tmp_path, bad_cycle
) -> None:
    database = _open_db(tmp_path / f"cycle-{type(bad_cycle).__name__}.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_pattern(database, child_id=1, cycle_length_weeks=bad_cycle)
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
def test_presence_patterns_valid_patterns_succeed(tmp_path, cycle, pattern) -> None:
    database = _open_db(tmp_path / "presence-patterns-patterns-valid.db")
    try:
        _apply(database)
        _child(database)
        pattern_id = _insert_pattern(
            database, child_id=1, cycle_length_weeks=cycle, pattern=pattern
        )
        row = _run(
            database.fetch_one(
                "SELECT pattern FROM presence_patterns WHERE id = ?",
                (pattern_id,),
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
def test_presence_patterns_invalid_patterns_fail(tmp_path, cycle, pattern) -> None:
    database = _open_db(tmp_path / "presence-patterns-patterns-invalid.db")
    try:
        _apply(database)
        _child(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_pattern(
                database, child_id=1, cycle_length_weeks=cycle, pattern=pattern
            )
    finally:
        _run(database.close())


def test_presence_patterns_cycle_length_bounds_pass(tmp_path) -> None:
    database = _open_db(tmp_path / "presence-patterns-cycle-bounds.db")
    try:
        _apply(database)
        _child(database)
        _insert_pattern(database, child_id=1, cycle_length_weeks=1, pattern="0")
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Bo", "2026-09-13T00:00:00+00:00"),
            )
        )
        _insert_pattern(database, child_id=2, cycle_length_weeks=4, pattern="|||")
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
        _insert_pattern(database, child_id=1)
        _insert_override(database, child_id=1)
        _apply(database)
        counts = []
        for table in ("presence_patterns", "presence_overrides"):
            row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
            counts.append(row[0])
        assert counts == [1, 1]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# quest_instances and completion_events: helpers
# ---------------------------------------------------------------------------


def _insert_instance(database, definition_id=1, window="morning", **overrides):
    """Insert one valid quest_instance, returning the instance id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "definition_id": definition_id,
        "child_id": 1,
        "window": window,
        "due_date": "2026-09-14",
        "generated_at": "2026-09-14T00:00:00+00:00",
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO quest_instances ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _insert_event(database, instance_id=1, **overrides):
    """Insert one valid completion_event, returning the event id.

    Pass ``_OMIT`` as a value to leave that column out of the INSERT so
    its DDL DEFAULT applies.
    """
    values: dict[str, object] = {
        "instance_id": instance_id,
        "child_id": 1,
        "event_type": "completed",
        "actor_source": "user",
        "actor_user_id": "user-1",
        "occurred_at": "2026-09-14T08:30:00+00:00",
        "was_on_time": 1,
    }
    values.update(overrides)
    values = {k: v for k, v in values.items() if v is not _OMIT}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    result = _run(
        database.execute(
            f"INSERT INTO completion_events ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _setup_definition(database) -> None:
    """Create one child, one schedule rule and one quest definition."""
    _child(database)
    _insert_rule(database)
    _insert_definition(database, rule_id=1)


# ---------------------------------------------------------------------------
# quest_instances and completion_events: DDL shape
# ---------------------------------------------------------------------------


def test_quest_instances_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'quest_instances'"
            )
        )
        assert row is not None and row[0] == "quest_instances"
    finally:
        _run(database.close())


def test_completion_events_table_exists_after_applying_ddl(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events.db")
    try:
        _apply(database)
        row = _run(
            database.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'completion_events'"
            )
        )
        assert row is not None and row[0] == "completion_events"
    finally:
        _run(database.close())


def test_quest_instances_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(quest_instances)"))
        # cid, name, type, notnull, dflt_value, pk
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("definition_id", "INTEGER", 1, None, 0),
            ("child_id", "INTEGER", 1, None, 0),
            ("window", "TEXT", 1, None, 0),
            ("due_date", "TEXT", 1, None, 0),
            ("due_time", "TEXT", 0, None, 0),
            ("generated_at", "TEXT", 1, None, 0),
        ]
    finally:
        _run(database.close())


def test_completion_events_columns_types_and_constraints(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-columns.db")
    try:
        _apply(database)
        columns = _run(database.fetch_all("PRAGMA table_info(completion_events)"))
        assert [(row[1], row[2], row[3], row[4], row[5]) for row in columns] == [
            ("id", "INTEGER", 0, None, 1),
            ("instance_id", "INTEGER", 1, None, 0),
            ("child_id", "INTEGER", 1, None, 0),
            ("event_type", "TEXT", 1, None, 0),
            ("actor_source", "TEXT", 1, None, 0),
            ("actor_user_id", "TEXT", 0, None, 0),
            ("actor_child_id", "INTEGER", 0, None, 0),
            ("occurred_at", "TEXT", 1, None, 0),
            ("was_on_time", "INTEGER", 0, None, 0),
        ]
    finally:
        _run(database.close())


def test_quest_instances_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(quest_instances)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("quest_definitions", "definition_id", "id"),
            ("children", "child_id", "id"),
        }
    finally:
        _run(database.close())


def test_completion_events_foreign_keys_declared(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-fks.db")
    try:
        _apply(database)
        fks = _run(database.fetch_all("PRAGMA foreign_key_list(completion_events)"))
        declared = {(row[2], row[3], row[4]) for row in fks}
        assert declared == {
            ("quest_instances", "instance_id", "id"),
            ("children", "child_id", "id"),
            ("children", "actor_child_id", "id"),
        }
    finally:
        _run(database.close())


def test_quest_instances_unique_index_on_widened_key(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-unique.db")
    try:
        _apply(database)
        _setup_definition(database)
        rows = _run(
            database.fetch_all(
                "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name = 'quest_instances'"
            )
        )
        implicit = [(name, sql) for name, sql in rows if sql is None]
        assert len(implicit) == 1, (
            "the (definition_id, child_id, due_date, window) UNIQUE "
            "constraint must be backed by exactly one implicit unique index"
        )
        columns = _run(
            database.fetch_all(
                f"PRAGMA index_info('{implicit[0][0]}')"
            )
        )
        assert [row[2] for row in columns] == [
            "definition_id",
            "child_id",
            "due_date",
            "window",
        ]
        # The implicit index is genuinely unique: UNIQUE(...) is the only
        # constraint SQLite backs with a sql-less autoindex on this table.
        row = _run(
            database.fetch_one(
                "SELECT COUNT(DISTINCT name) FROM pragma_index_list"
                "('quest_instances') WHERE \"unique\" = 1"
            )
        )
        assert row == (1,)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# quest_instances: constraint enforcement
# ---------------------------------------------------------------------------


def test_quest_instances_valid_insert_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-valid.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1, child_id=1)
        row = _run(
            database.fetch_one(
                "SELECT definition_id, child_id, window, due_date, "
                "due_time, generated_at "
                "FROM quest_instances WHERE id = ?",
                (instance_id,),
            )
        )
        assert row == (
            1, 1, "morning", "2026-09-14", None,
            "2026-09-14T00:00:00+00:00",
        )
    finally:
        _run(database.close())


def test_quest_instances_due_time_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-due-time.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(
            database, definition_id=1, due_time="17:30"
        )
        row = _run(
            database.fetch_one(
                "SELECT due_time FROM quest_instances WHERE id = ?",
                (instance_id,),
            )
        )
        assert row == ("17:30",)
    finally:
        _run(database.close())


def test_quest_instances_duplicate_tuple_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-duplicate.db")
    try:
        _apply(database)
        _setup_definition(database)
        _insert_instance(database, definition_id=1, due_date="2026-09-14")
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            _insert_instance(database, definition_id=1, due_date="2026-09-14")
    finally:
        _run(database.close())


def test_quest_instances_duplicate_tuple_different_child_allowed(
    tmp_path,
) -> None:
    """D-008: same definition, date and window for two different
    assignees of the same definition are two distinct instances."""
    database = _open_db(tmp_path / "task-instances-shared.db")
    try:
        _apply(database)
        _setup_definition(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Bo", "2026-09-13T00:00:00+00:00"),
            )
        )
        _run(
            database.execute(
                "INSERT INTO quest_definition_assignees "
                "(definition_id, child_id) VALUES (1, 2)"
            )
        )
        _insert_instance(database, definition_id=1, child_id=1)
        _insert_instance(database, definition_id=1, child_id=2)
        row = _run(database.fetch_one("SELECT COUNT(*) FROM quest_instances"))
        assert row == (2,)
    finally:
        _run(database.close())


def test_quest_instances_duplicate_tuple_different_window_allowed(
    tmp_path,
) -> None:
    """D-008 twice-daily case: one definition, one child, one date,
    two windows — two rows."""
    database = _open_db(tmp_path / "task-instances-twice-daily.db")
    try:
        _apply(database)
        _setup_definition(database)
        _insert_instance(database, definition_id=1, window="morning")
        _insert_instance(database, definition_id=1, window="evening")
        rows = _run(
            database.fetch_all(
                "SELECT window FROM quest_instances ORDER BY window"
            )
        )
        assert [row[0] for row in rows] == ["evening", "morning"]
    finally:
        _run(database.close())


def test_quest_instances_unknown_window_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-bad-window.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_instance(database, definition_id=1, window="noon")
    finally:
        _run(database.close())


def test_quest_instances_window_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-window-null.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_instance(database, definition_id=1, window=_OMIT)
    finally:
        _run(database.close())


def test_quest_instances_same_date_different_definitions_allowed(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "task-instances-multi-def.db")
    try:
        _apply(database)
        _setup_definition(database)
        _run(
            database.execute(
                "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
                ("Bo", "2026-09-13T00:00:00+00:00"),
            )
        )
        rule_id = _insert_rule(database)
        _insert_definition(database, rule_id=rule_id, assignees=(2,))
        _insert_instance(database, definition_id=1, due_date="2026-09-14")
        _insert_instance(database, definition_id=2, due_date="2026-09-14")
        row = _run(database.fetch_one("SELECT COUNT(*) FROM quest_instances"))
        assert row == (2,)
    finally:
        _run(database.close())


def test_quest_instances_same_definition_different_dates_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-multi-date.db")
    try:
        _apply(database)
        _setup_definition(database)
        _insert_instance(database, definition_id=1, due_date="2026-09-14")
        _insert_instance(database, definition_id=1, due_date="2026-09-15")
        row = _run(database.fetch_one("SELECT COUNT(*) FROM quest_instances"))
        assert row == (2,)
    finally:
        _run(database.close())


def test_quest_instances_unknown_definition_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-bad-def.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_instance(database, definition_id=999)
    finally:
        _run(database.close())


def test_quest_instances_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-bad-child.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_instance(database, definition_id=1, child_id=999)
    finally:
        _run(database.close())


def test_quest_instances_due_date_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-due-null.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_instance(database, definition_id=1, due_date=None)
    finally:
        _run(database.close())


def test_quest_instances_generated_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "task-instances-generated-null.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_instance(database, definition_id=1, generated_at=None)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# completion_events: constraint enforcement
# ---------------------------------------------------------------------------


def test_completion_events_valid_user_completion_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-valid.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        event_id = _insert_event(
            database, instance_id=instance_id, child_id=1
        )
        row = _run(
            database.fetch_one(
                "SELECT instance_id, child_id, event_type, actor_source, "
                "actor_user_id, occurred_at, was_on_time "
                "FROM completion_events WHERE id = ?",
                (event_id,),
            )
        )
        assert row == (
            instance_id,
            1,
            "completed",
            "user",
            "user-1",
            "2026-09-14T08:30:00+00:00",
            1,
        )
    finally:
        _run(database.close())


def test_completion_events_valid_panel_completion_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-panel.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        event_id = _insert_event(
            database,
            instance_id=instance_id,
            actor_source="panel",
            actor_user_id=None,
            actor_child_id=1,
            was_on_time=0,
        )
        row = _run(
            database.fetch_one(
                "SELECT actor_source, actor_user_id, actor_child_id, "
                "was_on_time FROM completion_events WHERE id = ?",
                (event_id,),
            )
        )
        assert row == ("panel", None, 1, 0)
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    ("actor_source", "actor_user_id", "actor_child_id"),
    [
        ("user", "user-1", 1),  # admin event must not carry a profile
        ("panel", None, None),  # panel event requires the profile
        ("panel", "user-1", 1),  # panel must not carry a user id either
        ("panel", "user-1", None),
        ("user", None, None),
    ],
)
def test_completion_events_actor_child_coherence_enforced(
    tmp_path, actor_source, actor_user_id, actor_child_id
) -> None:
    """D-008 actor-pair shape: 'user' events carry actor_user_id and no
    actor_child_id; 'panel' events carry actor_child_id and no
    actor_user_id.  The CHECKs make both halves non-negotiable."""
    database = _open_db(tmp_path / "completion-events-coherence.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database,
                instance_id=instance_id,
                event_type="completed",
                actor_source=actor_source,
                actor_user_id=actor_user_id,
                actor_child_id=actor_child_id,
                was_on_time=1,
            )
    finally:
        _run(database.close())


def test_completion_events_actor_child_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-bad-actor-child.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_event(
                database,
                instance_id=instance_id,
                actor_source="panel",
                actor_user_id=None,
                actor_child_id=999,
                was_on_time=1,
            )
    finally:
        _run(database.close())


def test_completion_events_valid_uncompleted_round_trips(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-uncompleted.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        event_id = _insert_event(
            database,
            instance_id=instance_id,
            event_type="uncompleted",
            actor_source="user",
            was_on_time=_OMIT,
        )
        row = _run(
            database.fetch_one(
                "SELECT event_type, actor_source, was_on_time "
                "FROM completion_events WHERE id = ?",
                (event_id,),
            )
        )
        assert row == ("uncompleted", "user", None)
    finally:
        _run(database.close())


def test_completion_events_uncompleted_with_on_time_flag_allowed(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "completion-events-uncompleted-ontime.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        event_id = _insert_event(
            database,
            instance_id=instance_id,
            event_type="uncompleted",
            was_on_time=1,
        )
        row = _run(
            database.fetch_one(
                "SELECT was_on_time FROM completion_events WHERE id = ?",
                (event_id,),
            )
        )
        assert row == (1,)
    finally:
        _run(database.close())


def test_completion_events_unknown_instance_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-bad-instance.db")
    try:
        _apply(database)
        _setup_definition(database)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_event(database, instance_id=999)
    finally:
        _run(database.close())


def test_completion_events_unknown_child_fails(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-bad-child.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_event(database, instance_id=instance_id, child_id=999)
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_event_type", ["missed", "COMPLETE", ""])
def test_completion_events_event_type_check_enforced(
    tmp_path, bad_event_type
) -> None:
    database = _open_db(tmp_path / f"completion-events-type-{hash(bad_event_type)}.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database, instance_id=instance_id, event_type=bad_event_type
            )
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_source", ["kiosk", "system", "USER", ""])
def test_completion_events_actor_source_check_enforced(
    tmp_path, bad_source
) -> None:
    database = _open_db(tmp_path / f"completion-events-source-{hash(bad_source)}.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database, instance_id=instance_id, actor_source=bad_source
            )
    finally:
        _run(database.close())


@pytest.mark.parametrize(
    ("actor_source", "actor_user_id"),
    [
        ("user", None),  # user without id
        ("panel", "user-1"),  # panel with id
    ],
)
def test_completion_events_actor_pair_coherence_enforced(
    tmp_path, actor_source, actor_user_id
) -> None:
    database = _open_db(tmp_path / f"completion-events-actor-{actor_source}.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database,
                instance_id=instance_id,
                actor_source=actor_source,
                actor_user_id=actor_user_id,
            )
    finally:
        _run(database.close())


@pytest.mark.parametrize("bad_was_on_time", ["abc", 1.5, 2])
def test_completion_events_was_on_time_non_integer_or_out_of_range_fails(
    tmp_path, bad_was_on_time
) -> None:
    database = _open_db(tmp_path / f"completion-events-ontime-{type(bad_was_on_time).__name__}.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database, instance_id=instance_id, was_on_time=bad_was_on_time
            )
    finally:
        _run(database.close())


def test_completion_events_completed_requires_was_on_time(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-completed-ontime-null.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_event(
                database,
                instance_id=instance_id,
                event_type="completed",
                was_on_time=_OMIT,
            )
    finally:
        _run(database.close())


def test_completion_events_occurred_at_not_null_enforced(tmp_path) -> None:
    database = _open_db(tmp_path / "completion-events-occurred-null.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            _insert_event(
                database, instance_id=instance_id, occurred_at=None
            )
    finally:
        _run(database.close())


def test_completion_events_multiple_events_per_instance_allowed(
    tmp_path,
) -> None:
    database = _open_db(tmp_path / "completion-events-multi.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        _insert_event(
            database, instance_id=instance_id, event_type="completed",
            occurred_at="2026-09-14T08:30:00+00:00",
        )
        _insert_event(
            database, instance_id=instance_id, event_type="uncompleted",
            actor_source="user", was_on_time=1,
            occurred_at="2026-09-14T09:00:00+00:00",
        )
        _insert_event(
            database, instance_id=instance_id, event_type="completed",
            occurred_at="2026-09-14T09:15:00+00:00",
        )
        row = _run(database.fetch_one("SELECT COUNT(*) FROM completion_events"))
        assert row == (3,)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# Idempotence across the full eight-table v1 list
# ---------------------------------------------------------------------------


def test_applying_full_ddl_twice_keeps_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "idempotent-full.db")
    try:
        _apply(database)
        _setup_definition(database)
        instance_id = _insert_instance(database, definition_id=1)
        _insert_event(database, instance_id=instance_id)
        _apply(database)
        counts = []
        for table in (
            "children",
            "schedule_rules",
            "quest_definitions",
            "quest_instances",
            "completion_events",
        ):
            row = _run(database.fetch_one(f"SELECT COUNT(*) FROM {table}"))
            counts.append(row[0])
        assert counts == [1, 1, 1, 1, 1]
    finally:
        _run(database.close())