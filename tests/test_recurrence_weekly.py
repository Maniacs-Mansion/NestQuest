"""Tests for weekly and custom day-set recurrence evaluation."""
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


# 2026-09-01 is a TUESDAY (weekday 1).
# Anchor-week arithmetic (start_date = Tue Sep 1): week 0 spans
# Sep 1-7, week 1 spans Sep 8-14, week 2 spans Sep 15-21, and so on —
# whole weeks elapsed from the anchor, NOT calendar-Sunday weeks.
# A weekly Mon/Wed/Fri (0,2,4) rule at interval 1 anchored here fires
# on Wed Sep 2, Fri Sep 4 (both week 0), then Mon Sep 7, Wed Sep 9,
# Fri Sep 11 (week 1), Mon Sep 14... (week 2), and so on.


def test_weekly_fires_exactly_on_set_weekdays() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-09-01",
    )
    # Sep 2026: 1=Tue(1), 2=Wed(2), 4=Fri(4), 7=Mon(0), 8=Tue(1), 9=Wed,
    # 10=Thu(3), 11=Fri(4)
    assert occurs_on(rule, _d("2026-09-01")) is False  # Tue NOT in set
    assert occurs_on(rule, _d("2026-09-02")) is True   # Wed in set
    assert occurs_on(rule, _d("2026-09-03")) is False  # Thu not in set
    assert occurs_on(rule, _d("2026-09-04")) is True   # Fri in set
    assert occurs_on(rule, _d("2026-09-05")) is False  # Sat
    assert occurs_on(rule, _d("2026-09-06")) is False  # Sun
    assert occurs_on(rule, _d("2026-09-07")) is True   # Mon
    assert occurs_on(rule, _d("2026-09-08")) is False  # Tue not in set


def test_weekly_start_date_itself_may_not_be_in_set() -> None:
    """start_date anchors the WEEK count, not a firing day: a Tuesday
    start for a Mon/Wed/Fri rule fires on Wed Sep 2, not Sep 1."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-09-01",
    )
    assert occurs_on(rule, _d("2026-09-01")) is False  # Tue=1, not in set
    assert occurs_on(rule, _d("2026-09-02")) is True   # Wed=2
    assert occurs_on(rule, _d("2026-09-04")) is True   # Fri=4
    assert occurs_on(rule, _d("2026-09-07")) is True   # Mon, next week


def test_weekly_never_fires_before_start() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={2},  # Wednesdays
        start_date="2026-09-02",  # a Wednesday
    )
    # Wed Sep 2 is the anchor day and in-set: fires.  Wed Aug 26 (one
    # week BEFORE the anchor, in-set) must not fire: pre-window.
    assert occurs_on(rule, _d("2026-09-02")) is True
    assert occurs_on(rule, _d("2026-08-26")) is False  # Wed, before start
    assert occurs_on(rule, _d("2026-09-09")) is True   # Wed, next week


def test_weekly_respects_end_date() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-09-01", end_date="2026-09-10",
    )
    assert occurs_on(rule, _d("2026-09-09")) is True   # Wed within end
    assert occurs_on(rule, _d("2026-09-11")) is False  # Fri after end


def test_weekly_interval_2_fires_on_alternate_weeks() -> None:
    """Interval 2: fires on set weekdays only in even week-offsets."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0}, interval=2,
        start_date="2026-09-07",  # a Monday
    )
    # Week 0 (Sep 7-13): fires Mon Sep 7.
    assert occurs_on(rule, _d("2026-09-07")) is True
    # Week 1 (Sep 14-20): skipped.
    assert occurs_on(rule, _d("2026-09-14")) is False
    # Week 2 (Sep 21-27): fires Mon Sep 21.
    assert occurs_on(rule, _d("2026-09-21")) is True
    # Week 2 is not a firing week: Mon Sep 28 skipped.
    assert occurs_on(rule, _d("2026-09-28")) is False
    # Week 3: fires Mon Oct 5.
    assert occurs_on(rule, _d("2026-10-05")) is True


def test_weekly_interval_3_every_third_week() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={3}, interval=3,
        start_date="2026-09-03",  # a Thursday
    )
    assert occurs_on(rule, _d("2026-09-03")) is True   # week 0
    assert occurs_on(rule, _d("2026-09-10")) is False  # week 1
    assert occurs_on(rule, _d("2026-09-17")) is False  # week 2
    assert occurs_on(rule, _d("2026-09-24")) is True   # week 3
    assert occurs_on(rule, _d("2026-10-15")) is True   # week 6


