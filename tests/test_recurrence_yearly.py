"""Tests for YEARLY recurrence with the leap-day clamp policy."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.core.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
    occurs_on,
    occurrences_between,
)


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


# ---------------------------------------------------------------------------
# Nominal-day firings across four consecutive years (incl. leap 2028)
# ---------------------------------------------------------------------------


def test_yearly_june_15_four_consecutive_years() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15,
        start_date="2026-06-15",
    )
    for year in (2026, 2027, 2028, 2029):
        assert occurs_on(rule, datetime.date(year, 6, 15)) is True, year
    assert occurs_on(rule, datetime.date(2026, 6, 14)) is False
    assert occurs_on(rule, datetime.date(2026, 6, 16)) is False
    assert occurs_on(rule, datetime.date(2026, 5, 15)) is False
    assert occurs_on(rule, datetime.date(2026, 7, 15)) is False


def test_yearly_feb_15_across_four_years() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=15,
        start_date="2026-02-15",
    )
    # Feb 15 exists every year; the leap day is irrelevant.
    for year in (2026, 2027, 2028, 2029):
        assert occurs_on(rule, datetime.date(year, 2, 15)) is True, year


def test_yearly_never_fires_before_start() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15,
        start_date="2027-06-15",
    )
    assert occurs_on(rule, datetime.date(2026, 6, 15)) is False
    assert occurs_on(rule, datetime.date(2027, 6, 15)) is True


def test_yearly_respects_end_date() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15,
        start_date="2026-06-15", end_date="2028-06-15",
    )
    assert occurs_on(rule, datetime.date(2028, 6, 15)) is True
    assert occurs_on(rule, datetime.date(2029, 6, 15)) is False


# ---------------------------------------------------------------------------
# Leap-day policy: Feb 29 rule fires Feb 28 in non-leap years
# ---------------------------------------------------------------------------


def test_yearly_feb_29_clamps_to_feb_28_non_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    # 2026 non-leap: no Feb 29 — the clamp fires Feb 28.
    assert occurs_on(rule, datetime.date(2026, 2, 28)) is True
    assert occurs_on(rule, datetime.date(2026, 2, 27)) is False
    # 2027 non-leap: same clamp.
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is True


def test_yearly_feb_29_fires_feb_29_in_leap_years() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    # 2028 leap: Feb 29 exists — nominal day.
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True
    assert occurs_on(rule, datetime.date(2028, 2, 28)) is False


def test_yearly_feb_29_four_consecutive_years() -> None:
    """The done-condition's four-year sweep: 2026 (clamp 28), 2027
    (clamp 28), 2028 (leap: nominal 29), 2029 (clamp 28)."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    assert occurs_on(rule, datetime.date(2026, 2, 28)) is True
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is True
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True
    assert occurs_on(rule, datetime.date(2029, 2, 28)) is True
    # No other day in those Februaries fires.
    for year, non_firing in (
        (2026, (27,)), (2027, (26, 27)), (2028, (27,)),
        (2029, (26, 27)),
    ):
        for day in non_firing:
            assert occurs_on(rule, datetime.date(year, 2, day)) is False


def test_yearly_feb_30_is_impossible_by_model() -> None:
    """The model rejects day_of_month 30+ for February? No — 30/31 are
    accepted (1..31) and clamp to the month end like MONTHLY_DAY."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=30,
        start_date="2027-02-28",
    )
    # Non-leap 2027: Feb 28 is the month end — the clamp fires it.
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is True
    # Leap 2028: Feb 29 is the month end — clamps there.
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True
    assert occurs_on(rule, datetime.date(2028, 2, 28)) is False


# ---------------------------------------------------------------------------
# Day-less YEARLY rules fire on the first of the month
# ---------------------------------------------------------------------------


def test_yearly_without_day_fires_on_first_of_month() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, start_date="2026-01-01",
    )
    assert occurs_on(rule, datetime.date(2026, 6, 1)) is True
    assert occurs_on(rule, datetime.date(2026, 6, 2)) is False
    assert occurs_on(rule, datetime.date(2026, 5, 1)) is False
    assert occurs_on(rule, datetime.date(2027, 6, 1)) is True


# ---------------------------------------------------------------------------
# Interval: every N years
# ---------------------------------------------------------------------------


def test_yearly_interval_2_every_second_year() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15, interval=2,
        start_date="2026-06-15",
    )
    assert occurs_on(rule, datetime.date(2026, 6, 15)) is True   # y0
    assert occurs_on(rule, datetime.date(2027, 6, 15)) is False  # y1
    assert occurs_on(rule, datetime.date(2028, 6, 15)) is True   # y2
    assert occurs_on(rule, datetime.date(2029, 6, 15)) is False  # y3
    assert occurs_on(rule, datetime.date(2030, 6, 15)) is True   # y4


def test_yearly_interval_2_leap_day_every_second_year() -> None:
    """A Feb 29 rule at interval 2 anchored 2026 fires in even years:
    2026 clamps (Feb 28), 2027 skips, 2028 hits the nominal Feb 29."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29, interval=2,
        start_date="2026-02-28",
    )
    assert occurs_on(rule, datetime.date(2026, 2, 28)) is True   # y0 clamp
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is False  # y1
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True   # y2 nominal
    assert occurs_on(rule, datetime.date(2029, 2, 28)) is False  # y3
    assert occurs_on(rule, datetime.date(2030, 2, 28)) is True   # y4 clamp


def test_yearly_interval_3_across_start_year() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=3, day_of_month=10, interval=3,
        start_date="2026-03-10",
    )
    assert occurs_on(rule, datetime.date(2026, 3, 10)) is True
    assert occurs_on(rule, datetime.date(2027, 3, 10)) is False
    assert occurs_on(rule, datetime.date(2028, 3, 10)) is False
    assert occurs_on(rule, datetime.date(2029, 3, 10)) is True


# ---------------------------------------------------------------------------
# occurrences_between
# ---------------------------------------------------------------------------


def test_yearly_occurrences_between_span() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    result = occurrences_between(rule, "2026-01-01", "2029-12-31")
    assert result == [
        "2026-02-28", "2027-02-28", "2028-02-29", "2029-02-28",
    ]


def test_yearly_occurrences_between_disjoint_range() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=15,
        start_date="2026-06-15",
    )
    # The rule only ever fires in June: other months are empty.
    assert occurrences_between(rule, "2027-01-01", "2027-05-31") == []
    assert occurrences_between(rule, "2027-07-01", "2027-12-31") == []


def test_yearly_occurrences_between_rejects_inverted() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=2, day_of_month=29,
        start_date="2026-02-28",
    )
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2029-01-01", "2026-01-01")


# ---------------------------------------------------------------------------
# Day of month 31 in a 30-day month: clamp consistency with MONTHLY_DAY
# ---------------------------------------------------------------------------


def test_yearly_june_31_clamps_to_june_30() -> None:
    """June has 30 days: a June 31st yearly rule clamps to June 30."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6, day_of_month=31,
        start_date="2026-06-30",
    )
    assert occurs_on(rule, datetime.date(2026, 6, 30)) is True
    assert occurs_on(rule, datetime.date(2027, 6, 30)) is True
    assert occurs_on(rule, datetime.date(2026, 6, 29)) is False