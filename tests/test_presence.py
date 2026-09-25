"""Tests for presence.py: the Feature 05 custody model."""
from __future__ import annotations

import datetime

import pytest

from custom_components.nestquest.core.presence import (
    MAX_CYCLE_LENGTH_WEEKS,
    PATTERN_KINDS,
    PresenceEngine,
    PresenceOverride,
    PresencePattern,
    cycle_week_index,
)


ANCHOR = datetime.date(2026, 1, 5)  # a Monday

#: Every pre-schema-9 single schedule is exactly one ``home`` pattern
#: (migration 9 carries them across that way), so the model and engine
#: tests below use this name/kind unless they are about name or kind.
NAME = "Home schedule"
HOME = "home"

TWO_WEEK_PATTERN = {0: {0, 2, 4}, 1: {1, 3}}


# ---------------------------------------------------------------------------
# PresencePattern construction
# ---------------------------------------------------------------------------


def test_pattern_holds_validated_fields() -> None:
    pattern = PresencePattern(
        3, "Dad's weekends", "away", 2, "2026-01-05",
        {0: {0, 2, 4}, 1: {1, 3}},
    )
    assert pattern.child_id == 3
    assert pattern.name == "Dad's weekends"
    assert pattern.kind == "away"
    assert pattern.cycle_length_weeks == 2
    assert pattern.anchor_date == ANCHOR
    assert pattern.pattern == {0: frozenset({0, 2, 4}), 1: frozenset({1, 3})}


def test_pattern_accepts_date_objects() -> None:
    pattern = PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: {0}})
    assert pattern.anchor_date is ANCHOR


def test_pattern_name_is_stored_trimmed() -> None:
    pattern = PresencePattern(1, "  Mum's week \t", HOME, 1, ANCHOR, {0: {0}})
    assert pattern.name == "Mum's week"


@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_pattern_rejects_blank_name(bad) -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        PresencePattern(1, bad, HOME, 1, ANCHOR, {0: {0}})


@pytest.mark.parametrize("bad", [None, 5, b"Home", ["Home"]])
def test_pattern_rejects_non_string_name(bad) -> None:
    with pytest.raises(ValueError, match="name must be a string"):
        PresencePattern(1, bad, HOME, 1, ANCHOR, {0: {0}})


def test_pattern_kinds_are_home_and_away() -> None:
    """The model's kinds match the schema's CHECK exactly."""
    assert PATTERN_KINDS == ("home", "away")
    for kind in PATTERN_KINDS:
        assert PresencePattern(1, NAME, kind, 1, ANCHOR, {0: {0}}).kind == kind


@pytest.mark.parametrize("bad", ["Home", "AWAY", "present", "", None, True, 1])
def test_pattern_rejects_unknown_kind(bad) -> None:
    with pytest.raises(ValueError, match="kind must be one of home, away"):
        PresencePattern(1, NAME, bad, 1, ANCHOR, {0: {0}})


def test_pattern_rejects_cycle_length_below_one() -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        PresencePattern(1, NAME, HOME, 0, ANCHOR, {})
    with pytest.raises(ValueError, match="between 1 and"):
        PresencePattern(1, NAME, HOME, -1, ANCHOR, {})


def test_pattern_rejects_cycle_length_above_documented_cap() -> None:
    """The 4 cap matches the schema's CHECK — both documents agree."""
    with pytest.raises(ValueError, match="between 1 and"):
        PresencePattern(1, NAME, HOME, MAX_CYCLE_LENGTH_WEEKS + 1, ANCHOR, {})
    assert MAX_CYCLE_LENGTH_WEEKS == 4


@pytest.mark.parametrize("bad", [True, "2", 1.0, None])
def test_pattern_rejects_non_int_cycle_length(bad) -> None:
    with pytest.raises(ValueError, match="cycle_length_weeks must be an integer"):
        PresencePattern(1, NAME, HOME, bad, ANCHOR, {0: {0}})


