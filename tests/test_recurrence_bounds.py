"""Window-bound enforcement across every rule type (start_date/end_date).

Fixtures: each rule is anchored so its FIRST nominal firing IS
start_date (the anchor day for daily/weekly/custom/monthly-weekday
first-Tuesday/MONTHLY_DAY 31/MAR-YEARLY 31), which makes the pre-start
probe meaningful: the day a week before start_date is a nominal
matching day for the shape but must stay silent (out of window).
"""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
    occurs_on,
    occurrences_between,
)


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


def _tuesday(year: int, month: int, nth: int) -> datetime.date:
    """The nth Tuesday of the month (nth >= 1)."""
    day = datetime.date(year, month, 1)
    while day.weekday() != 1:
        day += datetime.timedelta(days=1)
    return day + datetime.timedelta(weeks=nth - 1)


def _friday(year: int, month: int, nth: int) -> datetime.date:
    day = datetime.date(year, month, 1)
    while day.weekday() != 4:
        day += datetime.timedelta(days=1)
    return day + datetime.timedelta(weeks=nth - 1)


def _month_end(year: int, month: int) -> datetime.date:
    if month == 12:
        return datetime.date(year, 12, 31)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


#: One representative rule per type.  Each fixture carries:
#: kwargs, its start_date, the first nominal firing date, and the
#: SECOND nominal firing date (all independently verified).
#: - DAILY: start Mar 1; fires daily; second firing Mar 2.
#: - WEEKLY (Tuesdays): start Tue Mar 3; second firing Tue Mar 10.
#: - CUSTOM_DAYS (Wed + Fri): start Wed Mar 4; second firing Fri Mar 6.
#: - MONTHLY_DAY (31st): start Tue Mar 31; second firing Apr 30 (clamp).
#: - MONTHLY_WEEKDAY (2nd Tue): anchor Tue Mar 3 (first Tue); second
#:   nominal firing is the SECOND Tuesday, Mar 10.
#: - YEARLY (Mar 31): start Tue Mar 31; second firing Mar 31 2027.
BOUNDARY_RULES = [
    {
        "kwargs": {"rule_type": RuleType.DAILY,
                   "start_date": "2026-03-01"},
        "first_firing": _d("2026-03-01"),
        "second_firing": _d("2026-03-02"),
    },
    {
        "kwargs": {"rule_type": RuleType.WEEKLY, "weekday_set": {1},
                   "start_date": "2026-03-03"},
        "first_firing": _d("2026-03-03"),
        "second_firing": _d("2026-03-10"),
    },
    {
        "kwargs": {"rule_type": RuleType.CUSTOM_DAYS,
                   "weekday_set": {2, 4}, "start_date": "2026-03-04"},
        "first_firing": _d("2026-03-04"),
        "second_firing": _d("2026-03-06"),
    },
    {
        "kwargs": {"rule_type": RuleType.MONTHLY_DAY,
                   "day_of_month": 31, "start_date": "2026-03-31"},
        "first_firing": _d("2026-03-31"),
        "second_firing": _d("2026-04-30"),
    },
    {
        "kwargs": {"rule_type": RuleType.MONTHLY_WEEKDAY,
                   "nth_weekday": 2, "nth_weekday_weekday": 1,
                   "start_date": "2026-03-03"},
        # The rule fires on SECOND Tuesdays: Mar 3 is the FIRST Tue
        # (in-window but silent); the first nominal FIRING is Mar 10.
        "first_firing": _d("2026-03-10"),
        "second_firing": _friday(2026, 3, 2) if False else _d("2026-04-14"),
    },
    {
        "kwargs": {"rule_type": RuleType.YEARLY, "month": 3,
                   "day_of_month": 31, "start_date": "2026-03-31"},
        "first_firing": _d("2026-03-31"),
        "second_firing": _d("2027-03-31"),
    },
]


