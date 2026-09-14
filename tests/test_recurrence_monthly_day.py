"""Tests for MONTHLY_DAY recurrence with the month-end clamp policy."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
    _month_end,
    occurs_on,
    occurrences_between,
)


def _d(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


# ---------------------------------------------------------------------------
# Nominal-day firings
# ---------------------------------------------------------------------------


def test_monthly_day_15_fires_on_the_15th() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-01-15",
    )
    for month in range(1, 13):
        assert occurs_on(rule, datetime.date(2026, month, 15)) is True
    assert occurs_on(rule, datetime.date(2026, 1, 14)) is False
    assert occurs_on(rule, datetime.date(2026, 1, 16)) is False


def test_monthly_day_never_fires_on_other_days() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=10,
        start_date="2026-01-10",
    )
    # Every non-10th day of a short month must be False.
    for day in range(1, 30):
        if day != 10:
            assert occurs_on(
                rule, datetime.date(2026, 1, day)
            ) is False, f"Jan {day}"


def test_monthly_day_never_fires_before_start() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-03-15",
    )
    # Feb 15 precedes the start: no firing even though the day matches.
    assert occurs_on(rule, datetime.date(2026, 2, 15)) is False
    assert occurs_on(rule, datetime.date(2026, 3, 15)) is True


def test_monthly_day_respects_end_date() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-01-15", end_date="2026-06-15",
    )
    assert occurs_on(rule, datetime.date(2026, 6, 15)) is True
    assert occurs_on(rule, datetime.date(2026, 7, 15)) is False


# ---------------------------------------------------------------------------
# Month-end clamp policy
# ---------------------------------------------------------------------------


def test_month_end_helper_is_leap_aware() -> None:
    assert _month_end(2026, 1) == 31
    assert _month_end(2026, 4) == 30
    assert _month_end(2026, 2) == 28   # non-leap
    assert _month_end(2028, 2) == 29   # leap
    assert _month_end(2000, 2) == 29   # divisible-by-400 leap
    assert _month_end(1900, 2) == 28   # divisible-by-100 non-leap
    assert _month_end(2026, 12) == 31


def test_day_31_clamps_to_month_end_in_shorter_months() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )
    # Months with a 31st: fire on the 31st.
    for month, day in ((1, 31), (3, 31), (5, 31), (7, 31), (8, 31),
                       (10, 31), (12, 31)):
        assert occurs_on(rule, datetime.date(2026, month, day)) is True, (
            f"2026-{month:02d}-{day:02d}"
        )
    # Months WITHOUT a 31st: fire on the month's last day.
    assert occurs_on(rule, datetime.date(2026, 4, 30)) is True   # Apr 30
    assert occurs_on(rule, datetime.date(2026, 6, 30)) is True   # Jun 30
    assert occurs_on(rule, datetime.date(2026, 9, 30)) is True   # Sep 30
    assert occurs_on(rule, datetime.date(2026, 11, 30)) is True  # Nov 30
    # The day BEFORE the clamp is not a firing.
    assert occurs_on(rule, datetime.date(2026, 4, 29)) is False
    assert occurs_on(rule, datetime.date(2026, 4, 28)) is False


def test_day_30_clamps_to_feb_28_non_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=30,
        start_date="2026-01-30",
    )
    assert occurs_on(rule, datetime.date(2026, 2, 28)) is True   # clamp
    # No Feb 29 in 2026 (non-leap): nothing else in February fires.
    assert occurs_on(rule, datetime.date(2026, 2, 27)) is False
    # Months with a 30th: nominal day.
    assert occurs_on(rule, datetime.date(2026, 4, 30)) is True
    assert occurs_on(rule, datetime.date(2026, 3, 30)) is True


def test_day_29_feb_clamps_to_28_non_leap_and_29_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=29,
        start_date="2026-01-29",
    )
    # Non-leap 2027: Feb 28 is the clamp.
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is True
    assert occurs_on(rule, datetime.date(2027, 2, 27)) is False
    # Leap 2028: Feb 29 exists — nominal day.
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True
    assert occurs_on(rule, datetime.date(2028, 2, 28)) is False


def test_day_30_feb_leap_year_clamps_to_29() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=30,
        start_date="2027-01-30",
    )
    # Leap 2028: Feb has 29 days; the 30th clamps to Feb 29.
    assert occurs_on(rule, datetime.date(2028, 2, 29)) is True
    # Non-leap 2026 (rule starts 2027 so Feb 2027 is non-leap): clamps 28.
    assert occurs_on(rule, datetime.date(2027, 2, 28)) is True


# ---------------------------------------------------------------------------
# Full-year sweeps: the 29th, 30th, 31st across leap and non-leap years
# ---------------------------------------------------------------------------


def _sweep_monthly(rule: ScheduleRule, year: int) -> list[tuple[int, int]]:
    """Every (month, day) in ``rule``'s year the engine says fires."""
    hits = []
    for month in range(1, 13):
        for day in range(1, _month_end(year, month) + 1):
            if occurs_on(rule, datetime.date(year, month, day)):
                hits.append((month, day))
    return hits


