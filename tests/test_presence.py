"""Tests for presence.py: the Feature 05 custody model."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.presence import (
    MAX_CYCLE_LENGTH_WEEKS,
    PresenceEngine,
    PresenceOverride,
    PresenceSchedule,
    cycle_week_index,
)


ANCHOR = datetime.date(2026, 1, 5)  # a Monday

TWO_WEEK_PATTERN = {0: {0, 2, 4}, 1: {1, 3}}


# ---------------------------------------------------------------------------
# PresenceSchedule construction
# ---------------------------------------------------------------------------


def test_schedule_holds_validated_fields() -> None:
    schedule = PresenceSchedule(
        3, 2, "2026-01-05", {0: {0, 2, 4}, 1: {1, 3}}
    )
    assert schedule.child_id == 3
    assert schedule.cycle_length_weeks == 2
    assert schedule.anchor_date == ANCHOR
    assert schedule.pattern == {0: frozenset({0, 2, 4}), 1: frozenset({1, 3})}


def test_schedule_accepts_date_objects() -> None:
    schedule = PresenceSchedule(1, 1, ANCHOR, {0: {0}})
    assert schedule.anchor_date is ANCHOR


def test_schedule_rejects_cycle_length_below_one() -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        PresenceSchedule(1, 0, ANCHOR, {})
    with pytest.raises(ValueError, match="between 1 and"):
        PresenceSchedule(1, -1, ANCHOR, {})


def test_schedule_rejects_cycle_length_above_documented_cap() -> None:
    """The 4 cap matches the schema's CHECK — both documents agree."""
    with pytest.raises(ValueError, match="between 1 and"):
        PresenceSchedule(1, MAX_CYCLE_LENGTH_WEEKS + 1, ANCHOR, {})
    assert MAX_CYCLE_LENGTH_WEEKS == 4


@pytest.mark.parametrize("bad", [True, "2", 1.0, None])
def test_schedule_rejects_non_int_cycle_length(bad) -> None:
    with pytest.raises(ValueError, match="cycle_length_weeks must be an integer"):
        PresenceSchedule(1, bad, ANCHOR, {0: {0}})


def test_schedule_rejects_pattern_missing_week_indices() -> None:
    with pytest.raises(ValueError, match="missing \\[1\\]"):
        PresenceSchedule(1, 2, ANCHOR, {0: {0, 2}})


def test_schedule_rejects_pattern_with_extra_week_indices() -> None:
    with pytest.raises(ValueError, match="week index must be in 0"):
        PresenceSchedule(1, 2, ANCHOR, {0: {0}, 1: {1}, 2: {2}})


def test_schedule_rejects_pattern_with_non_int_week_keys() -> None:
    with pytest.raises(ValueError, match="week index must be an integer"):
        PresenceSchedule(1, 1, ANCHOR, {"0": {0}})


def test_schedule_rejects_pattern_with_bool_week_key() -> None:
    """True would silently be week 1; bools are never valid indices."""
    with pytest.raises(ValueError, match="week index must be an integer"):
        PresenceSchedule(1, 2, ANCHOR, {0: {0}, True: {1}})


@pytest.mark.parametrize("bad_weekday", [-1, 7, 100])
def test_schedule_rejects_weekday_outside_zero_to_six(bad_weekday) -> None:
    with pytest.raises(ValueError, match="weekday must be in 0..6"):
        PresenceSchedule(1, 1, ANCHOR, {0: {bad_weekday}})


@pytest.mark.parametrize("bad", [True, "1", 1.5, None])
def test_schedule_rejects_non_int_weekdays(bad) -> None:
    with pytest.raises(ValueError, match="weekday must be an int"):
        PresenceSchedule(1, 1, ANCHOR, {0: [bad]})


def test_schedule_rejects_string_and_none_week_sets() -> None:
    """A string is iterable — "02" would silently mean {0, 2}."""
    with pytest.raises(ValueError, match="iterable of weekday ints"):
        PresenceSchedule(1, 1, ANCHOR, {0: "02"})
    with pytest.raises(ValueError, match="iterable of weekday ints"):
        PresenceSchedule(1, 1, ANCHOR, {0: None})


