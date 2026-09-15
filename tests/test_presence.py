"""Tests for presence.py: the Feature 05 custody model."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.presence import (
    MAX_CYCLE_LENGTH_WEEKS,
    PresenceOverride,
    PresenceSchedule,
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
