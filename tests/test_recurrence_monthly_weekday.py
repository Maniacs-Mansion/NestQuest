"""Tests for MONTHLY_WEEKDAY (nth-weekday-of-month) recurrence."""
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
from custom_components.nestquest.core.recurrence import _nth_weekday_of_month


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


# ---------------------------------------------------------------------------
# The helper: nth occurrence day-of-month
# ---------------------------------------------------------------------------


def test_nth_weekday_helper_first_second_third() -> None:
    """Independently verified: Mar 1 2026 is a Sunday; Wednesdays are
    4, 11, 18, 25 (four — no 5th)."""
    assert _nth_weekday_of_month(2026, 3, 2, 1) == 4
    assert _nth_weekday_of_month(2026, 3, 2, 2) == 11
    assert _nth_weekday_of_month(2026, 3, 2, 3) == 18
    assert _nth_weekday_of_month(2026, 3, 2, 4) == 25
    assert _nth_weekday_of_month(2026, 3, 2, 5) is None


def test_nth_weekday_helper_none_when_month_lacks_nth() -> None:
    """Independently verified: April 2026 Fridays are 3, 10, 17, 24
    (four) — no 5th occurrence."""
    assert _nth_weekday_of_month(2026, 4, 4, 5) is None


def test_nth_weekday_helper_last() -> None:
    """Independently verified: March 2026 Fridays are 6, 13, 20, 27;
    February 2028 Saturdays are 5, 12, 19, 26 (Feb 29 2028 is a
    Tuesday, so the last SATURDAY is the 26th, not the last day)."""
    assert _nth_weekday_of_month(2026, 3, 4, -1) == 27
    # February 2026: 28 days, last day IS a Saturday.
    assert _nth_weekday_of_month(2026, 2, 5, -1) == 28
    # February 2028: the last Saturday is the 26th (Feb 29 is a Tue).
    assert _nth_weekday_of_month(2028, 2, 5, -1) == 26


def test_nth_weekday_helper_last_when_month_has_five() -> None:
    """Independently verified: October 2026 Fridays are 2, 9, 16, 23, 30
    (five) — the last is the 30th, and the 5th is the same day."""
    assert _nth_weekday_of_month(2026, 10, 4, -1) == 30
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
    """Independently verified second Wednesdays of 2026 (Jan 1 is a
    Thursday; Wednesdays per month from the calendar): the SECOND one
    fires; the FIRST one does not."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
        nth_weekday_weekday=2,
        start_date="2026-01-01",
    )
    # (month, first_wed, second_wed) from plain datetime arithmetic:
    verified = [
        (1, 7, 14), (2, 4, 11), (3, 4, 11), (4, 1, 8),
        (5, 6, 13), (6, 3, 10), (7, 1, 8), (8, 5, 12),
        (9, 2, 9), (10, 7, 14), (11, 4, 11), (12, 2, 9),
    ]
    for month, first_wed, second_wed in verified:
        assert _d(f"2026-{month:02d}-{first_wed:02d}").weekday() == 2
        assert _d(f"2026-{month:02d}-{second_wed:02d}").weekday() == 2
        assert occurs_on(
            rule, datetime.date(2026, month, second_wed)
        ) is True, f"2026-{month:02d}-{second_wed:02d}"
        assert occurs_on(
            rule, datetime.date(2026, month, first_wed)
        ) is False, f"2026-{month:02d}-{first_wed:02d}"


def test_third_friday_of_twelve_consecutive_months() -> None:
    """Independently verified 2026 Fridays; the THIRD fires, the SECOND
    does not."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=3,
        nth_weekday_weekday=4,
        start_date="2026-01-01",
    )
    verified = [
        # (month, first_fri, second_fri, third_fri)
        (1, 2, 9, 16), (2, 6, 13, 20), (3, 6, 13, 20),
        (4, 3, 10, 17), (5, 1, 8, 15), (6, 5, 12, 19),
        (7, 3, 10, 17), (8, 7, 14, 21), (9, 4, 11, 18),
        (10, 2, 9, 16), (11, 6, 13, 20), (12, 4, 11, 18),
    ]
    for month, first_fri, second_fri, third_fri in verified:
        third = _d(f"2026-{month:02d}-{third_fri:02d}")
        assert third.weekday() == 4
        assert occurs_on(rule, third) is True, third
        second = _d(f"2026-{month:02d}-{second_fri:02d}")
        assert occurs_on(rule, second) is False, second


