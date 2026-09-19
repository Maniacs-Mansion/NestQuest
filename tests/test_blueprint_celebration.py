"""Tests for the NestQuest day-complete celebration automation blueprint.

The celebration fires on the ``nestquest_child_day_complete`` event —
which NestQuest only fires when quests were owed and all are complete,
so a zero-quest day can never celebrate.  Dedupe design (per-child,
per-day): the household points ONE ``input_text`` helper at the
blueprint; the condition celebrates only when THIS child has no
``<child_id>:<today>`` entry stored, and the action rewrites the
helper with only today's entries plus the new one — so a child who
un-completes and re-completes the same day is celebrated once, not
twice, while a second child clearing the same day is still celebrated.

The harness (YAML ``!input`` loader, state fixtures, jinja rendering)
is shared in :mod:`tests.blueprint_helpers`; the directory-wide shape
and entity-discipline tests in test_blueprints.py cover this file
too.  ``now()`` in the dedupe condition is injected by the test as a
fixed callable, keeping the render deterministic.
"""
from __future__ import annotations

import datetime
import re

from custom_components.nestquest.const import EVENT_CHILD_DAY_COMPLETE

from tests.blueprint_helpers import (
    BlueprintInput,
    notify_data,
    blueprint,
    iter_strings,
    make_states,
    render,
    TemplateState,
)

CELEBRATION_TITLE = "NestQuest day complete"

HELPER_ENTITY = "input_text.nestquest_last_celebrated"

#: The fixed "now" every dedupe render uses: 2026-09-19 15:00 local.
FIXED_NOW = datetime.datetime(2026, 9, 19, 15, 0, 0)


def celebration() -> dict:
    """Return the parsed day-complete-celebration blueprint."""
    return blueprint("day_complete_celebration")


def celebration_conditions(bp: dict) -> list[dict]:
    """Return the blueprint's conditions: toggle first, dedupe second."""
    conditions = bp["conditions"]
    assert isinstance(conditions, list) and len(conditions) == 2
    return conditions


def dedupe_condition(bp: dict) -> str:
    """Return the once-per-child-per-day dedupe template (true = celebrate)."""
    return celebration_conditions(bp)[1]["value_template"]


def stamp_value_template(bp: dict) -> str:
    """Return the helper-stamp action's value template."""
    stamp = bp["actions"][1]
    return stamp["data"]["value"]


def trigger_payload(child_id: int, child_name: str) -> dict:
    """A nestquest_child_day_complete trigger payload fixture."""
    return {
        "payload": {
            "child_id": child_id,
            "child_name": child_name,
            "quests_due": 3,
            "quests_completed": 3,
            "occurred_at": "2026-09-19T15:00:00+00:00",
        }
    }


def render_dedupe(
    helper_state: str | None, child_id: int = 1
) -> str:
    """Render the dedupe condition with the helper holding helper_state.

    ``None`` models a helper entity the fixture does not hold (never
    created or not yet set), which HA exposes as a missing state.
    """
    states = make_states(
        input_texts=(
            []
            if helper_state is None
            else [TemplateState(HELPER_ENTITY, helper_state)]
        )
    )
    return render(
        dedupe_condition(celebration()),
        states=states,
        last_celebrated_helper=HELPER_ENTITY,
        now=lambda: FIXED_NOW,
        trigger=trigger_payload(child_id, "Ada"),
    ).strip()


def render_stamp(helper_state: str | None, child_id: int = 1) -> str:
    """Render the stamp action's value with the helper holding helper_state."""
    states = make_states(
        input_texts=(
            []
            if helper_state is None
            else [TemplateState(HELPER_ENTITY, helper_state)]
        )
    )
    return render(
        stamp_value_template(celebration()),
        states=states,
        last_celebrated_helper=HELPER_ENTITY,
        now=lambda: FIXED_NOW,
        trigger=trigger_payload(child_id, "Ada"),
    ).strip()


# ---------------------------------------------------------------------------
# Trigger, inputs, defaults, and wiring.
# ---------------------------------------------------------------------------
def test_celebration_triggers_on_the_child_day_complete_event() -> None:
    """The event trigger references the real nestquest_child_day_complete."""
    trigger = celebration()["triggers"][0]
    assert trigger["trigger"] == "event"
    assert trigger["event_type"] == "nestquest_child_day_complete"
    assert trigger["event_type"] == EVENT_CHILD_DAY_COMPLETE


def test_celebration_declares_inputs_with_selectors() -> None:
    """The four inputs exist, carry selectors, and default sanely."""
    bp = celebration()
    inputs = bp["blueprint"]["input"]
    expected = {
        "notify_target",
        "celebration_message",
        "celebrate",
        "last_celebrated_helper",
    }
    assert set(inputs) == expected
    for name, spec in inputs.items():
        assert isinstance(spec["selector"], dict) and spec["selector"], name
    assert inputs["celebrate"]["default"] is True
    assert "text" in inputs["notify_target"]["selector"]
    assert "text" in inputs["celebration_message"]["selector"]
    assert "boolean" in inputs["celebrate"]["selector"]
    assert inputs["last_celebrated_helper"]["selector"]["entity"]["filter"] == [
        {"domain": "input_text"}
    ]
    # The description documents the zero-quest-day rule and the dedupe.
    description = bp["blueprint"]["description"]
    assert "zero-quest day" in description
    assert "once" in description.lower()


