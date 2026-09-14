"""Window-bound enforcement across every rule type (start_date/end_date)."""
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


#: One representative rule per type, all anchored inside a common
#: window (2026-03-01 .. 2026-09-30) so a boundary probe is meaningful.
BOUNDARY_RULES = [
    # (kwargs, a firing date inside the window)
    ({"rule_type": RuleType.DAILY, "start_date": "2026-03-01"}, _d("2026-03-01")),
    ({"rule_type": RuleType.WEEKLY, "weekday_set": {1},
      "start_date": "2026-03-03"}, _d("2026-03-03")),
    ({"rule_type": RuleType.CUSTOM_DAYS, "weekday_set": {2, 4},
      "start_date": "2026-03-04"}, _d("2026-03-04")),
    ({"rule_type": RuleType.MONTHLY_DAY, "day_of_month": 31,
      "start_date": "2026-03-31"}, _d("2026-03-31")),
    ({"rule_type": RuleType.MONTHLY_WEEKDAY, "nth_weekday": 1,
      "nth_weekday_weekday": 2, "start_date": "2026-03-03"},
     _d("2026-03-10")),  # first Tue = Mar 3; second = Mar 10
    ({"rule_type": RuleType.YEARLY, "month": 3, "day_of_month": 31,
      "start_date": "2026-03-31"}, _d("2026-03-31")),
]


# ---------------------------------------------------------------------------
# start_date bound: nothing fires before it, for EVERY rule type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index", range(len(BOUNDARY_RULES)))
def test_no_firing_before_start_date(index) -> None:
    kwargs, firing = BOUNDARY_RULES[index]
    rule = ScheduleRule(**kwargs)
    # The day BEFORE start_date (and a week, and a month before) never
    # fires, even if it matches the nominal pattern.
    for offset in (1, 7, 30):
        before = firing_date(f=index) - datetime.timedelta(days=offset)
        assert occurs_on(rule, before) is False, before


def firing_date(f: int) -> datetime.date:
    return BOUNDARY_RULES[f][1]


def test_start_date_itself_can_fire_for_all_types() -> None:
    """The anchor date is IN the window: types whose nominal pattern
    includes it fire; ones that don't include it stay silent — but the
    WINDOW never excludes it."""
    for index, (kwargs, firing) in enumerate(BOUNDARY_RULES):
        rule = ScheduleRule(**kwargs)
        # The window check must not reject start_date itself.
        in_window = firing >= _d(rule.start_date)
        assert in_window, (index, rule.start_date)


# ---------------------------------------------------------------------------
# end_date bound: nothing fires after it
# ---------------------------------------------------------------------------


def test_no_firing_after_end_date_all_types() -> None:
    window_end = _d("2026-09-30")
    for kwargs, firing in BOUNDARY_RULES:
        rule = ScheduleRule(
            end_date="2026-09-30",
            **{
                **kwargs,
                "start_date": min(kwargs["start_date"], "2026-09-01"),
            },
        )
        assert occurs_on(rule, window_end) is not None  # in window probe
        for offset in (1, 7, 30):
            after = window_end + datetime.timedelta(days=offset)
            assert occurs_on(rule, after) is False, after


def test_no_end_date_means_no_upper_bound() -> None:
    """A rule without end_date keeps firing arbitrarily far out."""
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-03-01")
    for years in (1, 10, 50, 100):
        assert occurs_on(rule, _d("2026-03-01") + datetime.timedelta(
            days=365 * years
        )) is True
    weekly = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1},
        start_date="2026-03-03",
    )
    # 2076-03-03 is 50 years to the day after the anchor and a Tuesday.
    assert occurs_on(weekly, _d("2076-03-03")) is True
    # 10 more years of weekly Tuesdays still fire (2076-05-12).
    assert occurs_on(weekly, _d("2076-05-12")) is True
    # A century of weekly arithmetic: anchor + 5200 weeks.
    far = datetime.date(2026, 3, 3) + datetime.timedelta(weeks=5200)
    assert far.weekday() == 1
    assert occurs_on(weekly, far) is True


def test_end_date_equal_to_start_date_allows_one_day_window() -> None:
    """end == start: exactly one day can fire."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-03-15",
        end_date="2026-03-15",
    )
    assert occurs_on(rule, _d("2026-03-15")) is True
    assert occurs_on(rule, _d("2026-03-14")) is False
    assert occurs_on(rule, _d("2026-03-16")) is False


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
    for kwargs, firing in BOUNDARY_RULES:
        rule = ScheduleRule(
            **{**kwargs, "start_date": kwargs["start_date"],
               "end_date": "2026-06-30"}
        )
        result = occurrences_between(rule, "2026-01-01", "2026-12-31")
        # Every result inside the queried range, none beyond June.
        assert all(date <= "2026-06-30" for date in result), result
        assert all(date >= kwargs["start_date"] for date in result), result


def test_occurrences_between_empty_when_range_before_start() -> None:
    for kwargs, _ in BOUNDARY_RULES:
        rule = ScheduleRule(**kwargs)
        assert occurrences_between(rule, "2026-01-01", "2026-02-28") == []


def test_occurrences_between_empty_when_range_after_end() -> None:
    for kwargs, _ in BOUNDARY_RULES:
        rule = ScheduleRule(
            end_date="2026-06-30", **kwargs,
        )
        result = occurrences_between(rule, "2026-10-01", "2026-12-31")
        assert result == []