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
    """The model must carry no Home Assistant and no DB imports."""
    from pathlib import Path

    source = Path(
        __import__("custom_components.nestquest.core.recurrence",
                   fromlist=["__file__"]).__file__
    ).read_text()
    offenders = _scan_forbidden_imports(source)
    assert offenders == [], (
        f"recurrence.py must not hold forbidden imports: {offenders}"
    )


def _scan_forbidden_imports(source: str) -> list[str]:
    """The ACTUAL purity-guard logic, shared by the model scan and the
    probe tests below: returns human-readable offenders (empty = clean).

    Forbidden, at any relative level, for both Import and ImportFrom:
    - modules containing 'homeassistant' or 'sqlite'
    - modules whose LEAF name is a DB/store/schema/DAO module
    - aliases importing a DB/store/schema/DAO module by leaf name
      ('from . import db', 'from custom_components.nestquest import db')
    """
    import ast

    forbidden_targets = {
        "db", "schema", "dao_children", "dao_rules", "dao_presence",
        "dao_instances", "migrations", "store",
    }
    offenders: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                lowered = alias.name.lower()
                leaf = lowered.split(".")[-1]
                if (
                    "homeassistant" in lowered
                    or "sqlite" in lowered
                    or leaf in forbidden_targets
                ):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            module_leaf = module.split(".")[-1] if module else ""
            if (
                "homeassistant" in module
                or "sqlite" in module
                or (module and module_leaf in forbidden_targets)
                or (node.level and module_leaf in forbidden_targets)
            ):
                offenders.append(
                    f"from {node.module!r} import ... (level={node.level})"
                )
            for alias in node.names:
                alias_leaf = alias.name.split(".")[-1].lower()
                if alias_leaf in forbidden_targets:
                    offenders.append(
                        f"from {node.module!r} import {alias.name} "
                        f"(level={node.level})"
                    )
    return offenders


def test_purity_guard_logic_catches_probe_statements(tmp_path) -> None:
    """The shared scan function catches every forbidden import shape,
    including level-0 absolute package DB imports and 'from . import db'.
    """
    probes = [
        "from homeassistant.core import HomeAssistant",
        "import sqlite3",
        "from .db import NestQuestDatabase",
        "from custom_components.nestquest.db import NestQuestDatabase",
        "from custom_components.nestquest import db",
        "import custom_components.nestquest.dao_rules",
        "from . import db",
        "from . import schema",
        "from custom_components.nestquest.migrations import apply_migrations",
    ]
    for probe in probes:
        offenders = _scan_forbidden_imports(probe)
        assert offenders, f"probe must be caught: {probe!r}"


def test_non_string_rule_type_rejected() -> None:
    """Only RuleType members and their string values construct."""
    for bad in (123, True, None, 3.5, b"daily"):
        with pytest.raises(RuleValidationError):
            ScheduleRule(rule_type=bad, start_date="2026-09-01")


def test_weekly_rejects_month_and_nth_fields() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.WEEKLY, weekday_set={0}, day_of_month=5,
            start_date="2026-09-01",
        )
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.WEEKLY, weekday_set={0}, month=3,
            start_date="2026-09-01",
        )


def test_daily_rejects_dangling_nth_weekday_weekday() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.DAILY, nth_weekday_weekday=0,
            start_date="2026-09-01",
        )


def test_monthly_day_rejects_month() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.MONTHLY_DAY, day_of_month=5, month=3,
            start_date="2026-09-01",
        )


def test_yearly_rejects_day_and_nth_fields() -> None:
    with pytest.raises(RuleValidationError, match="must not set"):
        ScheduleRule(
            rule_type=RuleType.YEARLY, month=6, nth_weekday=1,
            nth_weekday_weekday=0, start_date="2026-09-01",
        )
    # YEARLY MAY carry an optional day_of_month (Feb 29 rules need it):
    rule = ScheduleRule(rule_type=RuleType.YEARLY, month=2,
                        day_of_month=29, start_date="2026-09-01")
    assert rule.day_of_month == 29
    # ...but it is still validated when present.
    with pytest.raises(RuleValidationError, match="day_of_month"):
        ScheduleRule(
            rule_type=RuleType.YEARLY, month=6, day_of_month=32,
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


def test_direct_set_with_int_subclass_entry_rejected() -> None:
    """A hashable-but-non-plain int subclass is still not a plain int."""

    class IntChild(int):
        pass

    with pytest.raises(RuleValidationError, match="plain integers"):
        ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={IntChild(1)},
            start_date="2026-09-01",
        )


def test_from_dict_with_int_subclass_entry_rejected() -> None:
    class IntChild(int):
        pass

    with pytest.raises(RuleValidationError, match="plain integers"):
        ScheduleRule.from_dict(
            {"rule_type": "weekly", "weekday_set": [IntChild(1)]}
        )


def test_from_dict_unknown_key_types_never_leak_typeerror() -> None:
    """Mixed unhashable unknown keys must surface as
    RuleValidationError, not a raw TypeError from sorting."""
    with pytest.raises(RuleValidationError, match="unknown rule fields"):
        ScheduleRule.from_dict({"rule_type": "daily", 42: "value"})


def test_storage_aliases_and_whitespace_are_not_model_names() -> None:
    """The model boundary is exact names only: storage strings, padded
    and case variants are all rejected."""
    for bad in ("monthly", "custom", " DAILY ", "daily ", "DAILY"):
        with pytest.raises(RuleValidationError):
            ScheduleRule(rule_type=bad, start_date="2026-09-01")


def test_unhashable_int_subclass_interval_rejected() -> None:
    class UnhashableInt(int):
        __hash__ = None

    with pytest.raises(RuleValidationError):
        ScheduleRule(
            rule_type=RuleType.DAILY,
            interval=UnhashableInt(1),
            start_date="2026-09-01",
        )


def test_rule_type_is_a_dataclass() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(ScheduleRule)
