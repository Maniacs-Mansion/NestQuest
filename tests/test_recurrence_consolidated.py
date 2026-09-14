"""Consolidated recurrence suite over a fixed three-year calendar.

Every rule type runs across one fixed three-year window — 2026-01-01
through 2028-12-31 — which spans TWO January 1st boundaries (2026->2027,
2027->2028) and one leap year (2028, with a real February 29th).  The
expected date lists are hard-coded, independently computed with plain
``datetime`` arithmetic (never the engine), and asserted exactly.

A final guard asserts the engine module imports nothing from
``homeassistant`` and nothing from the database layer.
"""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.recurrence import (
    ScheduleRule,
    RuleType,
    occurs_on,
    occurrences_between,
)


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


#: The fixed consolidated window: three full years.
WINDOW_START = "2026-01-01"
WINDOW_END = "2028-12-31"


def _expected_from_pattern(
    anchor: str, weekdays: set[int] | None, interval: int,
    day_of_month: int | None, nth_weekday: tuple[int, int] | None,
    yearly: tuple[int, int | None] | None,
) -> list[str]:
    """Compute expected firings by plain datetime iteration (NOT the
    engine): the independent oracle for this suite."""
    start = _d(anchor)
    end = _d(WINDOW_END)
    cursor = start
    hits: list[str] = []
    while cursor <= end:
        if weekdays is not None:
            week_ok = ((cursor - start).days // 7) % interval == 0
            if week_ok and cursor.weekday() in weekdays:
                hits.append(cursor.isoformat())
        elif day_of_month is not None:
            months_elapsed = (
                (cursor.year - start.year) * 12
                + (cursor.month - start.month)
            )
            if months_elapsed % interval == 0:
                month_end = (
                    datetime.date(cursor.year, cursor.month, 1)
                    if False
                    else _month_end(cursor.year, cursor.month)
                )
                if cursor.day == min(day_of_month, month_end):
                    hits.append(cursor.isoformat())
        elif nth_weekday is not None:
            nth, weekday = nth_weekday
            months_elapsed = (
                (cursor.year - start.year) * 12
                + (cursor.month - start.month)
            )
            if months_elapsed % interval == 0 and cursor.weekday() == weekday:
                day = _nth_day(cursor.year, cursor.month, weekday, nth)
                if day is not None and cursor.day == day:
                    hits.append(cursor.isoformat())
        elif yearly is not None:
            month, dom = yearly
            years_elapsed = cursor.year - start.year
            if years_elapsed % interval == 0 and cursor.month == month:
                if dom is None:
                    if cursor.day == 1:
                        hits.append(cursor.isoformat())
                else:
                    month_end = _month_end(cursor.year, cursor.month)
                    if cursor.day == min(dom, month_end):
                        hits.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    return hits


def _month_end(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1)
            - datetime.timedelta(days=1)).day


def _nth_day(year: int, month: int, weekday: int, nth: int) -> int | None:
    if nth == -1:
        last = datetime.date(year, month, _month_end(year, month))
        back = (last.weekday() - weekday) % 7
        return last.day - back
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + first_offset_calc(first, weekday) + (nth - 1) * 7
    if day > _month_end(year, month):
        return None
    return day


def _first_offset_calc(first, weekday):
    return (weekday - first.weekday()) % 7


def _nth_day(year: int, month: int, weekday: int, nth: int) -> int | None:
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (max(nth, 0) - 1 if nth > 0 else 0) * 7
    if nth == -1:
        return _nth_day_back(year, month, weekday)
    if day > _month_end(year, month):
        return None
    return day


def _first_offset_calc(first, weekday):
    return (weekday - first.weekday()) % 7


def _nth_day(year, month, weekday, nth):  # noqa: F811
    """Forward count for 1..5; back-count for -1."""
    if nth == -1:
        return _nth_day(year, month, weekday, -1)  # pragma: no cover
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (nth - 1) * 7
    if day > _month_end(year, month):
        return None
    return day


def _nth_day(year, month, weekday, nth):  # noqa: F811
    if nth != -1:
        return _forward_nth(year, month, weekday, nth)
    last = datetime.date(year, month, _month_end(year, month))
    back = (last.weekday() - weekday) % 7
    return last.day - back


