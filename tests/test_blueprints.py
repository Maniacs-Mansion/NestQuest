"""Tests for the NestQuest morning-summary automation blueprint.

The blueprints are YAML data consumed by Home Assistant's blueprint
engine; the integration itself never imports yaml or jinja2.  These
tests therefore exercise them exactly the way HA would: parse the YAML
(with a loader that understands ``!input`` tags), then render the
message template with a plain jinja2 environment over a fixture state
set shaped like HA's template state objects — all via the shared
harness in :mod:`tests.blueprint_helpers`.

This module also carries the directory-wide blueprint discipline tests
(entity-id shapes, domain mentions, notify-target hygiene), which scan
EVERY blueprint file under the automation directory, so new blueprint
files are covered automatically.

Rendering policy under test (settled for the morning summary): a
PRESENT child always appears — with remaining quests owed, or as "all
clear" at zero remaining — and a child who is not present that day is
omitted entirely, never listed with zero quests.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from custom_components.nestquest.const import DEFAULT_MORNING_SUMMARY_TIME

from tests.blueprint_helpers import (
    ALLOWED_ENTITY_SHAPES,
    BlueprintInput,
    _ENTITY_LITERAL_RE,
    _MENTION_RE,
    iter_strings,
    load_blueprints,
    make_states,
    morning_action,
    morning_summary,
    render,
    TemplateState,
)

MORNING_TITLE = "NestQuest morning summary"


# ---------------------------------------------------------------------------
# YAML parsing and blueprint shape.
# ---------------------------------------------------------------------------
def test_blueprints_parse_and_declare_valid_shape() -> None:
    """Every blueprint parses and carries the required blueprint keys."""
    blueprints = load_blueprints()
    assert blueprints, "no blueprints found"
    for name, bp in blueprints.items():
        assert isinstance(bp, dict), f"{name} did not parse to a mapping"
        spec = bp["blueprint"]
        assert isinstance(spec["name"], str) and spec["name"].strip()
        assert spec["domain"] == "automation"
        assert isinstance(spec["input"], dict) and spec["input"]
        for key in ("triggers", "conditions", "actions"):
            assert isinstance(bp[key], list) and bp[key], f"{name}: empty {key}"


def test_morning_summary_declares_inputs_with_selectors() -> None:
    """The three blueprint inputs exist, carry selectors, and default sanely."""
    inputs = morning_summary()["blueprint"]["input"]
    expected = {"morning_time", "notify_target", "send_summary"}
    assert set(inputs) == expected
    for name, spec in inputs.items():
        assert isinstance(spec["selector"], dict) and spec["selector"], name
    assert inputs["morning_time"]["default"] == DEFAULT_MORNING_SUMMARY_TIME
    assert inputs["send_summary"]["default"] is True
    assert "time" in inputs["morning_time"]["selector"]
    assert "text" in inputs["notify_target"]["selector"]
    assert "boolean" in inputs["send_summary"]["selector"]


def test_morning_summary_wires_inputs_not_literals() -> None:
    """Time trigger, toggle condition, and notify action all use !input."""
    bp = morning_summary()
    assert bp["variables"]["send_summary"] == BlueprintInput("send_summary")

    trigger = bp["triggers"][0]
    assert trigger["trigger"] == "time"
    assert trigger["at"] == BlueprintInput("morning_time")

    condition = bp["conditions"][0]
    assert condition["condition"] == "template"
    assert "send_summary" in condition["value_template"]

    action = morning_action(bp)
    assert action["action"] == BlueprintInput("notify_target")
    assert action["title"] == MORNING_TITLE
    assert isinstance(action["message"], str) and action["message"].strip()


# ---------------------------------------------------------------------------
# Entity-reference discipline (Feature 10 shapes only).  These tests
# scan EVERY blueprint in the directory, so new blueprint files are
# automatically held to the same rules.
# ---------------------------------------------------------------------------
def test_entity_literals_match_feature_10_shapes() -> None:
    """Every id-like entity string in the YAML is a Feature 10 shape."""
    for name, bp in load_blueprints().items():
        for value in iter_strings(bp):
            for literal in _ENTITY_LITERAL_RE.findall(value):
                assert any(
                    shape.fullmatch(literal) for shape in ALLOWED_ENTITY_SHAPES
                ), f"{name}: invented entity {literal!r}"
    # The validator itself must separate Feature 10 ids from lookalikes.
    assert any(
        shape.fullmatch("binary_sensor.nestquest_alice_present_today")
        for shape in ALLOWED_ENTITY_SHAPES
    )
    assert any(
        shape.fullmatch("sensor.nestquest_bob_quests_remaining_today")
        for shape in ALLOWED_ENTITY_SHAPES
    )
    for foreign in (
        "binary_sensor.someone_else_present_today",
        "binary_sensor.nestquest_alice_at_home",
        "sensor.nestquest_alice_streak",
        "vacuum.nestquest_robot",
    ):
        assert not any(shape.fullmatch(foreign) for shape in ALLOWED_ENTITY_SHAPES)


def test_domain_mentions_are_nestquest_prefixed() -> None:
    """Every sensor/binary_sensor mention (regex or literal) is nestquest_."""
    for name, bp in load_blueprints().items():
        for value in iter_strings(bp):
            flattened = value.replace("\\", "")
            for tail in _MENTION_RE.findall(flattened):
                assert tail.startswith("nestquest_"), (
                    f"{name}: non-nestquest entity mention in {value!r}"
                )


def test_due_sensor_regex_selects_only_nestquest_due_sensors() -> None:
    """The extracted due-sensor regex matches Feature 10 due ids —
    including HA collision-suffixed duplicates (a second child with
    the same name gets entity ids ending _2) — and rejects everything
    else."""
    message = morning_action(morning_summary())["message"]
    match = re.search(
        r"\^(sensor\\\\\.nestquest_\.\*_quests_due_today\(_\\\\d\+\)\?\$)", message
    )
    assert match is not None, "due-sensor pattern missing from the template"
    pattern = match.group(1).replace("\\\\", "\\")
    assert pattern.endswith("$")
    assert re.search(pattern, "sensor.nestquest_alice_quests_due_today")
    assert re.search(pattern, "sensor.nestquest_alice_quests_due_today_2")
    assert re.search(pattern, "sensor.nestquest_bob_quests_remaining_today") is None
    # The household rollup due sensor unavoidably matches the pattern;
    # the template's present-attribute guard excludes it (proven in the
    # render test below).
    assert re.search(pattern, "sensor.nestquest_household_quests_due_today")
    assert re.search(pattern, "sensor.carol_unrelated") is None


def test_morning_summary_never_hard_codes_notify_target() -> None:
    """No notify service literal outside input descriptions; the choice is text."""
    bp = morning_summary()
    spec = bp["blueprint"]
    assert "hard-code" in spec["description"]
    assert not re.search(r"notify\.[a-z_]+", spec["description"])

    outside_input = {k: v for k, v in bp.items() if k != "blueprint"}
    for value in iter_strings(outside_input):
        assert not re.search(r"notify\.[a-z_.]+", value), value

    target_description = spec["input"]["notify_target"]["description"]
    assert re.search(r"notify\.[a-z_]+", target_description), (
        "the input description should show a placeholder example"
    )
    assert morning_action(bp)["action"] == BlueprintInput("notify_target")


# ---------------------------------------------------------------------------
# Message rendering against fixture state sets.
# ---------------------------------------------------------------------------
def morning_fixture() -> SimpleNamespace:
    """Two children — Alice present (2 owed), Bob absent — plus decoys."""
    return make_states(
        binary_sensors=[
            TemplateState("binary_sensor.nestquest_alice_present_today", "on"),
            TemplateState("binary_sensor.nestquest_bob_present_today", "off"),
            TemplateState("binary_sensor.motion_present_today", "on"),
            TemplateState("binary_sensor.nestquest_dave_all_done", "on"),
            TemplateState("binary_sensor.nestquest_erin_present_today", "unavailable"),
        ],
        sensors=[
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "3",
                {"child_name": "Alice", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "2",
                {"child_id": 1},
            ),
            TemplateState(
                "sensor.nestquest_bob_quests_due_today",
                "2",
                {"child_name": "Bob", "child_id": 2, "present": False},
            ),
            TemplateState(
                "sensor.nestquest_bob_quests_remaining_today",
                "1",
                {"child_id": 2},
            ),
            TemplateState("sensor.nestquest_household_quests_due_today", "5"),
            TemplateState("sensor.nestquest_carol_unrelated", "7"),
        ],
    )


def test_morning_summary_lists_present_child_and_omits_absent() -> None:
    """Present Alice appears with her count; absent Bob and decoys never do."""
    message = morning_action(morning_summary())["message"]
    rendered = render(message, states=morning_fixture())
    assert rendered == "Alice owes 2 quest(s) today."
    assert "Bob" not in rendered
    for absent in ("motion", "Dave", "Erin", "household", "carol"):
        assert absent not in rendered


def test_morning_summary_present_child_zero_remaining_is_all_clear() -> None:
    """A present child always appears — zero remaining reads as all clear."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_carol_quests_due_today",
                "2",
                {"child_name": "Carol", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_carol_quests_remaining_today",
                "0",
                {"child_id": 1},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "3",
                {"child_name": "Alice", "child_id": 2, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "2",
                {"child_id": 2},
            ),
        ],
    )
    rendered = render(morning_action(morning_summary())["message"], states=states)
    assert "Alice owes 2 quest(s) today." in rendered
    assert "Carol is all clear today (0 quests remaining)." in rendered


