"""Tests for the NestQuest afternoon-reminder automation blueprint.

The afternoon reminder nudges only the stragglers: a child appears
exactly when they are PRESENT today and still have open quests.
Present-and-clear children, absent children, and the household rollup
sensors are all omitted, and when nobody qualifies the automation
sends nothing at all — the all-clear template condition stops the run
before the notification.  The harness (YAML ``!input`` loader, state
fixtures, jinja rendering) is shared in
:mod:`tests.blueprint_helpers`; the directory-wide shape and
entity-discipline tests in test_blueprints.py cover this file too.
"""
from __future__ import annotations

import re

from custom_components.nestquest.const import DEFAULT_AFTERNOON_REMINDER_TIME

from tests.blueprint_helpers import (
    notify_data,
    BlueprintInput,
    blueprint,
    iter_strings,
    make_states,
    render,
    single_action,
    TemplateState,
)

AFTERNOON_TITLE = "NestQuest afternoon reminder"


def afternoon_reminder() -> dict:
    """Return the parsed afternoon-reminder blueprint."""
    return blueprint("afternoon_reminder")


def afternoon_conditions(bp: dict) -> list[dict]:
    """Return the blueprint's conditions: toggle first, guard second."""
    conditions = bp["conditions"]
    assert isinstance(conditions, list) and len(conditions) == 2
    return conditions


def all_clear_guard(bp: dict) -> str:
    """Return the template that is false when every present child is done."""
    return afternoon_conditions(bp)[1]["value_template"]


# ---------------------------------------------------------------------------
# Inputs, defaults, and wiring.
# ---------------------------------------------------------------------------
def test_afternoon_reminder_declares_inputs_with_selectors() -> None:
    """The three inputs exist, carry selectors, and default sanely."""
    inputs = afternoon_reminder()["blueprint"]["input"]
    expected = {"afternoon_time", "notify_target", "send_reminder"}
    assert set(inputs) == expected
    for name, spec in inputs.items():
        assert isinstance(spec["selector"], dict) and spec["selector"], name
    assert inputs["afternoon_time"]["default"] == DEFAULT_AFTERNOON_REMINDER_TIME
    assert DEFAULT_AFTERNOON_REMINDER_TIME == "15:00"
    assert inputs["send_reminder"]["default"] is True
    assert "time" in inputs["afternoon_time"]["selector"]
    assert "text" in inputs["notify_target"]["selector"]
    assert "boolean" in inputs["send_reminder"]["selector"]


def test_afternoon_reminder_wires_inputs_not_literals() -> None:
    """Time trigger, toggle and guard conditions, and notify action use !input."""
    bp = afternoon_reminder()
    assert bp["variables"]["send_reminder"] == BlueprintInput("send_reminder")

    trigger = bp["triggers"][0]
    assert trigger["trigger"] == "time"
    assert trigger["at"] == BlueprintInput("afternoon_time")

    toggle, guard = afternoon_conditions(bp)
    assert toggle["condition"] == "template"
    assert "send_reminder" in toggle["value_template"]
    assert guard["condition"] == "template"

    action = single_action(bp)
    assert action["action"] == BlueprintInput("notify_target")
    data = notify_data(afternoon_reminder())
    assert data["title"] == AFTERNOON_TITLE
    assert isinstance(data["message"], str) and data["message"].strip()


# ---------------------------------------------------------------------------
# Rendering: only present children with open quests are listed.
# ---------------------------------------------------------------------------
def test_afternoon_reminder_lists_only_present_children_with_open_quests() -> None:
    """Present+open Alice is listed; present+clear Carol, absent Bob,
    and the household rollup are all omitted."""
    states = make_states(
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
                "sensor.nestquest_carol_quests_due_today",
                "2",
                {"child_name": "Carol", "child_id": 2, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_carol_quests_remaining_today",
                "0",
                {"child_id": 2},
            ),
            TemplateState(
                "sensor.nestquest_bob_quests_due_today",
                "2",
                {"child_name": "Bob", "child_id": 3, "present": False},
            ),
            TemplateState(
                "sensor.nestquest_bob_quests_remaining_today",
                "1",
                {"child_id": 3},
            ),
            TemplateState("sensor.nestquest_household_quests_due_today", "7"),
        ],
    )
    rendered = render(notify_data(afternoon_reminder())["message"], states=states)
    assert rendered == "Alice still has 2 quest(s) open."
    assert "Carol" not in rendered
    assert "Bob" not in rendered
    assert "household" not in rendered


def test_afternoon_reminder_all_clear_guard_renders_false() -> None:
    """With every present child done (and absent children owing), the
    guard condition is false: the automation sends nothing at all."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "2",
                {"child_name": "Alice", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "0",
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
            TemplateState("sensor.nestquest_household_quests_due_today", "2"),
        ],
    )
    guard = all_clear_guard(afternoon_reminder())
    assert render(guard, states=states).strip() == "False"


def test_afternoon_reminder_guard_renders_true_when_a_present_child_owes() -> None:
    """A present child with open quests makes the guard true."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "3",
                {"child_name": "Alice", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "1",
                {"child_id": 1},
            ),
        ],
    )
    guard = all_clear_guard(afternoon_reminder())
    assert render(guard, states=states).strip() == "True"


def test_afternoon_reminder_send_reminder_toggle_renders() -> None:
    """The enable condition renders truthy/false from the input value."""
    toggle = afternoon_conditions(afternoon_reminder())[0]
    assert render(toggle["value_template"], send_reminder=True).strip() == "True"
    assert render(toggle["value_template"], send_reminder=False).strip() == "False"


def test_afternoon_reminder_collision_suffixed_duplicate_names() -> None:
    """Two children sharing a display name (HA registry suffix _2 on the
    second one's entity ids) both appear, each with their own count."""
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
                "3",
                {"child_name": "Ada", "child_id": 2, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_ada_quests_remaining_today_2",
                "3",
                {"child_id": 2},
            ),
        ],
    )
    rendered = render(notify_data(afternoon_reminder())["message"], states=states)
    assert rendered.split("\n") == [
        "Ada still has 1 quest(s) open.",
        "Ada still has 3 quest(s) open.",
    ]


def test_afternoon_reminder_never_hard_codes_notify_target() -> None:
    """No notify service literal outside the input's placeholder text."""
    bp = afternoon_reminder()
    spec = bp["blueprint"]
    assert not re.search(r"notify\.[a-z_]+", spec["description"])

    outside_input = {k: v for k, v in bp.items() if k != "blueprint"}
    for value in iter_strings(outside_input):
        assert not re.search(r"notify\.[a-z_.]+", value), value

    target_description = spec["input"]["notify_target"]["description"]
    assert re.search(r"notify\.[a-z_]+", target_description), (
        "the input description should show a placeholder example"
    )
    assert single_action(bp)["action"] == BlueprintInput("notify_target")

def test_afternoon_reminder_absent_child_regression() -> None:
    """The Feature 11 guardrail, stated as one regression test: no
    reminder message is ever produced for an absent child."""
    states = make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_bob_quests_due_today",
                "3",
                {"child_name": "Bob", "child_id": 1, "present": False},
            ),
            TemplateState(
                "sensor.nestquest_bob_quests_remaining_today",
                "3",
                {"child_id": 1},
            ),
        ],
    )
    guard = afternoon_conditions(afternoon_reminder())[-1]
    assert render(guard["value_template"], states=states).strip() == "False"
    message = render(
        notify_data(afternoon_reminder())["message"], states=states
    )
    assert "Bob" not in message