def test_schedule_rejects_non_dict_pattern() -> None:
    with pytest.raises(ValueError, match="must map week index"):
        PresenceSchedule(1, 1, ANCHOR, "0,2")


@pytest.mark.parametrize("bad", [True, 1.0, "2026-01-05", None])
def test_schedule_rejects_non_int_child_id(bad) -> None:
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceSchedule(bad, 1, ANCHOR, {0: {0}})


@pytest.mark.parametrize(
    "bad", ["2026-1-5", "2026/01/05", "not-a-date", 5, None, True]
)
def test_schedule_rejects_non_strict_anchor_dates(bad) -> None:
    with pytest.raises(ValueError, match="anchor_date"):
        PresenceSchedule(1, 1, bad, {0: {0}})


def test_schedule_empty_week_means_absent_week() -> None:
    """An explicitly empty week is valid: absent every day of it —
    distinct from having no schedule (the engine's default)."""
    schedule = PresenceSchedule(1, 2, ANCHOR, {0: {0, 2}, 1: set()})
    assert schedule.pattern[1] == frozenset()


def test_schedule_empty_week_encodes_as_empty_segment() -> None:
    schedule = PresenceSchedule(1, 2, ANCHOR, {0: {0, 2}, 1: set()})
    assert schedule.encode() == "0,2|"


def test_schedule_equal_patterns_are_equal_and_encode_identically() -> None:
    one = PresenceSchedule(1, 2, ANCHOR, {0: {4, 2, 0}, 1: {3, 1}})
    two = PresenceSchedule(2, 2, ANCHOR, {0: {0, 2, 4}, 1: {1, 3}})
    assert one.encode() == two.encode() == "0,2,4|1,3"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "encoded",
    [
        "0,2,4|1,3",
        "0|1,2,3,4,5,6",
        "|",
        "0,2|",
        "|0,2",
        "6",
        "0,1,2,3,4,5,6|",
    ],
)
def test_schedule_decode_encode_round_trips_losslessly(encoded) -> None:
    schedule = PresenceSchedule.decode(1, ANCHOR, encoded)
    assert schedule.encode() == encoded
    again = PresenceSchedule.decode(1, ANCHOR, schedule.encode())
    assert again == schedule


def test_schedule_decode_sets_cycle_length_from_segments() -> None:
    one_week = PresenceSchedule.decode(1, ANCHOR, "0,2,4")
    assert one_week.cycle_length_weeks == 1
    four_week = PresenceSchedule.decode(1, ANCHOR, "0|1|2|3,4")
    assert four_week.cycle_length_weeks == 4


def test_schedule_decode_rejects_malformed_segments() -> None:
    for bad in ("0,12|1", "0,,2|1", "x|1", "0|-1|2", "8", "0,|1"):
        with pytest.raises(ValueError, match="invalid weekday"):
            PresenceSchedule.decode(1, ANCHOR, bad)


def test_schedule_decode_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        PresenceSchedule.decode(1, ANCHOR, None)


def test_schedule_decode_rejects_too_many_segments(tmp_path) -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        PresenceSchedule.decode(1, ANCHOR, "0|1|2|3|4")


# ---------------------------------------------------------------------------
# PresenceOverride
# ---------------------------------------------------------------------------


def test_override_single_date_and_range_cover() -> None:
    single = PresenceOverride(1, "2026-07-20", "2026-07-20", False)
    assert single.covers(datetime.date(2026, 7, 20))
    assert not single.covers(datetime.date(2026, 7, 21))
    span = PresenceOverride(1, "2026-07-20", "2026-07-24", True, note="trade")
    assert span.covers(datetime.date(2026, 7, 22))
    assert not span.covers(datetime.date(2026, 7, 19))
    assert not span.covers(datetime.date(2026, 7, 25))
    assert span.note == "trade"


def test_override_end_before_start_rejected() -> None:
    with pytest.raises(ValueError, match="end_date must be on or after"):
        PresenceOverride(1, "2026-07-24", "2026-07-20", True)


@pytest.mark.parametrize("bad", ["1", 0, 1.0, None])
def test_override_rejects_non_bool_is_present(bad) -> None:
    with pytest.raises(ValueError, match="is_present must be a real bool"):
        PresenceOverride(1, "2026-07-20", "2026-07-20", bad)