def test_fourth_wednesday_of_twelve_consecutive_months() -> None:
    """Independently verified 2026 Wednesdays; the FOURTH fires, the
    THIRD does not."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=4,
        nth_weekday_weekday=2,
        start_date="2026-01-01",
    )
    verified = [
        # (month, third_wed, fourth_wed)
        (1, 21, 28), (2, 18, 25), (3, 18, 25), (4, 15, 22),
        (5, 20, 27), (6, 17, 24), (7, 15, 22), (8, 19, 26),
        (9, 16, 23), (10, 21, 28), (11, 18, 25), (12, 16, 23),
    ]
    for month, third_wed, fourth_wed in verified:
        fourth = _d(f"2026-{month:02d}-{fourth_wed:02d}")
        assert fourth.weekday() == 2
        assert occurs_on(rule, fourth) is True, fourth
        third = _d(f"2026-{month:02d}-{third_wed:02d}")
        assert not occurs_on(rule, third), third


def test_last_monday_of_twelve_consecutive_months() -> None:
    """Independently verified last Mondays of 2026; each fires, and the
    PREVIOUS Monday of the same month does not (it is nth-from-last
    minus one, i.e. the second-to-last)."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=-1,
        nth_weekday_weekday=0,
        start_date="2026-01-01",
    )
    verified = [
        # (month, last_monday)
        (1, 26), (2, 23), (3, 30), (4, 27), (5, 25), (6, 29),
        (7, 27), (8, 31), (9, 28), (10, 26), (11, 30), (12, 28),
    ]
    for month, last_monday in verified:
        date = _d(f"2026-{month:02d}-{last_monday:02d}")
        assert date.weekday() == 0
        assert occurs_on(rule, date) is True, date
        # The Monday a week earlier is NOT the last: must not fire.
        week_before = date - datetime.timedelta(days=7)
        if week_before.month == month:
            assert occurs_on(rule, week_before) is False, week_before


# ---------------------------------------------------------------------------
# The five-occurrence skip: a 5th on a four-occurrence month
# ---------------------------------------------------------------------------


def test_fifth_weekday_skips_four_occurrence_months() -> None:
    """Independently verified: 2026 months with FIVE Mondays are March,
    June, August, November — every other month (four Mondays) must fire
    on no day at all, and each hit must be the month's FINAL Monday."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=5,
        nth_weekday_weekday=0,  # fifth Monday
        start_date="2026-01-01",
    )
    five_monday_months = {3: 30, 6: 29, 8: 31, 11: 30}
    hit_months = set()
    for month in range(1, 13):
        if month in five_monday_months:
            day = five_monday_months[month]
            hit = _d(f"2026-{month:02d}-{day:02d}")
            assert hit.weekday() == 0
            assert occurs_on(rule, hit) is True, hit
            # It is the FINAL Monday of the month: sweep EVERY remaining
            # calendar day after the hit — none may fire.
            for later in range(day + 1, _month_end_days(2026, month) + 1):
                assert occurs_on(
                    rule, datetime.date(2026, month, later)
                ) is False, f"2026-{month:02d}-{later:02d}"
            # The Monday a week earlier is not the fifth.
            assert occurs_on(
                rule, datetime.date(2026, month, day - 7)
            ) is False
            hit_months.add(month)
        else:
            for day in range(1, _month_end_days(2026, month) + 1):
                assert occurs_on(
                    rule, datetime.date(2026, month, day)
                ) is False, f"2026-{month:02d}-{day:02d}"
    assert hit_months == {3, 6, 8, 11}, hit_months


def _month_end_days(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1)
            - datetime.timedelta(days=1)).day


def test_fifth_weekday_fires_in_five_occurrence_months() -> None:
    """Independently verified: October 2026 Fridays are 2, 9, 16, 23, 30
    (five) — the 5th (and last) is the 30th; April 2026 has four Fridays
    (3, 10, 17, 24) so no day in April fires."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=5,
        nth_weekday_weekday=4,  # Fridays
        start_date="2026-01-01",
    )
    # October: the 30th fires, is a Friday, and no Monday-later day
    # (the 31st) is a Friday: the 30th is the FINAL Friday.
    oct_30 = datetime.date(2026, 10, 30)
    assert oct_30.weekday() == 4
    assert occurs_on(rule, oct_30) is True
    assert occurs_on(rule, datetime.date(2026, 10, 31)) is False
    # April: no Friday-5th, so no day fires.
    for day in range(1, _month_end_days(2026, 4) + 1):
        assert occurs_on(rule, datetime.date(2026, 4, day)) is False, (
            f"2026-04-{day:02d}"
        )


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
    # Independently verified second Fridays: Jan 9 (Jan 1 Thu), Feb 13
    # (Feb 1 Sun), Mar 13 (Mar 1 Sun), Apr 10 (Apr 1 Wed).
    assert result == [
        "2026-01-09", "2026-02-13", "2026-03-13", "2026-04-10",
    ]


def test_monthly_weekday_occurrences_between_rejects_inverted() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=1,
        nth_weekday_weekday=1, start_date="2026-01-01",
    )
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2026-06-01", "2026-01-01")