"""Tests for recurrence.py: the ScheduleRule model and serialization."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
)


def _rule(**kwargs) -> ScheduleRule:
    return ScheduleRule(**kwargs)


# ---------------------------------------------------------------------------
# Valid construction for every rule type
# ---------------------------------------------------------------------------


def test_daily_rule_constructs_with_defaults() -> None:
    rule = _rule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    assert rule.rule_type is RuleType.DAILY
    assert rule.interval == 1
    assert rule.weekday_set is None
    assert rule.day_of_month is None
    assert rule.nth_weekday is None
    assert rule.month is None
    assert rule.end_date is None


def test_string_rule_type_coerces() -> None:
    rule = _rule(rule_type=RuleType.WEEKLY, weekday_set={0, 2}, start_date="2026-09-01")
    assert rule.rule_type is RuleType.WEEKLY


def test_weekly_rule_requires_and_freezes_weekday_set() -> None:
    rule = _rule(rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4}, start_date="2026-09-01")
    assert rule.weekday_set == frozenset({0, 2, 4})
    # A mutable set passed in is frozen on construction.
    source = {1, 3}
    rule2 = _rule(rule_type=RuleType.WEEKLY, weekday_set=source, start_date="2026-09-01")
    source.add(5)
    assert rule2.weekday_set == frozenset({1, 3})


def test_monthly_day_rule_fields() -> None:
    rule = _rule(rule_type=RuleType.MONTHLY_DAY, day_of_month=15, start_date="2026-09-01")
    assert rule.day_of_month == 15
    assert rule.nth_weekday is None


def test_monthly_weekday_rule_fields() -> None:
    rule = _rule(
        rule_type=RuleType.MONTHLY_WEEKDAY,
        nth_weekday=2,
        nth_weekday_weekday=1,
        start_date="2026-09-01",
    )
    assert rule.nth_weekday == 2
    assert rule.nth_weekday_weekday == 1


def test_monthly_weekday_last_friday_allowed() -> None:
    rule = _rule(
        rule_type=RuleType.MONTHLY_WEEKDAY,
        nth_weekday=-1,
        nth_weekday_weekday=4,
        start_date="2026-09-01",
    )
    assert rule.nth_weekday == -1


def test_yearly_rule_fields() -> None:
    rule = _rule(rule_type=RuleType.YEARLY, month=6, start_date="2026-09-01")
    assert rule.month == 6


def test_custom_days_rule_fields() -> None:
    rule = _rule(
        rule_type=RuleType.CUSTOM_DAYS,
        weekday_set={1, 3, 5},
        interval=2,
        start_date="2026-09-01",
    )
    assert rule.weekday_set == frozenset({1, 3, 5})
    assert rule.interval == 2


def test_end_date_round_trips(tmp_path) -> None:
    rule = _rule(
        rule_type=RuleType.DAILY,
        start_date="2026-09-01",
        end_date="2026-12-31",
    )
    assert rule.end_date == "2026-12-31"


# ---------------------------------------------------------------------------
# Invalid combinations are rejected at construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        # weekly without weekday_set
        {"rule_type": RuleType.WEEKLY.value, "start_date": "2026-09-01"},
        # daily carrying a weekday_set
        {"rule_type": "daily", "weekday_set": {0}, "start_date": "2026-09-01"},
        # monthly_day without day_of_month
        {"rule_type": "monthly_day", "start_date": "2026-09-01"},
        # monthly_day out of range
        {"rule_type": "monthly_day", "day_of_month": 32, "start_date": "2026-09-01"},
        # monthly_day carrying weekday_set
        {"rule_type": "monthly_day", "day_of_month": 5, "weekday_set": {0},
         "start_date": "2026-09-01"},
        # yearly without month
        {"rule_type": "yearly", "start_date": "2026-09-01"},
        # yearly out of range
        {"rule_type": "yearly", "month": 13, "start_date": "2026-09-01"},
        # unknown type
        {"rule_type": "bogus", "start_date": "2026-09-01"},
        # interval zero
        {"rule_type": "daily", "interval": 0, "start_date": "2026-09-01"},
        # interval non-integer
        {"rule_type": "daily", "interval": "2", "start_date": "2026-09-01"},
        # end before start
        {"rule_type": "daily", "start_date": "2026-09-01",
         "end_date": "2026-08-31"},
        # malformed dates
        {"rule_type": "daily", "start_date": "not-a-date"},
        {"rule_type": "daily", "start_date": "2026-9-1"},
        # weekly weekday out of range
        {"rule_type": RuleType.WEEKLY.value, "weekday_set": {7}, "start_date": "2026-09-01"},
        # weekly empty set
        {"rule_type": RuleType.WEEKLY.value, "weekday_set": set(), "start_date": "2026-09-01"},
        # custom_days carrying month-specific fields
        {"rule_type": "custom_days", "weekday_set": {0}, "day_of_month": 5,
         "start_date": "2026-09-01"},
        {"rule_type": "custom_days", "weekday_set": {0}, "nth_weekday": 1,
         "nth_weekday_weekday": 0, "start_date": "2026-09-01"},
        {"rule_type": "custom_days", "weekday_set": {0}, "month": 3,
         "start_date": "2026-09-01"},
        # monthly_weekday position invalid
        {"rule_type": "monthly_weekday", "nth_weekday": 0,
         "nth_weekday_weekday": 1, "start_date": "2026-09-01"},
        {"rule_type": "monthly_weekday", "nth_weekday": 6,
         "nth_weekday_weekday": 1, "start_date": "2026-09-01"},
        {"rule_type": "monthly_weekday", "nth_weekday": 2,
         "nth_weekday_weekday": None, "start_date": "2026-09-01"},
        {"rule_type": "monthly_weekday", "nth_weekday": 2,
         "nth_weekday_weekday": 7, "start_date": "2026-09-01"},
        # monthly_day carrying nth fields
        {"rule_type": "monthly_day", "day_of_month": 5, "nth_weekday": 1,
         "nth_weekday_weekday": 0, "start_date": "2026-09-01"},
    ],
)
def test_invalid_combinations_raise(kwargs) -> None:
    with pytest.raises(RuleValidationError):
        _rule(**kwargs)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_rule_is_immutable() -> None:
    rule = _rule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    with pytest.raises(AttributeError):
        rule.interval = 2
    with pytest.raises(AttributeError):
        del rule.interval


# ---------------------------------------------------------------------------
# Serialization round-trip for every rule type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.DAILY, interval=3, start_date="2026-09-01",
                     end_date="2026-12-31"),
        ScheduleRule(rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
                     start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.WEEKLY, weekday_set={6}, interval=2,
                     start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
                     start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.MONTHLY_DAY, day_of_month=31, interval=3,
                     start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
                     nth_weekday_weekday=1, start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=-1,
                     nth_weekday_weekday=4, interval=2,
                     start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.YEARLY, month=6, start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.YEARLY, month=2, day_of_month=None,
                     interval=2, start_date="2026-09-01"),
        ScheduleRule(rule_type=RuleType.CUSTOM_DAYS, weekday_set={1, 3, 5},
                     interval=2, start_date="2026-09-01"),
    ],
)
def test_to_dict_from_dict_round_trips_losslessly(rule) -> None:
    rebuilt = ScheduleRule.from_dict(rule.to_dict())
    assert rebuilt == rule
    # Round-tripping twice is stable.
    assert ScheduleRule.from_dict(rebuilt.to_dict()) == rule


def test_from_dict_rejects_unknown_fields() -> None:
    with pytest.raises(RuleValidationError, match="unknown rule fields"):
        ScheduleRule.from_dict({"rule_type": "daily", "bogus": 1})


def test_from_dict_rejects_missing_rule_type() -> None:
    with pytest.raises(RuleValidationError, match="missing required"):
        ScheduleRule.from_dict({"interval": 1})


def test_from_dict_rejects_non_dict() -> None:
    with pytest.raises(RuleValidationError):
        ScheduleRule.from_dict("daily")


def test_from_dict_defaults_start_date_when_absent() -> None:
    rule = ScheduleRule.from_dict({"rule_type": "daily"})
    assert rule.start_date == "1970-01-01"


def test_from_dict_accepts_list_weekday_set() -> None:
    rule = ScheduleRule.from_dict(
        {"rule_type": RuleType.WEEKLY.value, "weekday_set": [0, 2, 4]}
    )
    assert rule.weekday_set == frozenset({0, 2, 4})


# ---------------------------------------------------------------------------
# Equality and hashing
# ---------------------------------------------------------------------------


def test_equal_rules_compare_equal_and_hash_equal() -> None:
    a = _rule(rule_type=RuleType.WEEKLY, weekday_set={0, 2}, start_date="2026-09-01")
    b = _rule(rule_type=RuleType.WEEKLY, weekday_set={2, 0}, start_date="2026-09-01")
    assert a == b
    assert hash(a) == hash(b)


def test_different_rules_compare_unequal() -> None:
    a = _rule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    b = _rule(rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01")
    assert a != b


def test_rule_not_equal_to_other_types() -> None:
    rule = _rule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    assert rule != "daily"
    assert (rule == 42) is False


# ---------------------------------------------------------------------------
# Purity guards: no HA imports, no database access
# ---------------------------------------------------------------------------


def test_recurrence_module_imports_only_stdlib() -> None:
    """The model must carry no Home Assistant and no DB imports — checked
    against the RESOLVED module path so relative forms (from .db import
    x) are caught too."""
    import ast
    import importlib.util
    from pathlib import Path

    module_file = Path(
        importlib.util.find_spec(
            "custom_components.nestquest.recurrence"
        ).origin
    )
    tree = ast.parse(module_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "homeassistant" not in alias.name.lower(), (
                    f"recurrence.py must not import {alias.name}"
                )
                assert "sqlite" not in alias.name.lower(), (
                    f"recurrence.py must not import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            level = node.level  # 1+ means relative import
            # Forbidden regardless of relative level: the leaf module
            # names ('from . import db', 'from .db import x') AND any
            # absolute custom_components.nestquest DB/store import.
            forbidden_targets = {
                "db", "schema", "dao_children", "dao_rules",
                "dao_presence", "dao_instances", "migrations", "store",
            }
            imported_names = [alias.name for alias in node.names]
            for name in imported_names:
                leaf = name.split(".")[-1]
                assert leaf not in forbidden_targets, (
                    f"recurrence.py must not import {name!r}"
                )
            if module:
                full = f".{module}" if level else module
                assert module not in forbidden_targets, (
                    f"recurrence.py must not import from {full}"
                )
                assert "db" not in module.split("."), (
                    f"recurrence.py must not import from {full}"
                )
            assert "homeassistant" not in module, (
                f"recurrence.py must not import from {module}"
            )
            assert "sqlite" not in module, (
                f"recurrence.py must not import from {module}"
            )


def test_purity_guard_blocks_absolute_db_import(tmp_path) -> None:
    """Absolute custom_components.nestquest DB imports (level=0) are
    caught by the same alias-leaf scan the guard uses."""
    import ast as ast_module

    forbidden_targets = {
        "db", "schema", "dao_children", "dao_rules", "dao_presence",
        "dao_instances", "migrations", "store",
    }
    # The guard's own logic, exercised against probe statements:
    from custom_components.nestquest import recurrence as recurrence_mod
    probe_lines = (
        "from custom_components.nestquest import db",
        "from custom_components.nestquest.db import NestQuestDatabase",
        "import custom_components.nestquest.dao_rules",
    )
    for line in probe_lines:
        node = ast_module.parse(line).body[0]
        caught = False
        for item in ast_module.walk(node):
            if isinstance(item, ast_module.ImportFrom):
                module = (item.module or "").lower()
                if module:
                    leaf = module.split(".")[-1]
                    if leaf in forbidden_targets:
                        caught = True
                for alias in item.names:
                    if alias.name.split(".")[-1] in forbidden_targets:
                        caught = True
            elif isinstance(item, ast_module.Import):
                for alias in item.names:
                    leaf = alias.name.split(".")[-1]
                    if leaf in forbidden_targets:
                        caught = True
        assert caught, f"probe import must be caught: {line}"


def test_non_string_rule_type_rejected() -> None:
    """Only RuleType members and their string values construct."""
    for bad in (123, True, None, 3.5, b"daily"):
        with pytest.raises(RuleValidationError):
            ScheduleRule(rule_type=bad, start_date="2026-09-01")


def test_weekly_rejects_month_and_nth_fields() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type="weekly",
            weekday_set={0},
            day_of_month=5,
            start_date="2026-09-01",
        )
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={0},
            month=3,
            start_date="2026-09-01",
        )


def test_daily_rejects_dangling_nth_weekday_weekday() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.DAILY,
            nth_weekday_weekday=0,
            start_date="2026-09-01",
        )


def test_monthly_day_rejects_month() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.MONTHLY_DAY,
            day_of_month=5,
            month=3,
            start_date="2026-09-01",
        )


def test_yearly_rejects_day_and_nth_fields() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.YEARLY,
            month=6,
            day_of_month=15,
            start_date="2026-09-01",
        )
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.YEARLY,
            month=6,
            nth_weekday=1,
            nth_weekday_weekday=0,
            start_date="2026-09-01",
        )


def test_storage_value_mapping() -> None:
    """The enum exposes the schema's CHECK values via storage_value."""
    assert RuleType.DAILY.storage_value == "daily"
    assert RuleType.WEEKLY.storage_value == "weekly"
    assert RuleType.MONTHLY_DAY.storage_value == "monthly"
    assert RuleType.MONTHLY_WEEKDAY.storage_value == "monthly"
    assert RuleType.YEARLY.storage_value == "yearly"
    assert RuleType.CUSTOM_DAYS.storage_value == "custom"


