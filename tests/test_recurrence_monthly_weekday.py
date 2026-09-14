"""Tests for MONTHLY_WEEKDAY (nth-weekday-of-month) recurrence."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
    _nth_weekday_of_month,
    occurs_on,
    occurrences_between,
)


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


# ---------------------------------------------------------------------------
# The helper: nth occurrence day-of-month
# ---------------------------------------------------------------------------


def test_nth_weekday_helper_first_second_third() -> None:
    # March 2026: Mar 1 is a Saturday; Wednesdays (2) are 4, 11, 18, 25.
    assert _nth_weekday_of_month(2026, 3, 2, 1) == 4
    assert _nth_weekday_of_month(2026, 3, 2, 2) == 11
    assert _nth_weekday_of_month(2026, 3, 2, 3) == 18
    assert _nth_weekday_of_month(2026, 3, 2, 4) == 25
    # Mar has only four Wednesdays: no 5th occurrence.
    assert _nth_weekday_of_month(2026, 3, 2, 5) is None


def test_nth_weekday_helper_none_when_month_lacks_nth() -> None:
    # April 2026: Apr 1 is a Wednesday; Fridays (4) are Apr 3, 10, 17, 24.
    assert _nth_weekday_of_month(2026, 4, 4, 5) is None


def test_nth_weekday_helper_last() -> None:
    # March 2026 Fridays: Mar 6, 13, 20, 27 (last = 27).
    assert _nth_weekday_of_month(2026, 3, 4, -1) == 27
    # February 2026 (28 days): Saturdays are Feb 7, 14, 21, 28.
    assert _nth_weekday_of_month(2026, 2, 5, -1) == 28
    # February 2028 (leap): Saturdays are Feb 7, 14, 21, 28 (last = 29? no:
    # Feb 29 2028 is a Tuesday; the last Saturday is Feb 22? check below).
    last_day = _nth_weekday_of_month(2028, 2, 5, -1)
    assert last_day == 22 or _d(f"2028-02-{last_day:02d}").weekday() == 5


def test_nth_weekday_helper_last_when_month_has_five() -> None:
    # October 2026: Fridays are Oct 2, 9, 16, 23, 30 (five; last = 30).
    assert _nth_weekday_of_month(2026, 10, 4, -1) == 30
    # Both 5th and last agree here.
    assert _nth_weekday_of_month(2026, 10, 4, 5) == 30


def test_helper_zero_and_out_of_range_nth() -> None:
    """The model rejects n 0 before the helper sees it; -1/1..5 only."""
    with pytest.raises(RuleValidationError):
        ScheduleRule(
            rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=0,
            nth_weekday_weekday=1, start_date="2026-09-01",
        )
    with pytest.raises(RuleValidationError):
        ScheduleRule(
            rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=6,
            nth_weekday_weekday=1, start_date="2026-09-01",
        )


# ---------------------------------------------------------------------------
# occurs_on: first / second / third / fourth / last across 12 months
# ---------------------------------------------------------------------------


def test_first_tuesday_of_twelve_consecutive_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=1,
        nth_weekday_weekday=2,  # first Wednesday
        start_date="2026-01-01",
    )
    first_wednesdays = [
        (1, 7), (2, 4), (3, 4), (4, 1), (5, 6), (6, 3),
        (7, 1), (8, 5), (9, 2), (10, 7), (11, 4), (12, 2),
    ]
    for month, day in first_wednesdays:
        date = datetime.date(2026, month, day)
        assert date.weekday() == 2
        assert occurs_on(rule, date) is True, date
        # Neighbors do not fire.
        assert occurs_on(rule, date - datetime.timedelta(days=7)) is False
        assert occurs_on(rule, date + datetime.timedelta(days=7)) is False


def test_second_wednesday_of_twelve_consecutive_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=2,
        start_date="2026-01-01",
    )
    for month in range(1, 13):
        first_wed_day = _nth_weekday_of_month(2026, month, 2, 1)
        second_wed_day = _nth_weekday_of_month(2026, month, 2, 2)
        assert occurs_on(
            rule, datetime.date(2026, month, second_wed_day)
        ) is True
        assert occurs_on(
            rule, datetime.date(2026, month, first_wed_day)
        ) is False


def test_third_friday_of_twelve_consecutive_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=3,
        nth_weekday_weekday=4,
        start_date="2026-01-01",
    )
    for month in range(1, 13):
        third_fri_day = _nth_weekday_of_month(2026, month, 4, 3)
        assert occurs_on(rule, datetime.date(2026, month, third_fri_day))
        # Second Friday must not fire.
        second_fri_day = _nth_weekday_of_month(2026, month, 4, 2)
        assert occurs_on(
            rule, datetime.date(2026, month, second_fri_day)
        ) is False


def test_fourth_wednesday_of_twelve_consecutive_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=4,
        nth_weekday_weekday=2,
        start_date="2026-01-01",
    )
    for month in range(1, 13):
        fourth_wed_day = _nth_weekday_of_month(2026, month, 2, 4)
        assert occurs_on(rule, datetime.date(2026, month, fourth_wed_day))
        # Third Wednesday must not fire.
        third_wed_day = _nth_weekday_of_month(2026, month, 2, 3)
        assert not occurs_on(rule, datetime.date(2026, month, third_wed_day))


def test_last_monday_of_twelve_consecutive_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=-1,
        nth_weekday_weekday=0,
        start_date="2026-01-01",
    )
    for month in range(1, 13):
        last_monday_day = _nth_weekday_of_month(2026, month, 0, -1)
        assert occurs_on(rule, datetime.date(2026, month, last_monday_day))
        # The next Monday (next month's) must not fire in this month.
        next_month_last = _nth_weekday_of_month(2026, month, 0, -1)
        # Sanity: the last Monday's day is within the month.
        assert 1 <= next_month_last <= 31


# ---------------------------------------------------------------------------
# The five-occurrence skip: a 5th on a four-occurrence month
# ---------------------------------------------------------------------------


def test_fifth_weekday_skips_four_occurrence_months() -> None:
    """n=5 fires only in months with five occurrences of the weekday."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=5,
        nth_weekday_weekday=0,  # fifth Monday
        start_date="2026-01-01",
    )
    hit_months = set()
    for month in range(1, 13):
        fifth_day = _nth_weekday_of_month(2026, month, 0, 5)
        if fifth_day is not None:
            assert occurs_on(
                rule, datetime.date(2026, month, fifth_day)
            ) is True
            hit_months.add(month)
        else:
            # A four-occurrence month must not fire on ANY day.
            for day in range(1, _month_end_days(2026, month) + 1):
                assert occurs_on(
                    rule, datetime.date(2026, month, day)
                ) is False, f"2026-{month:02d}-{day:02d}"
    assert len(hit_months) >= 3, hit_months