def test_pattern_rejects_pattern_missing_week_indices() -> None:
    with pytest.raises(ValueError, match="missing \\[1\\]"):
        PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0, 2}})


def test_pattern_rejects_pattern_with_extra_week_indices() -> None:
    with pytest.raises(ValueError, match="week index must be in 0"):
        PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0}, 1: {1}, 2: {2}})


def test_pattern_rejects_pattern_with_non_int_week_keys() -> None:
    with pytest.raises(ValueError, match="week index must be an integer"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, {"0": {0}})


def test_pattern_rejects_pattern_with_bool_week_key() -> None:
    """True would silently be week 1; bools are never valid indices."""
    with pytest.raises(ValueError, match="week index must be an integer"):
        PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0}, True: {1}})


@pytest.mark.parametrize("bad_weekday", [-1, 7, 100])
def test_pattern_rejects_weekday_outside_zero_to_six(bad_weekday) -> None:
    with pytest.raises(ValueError, match="weekday must be in 0..6"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: {bad_weekday}})


@pytest.mark.parametrize("bad", [True, "1", 1.5, None])
def test_pattern_rejects_non_int_weekdays(bad) -> None:
    with pytest.raises(ValueError, match="weekday must be an int"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: [bad]})


def test_pattern_rejects_string_and_none_week_sets() -> None:
    """A string is iterable — "02" would silently mean {0, 2}."""
    with pytest.raises(ValueError, match="iterable of weekday ints"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: "02"})
    with pytest.raises(ValueError, match="iterable of weekday ints"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: None})


def test_pattern_rejects_non_dict_pattern() -> None:
    with pytest.raises(ValueError, match="must map week index"):
        PresencePattern(1, NAME, HOME, 1, ANCHOR, "0,2")


@pytest.mark.parametrize("bad", [True, 1.0, "2026-01-05", None])
def test_pattern_rejects_non_int_child_id(bad) -> None:
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresencePattern(bad, NAME, HOME, 1, ANCHOR, {0: {0}})


@pytest.mark.parametrize(
    "bad", ["2026-1-5", "2026/01/05", "not-a-date", 5, None, True]
)
def test_pattern_rejects_non_strict_anchor_dates(bad) -> None:
    with pytest.raises(ValueError, match="anchor_date"):
        PresencePattern(1, NAME, HOME, 1, bad, {0: {0}})


def test_pattern_empty_week_means_absent_week() -> None:
    """An explicitly empty week is valid: absent every day of it —
    distinct from having no pattern (the engine's default)."""
    pattern = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0, 2}, 1: set()})
    assert pattern.pattern[1] == frozenset()


def test_pattern_empty_week_encodes_as_empty_segment() -> None:
    pattern = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0, 2}, 1: set()})
    assert pattern.encode() == "0,2|"


def test_pattern_equal_patterns_are_equal_and_encode_identically() -> None:
    one = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {4, 2, 0}, 1: {3, 1}})
    two = PresencePattern(2, NAME, HOME, 2, ANCHOR, {0: {0, 2, 4}, 1: {1, 3}})
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
def test_pattern_decode_encode_round_trips_losslessly(encoded) -> None:
    pattern = PresencePattern.decode(1, NAME, HOME, ANCHOR, encoded)
    assert pattern.encode() == encoded
    again = PresencePattern.decode(1, NAME, HOME, ANCHOR, pattern.encode())
    assert again == pattern


def test_pattern_decode_sets_cycle_length_from_segments() -> None:
    one_week = PresencePattern.decode(1, NAME, HOME, ANCHOR, "0,2,4")
    assert one_week.cycle_length_weeks == 1
    four_week = PresencePattern.decode(1, NAME, HOME, ANCHOR, "0|1|2|3,4")
    assert four_week.cycle_length_weeks == 4


def test_pattern_decode_rejects_malformed_segments() -> None:
    for bad in ("0,12|1", "0,,2|1", "x|1", "0|-1|2", "8", "0,|1"):
        with pytest.raises(ValueError, match="invalid weekday"):
            PresencePattern.decode(1, NAME, HOME, ANCHOR, bad)