@pytest.mark.parametrize("bad", [5, ["note"], 1.5])
def test_override_rejects_non_string_note(bad) -> None:
    with pytest.raises(ValueError, match="note must be a string or None"):
        PresenceOverride(1, "2026-07-20", "2026-07-20", True, note=bad)


@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_override_rejects_non_int_child_id(bad) -> None:
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceOverride(bad, "2026-07-20", "2026-07-20", True)


@pytest.mark.parametrize(
    ("start", "end"), [("2026-7-20", "2026-07-20"), ("nope", "2026-07-20")]
)
def test_override_rejects_non_strict_dates(start, end) -> None:
    with pytest.raises(ValueError, match="date"):
        PresenceOverride(1, start, end, True)


def test_schedule_rejects_datetime_anchor() -> None:
    """datetime.datetime subclasses date: a bare isinstance check would
    store a time component and every date comparison would TypeError."""
    with pytest.raises(ValueError, match="plain calendar date"):
        PresenceSchedule(1, 1, datetime.datetime(2026, 1, 5, 9, 30), {0: {0}})


def test_override_rejects_datetime_bounds() -> None:
    with pytest.raises(ValueError, match="plain calendar date"):
        PresenceOverride(
            1, datetime.datetime(2026, 7, 20), "2026-07-20", True
        )


def test_schedule_pattern_is_immutable_after_construction() -> None:
    """The frozen schedule must not leak a mutable dict: injecting
    unvalidated weekdays or dropping required weeks after construction
    would bypass total validation."""
    schedule = PresenceSchedule(1, 2, ANCHOR, {0: {0, 2}, 1: {1}})
    with pytest.raises(TypeError):
        schedule.pattern[0] = {9}
    with pytest.raises(TypeError):
        del schedule.pattern[1]
    # mappingproxy exposes no mutators at all.
    assert not any(
        hasattr(schedule.pattern, name)
        for name in ("clear", "pop", "popitem", "setdefault", "update")
    )
    # The validated contents are still readable and encode correctly.
    assert schedule.pattern[0] == frozenset({0, 2})
    assert schedule.encode() == "0,2|1"


# ---------------------------------------------------------------------------
# Cycle arithmetic: anchor-date only, never ISO week parity
# ---------------------------------------------------------------------------


def test_cycle_week_index_follows_the_anchor_formula() -> None:
    schedule = PresenceSchedule(1, 2, ANCHOR, {0: {0}, 1: {1}})
    # The anchor day starts week 0; each whole 7 days steps the cycle.
    offsets = {0: 0, 1: 0, 6: 0, 7: 1, 8: 1, 13: 1, 14: 0, 15: 0, 22: 1}
    for offset, expected in offsets.items():
        assert (
            cycle_week_index(
                schedule, ANCHOR + datetime.timedelta(days=offset)
            )
            == expected
        ), f"offset {offset}"


def test_cycle_week_index_before_the_anchor_walks_backwards() -> None:
    """Python floor division: day -1 is the LAST week of the cycle,
    wrapping backwards — never inverting."""
    schedule = PresenceSchedule(1, 2, ANCHOR, {0: {0}, 1: {1}})
    assert cycle_week_index(schedule, ANCHOR - datetime.timedelta(days=1)) == 1
    assert cycle_week_index(schedule, ANCHOR - datetime.timedelta(days=7)) == 1
    assert cycle_week_index(schedule, ANCHOR - datetime.timedelta(days=8)) == 0


def test_cycle_week_index_three_week_pattern() -> None:
    schedule = PresenceSchedule(
        1, 3, ANCHOR, {0: {0}, 1: {1}, 2: {2}}
    )
    offsets = [0, 7, 14, 21, 28]
    assert [cycle_week_index(schedule, ANCHOR + datetime.timedelta(days=o)) for o in offsets] == [
        0, 1, 2, 0, 1
    ]