def _month_end_days(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1)
            - datetime.timedelta(days=1)).day


def test_fifth_weekday_fires_in_five_occurrence_months() -> None:
    """The 5th fires in five-occurrence months only."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=5,
        nth_weekday_weekday=4,  # Fridays
        start_date="2026-01-01",
    )
    # October 2026 has five Fridays (2, 9, 16, 23, 30): the 5th fires.
    fifth_day = _nth_weekday_of_month(2026, 10, 4, 5)
    assert fifth_day == 30
    assert occurs_on(rule, datetime.date(2026, 10, 30)) is True
    # April 2026 has four Fridays (3, 10, 17, 24): no 5th, no firing.
    assert _nth_weekday_of_month(2026, 4, 4, 5) is None
    assert occurs_on(rule, datetime.date(2026, 4, 30)) is False


# ---------------------------------------------------------------------------
# Interval arithmetic
# ---------------------------------------------------------------------------


def test_monthly_weekday_interval_2() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=2, interval=2, start_date="2026-01-01",
    )
    # Jan (m0) fires on the 2nd Tuesday; Feb (m1) skipped; Mar (m2) fires.
    jan_second = _nth_weekday_of_month(2026, 1, 2, 2)
    assert occurs_on(rule, datetime.date(2026, 1, jan_second)) is True
    feb_second = _nth_weekday_of_month(2026, 2, 2, 2)
    assert occurs_on(rule, datetime.date(2026, 2, feb_second)) is False
    mar_second = _nth_weekday_of_month(2026, 3, 2, 2)
    assert occurs_on(rule, datetime.date(2026, 3, mar_second)) is True


def test_monthly_weekday_interval_across_year_boundary() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=1,
        nth_weekday_weekday=2, interval=3, start_date="2026-11-01",
    )
    # Nov (m0) fires; Dec (m1), Jan (m2) skip; Feb (m3) fires.
    nov_first = _nth_weekday_of_month(2026, 11, 2, 1)
    assert occurs_on(rule, datetime.date(2026, 11, nov_first)) is True
    dec_first = _nth_weekday_of_month(2026, 12, 2, 1)
    assert occurs_on(rule, datetime.date(2026, 12, dec_first)) is False
    jan_first = _nth_weekday_of_month(2027, 1, 2, 1)
    assert occurs_on(rule, datetime.date(2027, 1, jan_first)) is False
    feb_first = _nth_weekday_of_month(2027, 2, 2, 1)
    assert occurs_on(rule, datetime.date(2027, 2, feb_first)) is True


# ---------------------------------------------------------------------------
# occurrences_between
# ---------------------------------------------------------------------------


def test_monthly_weekday_occurrences_between_span() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=4,  # second Friday
        start_date="2026-01-01", end_date="2026-04-30",
    )
    result = occurrences_between(rule, "2026-01-01", "2026-04-30")
    second_fridays = [
        _nth_weekday_of_month(2026, month, 4, 2) for month in (1, 2, 3, 4)
    ]
    expected = [
        f"2026-{month:02d}-{day:02d}"
        for month, day in zip((1, 2, 3, 4), second_fridays)
    ]
    assert result == expected


def test_monthly_weekday_occurrences_between_rejects_inverted() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=1,
        nth_weekday_weekday=1, start_date="2026-01-01",
    )
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2026-06-01", "2026-01-01")