def test_pattern_decode_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        PresencePattern.decode(1, NAME, HOME, ANCHOR, None)


def test_pattern_decode_rejects_too_many_segments(tmp_path) -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        PresencePattern.decode(1, NAME, HOME, ANCHOR, "0|1|2|3|4")


def test_pattern_decode_carries_and_validates_name_and_kind() -> None:
    """decode is ordinary construction: name trimmed, kind checked."""
    decoded = PresencePattern.decode(1, " Away days ", "away", ANCHOR, "3,4")
    assert (decoded.name, decoded.kind) == ("Away days", "away")
    with pytest.raises(ValueError, match="name must not be empty"):
        PresencePattern.decode(1, " ", "away", ANCHOR, "3,4")
    with pytest.raises(ValueError, match="kind must be one of"):
        PresencePattern.decode(1, NAME, "absent", ANCHOR, "3,4")


def test_pattern_covers_follows_the_cycle_week() -> None:
    """covers() is the weekday-in-this-cycle-week test, independent of
    kind: an away pattern covers its days exactly like a home one."""
    for kind in PATTERN_KINDS:
        pattern = PresencePattern(1, NAME, kind, 2, ANCHOR, {0: {1, 3}, 1: {2}})
        # Tue Jan 6: week 0, weekday 1 -> covered.
        assert pattern.covers(datetime.date(2026, 1, 6)) is True
        # Wed Jan 7: week 0, weekday 2 -> not covered.
        assert pattern.covers(datetime.date(2026, 1, 7)) is False
        # Wed Jan 14: week 1, weekday 2 -> covered.
        assert pattern.covers(datetime.date(2026, 1, 14)) is True
        # Tue Dec 30 2025: before the anchor, walks back into week 1.
        assert pattern.covers(datetime.date(2025, 12, 30)) is False
        assert pattern.covers(datetime.date(2025, 12, 31)) is True


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


def test_pattern_rejects_datetime_anchor() -> None:
    """datetime.datetime subclasses date: a bare isinstance check would
    store a time component and every date comparison would TypeError."""
    with pytest.raises(ValueError, match="plain calendar date"):
        PresencePattern(1, NAME, HOME, 1, datetime.datetime(2026, 1, 5, 9, 30), {0: {0}})


def test_override_rejects_datetime_bounds() -> None:
    with pytest.raises(ValueError, match="plain calendar date"):
        PresenceOverride(
            1, datetime.datetime(2026, 7, 20), "2026-07-20", True
        )


def test_pattern_pattern_is_immutable_after_construction() -> None:
    """The frozen pattern must not leak a mutable dict: injecting
    unvalidated weekdays or dropping required weeks after construction
    would bypass total validation."""
    pattern = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0, 2}, 1: {1}})
    with pytest.raises(TypeError):
        pattern.pattern[0] = {9}
    with pytest.raises(TypeError):
        del pattern.pattern[1]
    # mappingproxy exposes no mutators at all.
    assert not any(
        hasattr(pattern.pattern, name)
        for name in ("clear", "pop", "popitem", "setdefault", "update")
    )
    # The validated contents are still readable and encode correctly.
    assert pattern.pattern[0] == frozenset({0, 2})
    assert pattern.encode() == "0,2|1"


# ---------------------------------------------------------------------------
# Cycle arithmetic: anchor-date only, never ISO week parity
# ---------------------------------------------------------------------------


def test_cycle_week_index_follows_the_anchor_formula() -> None:
    pattern = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0}, 1: {1}})
    # The anchor day starts week 0; each whole 7 days steps the cycle.
    offsets = {0: 0, 1: 0, 6: 0, 7: 1, 8: 1, 13: 1, 14: 0, 15: 0, 22: 1}
    for offset, expected in offsets.items():
        assert (
            cycle_week_index(
                pattern, ANCHOR + datetime.timedelta(days=offset)
            )
            == expected
        ), f"offset {offset}"