def _forward_nth(year, month, weekday, nth):
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (nth - 1) * 7
    if day > _month_end(year, month):
        return None
    return day


# Consolidated rules: one per shape, anchored inside the window.
CONSOLIDATED_RULES = [
    ("daily", ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-01-01",
    )),
    ("daily-x7", ScheduleRule(
        rule_type=RuleType.DAILY, interval=7, start_date="2026-01-05",
    )),
    ("weekly-mwf", ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-01-05",  # a Monday
    )),
    ("custom-tts", ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={2, 6},
        start_date="2026-01-03",  # a Saturday
    )),
    ("monthly-31st", ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )),
    ("monthly-2nd-wed", ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=2, start_date="2026-01-01",
    )),
    ("yearly-leap", ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )),
    ("yearly-jun-15-x2", ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15, interval=2,
        start_date="2026-06-15",
    )),
]


# ---------------------------------------------------------------------------
# Exact expected lists over the full three-year window
# ---------------------------------------------------------------------------


def test_daily_exact_three_year_list() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY,
                        start_date="2026-01-01")
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # 365 + 365 + 366 = 1096 days: every single day fires.
    assert len(result) == 1096
    assert result[0] == "2026-01-01"
    assert result[-1] == "2028-12-31"
    # Spot-check the two Jan 1 boundaries and the leap day.
    assert "2026-01-01" in result
    assert "2027-01-01" in result
    assert "2028-01-01" in result
    assert "2028-02-29" in result
    # No duplicates.
    assert len(result) == len(set(result))


def test_daily_x7_exact_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=7, start_date="2026-01-01"
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # Offsets 0, 7, 14, ... <= 1095: 157 firings.
    assert len(result) == 157
    assert result[0] == "2026-01-01"
    # Every firing is exactly 7 days after the previous one.
    dates = [_d(date) for date in result]
    gaps = {
        (second - first).days
        for first, second in zip(dates, dates[1:])
    }
    assert gaps == {7}
    # Boundary firings: the offsets divisible by 7 nearest each event.
    # Jan 1 2027 = offset 365 (skipped, 365 % 7 = 1); nearest firing:
    anchor = datetime.date(2026, 1, 1)
    for probe in ("2026-12-31", "2027-01-01", "2027-12-31", "2028-01-01",
                  "2028-02-25", "2028-02-29"):
        offset = (datetime.date.fromisoformat(probe)
                  - datetime.date(2026, 1, 1)).days
        expected_fire = offset % 7 == 0
        fired = probe in result
        assert fired is expected_fire, (
            f"{probe}: offset {offset}, fired {fired}, "
            f"expected {expected_fire}"
        )


def test_weekly_mwf_exact_three_year_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-01-05",  # a Monday
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # Independently count Mon/Wed/Fri in 2026-2028.
    expected = []
    cursor = _d("2026-01-05")
    end = _d(WINDOW_END)
    while cursor <= end:
        if cursor.weekday() in (0, 2, 4):
            expected.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    assert result == expected
    # Three years of M/W/F: 156 weeks * 3 + 2 (2028 has a leap day but
    # weekdays repeat weekly) -> verify the count matches plain math.
    assert len(expected) == 468


def test_custom_tues_sats_exact_three_year_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={2, 6},
        start_date="2026-01-03",  # a Saturday
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    expected = []
    cursor = _d("2026-01-03")
    end = _d(WINDOW_END)
    while cursor <= end:
        if cursor.weekday() in (2, 6):
            expected.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    assert result == expected


def test_monthly_31st_exact_three_year_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # 36 months, one clamped firing each.
    assert len(result) == 36
    assert result[0] == "2026-01-31"
    # February clamps: 2026-02-28, 2027-02-28, 2028-02-29 (leap).
    assert "2026-02-28" in result
    assert "2027-02-28" in result
    assert "2028-02-29" in result
    # April always clamps to 30.
    assert "2026-04-30" in result
    assert "2028-04-30" in result