def test_cycle_week_index_stable_across_three_year_boundaries() -> None:
    """The regression this exists for: walking day by day through a
    December 31st -> January 1st boundary, the cycle index steps by 0
    or +1 (mod cycle length) and NEVER resets or inverts — including
    2020, a 53-ISO-week year, where ISO week parity flips and would
    invert a two-week custody schedule on January 1st."""
    schedule = PresenceSchedule(
        1, 2, datetime.date(2019, 1, 6), {0: {0, 2, 4}, 1: {1, 3}}
    )
    # Independently derived expectations (anchor 2019-01-06, index =
    # floor(days-since-anchor / 7) % 2, hand-verified) — hardcoded so
    # even an implementation that resets or inverts at January 1st
    # cannot pass by coincidence:
    expected = {
        # 2019 -> 2020 boundary
        datetime.date(2019, 12, 26): 0,
        datetime.date(2019, 12, 27): 0,
        datetime.date(2019, 12, 28): 0,
        datetime.date(2019, 12, 29): 1,
        datetime.date(2019, 12, 30): 1,
        datetime.date(2019, 12, 31): 1,
        datetime.date(2020, 1, 1): 1,
        datetime.date(2020, 1, 2): 1,
        datetime.date(2020, 1, 3): 1,
        datetime.date(2020, 1, 4): 1,
        datetime.date(2020, 1, 5): 0,
        datetime.date(2020, 1, 6): 0,
        datetime.date(2020, 1, 7): 0,
        # 2020 (53 ISO weeks) -> 2021 boundary
        datetime.date(2020, 12, 27): 1,
        datetime.date(2020, 12, 28): 1,
        datetime.date(2020, 12, 29): 1,
        datetime.date(2020, 12, 30): 1,
        datetime.date(2020, 12, 31): 1,
        datetime.date(2021, 1, 1): 1,
        datetime.date(2021, 1, 2): 1,
        datetime.date(2021, 1, 3): 0,
        datetime.date(2021, 1, 4): 0,
        datetime.date(2021, 1, 5): 0,
        datetime.date(2021, 1, 6): 0,
        datetime.date(2021, 1, 7): 0,
        # 2021 -> 2022 boundary
        datetime.date(2021, 12, 27): 1,
        datetime.date(2021, 12, 28): 1,
        datetime.date(2021, 12, 29): 1,
        datetime.date(2021, 12, 30): 1,
        datetime.date(2021, 12, 31): 1,
        datetime.date(2022, 1, 1): 1,
        datetime.date(2022, 1, 2): 0,
        datetime.date(2022, 1, 3): 0,
        datetime.date(2022, 1, 4): 0,
        datetime.date(2022, 1, 5): 0,
        datetime.date(2022, 1, 6): 0,
        datetime.date(2022, 1, 7): 0,
    }
    for day, wanted in expected.items():
        got = cycle_week_index(schedule, day)
        assert got == wanted, f"{day}: expected week {wanted}, got {got}"
    # And 2020 really is the 53-ISO-week year this guards against.
    assert datetime.date(2020, 12, 31).isocalendar()[1] == 53


def test_module_uses_no_iso_week_functions() -> None:
    """D-004 guardrail: cycle math never reads ISO week numbers."""
    from pathlib import Path

    source = Path(
        __import__("custom_components.nestquest.presence", fromlist=["__file__"]).__file__
    ).read_text()
    assert "isocalendar" not in source
    assert "isoweek" not in source


# ---------------------------------------------------------------------------
# PresenceEngine: is_present with the always-present default
# ---------------------------------------------------------------------------


def _three_child_engine() -> PresenceEngine:
    """Two children on opposite weeks of one two-week rotation, one
    with no schedule at all (the always-present sibling)."""
    anchor = datetime.date(2026, 1, 5)  # Monday, week 0
    declan = PresenceSchedule(
        1, 2, anchor, {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()}
    )
    jordyn = PresenceSchedule(
        2, 2, anchor, {0: set(), 1: {0, 1, 2, 3, 4, 5, 6}}
    )
    return PresenceEngine({1: declan, 2: jordyn})