def test_cycle_week_index_before_the_anchor_walks_backwards() -> None:
    """Python floor division: day -1 is the LAST week of the cycle,
    wrapping backwards — never inverting."""
    pattern = PresencePattern(1, NAME, HOME, 2, ANCHOR, {0: {0}, 1: {1}})
    assert cycle_week_index(pattern, ANCHOR - datetime.timedelta(days=1)) == 1
    assert cycle_week_index(pattern, ANCHOR - datetime.timedelta(days=7)) == 1
    assert cycle_week_index(pattern, ANCHOR - datetime.timedelta(days=8)) == 0


def test_cycle_week_index_three_week_pattern() -> None:
    pattern = PresencePattern(
        1, NAME, HOME, 3, ANCHOR, {0: {0}, 1: {1}, 2: {2}}
    )
    offsets = [0, 7, 14, 21, 28]
    assert [cycle_week_index(pattern, ANCHOR + datetime.timedelta(days=o)) for o in offsets] == [
        0, 1, 2, 0, 1
    ]


def test_cycle_week_index_stable_across_three_year_boundaries() -> None:
    """The regression this exists for: walking day by day through a
    December 31st -> January 1st boundary, the cycle index steps by 0
    or +1 (mod cycle length) and NEVER resets or inverts — including
    2020, a 53-ISO-week year, where ISO week parity flips and would
    invert a two-week custody schedule on January 1st."""
    pattern = PresencePattern(
        1, NAME, HOME, 2, datetime.date(2019, 1, 6), {0: {0, 2, 4}, 1: {1, 3}}
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
        got = cycle_week_index(pattern, day)
        assert got == wanted, f"{day}: expected week {wanted}, got {got}"
    # And 2020 really is the 53-ISO-week year this guards against.
    assert datetime.date(2020, 12, 31).isocalendar()[1] == 53


def test_module_uses_no_iso_week_functions() -> None:
    """D-004 guardrail: cycle math never reads ISO week numbers.

    Scanned against ``custom_components.nestquest.core.presence`` (the
    real presence model since task 510c1f78); the integration's
    ``presence.py`` is now a re-export shim, so scanning the shim is
    vacuous.  Mirrors ``test_recurrence_model.py``'s scan of
    ``core.recurrence``.
    """
    from pathlib import Path

    source = Path(
        __import__("custom_components.nestquest.core.presence",
                   fromlist=["__file__"]).__file__
    ).read_text()
    assert "isocalendar" not in source
    assert "isoweek" not in source


# ---------------------------------------------------------------------------
# PresenceEngine: is_present with the always-present default
# ---------------------------------------------------------------------------


def _three_child_engine() -> PresenceEngine:
    """Two children on opposite weeks of one two-week rotation (each a
    single ``home`` pattern), one with no pattern at all (the
    always-present sibling)."""
    anchor = datetime.date(2026, 1, 5)  # Monday, week 0
    declan = PresencePattern(
        1, NAME, HOME, 2, anchor, {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()}
    )
    jordyn = PresencePattern(
        2, NAME, HOME, 2, anchor, {0: set(), 1: {0, 1, 2, 3, 4, 5, 6}}
    )
    return PresenceEngine({1: [declan], 2: [jordyn]})


def test_engine_child_without_pattern_is_always_present() -> None:
    """Every day of the four-week span, all three children get the
    expected verdict: Chloe (no pattern) always present; the two
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
            1: [
                PresencePattern(
                    1, NAME, HOME, 2, datetime.date(2026, 1, 5),
                    {0: {1, 3}, 1: {2, 4}},
                )
            ]
        }
    )
    # 2026-01-06 (Tue) is week 0, weekday 1 -> present.
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is True
    # 2026-01-07 (Wed) is week 0, weekday 2 -> absent.
    assert engine.is_present(1, datetime.date(2026, 1, 7)) is False
    # 2026-01-14 (Wed) is week 1, weekday 2 -> present.
    assert engine.is_present(1, datetime.date(2026, 1, 14)) is True


def test_engine_rejects_bad_construction_and_inputs() -> None:
    pattern = PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: {0}})
    with pytest.raises(ValueError, match="must map child_id"):
        PresenceEngine([pattern])
    # Values are LISTS now: a bare pattern (the retired one-schedule
    # shape) is refused rather than silently iterated.
    with pytest.raises(ValueError, match="must be a list of PresencePattern"):
        PresenceEngine({1: pattern})
    with pytest.raises(ValueError, match="must be a list of PresencePattern"):
        PresenceEngine({1: (pattern,)})
    with pytest.raises(ValueError, match="entries must be PresencePattern"):
        PresenceEngine({1: ["not-a-pattern"]})
    with pytest.raises(ValueError, match="holds a pattern of child 1"):
        PresenceEngine({2: [pattern]})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({True: [pattern]})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({1.0: [PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: {0}})]})
    engine = PresenceEngine({1: [pattern]})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        engine.is_present(True, ANCHOR)
    with pytest.raises(ValueError, match="plain calendar date"):
        engine.is_present(1, datetime.datetime(2026, 1, 5))


def test_engine_is_immutable() -> None:
    engine = _three_child_engine()
    with pytest.raises(AttributeError, match="immutable snapshot"):
        engine._patterns = {}
    with pytest.raises(AttributeError, match="immutable snapshot"):
        engine.something_new = 1


# ---------------------------------------------------------------------------
# PresenceEngine: combining several patterns per child
# ---------------------------------------------------------------------------


def _pattern(kind: str, pattern: dict, *, cycle: int = 1) -> PresencePattern:
    return PresencePattern(1, f"{kind} pattern", kind, cycle, ANCHOR, pattern)


def test_engine_empty_pattern_list_is_always_present() -> None:
    """An empty list is the same as no entry: present every day."""
    engine = PresenceEngine({1: []})
    for offset in range(14):
        day = ANCHOR + datetime.timedelta(days=offset)
        assert engine.is_present(1, day) is True, f"offset {offset}"


def test_engine_away_only_child_is_present_except_covered_days() -> None:
    """Away patterns alone never make an uncovered day absent: the
    household default (present) holds outside their coverage."""
    engine = PresenceEngine({1: [_pattern("away", {0: {3, 4}})]})
    for offset in range(14):
        day = ANCHOR + datetime.timedelta(days=offset)
        expected = day.weekday() not in {3, 4}
        assert engine.is_present(1, day) is expected, f"{day}"


def test_engine_several_home_patterns_union_their_days() -> None:
    """Any covering home pattern makes the day present; a day no home
    pattern covers is absent once the child has a home pattern."""
    engine = PresenceEngine(
        {
            1: [
                _pattern("home", {0: {0, 1}}),
                _pattern("home", {0: {4}, 1: set()}, cycle=2),
            ]
        }
    )
    # Week 0 (Jan 5-11): Mon, Tue from the first, Fri from the second.
    present = {
        ANCHOR + datetime.timedelta(days=offset)
        for offset in range(7)
        if engine.is_present(1, ANCHOR + datetime.timedelta(days=offset))
    }
    assert present == {
        datetime.date(2026, 1, 5),
        datetime.date(2026, 1, 6),
        datetime.date(2026, 1, 9),
    }
    # Week 1: the second pattern's empty week leaves only Mon/Tue.
    assert engine.is_present(1, datetime.date(2026, 1, 16)) is False
    assert engine.is_present(1, datetime.date(2026, 1, 12)) is True


def test_engine_away_pattern_beats_covering_home_pattern() -> None:
    """Rule order: a covering away pattern wins over a covering home
    pattern, whichever is listed first."""
    home = _pattern("home", {0: {0, 1, 2, 3, 4, 5, 6}})
    away = _pattern("away", {0: {5, 6}})
    for patterns in ([home, away], [away, home]):
        engine = PresenceEngine({1: patterns})
        assert engine.is_present(1, datetime.date(2026, 1, 9)) is True  # Fri
        assert engine.is_present(1, datetime.date(2026, 1, 10)) is False  # Sat
        assert engine.is_present(1, datetime.date(2026, 1, 11)) is False  # Sun


def test_engine_home_pattern_makes_uncovered_days_absent_even_with_away() -> None:
    """Mixing kinds: a day neither pattern covers is absent because the
    child has a home pattern (rule 4), not present."""
    engine = PresenceEngine(
        {1: [_pattern("home", {0: {0, 1}}), _pattern("away", {0: {5}})]}
    )
    assert engine.is_present(1, datetime.date(2026, 1, 5)) is True  # Mon
    assert engine.is_present(1, datetime.date(2026, 1, 7)) is False  # Wed
    assert engine.is_present(1, datetime.date(2026, 1, 10)) is False  # Sat


def test_engine_override_beats_away_pattern() -> None:
    engine = PresenceEngine(
        {1: [_pattern("away", {0: {5, 6}})]},
        overrides={
            1: [PresenceOverride(1, "2026-01-10", "2026-01-10", True)]
        },
    )
    assert engine.is_present(1, datetime.date(2026, 1, 10)) is True
    assert engine.is_present(1, datetime.date(2026, 1, 11)) is False


def test_engine_pattern_lists_are_frozen() -> None:
    """Mutating the caller's pattern list after construction must not
    change the engine's answers."""
    patterns = [_pattern("home", {0: {0}})]
    engine = PresenceEngine({1: patterns})
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is False
    patterns.append(_pattern("home", {0: {1}}))
    assert engine.is_present(1, datetime.date(2026, 1, 6)) is False
    with pytest.raises(AttributeError):
        engine._patterns[1].append(patterns[1])


# ---------------------------------------------------------------------------
# Overrides take precedence over the pattern
# ---------------------------------------------------------------------------


def _engine_with_overrides(*overrides_for_declan) -> PresenceEngine:
    anchor = datetime.date(2026, 1, 5)  # Monday
    return PresenceEngine(
        {
            1: [
                PresencePattern(
                    1, NAME, HOME, 2, anchor,
                    {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()},
                )
            ]
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


def test_override_applies_without_a_pattern() -> None:
    """An override on a pattern-free child still applies: holidays and
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
    patterns = [PresencePattern(1, NAME, HOME, 1, ANCHOR, {0: {0}})]
    entry = PresenceOverride(1, "2026-07-20", "2026-07-20", True)
    with pytest.raises(ValueError, match="must map child_id"):
        PresenceEngine({1: patterns}, overrides=[entry])
    with pytest.raises(ValueError, match="must be a list"):
        PresenceEngine({1: patterns}, overrides={1: entry})
    with pytest.raises(ValueError, match="must be"):
        PresenceEngine({1: patterns}, overrides={1: ["nope"]})
    with pytest.raises(ValueError, match="holds an override"):
        PresenceEngine({1: patterns}, overrides={2: [entry]})
    with pytest.raises(ValueError, match="child_id must be an integer"):
        PresenceEngine({1: patterns}, overrides={True: [entry]})


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
    """The overrides snapshot must be truly read-only: the engine is
    built directly on the CALLER's list, so mutating that list after
    construction would change answers under a shallow copy — under the
    frozen snapshot it must not."""
    entry = PresenceOverride(1, "2026-01-06", "2026-01-06", False)
    entries = [entry]
    pattern = PresencePattern(
        1, NAME, HOME, 2, ANCHOR, {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()}
    )
    engine = PresenceEngine(
        {1: [pattern]}, overrides={1: entries}  # caller-owned list
    )
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


# ---------------------------------------------------------------------------
# next_present_dates: the parent's pattern preview
# ---------------------------------------------------------------------------


def _preview_engine() -> PresenceEngine:
    """Declan: home all of week 0, away all of week 1 (anchor
    2026-01-05, a Monday); an away override Tue Jan 13 (his away week)
    would matter only for the override test."""
    return PresenceEngine(
        {
            1: [
                PresencePattern(
                    1, NAME, HOME, 2, datetime.date(2026, 1, 5),
                    {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()},
                )
            ]
        }
    )


def test_preview_returns_the_next_present_days_of_a_known_pattern() -> None:
    engine = _preview_engine()
    # Starting Monday Jan 5 (present week 0): five straight days.
    preview = engine.next_present_dates(1, "2026-01-05", 5)
    assert preview == [
        datetime.date(2026, 1, 5),
        datetime.date(2026, 1, 6),
        datetime.date(2026, 1, 7),
        datetime.date(2026, 1, 8),
        datetime.date(2026, 1, 9),
    ]
    # Starting mid-week: the rest of week 0 first, then the absent
    # week 1 is skipped and the next present week picks up.
    preview = engine.next_present_dates(1, "2026-01-07", 3)
    assert preview == [
        datetime.date(2026, 1, 7),
        datetime.date(2026, 1, 8),
        datetime.date(2026, 1, 9),
    ]
    preview = engine.next_present_dates(1, "2026-01-07", 6)
    # Week 0 runs Mon Jan 5 .. Sun Jan 11 (all present); the away week
    # (Jan 12-18) is skipped; week 2 resumes Jan 19.
    assert preview == [
        datetime.date(2026, 1, 7),
        datetime.date(2026, 1, 8),
        datetime.date(2026, 1, 9),
        datetime.date(2026, 1, 10),
        datetime.date(2026, 1, 11),
        datetime.date(2026, 1, 19),
    ]


def test_preview_start_date_is_inclusive() -> None:
    engine = _preview_engine()
    # Jan 12 (Monday of the away week) is absent: the first present day
    # is Jan 19 — the start date itself when present.
    preview = engine.next_present_dates(1, "2026-01-19", 1)
    assert preview == [datetime.date(2026, 1, 19)]


def test_preview_honours_overrides() -> None:
    pattern = PresencePattern(
        1, NAME, HOME, 2, datetime.date(2026, 1, 5),
        {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()},
    )
    engine = PresenceEngine(
        {1: [pattern]},
        overrides={
            1: [
                PresenceOverride(
                    1, "2026-01-05", "2026-01-06", False, note="holiday"
                )
            ]
        },
    )
    # Jan 5-6 blocked by the override: the preview starts Jan 7.
    preview = engine.next_present_dates(1, "2026-01-04", 3)
    assert preview == [
        datetime.date(2026, 1, 7),
        datetime.date(2026, 1, 8),
        datetime.date(2026, 1, 9),
    ]


def test_preview_pattern_free_child_returns_consecutive_days() -> None:
    engine = PresenceEngine({})
    preview = engine.next_present_dates(3, "2026-03-01", 3)
    assert preview == [
        datetime.date(2026, 3, 1),
        datetime.date(2026, 3, 2),
        datetime.date(2026, 3, 3),
    ]


def test_preview_rejects_bad_inputs() -> None:
    engine = _preview_engine()
    with pytest.raises(ValueError, match="count must be an integer"):
        engine.next_present_dates(1, "2026-01-05", "3")
    with pytest.raises(ValueError, match="count must be at least 1"):
        engine.next_present_dates(1, "2026-01-05", 0)
    with pytest.raises(ValueError, match="child_id must be an integer"):
        engine.next_present_dates(True, "2026-01-05", 1)
    with pytest.raises(ValueError, match="plain calendar date"):
        engine.next_present_dates(1, datetime.datetime(2026, 1, 5), 1)


def test_preview_always_absent_child_raises_not_loops() -> None:
    """A child absent every scanned day must surface as an error, not
    hang the admin preview."""
    engine = PresenceEngine(
        {
            1: [
                PresencePattern(
                    1, NAME, HOME, 1, datetime.date(2026, 1, 5), {0: set()}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="not present on any"):
        engine.next_present_dates(1, "2026-01-05", 2)


# ---------------------------------------------------------------------------
# The week-parity regression guard (Feature 05, D-004)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "length", "reason"),
    [
        (2020, 366, "leap year, 53 ISO weeks"),
        (2015, 365, "365 days, 53 ISO weeks"),
    ],
)
def test_custody_rotation_walks_full_years_without_inversion(
    year, length, reason
) -> None:
    """REGRESSION GUARD for the week-parity bug (D-004).

    Walks a two-week alternating rotation day by day across a FULL
    {length}-day year ({year} — {reason}) plus the following January,
    asserting the present/absent sequence never breaks or inverts at
    any point, including January 1st.  ISO week parity silently flips
    at the ISO-week rollover (the Monday on or after January 4th —
    January 4th itself in both of these years, which end ISO week 53)
    and would invert every custody schedule there; anchor-date
    arithmetic must not.
    """.format(length=length, year=year, reason=reason)
    if year == 2020:
        assert datetime.date(2020, 12, 31).isocalendar()[1] == 53
        assert (datetime.date(2021, 1, 1) - datetime.date(2020, 1, 1)).days == 366
    if year == 2015:
        assert datetime.date(2015, 12, 31).isocalendar()[1] == 53
        assert (datetime.date(2016, 1, 1) - datetime.date(2015, 1, 1)).days == 365

    # The first Monday of January (2020: Jan 6; 2015: Jan 5) — an
    # on-week anchor, whatever the year.
    anchor = datetime.date(year, 1, 1) + datetime.timedelta(
        days=(7 - datetime.date(year, 1, 1).weekday()) % 7
    )
    assert anchor.weekday() == 0
    rotation = PresencePattern(
        1, NAME, HOME, 2, anchor, {0: {0, 1, 2, 3, 4, 5, 6}, 1: set()}
    )
    engine = PresenceEngine({1: [rotation]})

    # Walk EVERY day of the year.  The expectation is derived from the
    # anchor's 7-day BLOCKS, not from the engine: each block of seven
    # days starting at the anchor is uniformly present (even block
    # index) or uniformly absent (odd block index), and consecutive
    # blocks alternate.  A parity-based implementation resets on
    # January 1st and breaks either the uniformity of a block or the
    # alternation between them — most visibly in the block spanning
    # December 31st -> January 1st of a 53-ISO-week year.
    # Walk the FULL year AND the first two weeks of the following
    # January: the block spanning December 31st -> January 1st must
    # stay uniform ACROSS the boundary, so an implementation that
    # resets when the target year differs from the anchor's fails
    # here (the post-boundary days of its final block disagree).
    first_day = datetime.date(year, 1, 1)
    last_day = datetime.date(year + 1, 1, 14)
    days_seen = 0
    day = first_day
    while day <= last_day:
        days_since_anchor = (day - anchor).days
        block = days_since_anchor // 7  # which 7-day block of the cycle
        block_start = anchor + datetime.timedelta(days=block * 7)
        # Uniformity within the block: every day of this 7-day block
        # must answer exactly like the block's first day.
        expected = ((block % 2) == 0)
        assert engine.is_present(1, day) is expected, (
            f"{day} (block {block}, day offset "
            f"{(day - block_start).days}): present="
            f"{engine.is_present(1, day)}, expected {expected}"
        )
        # The block's OTHER days must agree — including the days on
        # the far side of January 1st.
        for offset in range(7):
            block_day = block_start + datetime.timedelta(days=offset)
            if first_day <= block_day <= last_day:
                assert engine.is_present(1, block_day) is expected, (
                    f"{block_day} disagrees with its block {block}"
                )
        days_seen += 1
        day += datetime.timedelta(days=1)
    # The walked year itself contributed exactly its full length.
    year_days = sum(
        1
        for offset in range((last_day - first_day).days + 1)
        if (first_day + datetime.timedelta(days=offset)).year == year
    )
    assert year_days == length, (
        f"walked {year_days} days of {year}, expected {length}"
    )
