"""Tests for the daily recurrence evaluation (occurs_on/occurrences_between)."""
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


def test_daily_fires_every_day_from_start() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    assert occurs_on(rule, _d("2026-09-01")) is True
    assert occurs_on(rule, _d("2026-09-02")) is True
    assert occurs_on(rule, _d("2026-09-30")) is True


def test_daily_never_fires_before_start() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    assert occurs_on(rule, _d("2026-08-31")) is False


def test_daily_respects_end_date() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-09-01",
        end_date="2026-09-10",
    )
    assert occurs_on(rule, _d("2026-09-10")) is True
    assert occurs_on(rule, _d("2026-09-11")) is False


def test_daily_interval_2_fires_every_second_day() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01"
    )
    # Odd offsets fire (0, 2, 4...); odd offsets don't.
    assert occurs_on(rule, _d("2026-09-01")) is True   # offset 0
    assert occurs_on(rule, _d("2026-09-02")) is False  # offset 1
    assert occurs_on(rule, _d("2026-09-03")) is True   # offset 2
    assert occurs_on(rule, _d("2026-09-04")) is False  # offset 3
    assert occurs_on(rule, _d("2026-09-05")) is True   # offset 4


def test_daily_interval_3_fires_every_third_day() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=3, start_date="2026-09-01"
    )
    assert occurs_on(rule, _d("2026-09-01")) is True   # 0
    assert occurs_on(rule, _d("2026-09-02")) is False  # 1
    assert occurs_on(rule, _d("2026-09-03")) is False  # 2
    assert occurs_on(rule, _d("2026-09-04")) is True   # 3
    assert occurs_on(rule, _d("2026-09-07")) is True   # 6


def test_hand_checked_30_day_sequence_interval_1() -> None:
    """The done-condition's hand-checked sequence: 30 days, all fire."""
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    expected = [
        (2026, 9, day) for day in range(1, 31)
    ]
    for (year, month, day) in expected:
        assert occurs_on(rule, datetime.date(year, month, day)) is True, (
            f"{year}-{month:02d}-{day:02d} must fire (interval 1)"
        )


def test_hand_checked_30_day_sequence_interval_2() -> None:
    """30-day sequence at interval 2: days 1, 3, 5, ... (odd days)."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01"
    )
    for day in range(1, 31):
        fired = occurs_on(rule, datetime.date(2026, 9, day))
        expected = (day - 1) % 2 == 0
        assert fired is expected, f"day {day}: got {fired}, want {expected}"


def test_hand_checked_30_day_sequence_interval_3() -> None:
    """30-day sequence at interval 3: days 1, 4, 7, 10, ... 28."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=3, start_date="2026-09-01"
    )
    fired_days = [
        day
        for day in range(1, 31)
        if occurs_on(rule, datetime.date(2026, 9, day))
    ]
    assert fired_days == [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]


def test_interval_2_across_month_boundary() -> None:
    """Interval arithmetic spans months: Sept 29/30 (offsets 28/29) then
    Oct 1 (offset 30) — the offset keeps counting across the month edge."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01"
    )
    assert occurs_on(rule, _d("2026-09-29")) is True   # offset 28
    assert occurs_on(rule, _d("2026-09-30")) is False  # offset 29
    assert occurs_on(rule, _d("2026-10-01")) is True   # offset 30
    assert occurs_on(rule, _d("2026-10-02")) is False  # offset 31


def test_interval_2_across_year_boundary() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-12-30"
    )
    assert occurs_on(rule, _d("2026-12-30")) is True  # 0
    assert occurs_on(rule, _d("2026-12-31")) is False  # 1
    assert occurs_on(rule, _d("2027-01-01")) is True   # 2


# ---------------------------------------------------------------------------
# occurrences_between
# ---------------------------------------------------------------------------


def test_occurrences_between_daily_interval_1() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    result = occurrences_between(rule, "2026-09-05", "2026-09-08")
    assert result == [
        "2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08",
    ]


def test_occurrences_between_daily_interval_2() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01"
    )
    result = occurrences_between(rule, "2026-09-01", "2026-09-10")
    assert result == [
        "2026-09-01", "2026-09-03", "2026-09-05", "2026-09-07", "2026-09-09",
    ]


def test_occurrences_between_clamps_to_rule_start() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-05")
    result = occurrences_between(rule, "2026-09-01", "2026-09-08")
    assert result == ["2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08"]


def test_occurrences_between_clamps_to_rule_end() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-09-01",
        end_date="2026-09-06",
    )
    result = occurrences_between(rule, "2026-09-01", "2026-09-20")
    assert result == [
        f"2026-09-{day:02d}" for day in range(1, 7)
    ]


def test_occurrences_between_disjoint_range_is_empty() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, start_date="2026-09-01",
        end_date="2026-09-15",
    )
    # The rule ends Sept 15: October is entirely outside its window.
    assert occurrences_between(rule, "2026-10-01", "2026-10-05") == []
    assert occurrences_between(rule, "2026-08-01", "2026-08-05") == []


def test_occurrences_between_inclusive_bounds() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-09-01"
    )
    # Both boundary dates fire at interval 2 (offsets 0 and 6).
    result = occurrences_between(rule, "2026-09-01", "2026-09-07")
    assert result[0] == "2026-09-01"
    assert result[-1] == "2026-09-07"


def test_occurrences_between_rejects_inverted_range() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2026-09-10", "2026-09-05")


def test_occurrences_between_rejects_malformed_dates() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01")
    with pytest.raises(RuleValidationError, match="YYYY-MM-DD"):
        occurrences_between(rule, "oops", "2026-09-05")
    with pytest.raises(RuleValidationError, match="YYYY-MM-DD"):
        occurrences_between(rule, "2026-09-05", "2026-9-5")


def test_occurrences_between_leap_day_fires() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-02-27")
    # 2028 is a leap year: Feb 29 exists and is 2 days after Feb 27.
    result = occurrences_between(rule, "2028-02-28", "2028-03-01")
    assert result == ["2028-02-28", "2028-02-29", "2028-03-01"]


def test_occurrences_between_year_boundary() -> None:
    rule = ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-12-30")
    result = occurrences_between(rule, "2026-12-30", "2027-01-02")
    assert result == [
        "2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02",
    ]


# ---------------------------------------------------------------------------
# Purity: the engine raises on unknown shapes rather than guessing
# ---------------------------------------------------------------------------


def test_occurs_on_rejects_unimplemented_shapes_loudly() -> None:
    """Monthly/yearly land with their own engine tasks; a loud
    NotImplementedError beats a silent wrong answer."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6,
        start_date="2026-09-01",
    )
    with pytest.raises(NotImplementedError):
        occurs_on(rule, _d("2026-09-15"))