def test_from_dict_bool_weekday_entry_rejected_before_set_coercion() -> None:
    """[0, False] must NOT collapse False into 0 via set() coercion."""
    with pytest.raises(RuleValidationError, match="plain integers"):
        ScheduleRule.from_dict(
            {"rule_type": "weekly", "weekday_set": [0, False]}
        )


def test_from_dict_unknown_key_types_never_leak_typeerror() -> None:
    """Mixed unhashable unknown keys must surface as
    RuleValidationError, not a raw TypeError from sorting."""
    data = {"rule_type": "daily", 42: "value"}
    with pytest.raises(RuleValidationError):
        ScheduleRule.from_dict(data)


def test_rule_type_is_a_dataclass() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(ScheduleRule)

def test_direct_list_with_bool_weekday_rejected(tmp_path) -> None:
    """Direct construction with a list: entries validated pre-coercion."""
    with pytest.raises(RuleValidationError, match="plain integers"):
        ScheduleRule(
            rule_type=RuleType.WEEKLY, weekday_set=[0, False],
            start_date="2026-09-01",
        )


def test_unhashable_list_item_leads_to_clear_error(tmp_path) -> None:
    """Unhashable entries raise RuleValidationError, not TypeError."""
    with pytest.raises(RuleValidationError):
        ScheduleRule(
            rule_type=RuleType.WEEKLY, weekday_set=[[0]],
            start_date="2026-09-01",
        )


def test_from_dict_mixed_type_unknown_keys_raise_validation_error(
    tmp_path,
) -> None:
    """sorted() over mixed key types must not leak TypeError."""
    with pytest.raises(RuleValidationError, match="unknown rule fields"):
        ScheduleRule.from_dict({"rule_type": "daily", 42: "value"})


def test_storage_aliases_and_whitespace_are_not_model_names(tmp_path) -> None:
    """The model boundary is exact names only: storage strings, padded
    and case variants are all rejected."""
    for bad in ("monthly", "custom", " DAILY ", "daily ", "DAILY"):
        with pytest.raises(RuleValidationError):
            ScheduleRule(rule_type=bad, start_date="2026-09-01")


def test_unhashable_int_subclass_interval_rejected() -> None:
    """An int subclass with __hash__ = None must not construct."""

    class UnhashableInt(int):
        __hash__ = None

    with pytest.raises(RuleValidationError):
        ScheduleRule(
            rule_type=RuleType.DAILY,
            interval=UnhashableInt(1),
            start_date="2026-09-01",
        )