def test_full_year_day_31_sweep_2026() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )
    # Exactly one firing per month, twelve total.
    hits = _sweep_monthly(rule, 2026)
    assert len(hits) == 12
    by_month = dict(hits)
    assert (by_month[1], by_month[2], by_month[4]) == (31, 28, 30)
    assert by_month[2] == 28  # 2026 Feb is non-leap
    assert by_month[4] == 30
    # Each month has exactly one firing.
    months = [month for month, _ in hits]
    assert months == list(range(1, 13))


def test_full_year_day_31_sweep_2028_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2028-01-31",
    )
    hits = _sweep_monthly(rule, 2028)
    by_month = dict(hits)
    assert by_month[2] == 29  # leap February clamps to the 29th
    assert by_month[4] == 30
    months = [month for month, _ in hits]
    assert months == list(range(1, 13))


def test_full_year_day_30_sweep_2028() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=30,
        start_date="2028-01-30",
    )
    hits = _sweep_monthly(rule, 2028)
    by_month = dict(hits)
    assert by_month[2] == 29  # leap Feb clamps to 29
    months = [month for month, _ in hits]
    assert months == list(range(1, 13))


def test_full_year_day_29_sweep_2027_non_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=29,
        start_date="2027-01-29",
    )
    hits = _sweep_monthly(rule, 2027)
    by_month = dict(hits)
    assert by_month[2] == 28  # non-leap Feb clamps to the 28th
    months = [month for month, _ in hits]
    assert months == list(range(1, 13))


def test_full_year_day_29_sweep_2028_leap() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=29,
        start_date="2028-01-29",
    )
    hits = _sweep_monthly(rule, 2028)
    by_month = dict(hits)
    assert by_month[2] == 29  # leap Feb has a real 29th: nominal day
    months = [month for month, _ in hits]
    assert months == list(range(1, 13))


# ---------------------------------------------------------------------------
# Interval arithmetic
# ---------------------------------------------------------------------------


def test_monthly_interval_2_every_second_month() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15, interval=2,
        start_date="2026-01-15",
    )
    assert occurs_on(rule, datetime.date(2026, 1, 15)) is True
    assert occurs_on(rule, datetime.date(2026, 2, 15)) is False
    assert occurs_on(rule, datetime.date(2026, 3, 15)) is True
    assert occurs_on(rule, datetime.date(2026, 4, 15)) is False
    assert occurs_on(rule, datetime.date(2026, 5, 15)) is True


def test_monthly_interval_2_clamped_month_end_alignment() -> None:
    """Interval counts nominal months from the anchor: Jan 31 anchor,
    every 2 months -> Jan (m0), Mar (m2), May (m4), Jul (m6).  Clamped
    firings (Feb 28, Apr 30, Jun 30) occur only in interval months."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31, interval=2,
        start_date="2026-01-31",
    )
    assert occurs_on(rule, datetime.date(2026, 1, 31)) is True   # m0
    assert occurs_on(rule, datetime.date(2026, 2, 28)) is False  # m1
    assert occurs_on(rule, datetime.date(2026, 3, 31)) is True   # m2
    assert occurs_on(rule, datetime.date(2026, 4, 30)) is False  # m3
    assert occurs_on(rule, datetime.date(2026, 5, 31)) is True   # m4
    assert occurs_on(rule, datetime.date(2026, 6, 30)) is False  # m5
    assert occurs_on(rule, datetime.date(2026, 7, 31)) is True   # m6


def test_monthly_interval_arithmetic_across_year_boundary() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15, interval=2,
        start_date="2026-11-15",
    )
    # Nov (m0) fires, Jan 2027 (m2) fires, Mar (m4) fires.
    assert occurs_on(rule, datetime.date(2026, 11, 15)) is True
    assert occurs_on(rule, datetime.date(2026, 12, 15)) is False
    assert occurs_on(rule, datetime.date(2027, 1, 15)) is True
    assert occurs_on(rule, datetime.date(2027, 2, 15)) is False
    assert occurs_on(rule, datetime.date(2027, 3, 15)) is True


def test_monthly_day_occurrences_between_span() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )
    result = occurrences_between(rule, "2026-01-01", "2026-06-30")
    assert result == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30",
        "2026-05-31", "2026-06-30",
    ]


def test_monthly_day_occurrences_between_rejects_inverted() -> None:
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=15,
        start_date="2026-01-15",
    )
    with pytest.raises(RuleValidationError, match="on or after"):
        occurrences_between(rule, "2026-06-15", "2026-01-15")


def test_monthly_day_clamp_is_one_firing_per_month(tmp_path) -> None:
    """The clamp must not double-fire: only one day per month matches."""
    rule = ScheduleRule(
        rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
        start_date="2026-01-31",
    )
    hits = _sweep_monthly(rule, 2026)
    months = [month for month, _ in hits]
    assert months == sorted(months)
    assert len(months) == len(set(months)) == 12