def test_weekly_interval_2_never_fires_in_odd_weeks_across_months() -> None:
    """The week offset is anchored to start_date across month edges."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={2}, interval=2,
        start_date="2026-09-02",  # a Wednesday
    )
    # Week 0: Wed Sep 2 fires. Week 1: Wed Sep 9 skipped.
    # Week 2: Wed Sep 16 fires. Week 3: Wed Sep 23 skipped.
    # Week 4 (Oct): Wed Sep 30 fires (still week 4!). Week 5: Wed Oct 7 skipped.
    assert occurs_on(rule, _d("2026-09-02")) is True
    assert occurs_on(rule, _d("2026-09-09")) is False
    assert occurs_on(rule, _d("2026-09-16")) is True
    assert occurs_on(rule, _d("2026-09-23")) is False
    assert occurs_on(rule, _d("2026-09-30")) is True
    assert occurs_on(rule, _d("2026-10-07")) is False
    assert occurs_on(rule, _d("2026-10-14")) is True


def test_custom_days_interval_1_behaves_like_weekly() -> None:
    """CUSTOM_DAYS with interval 1 behaves identically to WEEKLY."""
    weekly = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1, 3, 5},
        start_date="2026-09-01",
    )
    custom = ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={1, 3, 5},
        start_date="2026-09-01",
    )
    # Whole month of September must match exactly.
    for day in range(1, 31):
        date = datetime.date(2026, 9, day)
        assert occurs_on(weekly, date) == occurs_on(custom, date), date


def test_custom_days_never_fires_before_start(tmp_path) -> None:
    rule = ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={0},
        start_date="2026-09-07",  # a Monday
    )
    assert occurs_on(rule, _d("2026-09-06")) is False  # Sun, before
    assert occurs_on(rule, _d("2026-09-07")) is True   # Mon, on


def test_hand_checked_8_week_sequence_weekly_mon_wed_fri() -> None:
    """The done-condition's hand-checked sequence: 8 weeks of a
    Mon/Wed/Fri rule anchored at Tue 2026-09-01, interval 1.

    Anchor weeks from Tue Sep 1 (week 0 = Sep 1-7, week 1 = Sep 8-14,
    ... week 7 = Oct 20-26).  Mon/Wed/Fri firings (interval 1, so every
    in-set weekday fires regardless of week):
    Week 0 (Sep 1-7):   Wed 2, Fri 4        (Mon Sep 7 is ALSO week 0:
                        6 elapsed days // 7 = 0 — the anchor week
                        boundary sits on Sep 8, not on the Monday)
    Week 1 (Sep 8-14):  Wed 9, Fri 11, Mon 14 (13 elapsed days // 7 = 1)
    Week 2 (Sep 15-21): Wed 16, Fri 18, Mon 21
    Week 3 (Sep 22-28): Wed 23, Fri 25, Mon 28
    Week 4 (Sep 29-Oct 5): Wed 30, Fri 2 (Oct), Mon 5 (Oct)
    Week 5 (Oct 6-12):  Wed 7, Fri 9, Mon 12
    Week 6 (Oct 13-19): Wed 14, Fri 16, Mon 19
    Week 7 (Oct 20-26): Wed 21, Fri 23, Mon 26
    """
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
        start_date="2026-09-01", end_date="2026-10-26",
    )
    expected = [
        "2026-09-02", "2026-09-04",
        "2026-09-07", "2026-09-09", "2026-09-11",
        "2026-09-14", "2026-09-16", "2026-09-18",
        "2026-09-21", "2026-09-23", "2026-09-25",
        "2026-09-28", "2026-09-30", "2026-10-02",
        "2026-10-05", "2026-10-07", "2026-10-09",
        "2026-10-12", "2026-10-14", "2026-10-16",
        "2026-10-19", "2026-10-21", "2026-10-23", "2026-10-26",
    ]
    actual = occurrences_between(rule, "2026-09-01", "2026-10-26")
    assert actual == expected, (
        f"diff: {set(expected) ^ set(actual)}"
    )


def test_hand_checked_8_week_sequence_weekly_interval_2_mondays() -> None:
    """8 weeks of a Monday rule at interval 2, anchored Mon 2026-09-07
    (week 0 = Sep 7-13): fires in weeks 0, 2, 4, 6 -> Mon Sep 7, Mon Sep 21,
    Mon Oct 5, Mon Oct 19."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0}, interval=2,
        start_date="2026-09-07", end_date="2026-10-31",
    )
    actual = occurrences_between(rule, "2026-09-07", "2026-10-31")
    assert actual == ["2026-09-07", "2026-09-21", "2026-10-05", "2026-10-19"]