def test_interval_7_preserves_weekday_alignment_across_months() -> None:
    """Weekly-by-interval semantics: every firing lands on the SAME
    weekday as start_date, no matter how many month edges intervene."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=7, start_date="2026-09-01"
    )
    # 2026-09-01 is a Tuesday; every firing must be a Tuesday too.
    assert _d("2026-09-01").weekday() == 1
    for day in ("2026-09-08", "2026-09-29", "2026-10-06", "2026-11-03"):
        assert occurs_on(rule, _d(day)) is True, day
        assert _d(day).weekday() == 1, f"{day} must be a Tuesday"
    # The day after a firing is never a firing.
    assert occurs_on(rule, _d("2026-10-07")) is False


def test_interval_2_across_leap_day() -> None:
    """Interval > 1 arithmetic across a leap day: the extra day shifts
    subsequent offsets by one, and the mod arithmetic reflects it."""
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2028-02-27"
    )
    assert occurs_on(rule, _d("2028-02-27")) is True   # 0
    assert occurs_on(rule, _d("2028-02-28")) is False  # 1
    assert occurs_on(rule, _d("2028-02-29")) is True   # 2 (leap day)
    assert occurs_on(rule, _d("2028-03-01")) is False  # 3
    assert occurs_on(rule, _d("2028-03-02")) is True   # 4


def test_occurrences_between_leap_day_interval_2() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2028-02-27"
    )
    result = occurrences_between(rule, "2028-02-27", "2028-03-03")
    assert result == ["2028-02-27", "2028-02-29", "2028-03-02"]


def test_occurrences_between_year_boundary_interval_2() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.DAILY, interval=2, start_date="2026-12-30"
    )
    result = occurrences_between(rule, "2026-12-30", "2027-01-04")
    # Offsets 0, 2, 4, 6 = Dec 30, Jan 1, Jan 3 ... wait: offsets are
    # Dec30=0, Dec31=1, Jan1=2, Jan2=3, Jan3=4, Jan4=5. Even offsets:
    assert result == ["2026-12-30", "2027-01-01", "2027-01-03"]


def test_occurs_on_unimplemented_shape_raises_even_outside_window() -> None:
    """An unimplemented shape must raise whether the date is inside or
    outside the window — silent False would hide a missing engine."""
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6,
        start_date="2026-09-01", end_date="2026-09-10",
    )
    # Before start, inside window, after end: all must raise.
    for day in ("2026-08-31", "2026-09-07", "2026-09-20"):
        with pytest.raises(NotImplementedError):
            occurs_on(rule, _d(day))


def test_occurrences_between_unimplemented_shape_raises_even_disjoint(
    tmp_path,
) -> None:
    rule = ScheduleRule(
        rule_type=RuleType.YEARLY, month=6,
        start_date="2026-09-01"
    )
    # A range entirely before the rule's start still raises: the shape
    # is unimplemented, and silence would hide it.
    with pytest.raises(NotImplementedError):
        occurrences_between(rule, "2026-08-01", "2026-08-10")