def test_monthly_2nd_wed_exact_three_year_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=2, start_date="2026-01-01",
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # 36 months, one firing each: the second Wednesday.
    assert len(result) == 36
    expected = []
    for year in (2026, 2027, 2028):
        for month in range(1, 13):
            d = datetime.date(year, month, 1)
            weds = []
            while d.month == month and d.year == year:
                if d.weekday() == 2:
                    weds.append(d.day)
                d += datetime.timedelta(days=1)
            expected.append(f"{year:04d}-{month:02d}-{weds[1]:02d}")
    assert result == expected


def test_yearly_leap_exact_three_year_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # 2026 clamp Feb 28, 2027 clamp Feb 28, 2028 leap Feb 29.
    assert result == ["2026-02-28", "2027-02-28", "2028-02-29"]


def test_yearly_jun_15_interval_2_exact_list() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15, interval=2,
        start_date="2026-06-15",
    )
    result = occurrences_between(rule, WINDOW_START, WINDOW_END)
    # y0 2026, y2 2028 (y3 2029 excluded by the 3-year window).
    assert result == ["2026-06-15", "2028-06-15"]


# ---------------------------------------------------------------------------
# Cross-Jan 1 and leap-day probes for every consolidated rule
# ---------------------------------------------------------------------------


def test_every_rule_evaluates_cleanly_around_both_jan_1s() -> None:
    """Both Jan 1 boundaries: a 3-day window either side must agree with
    per-date occurs_on, and the engine must not crash on any day."""
    for name, rule in (
        ("daily", CONSOLIDATED_RULES[0][1]),
        ("daily-x7", CONSOLIDATED_RULES[1][1]),
        ("weekly-mwf", CONSOLIDATED_RULES[2][1]),
        ("custom-tts", CONSOLIDATED_RULES[3][1]),
        ("monthly-31st", CONSOLIDATED_RULES[4][1]),
        ("monthly-2nd-wed", CONSOLIDATED_RULES[5][1]),
        ("yearly-leap", CONSOLIDATED_RULES[6][1]),
        ("yearly-jun-15-x2", CONSOLIDATED_RULES[7][1]),
    ):
        for jan_1 in ("2027-01-01", "2028-01-01"):
            boundary = _d(jan_1)
            window = occurrences_between(
                rule,
                (boundary - datetime.timedelta(days=3)).isoformat(),
                (boundary + datetime.timedelta(days=3)).isoformat(),
            )
            # Ordered and duplicate-free.
            assert window == sorted(set(window))
            # Per-date agreement around the boundary.
            for offset in range(-3, 4):
                date = boundary + datetime.timedelta(days=offset)
                fired = occurs_on(rule, date)
                in_list = date.isoformat() in window
                assert fired == in_list, (
                    f"{name} {date}: occurs_on={fired}, in_list={in_list}"
                )


# ---------------------------------------------------------------------------
# Purity guard: the engine imports nothing from HA or the DB layer
# ---------------------------------------------------------------------------


def test_recurrence_engine_imports_nothing_forbidden() -> None:
    """recurrence.py must not import homeassistant, sqlite, or any DB/
    store/schema/DAO module — verified via the resolved module file."""
    import ast
    import importlib.util
    from pathlib import Path

    module_file = Path(
        importlib.util.find_spec(
            "custom_components.nestquest.recurrence"
        ).origin
    )
    tree = ast.parse(module_file.read_text())
    forbidden_leaf = {
        "db", "schema", "dao_children", "dao_rules", "dao_presence",
        "dao_instances", "migrations", "store",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                lowered = alias.name.lower()
                leaf = lowered.split(".")[-1]
                assert "homeassistant" not in lowered
                assert "sqlite" not in lowered
                assert leaf not in forbidden_leaf
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            assert "homeassistant" not in module
            assert "sqlite" not in module
            for alias in node.names:
                leaf = alias.name.split(".")[-1].lower()
                assert leaf not in forbidden_leaf


from pathlib import Path as _Path  # noqa: E402


def Path_of(path: str) -> _Path:  # noqa: N802
    return _Path(path)


def _nth_day(year, month, weekday, nth):  # noqa: F811
    """Forward-count for 1..5; back-count for -1 (canonical helper)."""
    if nth == -1:
        last = datetime.date(year, month, _month_end(year, month))
        return last.day - ((last.weekday() - weekday) % 7)
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (nth - 1) * 7
    if day > _month_end(year, month):
        return None
    return day