def test_custom_days_hand_checked_8_week_sequence() -> None:
    """8 weeks of a Tue/Thu/Sun rule (1,3,6) anchored Mon 2026-09-07:
    fires Tue 8, Thu 10, Sun 13, then weekly."""
    rule = ScheduleRule(
        rule_type=RuleType.CUSTOM_DAYS, weekday_set={1, 3, 6},
        start_date="2026-09-07",
    )
    # Anchor weeks from Mon Sep 7 (w0 = Sep 7-13 ... w7 = Oct 26-Nov 1):
    # Tue/Thu/Sun firings per week, 8 weeks fully covered.
    actual = occurrences_between(rule, "2026-09-07", "2026-11-01")
    assert actual == [
        "2026-09-08", "2026-09-10", "2026-09-13",
        "2026-09-15", "2026-09-17", "2026-09-20",
        "2026-09-22", "2026-09-24", "2026-09-27",
        "2026-09-29", "2026-10-01", "2026-10-04",
        "2026-10-06", "2026-10-08", "2026-10-11",
        "2026-10-13", "2026-10-15", "2026-10-18",
        "2026-10-20", "2026-10-22", "2026-10-25",
        "2026-10-27", "2026-10-29", "2026-11-01",
    ]


def test_weekly_survives_53_week_year_boundary() -> None:
    """Anchor arithmetic never flips at Jan 1 (the ISO parity trap):
    a weekly rule spanning New Year keeps its weekday pattern."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={3},  # Thursdays
        start_date="2026-12-24",  # a Thursday
    )
    # Thursdays around New Year 2026->2027: Dec 24, 31, Jan 7, 14.
    assert occurs_on(rule, _d("2026-12-24")) is True
    assert occurs_on(rule, _d("2026-12-31")) is True
    assert occurs_on(rule, _d("2027-01-07")) is True
    assert occurs_on(rule, _d("2027-01-14")) is True
    # Interleaved days are not Thursdays.
    assert occurs_on(rule, _d("2027-01-04")) is False  # Monday
    assert occurs_on(rule, _d("2027-01-05")) is False  # Tuesday


def test_weekly_interval_2_across_year_boundary() -> None:
    """Interval weeks continue across Jan 1 with no parity flip."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={4}, interval=2,
        start_date="2026-12-25",  # a Friday
    )
    # Weeks: Dec 25 (w0) fires, Jan 1 (w1) skipped, Jan 8 (w2) fires,
    # Jan 15 (w3) skipped, Jan 22 (w4) fires.
    assert occurs_on(rule, _d("2026-12-25")) is True
    assert occurs_on(rule, _d("2027-01-01")) is False
    assert occurs_on(rule, _d("2027-01-08")) is True
    assert occurs_on(rule, _d("2027-01-15")) is False
    assert occurs_on(rule, _d("2027-01-22")) is True


def test_occurrences_between_weekly_disjoint(tmp_path) -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={1},
        start_date="2026-09-01", end_date="2026-09-30",
    )
    assert occurrences_between(rule, "2026-10-01", "2026-10-31") == []


def test_occurrences_between_weekly_interval_2_span() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0}, interval=2,
        start_date="2026-09-07", end_date="2026-10-31",
    )
    result = occurrences_between(rule, "2026-09-01", "2026-10-31")
    assert result == ["2026-09-07", "2026-09-21", "2026-10-05", "2026-10-19"]


def test_occurrences_between_rejects_inverted_bounds() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0}, start_date="2026-09-01"
    )
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2026-10-10", "2026-09-01")

def test_weekly_interval_2_non_monday_anchor_boundary() -> None:
    """The anchor week is anchored at start_date, NOT a calendar week:
    a Tuesday-anchored Monday rule fires on Mon Sep 7 (week 0 extends
    through Sep 7), skips Mon Sep 14 (week 1), fires Mon Sep 21 (week 2)."""
    rule = ScheduleRule(
        rule_type=RuleType.WEEKLY, weekday_set={0}, interval=2,
        start_date="2026-09-01",  # a TUESDAY anchor
    )
    # Sep 7 - Sep 1 = 6 days -> week 0 (even): fires.
    assert occurs_on(rule, _d("2026-09-07")) is True
    # Sep 14: 13 days -> week 1 (odd): skipped.
    assert occurs_on(rule, _d("2026-09-14")) is False
    # Sep 21: 20 days -> week 2 (even): fires.
    assert occurs_on(rule, _d("2026-09-21")) is True
    # Sep 28: 27 days -> week 3 (odd): skipped.
    assert occurs_on(rule, _d("2026-09-28")) is False
    # Oct 5: 34 days -> week 4 (even): fires.
    assert occurs_on(rule, _d("2026-10-05")) is True