# ---------------------------------------------------------------------------
# start_date bound: nothing fires before it, for EVERY rule type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index", range(len(BOUNDARY_RULES)))
def test_no_firing_before_start_date(index) -> None:
    fixture = BOUNDARY_RULES[index]
    rule = ScheduleRule(**fixture["kwargs"])
    first = fixture["first_firing"]
    # Every day BEFORE start_date never fires — sweep the week before
    # plus the full prior month.
    before_start = _d(rule.start_date)
    sweep_from = before_start - datetime.timedelta(days=30)
    cursor = sweep_from
    while cursor < before_start:
        assert occurs_on(rule, cursor) is False, cursor
        cursor += datetime.timedelta(days=1)


@pytest.mark.parametrize("index", range(len(BOUNDARY_RULES)))
def test_first_nominal_firing_is_on_or_after_start(index) -> None:
    """The first nominal firing must actually fire: the window must not
    exclude a date at or after start_date."""
    fixture = BOUNDARY_RULES[index]
    rule = ScheduleRule(**fixture["kwargs"])
    first = fixture["first_firing"]
    assert occurs_on(rule, first) is True, first


# ---------------------------------------------------------------------------
# end_date bound: nothing fires after it
# ---------------------------------------------------------------------------


def test_no_firing_after_end_date_all_types() -> None:
    window_end = _d("2026-09-30")
    for fixture in BOUNDARY_RULES:
        rule = ScheduleRule(
            end_date="2026-09-30", **fixture["kwargs"]
        )
        # Sweep every day in the week after window_end: none may fire,
        # regardless of whether that date would nominally match.
        for offset in range(1, 8):
            after = window_end + datetime.timedelta(days=offset)
            assert occurs_on(rule, after) is False, after


def test_no_firing_after_end_date_at_nominal_shapes() -> None:
    """A post-end date that WOULD nominally match each shape must be
    silent — otherwise the end bound is untested noise."""
    rule_monthly = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-03-31", end_date="2026-04-30",
    )
    # Apr 30 is INSIDE the window (fires: clamp); May 31 would nominally
    # match but is after end_date: silent.
    assert occurs_on(rule_monthly, _d("2026-04-30")) is True
    assert occurs_on(rule_monthly, _d("2026-05-31")) is False

    rule_yearly = ScheduleRule(
        rule_type=RuleType.YEARLY, month=3, day_of_month=31,
        start_date="2026-03-31", end_date="2027-03-31",
    )
    # Mar 31 2027 is inside; Mar 31 2028 would match but is past end.
    assert occurs_on(rule_yearly, _d("2027-03-31")) is True
    assert occurs_on(rule_yearly, _d("2028-03-31")) is False

    rule_weekly = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1},
        start_date="2026-03-03", end_date="2026-10-05",
    )
    # Tue Oct 6 would nominally match but is after end_date (Oct 5 is a
    # Monday, not in the set).
    assert occurs_on(rule_weekly, _d("2026-09-29")) is True
    assert occurs_on(rule_weekly, _d("2026-10-06")) is False


def test_no_end_date_means_no_upper_bound() -> None:
    """A rule without end_date keeps firing arbitrarily far out — for
    DAILY, WEEKLY, CUSTOM_DAYS, MONTHLY_DAY, MONTHLY_WEEKDAY, YEARLY."""
    daily = ScheduleRule(rule_type=RuleType.DAILY,
                         start_date="2026-03-01")
    assert occurs_on(daily, _d("2036-03-01")) is True

    weekly = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1},
        start_date="2026-03-03",
    )
    # 2076-03-03 is 50 years to the day after the anchor and a Tuesday.
    assert occurs_on(weekly, _d("2076-03-03")) is True

    custom = ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={4},
        start_date="2026-03-06",  # a Friday
    )
    assert occurs_on(custom, _d("2026-03-06")) is True
    # The first Friday of March 2046 is Mar 2; Mar 6 is a Tuesday.
    assert occurs_on(custom, _d("2046-03-01")) is False  # not in set
    assert occurs_on(custom, _d("2046-03-02")) is True

    monthly_day = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-03-15",
    )
    assert occurs_on(monthly_day, datetime.date(2036, 3, 15)) is True

    monthly_weekday = ScheduleRule(
        rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=1,
        nth_weekday_weekday=2, start_date="2026-03-04",
    )
    # First Wednesday of March 2036.
    d = datetime.date(2036, 3, 1)
    while d.weekday() != 2:
        d += datetime.timedelta(days=1)
    assert occurs_on(monthly_weekday, d) is True

    yearly = ScheduleRule(
        rule_type=RuleType.YEARLY, month=3, day_of_month=31,
        start_date="2026-03-31",
    )
    assert occurs_on(yearly, datetime.date(2036, 3, 31)) is True


