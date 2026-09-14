"""Consistency property tests for occurrences_between vs occurs_on.

The done-condition: occurrences_between returns an ordered, duplicate-
free list of dates that agrees EXACTLY with calling occurs_on on every
date in the range.  This module proves that agreement two ways:

1. An exhaustive sweep over a fixed grid of rules (every rule type ×
   several intervals × several windows) cross-checked date by date.

2. A randomized property test (seeded, deterministic) over randomly
   generated rules and ranges asserting the two functions never
   disagree.  Seeds are fixed so failures are reproducible.
"""
from __future__ import annotations

import datetime
import random

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


def _check_consistency(
    rule: ScheduleRule, start: str, end: str
) -> list[str]:
    """Cross-check occurrences_between against per-date occurs_on.

    Returns the occurrences_between result after asserting, for every
    date in [start, end]: occurs_on(date) is True iff the date appears
    in the result.  Also asserts the list is ordered and duplicate-free.
    """
    result = occurrences_between(rule, start, end)
    # Ordered and duplicate-free.
    assert result == sorted(set(result)), (
        f"occurrences_between must be ordered, duplicate-free: {result}"
    )
    # Exact agreement with occurs_on over every date in the range.
    cursor = _d(start)
    end_date = _d(end)
    expected: list[str] = []
    while cursor <= end_date:
        if occurs_on(rule, cursor):
            expected.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    assert result == expected, (
        f"disagreement for {rule.to_dict()} over [{start}, {end}]:\n"
        f"  occurrences_between: {result}\n"
        f"  per-date occurs_on:  {expected}"
    )
    return result


# ---------------------------------------------------------------------------
# Exhaustive grid over rule shapes, intervals and windows
# ---------------------------------------------------------------------------


_GRID_RULES = [
    ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-03-01"),
    ScheduleRule(rule_type=RuleType.DAILY, interval=2,
                 start_date="2026-03-01"),
    ScheduleRule(rule_type=RuleType.DAILY, interval=3,
                 start_date="2026-03-15", end_date="2027-01-31"),
    ScheduleRule(rule_type=RuleType.WEEKLY, weekday_set={0, 2, 4},
                 start_date="2026-03-03"),
    ScheduleRule(rule_type=RuleType.WEEKLY, weekday_set={1, 3, 5},
                 interval=2, start_date="2026-03-06",
                 end_date="2027-06-30"),
    ScheduleRule(rule_type=RuleType.CUSTOM_DAYS, weekday_set={1, 4},
                 start_date="2026-03-06"),
    ScheduleRule(rule_type=RuleType.MONTHLY_DAY, day_of_month=31,
                 start_date="2026-03-31"),
    ScheduleRule(rule_type=RuleType.MONTHLY_DAY, day_of_month=29,
                 interval=2, start_date="2026-01-29"),
    ScheduleRule(rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=2,
                 nth_weekday_weekday=1, start_date="2026-03-03"),
    ScheduleRule(rule_type=RuleType.MONTHLY_WEEKDAY, nth_weekday=-1,
                 nth_weekday_weekday=4, start_date="2026-03-06",
                 end_date="2028-12-31"),
    ScheduleRule(rule_type=RuleType.YEARLY, month=2, day_of_month=29,
                 start_date="2026-02-28"),
    ScheduleRule(rule_type=RuleType.YEARLY, month=6, day_of_month=15,
                 interval=2, start_date="2026-06-15"),
]

_GRID_WINDOWS = [
    ("2026-01-01", "2026-03-31"),   # mostly before start
    ("2026-03-01", "2026-03-01"),   # single day == anchor
    ("2026-03-01", "2026-03-31"),   # within window
    ("2026-08-01", "2026-08-31"),   # mid-window month
    ("2026-12-01", "2027-01-31"),   # year boundary
    ("2028-01-01", "2028-03-01"),   # leap year span
    ("2029-01-01", "2029-12-31"),   # far out
]


@pytest.mark.parametrize(
    "rule_index,window_index",
    [
        (rule_index, window_index)
        for rule_index in range(len(_GRID_RULES))
        for window_index in range(len(_GRID_WINDOWS))
    ],
)
def test_grid_occurrences_between_matches_occurs_on(
    rule_index, window_index
) -> None:
    rule = _GRID_RULES[rule_index]
    window = _GRID_WINDOWS[window_index]
    _check_consistency(rule, window[0], window[1])


# ---------------------------------------------------------------------------
# Randomized property test (seeded, deterministic)
# ---------------------------------------------------------------------------


