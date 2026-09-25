"""Tests for the schema-9 multi-pattern presence engine.

A child carries zero or more :class:`PresencePattern` rules; the
engine resolves them override -> away -> home -> default.  The
expectations below are written out literally, week by week, rather
than recomputed with the engine's own arithmetic, so a wrong cycle
position cannot agree with itself.
"""
from __future__ import annotations

import datetime

from custom_components.nestquest.core.presence import (
    PresenceEngine,
    PresenceOverride,
    PresencePattern,
)

CHILD = 1

#: The owner's rules, both anchored on Monday 2026-09-07 (cycle week 0).
AWAY_THU_FRI = PresencePattern(
    CHILD, "Thursdays and Fridays away", "away", 1, "2026-09-07", {0: {3, 4}}
)
AWAY_ALTERNATE_WEEKENDS = PresencePattern(
    CHILD, "Weekends away", "away", 2, "2026-09-07", {0: {5, 6}, 1: set()}
)


def _owner_engine(overrides=None) -> PresenceEngine:
    return PresenceEngine(
        {CHILD: [AWAY_THU_FRI, AWAY_ALTERNATE_WEEKENDS]}, overrides
    )


def _week(engine: PresenceEngine, monday: str) -> str:
    """Render one Monday..Sunday week as ``P`` (present) / ``A`` (away)."""
    start = datetime.date.fromisoformat(monday)
    assert start.weekday() == 0, monday
    return "".join(
        "P" if engine.is_present(CHILD, start + datetime.timedelta(days=d))
        else "A"
        for d in range(7)
    )


def test_owner_scenario_day_by_day_across_several_weeks() -> None:
    """Away Thu+Fri every week, plus away Sat+Sun every other week."""
    engine = _owner_engine()
    #            Mon..Sun
    expected = {
        "2026-08-31": "PPPAAPP",  # cycle week 1, before the anchor
        "2026-09-07": "PPPAAAA",  # anchor week: weekend away
        "2026-09-14": "PPPAAPP",
        "2026-09-21": "PPPAAAA",
        "2026-09-28": "PPPAAPP",
        "2026-10-05": "PPPAAAA",
        "2026-10-12": "PPPAAPP",
        "2026-10-19": "PPPAAAA",
    }
    assert {monday: _week(engine, monday) for monday in expected} == expected


def test_owner_scenario_across_the_year_boundary() -> None:
    """2026 has 53 ISO weeks; the alternation must not skip a beat."""
    engine = _owner_engine()
    expected = {
        "2026-12-21": "PPPAAPP",  # Dec 26-27 home
        "2026-12-28": "PPPAAAA",  # Jan 1 (Fri) and Jan 2-3 away
        "2027-01-04": "PPPAAPP",  # Jan 9-10 home
        "2027-01-11": "PPPAAAA",  # Jan 16-17 away
    }
    assert {monday: _week(engine, monday) for monday in expected} == expected


def test_owner_scenario_through_a_leap_day() -> None:
    """February 29th 2028 is an ordinary Tuesday in the cycle."""
    engine = _owner_engine()
    expected = {
        "2028-02-21": "PPPAAAA",  # Feb 26-27 away
        "2028-02-28": "PPPAAPP",  # Tue Feb 29 home; Mar 4-5 home
        "2028-03-06": "PPPAAAA",  # Mar 11-12 away
    }
    assert {monday: _week(engine, monday) for monday in expected} == expected
    assert engine.is_present(CHILD, datetime.date(2028, 2, 29)) is True


def test_cycle_position_ignores_iso_week_parity() -> None:
    """D-004: consecutive Saturdays in odd ISO weeks 53 and 1 alternate.

    2027-01-02 sits in ISO week 53 of 2026 and 2027-01-09 in ISO week 1
    of 2027 — both odd, so a week-parity rule would give them the SAME
    answer.  Anchor-date arithmetic puts them in consecutive cycle
    weeks, so the alternate-weekend pattern covers exactly one.
    """
    first = datetime.date(2027, 1, 2)
    second = datetime.date(2027, 1, 9)
    assert first.isocalendar()[1] % 2 == second.isocalendar()[1] % 2 == 1
    assert AWAY_ALTERNATE_WEEKENDS.covers(first) is True
    assert AWAY_ALTERNATE_WEEKENDS.covers(second) is False
    engine = _owner_engine()
    assert engine.is_present(CHILD, first) is False
    assert engine.is_present(CHILD, second) is True


def test_child_with_no_patterns_is_present_every_day() -> None:
    engine = _owner_engine()
    other = 2
    start = datetime.date(2026, 12, 1)
    for offset in range(120):
        assert engine.is_present(other, start + datetime.timedelta(days=offset))
    empty = PresenceEngine({})
    assert all(
        empty.is_present(CHILD, start + datetime.timedelta(days=offset))
        for offset in range(120)
    )


def test_overrides_beat_patterns_both_ways() -> None:
    engine = _owner_engine(
        {
            CHILD: [
                # A Thursday the away pattern covers: present override.
                PresenceOverride(CHILD, "2026-09-10", "2026-09-10", True),
                # A Monday no pattern covers: absent override.
                PresenceOverride(CHILD, "2026-09-14", "2026-09-14", False),
            ]
        }
    )
    assert engine.is_present(CHILD, datetime.date(2026, 9, 10)) is True
    assert engine.is_present(CHILD, datetime.date(2026, 9, 14)) is False
    # The day after each override the patterns answer again.
    assert engine.is_present(CHILD, datetime.date(2026, 9, 11)) is False
    assert engine.is_present(CHILD, datetime.date(2026, 9, 15)) is True


def test_away_beats_home_where_both_cover_a_date() -> None:
    home_every_day = PresencePattern(
        CHILD, "Home schedule", "home", 1, "2026-09-07",
        {0: {0, 1, 2, 3, 4, 5, 6}},
    )
    engine = PresenceEngine({CHILD: [home_every_day, AWAY_THU_FRI]})
    assert _week(engine, "2026-09-07") == "PPPAAPP"
    # Order of the patterns does not matter.
    reversed_engine = PresenceEngine({CHILD: [AWAY_THU_FRI, home_every_day]})
    assert _week(reversed_engine, "2026-09-07") == "PPPAAPP"


def test_home_patterns_mark_uncovered_days_away() -> None:
    """A home pattern lists the days the child IS here (schedule semantics).

    With at least one home pattern, a date no pattern covers is away —
    the retired single-schedule behaviour migration 9 preserves.  Two
    home patterns union their covered days.
    """
    weekdays = PresencePattern(
        CHILD, "School weeks", "home", 1, "2026-09-07", {0: {0, 1, 2}}
    )
    alternate_weekends = PresencePattern(
        CHILD, "Alternate weekends", "home", 2, "2026-09-07",
        {0: {5, 6}, 1: set()},
    )
    engine = PresenceEngine({CHILD: [weekdays, alternate_weekends]})
    assert _week(engine, "2026-09-07") == "PPPAAPP"
    assert _week(engine, "2026-09-14") == "PPPAAAA"