def test_celebration_wires_inputs_not_literals() -> None:
    """Notify and stamp actions both use !input; the dedupe reads the helper."""
    bp = celebration()
    assert bp["variables"]["celebrate"] == BlueprintInput("celebrate")
    assert bp["variables"]["last_celebrated_helper"] == BlueprintInput(
        "last_celebrated_helper"
    )

    toggle, dedupe = celebration_conditions(bp)
    assert toggle["condition"] == "template"
    assert "celebrate" in toggle["value_template"]
    assert dedupe["condition"] == "template"
    assert "last_celebrated_helper" in dedupe["value_template"]
    assert "child_id" in dedupe["value_template"], (
        "the dedupe must be per child, not per household"
    )

    notify_action, stamp_action = bp["actions"]
    assert notify_action["action"] == BlueprintInput("notify_target")
    data = notify_data(bp)
    assert data["title"] == CELEBRATION_TITLE
    assert data["message"] == BlueprintInput("celebration_message")

    assert stamp_action["action"] == "input_text.set_value"
    assert stamp_action["target"]["entity_id"] == BlueprintInput(
        "last_celebrated_helper"
    )
    assert "now()" in stamp_action["data"]["value"]


def test_celebration_message_default_renders_the_child_name() -> None:
    """The default message renders the trigger payload's child_name."""
    default_message = celebration()["blueprint"]["input"]["celebration_message"][
        "default"
    ]
    rendered = render(default_message, trigger=trigger_payload(1, "Ada"))
    assert rendered == "Legendary! Ada cleared every quest today!"


# ---------------------------------------------------------------------------
# The once-per-child-per-day dedupe condition.
# ---------------------------------------------------------------------------
def test_celebration_dedupe_true_when_child_not_celebrated_today() -> None:
    """A helper without THIS child's entry for today lets the
    celebration through — including when another child was celebrated
    earlier the same day."""
    assert render_dedupe(None) == "True"
    assert render_dedupe("") == "True"
    assert render_dedupe("2:2026-09-19") == "True", (
        "a second child clearing the same day must still celebrate"
    )
    assert render_dedupe("1:2026-09-18") == "True", (
        "yesterday's entry never blocks today"
    )


def test_celebration_dedupe_false_when_child_already_celebrated_today() -> None:
    """A child already celebrated today is suppressed — the un-complete
    and re-complete the same day case."""
    assert render_dedupe("1:2026-09-19") == "False"
    assert render_dedupe("2:2026-09-19,1:2026-09-19") == "False"


def test_celebration_stamp_prunes_to_today_and_appends() -> None:
    """The stamp keeps only today's entries plus the new one: yesterday's
    entries are dropped (the helper never outgrows its text limit and
    stale entries cannot block next week), and the celebrated child is
    recorded."""
    assert render_stamp(None, child_id=1) == "1:2026-09-19"
    assert render_stamp("1:2026-09-18", child_id=2) == "2:2026-09-19"
    assert render_stamp("1:2026-09-19", child_id=2) == (
        "1:2026-09-19,2:2026-09-19"
    )
    assert render_stamp("1:2026-09-18,2:2026-09-18", child_id=3) == (
        "3:2026-09-19"
    )


def test_celebration_celebrate_toggle_renders() -> None:
    """The enable condition renders truthy/false from the input value."""
    toggle = celebration_conditions(celebration())[0]
    assert render(toggle["value_template"], celebrate=True).strip() == "True"
    assert render(toggle["value_template"], celebrate=False).strip() == "False"


def test_celebration_never_hard_codes_notify_target() -> None:
    """No notify service literal outside the input's placeholder text."""
    bp = celebration()
    spec = bp["blueprint"]
    assert not re.search(r"notify\.[a-z_]+", spec["description"])

    outside_input = {k: v for k, v in bp.items() if k != "blueprint"}
    for value in iter_strings(outside_input):
        assert not re.search(r"notify\.[a-z_.]+", value), value

    target_description = spec["input"]["notify_target"]["description"]
    assert re.search(r"notify\.[a-z_]+", target_description), (
        "the input description should show a placeholder example"
    )
    assert bp["actions"][0]["action"] == BlueprintInput("notify_target")

def test_celebration_dedupe_entry_equality_not_substring() -> None:
    """Child ids sharing a prefix must not suppress each other: after
    child 11 is celebrated, child 1 still celebrates (whole-entry
    comparison, not substring)."""
    assert render_dedupe("11:2026-09-19", child_id=11) == "False"
    assert render_dedupe("11:2026-09-19", child_id=1) == "True", (
        "child 1's entry must not be found inside child 11's entry"
    )
    assert render_dedupe("1:2026-09-19", child_id=11) == "True"


def test_celebration_mode_is_queued() -> None:
    """Two children completing at nearly the same time must both be
    processed: queued mode does not drop the second event."""
    assert celebration()["mode"] == "queued"


def test_every_blueprint_event_reference_is_real() -> None:
    """Every event a blueprint triggers on is one NestQuest actually
    fires or defines (Feature 10/11) — no invented event names."""
    from tests.blueprint_helpers import load_blueprints

    real_events = {
        "nestquest_quest_completed",
        "nestquest_quest_uncompleted",
        "nestquest_quest_missed",
        "nestquest_child_day_complete",
    }
    for name, bp in load_blueprints().items():
        for trigger in bp.get("triggers", []):
            if trigger.get("trigger") == "event":
                assert trigger["event_type"] in real_events, (
                    f"{name}: invented event {trigger['event_type']!r}"
                )
    assert celebration()["triggers"][0]["event_type"] == (
        "nestquest_child_day_complete"
    )