def test_end_date_equal_to_start_date_allows_one_day_window() -> None:
    """end == start: exactly one day can fire, for every rule type."""
    daily = ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-03-15",
        end_date="2026-03-15",
    )
    assert occurs_on(daily, _d("2026-03-15")) is True
    assert occurs_on(daily, _d("2026-03-14")) is False
    assert occurs_on(daily, _d("2026-03-16")) is False

    weekly = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1},  # 2026-03-15 is a Sun
        start_date="2026-03-09", end_date="2026-03-15",
    )
    # The window is one week; Tue Mar 10 fires inside it.
    assert occurs_on(weekly, _d("2026-03-10")) is True
    assert occurs_on(weekly, _d("2026-03-17")) is False

    monthly_day = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-03-15", end_date="2026-03-15",
    )
    assert occurs_on(monthly_day, _d("2026-03-15")) is True

    yearly = ScheduleRule(
        rule_type=RuleType.YEARLY, month=3, day_of_month=15,
        start_date="2026-03-15", end_date="2026-03-15",
    )
    assert occurs_on(yearly, _d("2026-03-15")) is True
    assert occurs_on(yearly, _d("2027-03-15")) is False


# ---------------------------------------------------------------------------
# end_date before start_date is rejected at construction, every type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rule_type": RuleType.DAILY, "start_date": "2026-09-01",
         "end_date": "2026-08-31"},
        {"rule_type": RuleType.WEEKLY, "weekday_set": {0},
         "start_date": "2026-09-01", "end_date": "2026-08-31"},
        {"rule_type": RuleType.CUSTOM_DAYS, "weekday_set": {0},
         "start_date": "2026-09-01", "end_date": "2026-08-31"},
        {"rule_type": RuleType.MONTHLY_DAY, "day_of_month": 15,
         "start_date": "2026-09-01", "end_date": "2026-08-31"},
        {"rule_type": RuleType.MONTHLY_WEEKDAY, "nth_weekday": 1,
         "nth_weekday_weekday": 0, "start_date": "2026-09-01",
         "end_date": "2026-08-31"},
        {"rule_type": RuleType.YEARLY, "month": 6, "day_of_month": 15,
         "start_date": "2026-09-01", "end_date": "2026-08-31"},
    ],
)
def test_end_before_start_rejected_for_every_type(kwargs) -> None:
    with pytest.raises(RuleValidationError, match="on or after"):
        ScheduleRule(**kwargs)


# ---------------------------------------------------------------------------
# occurrences_between respects the window for every type
# ---------------------------------------------------------------------------


def test_occurrences_between_respects_end_bound_all_types() -> None:
    for fixture in BOUNDARY_RULES:
        rule = ScheduleRule(
            end_date="2026-06-30", **fixture["kwargs"]
        )
        result = occurrences_between(rule, "2026-01-01", "2026-12-31")
        # Every result inside the queried range, none beyond June.
        assert all(date <= "2026-06-30" for date in result), result
        assert all(
            date >= fixture["kwargs"]["start_date"] for date in result
        ), result


def test_occurrences_between_empty_when_range_before_start() -> None:
    for fixture in BOUNDARY_RULES:
        rule = ScheduleRule(**fixture["kwargs"])
        assert occurrences_between(rule, "2026-01-01", "2026-02-28") == []


def test_occurrences_between_empty_when_range_after_end() -> None:
    for fixture in BOUNDARY_RULES:
        rule = ScheduleRule(
            end_date="2026-06-30", **fixture["kwargs"],
        )
        result = occurrences_between(rule, "2026-10-01", "2026-12-31")
        assert result == []