def test_morning_summary_present_child_without_sensors_is_flagged() -> None:
    """A present child whose remaining-count sensor is missing (the
    platform failed to add it) still gets a line, flagged unavailable."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_frances_quests_due_today",
                "2",
                {"child_name": "Frances", "child_id": 1, "present": True},
            ),
        ],
    )
    rendered = render(morning_action(morning_summary())["message"], states=states)
    assert rendered == "Frances's quest count is unavailable today."


def test_morning_summary_collision_suffixed_duplicate_names() -> None:
    """Two children sharing a display name get HA registry suffixes on
    their entity ids (..._2); both must appear, each with their own
    count (Codex review regression)."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_ada_quests_due_today",
                "2",
                {"child_name": "Ada", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_ada_quests_remaining_today",
                "1",
                {"child_id": 1},
            ),
            TemplateState(
                "sensor.nestquest_ada_quests_due_today_2",
                "2",
                {"child_name": "Ada", "child_id": 2, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_ada_quests_remaining_today_2",
                "2",
                {"child_id": 2},
            ),
        ],
    )
    rendered = render(morning_action(morning_summary())["message"], states=states)
    lines = rendered.split("\n")
    assert lines == [
        "Ada owes 1 quest(s) today.",
        "Ada owes 2 quest(s) today.",
    ]


def test_morning_summary_no_present_children() -> None:
    """With nobody present the body says so rather than listing zeros."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "3",
                {"child_name": "Alice", "child_id": 1, "present": False},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "3",
                {"child_id": 1},
            ),
        ],
    )
    rendered = render(morning_action(morning_summary())["message"], states=states)
    assert rendered == "No children present today."


def test_morning_summary_send_summary_toggle_renders() -> None:
    """The enable condition renders truthy/false from the input value."""
    condition = morning_summary()["conditions"][0]
    assert render(condition["value_template"], send_summary=True).strip() == "True"
    assert render(condition["value_template"], send_summary=False).strip() == "False"