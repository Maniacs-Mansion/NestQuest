"""Tests for the NestQuest end-of-day report automation blueprint.

The end-of-day report closes the day for the parent: every PRESENT
child gets a completion line (so the parent always receives the day's
summary when the report runs), children who still owe quests get their
open count called out on that line, and absent children are omitted
entirely.  The report runs deliberately before the midnight
missed-quest sweep so it reads the same day's data, and by default an
all-clear day sends nothing — unless the household opts into
send-even-when-clear.  The harness (YAML ``!input`` loader, state
fixtures, jinja rendering) is shared in
:mod:`tests.blueprint_helpers`; the directory-wide shape and
entity-discipline tests in test_blueprints.py cover this file too.
"""
from __future__ import annotations

import re

from custom_components.nestquest.const import DEFAULT_END_OF_DAY_REPORT_TIME

from tests.blueprint_helpers import (
    BlueprintInput,
    notify_data,
    blueprint,
    iter_strings,
    make_states,
    render,
    single_action,
    TemplateState,
)

REPORT_TITLE = "NestQuest end-of-day report"


def end_of_day_report() -> dict:
    """Return the parsed end-of-day-report blueprint."""
    return blueprint("end_of_day_report")


def report_conditions(bp: dict) -> list[dict]:
    """Return the blueprint's conditions: toggle first, guard second."""
    conditions = bp["conditions"]
    assert isinstance(conditions, list) and len(conditions) == 2
    return conditions


def clear_guard(bp: dict) -> str:
    """Return the template guarding an all-clear day (false = no report)."""
    return report_conditions(bp)[1]["value_template"]


def owing_clear_absent_fixture():
    """Alice owing (1/3 done, 2 open), Carol present and clear, Bob absent."""
    return make_states(
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
                "sensor.nestquest_alice_quests_completed_today",
                "1",
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
                "sensor.nestquest_carol_quests_completed_today",
                "2",
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
            TemplateState(
                "sensor.nestquest_bob_quests_completed_today",
                "1",
                {"child_id": 3},
            ),
            TemplateState("sensor.nestquest_household_quests_due_today", "7"),
        ],
    )


def all_clear_fixture():
    """Alice present with everything done; nobody owes anything."""
    return make_states(
        sensors=[
            TemplateState(
                "sensor.nestquest_alice_quests_due_today",
                "3",
                {"child_name": "Alice", "child_id": 1, "present": True},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_remaining_today",
                "0",
                {"child_id": 1},
            ),
            TemplateState(
                "sensor.nestquest_alice_quests_completed_today",
                "3",
                {"child_id": 1},
            ),
            TemplateState("sensor.nestquest_household_quests_due_today", "3"),
        ],
    )


# ---------------------------------------------------------------------------
# Inputs, defaults, and wiring.
# ---------------------------------------------------------------------------
def test_end_of_day_report_declares_inputs_with_selectors() -> None:
    """The four inputs exist, carry selectors, and default sanely."""
    bp = end_of_day_report()
    inputs = bp["blueprint"]["input"]
    expected = {"report_time", "notify_target", "send_report", "send_even_when_clear"}
    assert set(inputs) == expected
    for name, spec in inputs.items():
        assert isinstance(spec["selector"], dict) and spec["selector"], name
    assert inputs["report_time"]["default"] == DEFAULT_END_OF_DAY_REPORT_TIME
    assert DEFAULT_END_OF_DAY_REPORT_TIME == "20:00"
    assert inputs["send_report"]["default"] is True
    assert inputs["send_even_when_clear"]["default"] is False
    assert "time" in inputs["report_time"]["selector"]
    assert "text" in inputs["notify_target"]["selector"]
    assert "boolean" in inputs["send_report"]["selector"]
    assert "boolean" in inputs["send_even_when_clear"]["selector"]
    # The description must note the deliberate ordering: the report runs
    # before the midnight missed sweep, reading the same day's data.
    description = bp["blueprint"]["description"].lower()
    assert "before" in description
    assert "sweep" in description
    assert "same day" in description


def test_end_of_day_report_wires_inputs_not_literals() -> None:
    """Time trigger, toggle and guard conditions, and notify action use !input."""
    bp = end_of_day_report()
    assert bp["variables"]["send_report"] == BlueprintInput("send_report")
    assert bp["variables"]["send_even_when_clear"] == BlueprintInput(
        "send_even_when_clear"
    )

    trigger = bp["triggers"][0]
    assert trigger["trigger"] == "time"
    assert trigger["at"] == BlueprintInput("report_time")

    toggle, guard = report_conditions(bp)
    assert toggle["condition"] == "template"
    assert "send_report" in toggle["value_template"]
    assert guard["condition"] == "template"
    assert "send_even_when_clear" in guard["value_template"]

    action = single_action(bp)
    assert action["action"] == BlueprintInput("notify_target")
    data = notify_data(end_of_day_report())
    assert data["title"] == REPORT_TITLE
    assert isinstance(data["message"], str) and data["message"].strip()


# ---------------------------------------------------------------------------
# Rendering the day's summary.
# ---------------------------------------------------------------------------
def test_end_of_day_report_renders_owing_clear_and_absent_children() -> None:
    """The owing child's open count is called out with the completion
    ratio; the present-clear child still gets the day's completion
    line; the absent child is omitted entirely."""
    rendered = render(
        notify_data(end_of_day_report())["message"],
        states=owing_clear_absent_fixture(),
    )
    assert rendered.split("\n") == [
        "Alice: 2 still open (1/3 done).",
        "Carol: 2/2 done.",
    ]
    assert "Bob" not in rendered
    assert "household" not in rendered


def test_end_of_day_report_all_clear_guard_renders_false_by_default() -> None:
    """An all-clear day with send_even_when_clear off sends nothing:
    the guard condition is false."""
    rendered = render(
        clear_guard(end_of_day_report()),
        states=all_clear_fixture(),
        send_even_when_clear=False,
    )
    assert rendered.strip() == "False"


def test_end_of_day_report_all_clear_sends_summary_when_opted_in() -> None:
    """With send_even_when_clear on, the guard lets an all-clear day
    through and the message renders the day's completion summary."""
    guard = clear_guard(end_of_day_report())
    assert (
        render(guard, states=all_clear_fixture(), send_even_when_clear=True).strip()
        == "True"
    )
    message = render(
        notify_data(end_of_day_report())["message"],
        states=all_clear_fixture(),
    )
    assert message == "Alice: 3/3 done."


def test_end_of_day_report_guard_true_when_a_present_child_owes() -> None:
    """A present child with open quests passes the guard even with
    send_even_when_clear off."""
    rendered = render(
        clear_guard(end_of_day_report()),
        states=owing_clear_absent_fixture(),
        send_even_when_clear=False,
    )
    assert rendered.strip() == "True"


def test_end_of_day_report_collision_suffixed_duplicate_names() -> None:
    """Two children sharing a display name (HA registry suffix _2 on the
    second one's entity ids) both appear, each with their own counts."""
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
                "sensor.nestquest_ada_quests_completed_today",
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
                "0",
                {"child_id": 2},
            ),
            TemplateState(
                "sensor.nestquest_ada_quests_completed_today_2",
                "3",
                {"child_id": 2},
            ),
        ],
    )
    rendered = render(notify_data(end_of_day_report())["message"], states=states)
    assert rendered.split("\n") == [
        "Ada: 1 still open (1/2 done).",
        "Ada: 3/3 done.",
    ]


def test_end_of_day_report_never_hard_codes_notify_target() -> None:
    """No notify service literal outside the input's placeholder text."""
    bp = end_of_day_report()
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