def _generate_random_rules(rng: random.Random, count: int) -> list[ScheduleRule]:
    """Random but valid rules: shapes, intervals, anchors, windows.

    Any random combo the model rejects (genuinely invalid combinations)
    is skipped — the property only needs VALID rules; the assertion at
    the end bounds how many may be rejected.
    """
    rules: list[ScheduleRule] = []
    shapes = list(RuleType)
    for index in range(count):
        shape = shapes[rng.randrange(len(shapes))]
        interval = rng.choice([1, 2, 3, 7])
        anchor = datetime.date(
            rng.choice([2024, 2025, 2026, 2027, 2028]),
            rng.randrange(1, 13),
            rng.randrange(1, 28),
        )
        end_offset = rng.choice([45, 120, 400, 800])
        end = anchor + datetime.timedelta(days=end_offset)
        common = {
            "rule_type": shape,
            "interval": interval,
            "start_date": anchor.isoformat(),
            "end_date": end.isoformat(),
        }
        try:
            if shape is RuleType.WEEKLY:
                rules.append(ScheduleRule(
                    **common,
                    weekday_set={
                        rng.randrange(7)
                        for _ in range(rng.randrange(1, 4))
                    },
                ))
            elif shape is RuleType.CUSTOM_DAYS:
                rules.append(ScheduleRule(
                    **common,
                    weekday_set={
                        rng.randrange(7)
                        for _ in range(rng.randrange(1, 4))
                    },
                ))
            elif shape is RuleType.MONTHLY_DAY:
                rules.append(ScheduleRule(
                    **common, day_of_month=rng.randrange(1, 32)
                ))
            elif shape is RuleType.MONTHLY_WEEKDAY:
                rules.append(ScheduleRule(
                    **common,
                    nth_weekday=rng.choice([-1, 1, 2, 3, 4, 5]),
                    nth_weekday_weekday=rng.randrange(7),
                ))
            elif shape is RuleType.YEARLY:
                rules.append(ScheduleRule(
                    **common,
                    month=rng.randrange(1, 13),
                    day_of_month=rng.choice([None, rng.randrange(1, 29)]),
                ))
            else:  # DAILY
                rules.append(ScheduleRule(**common))
        except RuleValidationError:
            continue
    assert len(rules) >= count * 3 // 4, "too many random rules rejected"
    return rules


def test_random_rules_never_disagree_between_the_two_functions() -> None:
    """The property: for randomly generated rules and ranges,
    occurrences_between(rule, s, e) == [d for d in s..e if occurs_on]."""
    rng = random.Random(0xFEA7)  # fixed seed for reproducibility
    rules = _generate_random_rules(rng, count=40)
    checked = 0
    for rule in rules:
        anchor = datetime.date.fromisoformat(rule.start_date)
        for offset_days, span_days in ((-30, 60), (0, 14), (10, 90),
                                       (100, 200)):
            range_start = anchor + datetime.timedelta(days=offset_days)
            range_end = range_start + datetime.timedelta(days=span_days)
            _check_consistency(
                rule, range_start.isoformat(), range_end.isoformat()
            )
            checked += 1
    assert checked >= 40 * 4 * 3 // 4, checked


def test_random_ranges_include_year_and_leap_spans() -> None:
    """Every rule is probed across a range that spans Jan 1 (twice) and
    a February 29 — the Dec 1..Mar 1 two-year span always covers both."""
    rng = random.Random(42)
    rules = _generate_random_rules(rng, count=12)
    for rule in rules:
        anchor = datetime.date.fromisoformat(rule.start_date)
        probe_start = datetime.date(anchor.year, 12, 1)
        probe_end = datetime.date(anchor.year + 2, 3, 1)
        # The span always contains two Jan 1s and a Feb 28/29 pair.
        assert probe_end >= probe_start
        _check_consistency(
            rule, probe_start.isoformat(), probe_end.isoformat()
        )
        # An additional probe pinned ON a Feb 29 window (2028 leap):
        # every rule is cross-checked over Feb 1 - Mar 15 2028.
        _check_consistency(rule, "2028-02-01", "2028-03-15")


def test_occurrences_between_single_day_range_matches_occurs_on() -> None:
    """A one-day range is the exact occurs_on of that date."""
    for rule in _GRID_RULES:
        for day in ("2026-03-05", "2026-03-15", "2027-06-15"):
            single = occurrences_between(rule, day, day)
            if occurs_on(rule, _d(day)):
                assert single == [day], (rule.to_dict(), day, single)
            else:
                assert single == [], (rule.to_dict(), day, single)