def test_engine_child_without_schedule_is_always_present() -> None:
    """Every day of the four-week span, all three children get the
    expected verdict: Chloe (no schedule) always present; the two
    rotation children complementary per the anchor pattern."""
    engine = _three_child_engine()
    anchor = datetime.date(2026, 1, 5)
    for offset in range(28):
        day = anchor + datetime.timedelta(days=offset)
        week = ((day - anchor).days // 7) % 2
        assert engine.is_present(3, day) is True, f"offset {offset}: Chloe"
        assert engine.is_present(1, day) is (week == 0), (
            f"offset {offset}: Declan should follow week {week}"
        )
        assert engine.is_present(2, day) is (week == 1), (
            f"offset {offset}: Jordyn should follow week {week}"
        )


def test_engine_alternating_children_are_complementary_for_four_weeks() -> None:
    """Every day of a four-week span: the two rotation children swap
    presence exactly per the anchor pattern — when one is home the
    other is away."""
    engine = _three_child_engine()
    anchor = datetime.date(2026, 1, 5)
    for offset in range(28):
        day = anchor + datetime.timedelta(days=offset)
        d = engine.is_present(1, day)
        j = engine.is_present(2, day)
        assert d == (not j), f"offset {offset}: {d}/{j} not complementary"
        expected_week = ((day - anchor).days // 7) % 2
        expected_present = day.weekday() in {0, 1, 2, 3, 4, 5, 6}
        assert engine.is_present(1, day) == (expected_week == 0), (
            f"offset {offset}: Declan week {expected_week}"
        )
    # Spot-check the swap days.
    assert engine.is_present(1, anchor) is True
    assert engine.is_present(2, anchor) is False
    assert engine.is_present(1, anchor + datetime.timedelta(days=7)) is False
    assert engine.is_present(2, anchor + datetime.timedelta(days=7)) is True


def test_engine_weekend_absence_respects_the_pattern() -> None:
    """A weekday-set pattern excludes days outside the set even in the
    child's present week."""
    engine = PresenceEngine(
        {
            1: PresenceSchedule(
                1, 2, datetime.date(2026, 1, 5), {0: {1, 3}, 1: {2, 4}}
            )
        }
    )
    # 2026-01-06 (Tue) is week 0, weekday 1 -> present.
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is True
    # 2026-01-07 (Wed) is week 0, weekday 2 -> absent.
    assert engine.is_present(1, datetime.date(2026, 1, 7)) is False
    # 2026-01-14 (Wed) is week 1, weekday 2 -> present.
    assert engine.is_present(1, datetime.date(2026, 1, 14)) is True


def test_engine_rejects_bad_construction_and_inputs() -> None:
    schedule = PresenceSchedule(1, 1, ANCHOR, {0: {0}})
    with pytest.raises(ValueError, match="must map child_id"):
        PresenceEngine([schedule])
    with pytest.raises(ValueError, match="must be a PresenceSchedule"):
        PresenceEngine({1: "not-a-schedule"})
    with pytest.raises(ValueError, match="holds the schedule"):
        PresenceEngine({2: schedule})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({True: schedule})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({1.0: PresenceSchedule(1, 1, ANCHOR, {0: {0}})})
    engine = PresenceEngine({1: schedule})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        engine.is_present(True, ANCHOR)
    with pytest.raises(ValueError, match="plain calendar date"):
        engine.is_present(1, datetime.datetime(2026, 1, 5))


def test_engine_is_immutable() -> None:
    engine = _three_child_engine()
    with pytest.raises(AttributeError, match="immutable snapshot"):
        engine._schedules = {}
    with pytest.raises(AttributeError, match="immutable snapshot"):
        engine.something_new = 1


# ---------------------------------------------------------------------------
# Overrides take precedence over the pattern
# ---------------------------------------------------------------------------


def _engine_with_overrides(*overrides_for_declan) -> PresenceEngine:
    anchor = datetime.date(2026, 1, 5)  # Monday
    return PresenceEngine(
        {
            1: PresenceSchedule(
                1, 2, anchor, {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()}
            )
        },
        overrides={1: list(overrides_for_declan)} if overrides_for_declan else {},
    )


def test_absent_override_on_normally_present_day_wins() -> None:
    # 2026-01-06 is Tuesday of Declan's week 0: normally present.
    engine = _engine_with_overrides(
        PresenceOverride(1, "2026-01-06", "2026-01-06", False, note="away")
    )
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is False
    # The pattern resumes outside the override.
    assert engine.is_present(1, datetime.date(2026, 1, 7)) is True


def test_present_override_on_normally_absent_day_wins() -> None:
    # 2026-01-13 is in Declan's week 1 (away all week); a present
    # override on the Tuesday of week 1 brings him home for that day.
    engine = _engine_with_overrides(
        PresenceOverride(1, "2026-01-13", "2026-01-13", True, note="trade")
    )
    assert engine.is_present(1, datetime.date(2026, 1, 13)) is True
    assert engine.is_present(1, datetime.date(2026, 1, 14)) is False


def test_override_applies_without_a_schedule() -> None:
    """An override on a schedule-free child still applies: holidays and
    swaps must work for the always-present sibling too."""
    engine = PresenceEngine(
        {},
        overrides={
            3: [
                PresenceOverride(
                    3, "2026-07-20", "2026-07-24", False, note="holiday"
                )
            ]
        },
    )
    assert engine.is_present(3, datetime.date(2026, 7, 22)) is False
    assert engine.is_present(3, datetime.date(2026, 7, 19)) is True
    assert engine.is_present(3, datetime.date(2026, 7, 25)) is True


def test_override_range_beats_pattern_for_its_span() -> None:
    engine = _engine_with_overrides(
        PresenceOverride(1, "2026-01-13", "2026-01-17", True, note="traded week")
    )
    for offset in range(12, 17):
        day = datetime.date(2026, 1, 1) + datetime.timedelta(days=offset)
        assert engine.is_present(1, day) is True, f"{day}"
    # Days outside the span stay on the pattern (week 1: absent).
    assert engine.is_present(1, datetime.date(2026, 1, 12)) is False
    assert engine.is_present(1, datetime.date(2026, 1, 18)) is False


def test_engine_override_snapshot_validation() -> None:
    schedule = PresenceSchedule(1, 1, ANCHOR, {0: {0}})
    entry = PresenceOverride(1, "2026-07-20", "2026-07-20", True)
    with pytest.raises(ValueError, match="must map child_id"):
        PresenceEngine({1: schedule}, overrides=[entry])
    with pytest.raises(ValueError, match="must be a list"):
        PresenceEngine({1: schedule}, overrides={1: entry})
    with pytest.raises(ValueError, match="must be"):
        PresenceEngine({1: schedule}, overrides={1: ["nope"]})
    with pytest.raises(ValueError, match="holds an override"):
        PresenceEngine({1: schedule}, overrides={2: [entry]})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({1: schedule}, overrides={True: [entry]})


def test_engine_overlapping_snapshot_uses_latest_start() -> None:
    """The DAO layer refuses overlapping overrides per child; if a
    snapshot carries them anyway (hand-built), the latest start date
    wins deterministically."""
    engine = _engine_with_overrides(
        PresenceOverride(1, "2026-01-06", "2026-01-10", False),
        PresenceOverride(1, "2026-01-08", "2026-01-12", True),
    )
    # Jan 6-7: only the earlier override covers -> absent.
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is False
    # Jan 8-10: both cover; the LATER start (present) wins.
    assert engine.is_present(1, datetime.date(2026, 1, 9)) is True
    # Jan 11-12: only the later override covers -> present.
    assert engine.is_present(1, datetime.date(2026, 1, 11)) is True


def test_engine_override_lists_are_frozen() -> None:
    """The overrides snapshot must be truly read-only: mutating the
    caller's list after construction must not change answers."""
    entry = PresenceOverride(1, "2026-01-06", "2026-01-06", False)
    entries = [entry]
    engine = _engine_with_overrides(*entries)
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is False
    entries.append(PresenceOverride(1, "2026-01-07", "2026-01-07", False))
    # The late append must NOT change the engine's answers...
    assert engine.is_present(1, datetime.date(2026, 1, 7)) is True
    # Tuples have no append at all (AttributeError), and the mapping
    # itself refuses reassignment.
    with pytest.raises(AttributeError):
        engine._overrides[1].append(entry)
    with pytest.raises(AttributeError, match="immutable snapshot"):
        engine._overrides = {}
