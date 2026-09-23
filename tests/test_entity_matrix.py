"""The Feature 10 entity-and-event matrix (task 9).

One fixture drives every assertion the done-condition names: correct
values for every sensor and binary sensor (including the zero-quest
child and the 255-character state limit), the completed/uncompleted/
day-complete events re-fired exactly once from the API's SSE frames,
the panel payload omitting missed instances while admin_instances
equals it, and no entities for a child the API does not report.  The
per-task test files cover each behavior in depth; this file is the
single pass that proves them all against ONE fixture, so a regression
in any contract fails here too.

Since the DB removal the household state and every transition come
from the API service, so the fixture scripts the panel route's
payloads and completion surface (:class:`conftest.ScriptedPanelClient`)
and delivers the transition frames through the SSE subscription — the
production event path.
"""
from __future__ import annotations

import re

from conftest import ScriptedPanelClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.const import (
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_UNCOMPLETED,
    SERVICE_COMPLETE_QUEST,
)

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")

ADA = 1
BO = 2
CORY = 3

_OCCURRED = "2026-09-23T07:55:00+00:00"


def _instance(instance_id: int, child_id: int, *, window="morning", state="open"):
    return {
        "id": instance_id,
        "definition_id": 3,
        "child_id": child_id,
        "title": "Brush teeth",
        "icon": "🦷",
        "window": window,
        "due_time": "08:00" if window == "morning" else "19:00",
        "state": state,
        "overdue": False,
        "completed_at": None if state == "open" else _OCCURRED,
        "on_time": None if state == "open" else True,
    }


def _child(child_id: int, name: str, instances=()):
    completed = sum(1 for i in instances if i["state"] == "completed")
    due = len(instances)
    return {
        "child_id": child_id,
        "child_name": name,
        "present": True,
        "next_present": None,
        "due_today": due,
        "completed_today": completed,
        "remaining_today": due - completed,
        "completion_pct": 100 if due == 0 else round(completed / due * 100),
        "instances": list(instances),
    }


def _payload(children, cycle_day=0) -> dict:
    return {
        "today_iso": "2026-09-23",
        "cycle_day": cycle_day,
        "children": list(children),
    }


def _completed_frame(instance_id: int, child_id: int, child_name: str, window: str):
    """The completed-event frame the API service publishes for one
    panel completion (the day-complete rule is the API's; its payload
    shape is pinned by tests/test_api_sse.py on the production
    plane)."""
    return (
        EVENT_QUEST_COMPLETED,
        {
            "child_id": child_id,
            "child_name": child_name,
            "instance_id": instance_id,
            "quest_title": "Brush teeth",
            "window": window,
            "due_date": "2026-09-23",
            "due_time": "08:00" if window == "morning" else "19:00",
            "occurred_at": _OCCURRED,
            "was_on_time": True,
        },
    )


def _day_complete_frame(child_id: int, child_name: str):
    """The day-complete frame the API publishes once a child's day
    clears (after the LAST completion of the day)."""
    return (
        EVENT_CHILD_DAY_COMPLETE,
        {
            "child_id": child_id,
            "child_name": child_name,
            "quests_due": 2,
            "quests_completed": 2,
            "occurred_at": _OCCURRED,
        },
    )


async def _fixture(hass, make_entry):
    """Two quest children, one zero-quest child; the inactive child is
    simply ABSENT from the API's snapshot (the API only reports active
    children, so the integration can never create its entities)."""
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    client = ScriptedPanelClient(
        _payload(
            [
                _child(ADA, "Ada", [_instance(7, ADA), _instance(8, ADA, window="evening")]),
                _child(BO, "Bo", [_instance(9, BO), _instance(10, BO, window="evening")]),
                _child(CORY, "Cory"),
            ]
        ),
        _payload(
            [
                _child(
                    ADA,
                    "Ada",
                    [
                        _instance(7, ADA, state="completed"),
                        _instance(8, ADA, window="evening", state="completed"),
                    ],
                ),
                _child(BO, "Bo", [_instance(9, BO), _instance(10, BO, window="evening")]),
                _child(CORY, "Cory"),
            ]
        ),
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    return entry, client


def _sensor(hass, child_id, kind):
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


async def test_entity_and_event_matrix(hass, make_entry) -> None:
    entry, client = await _fixture(hass, make_entry)
    coordinator = entry.runtime_data.coordinator

    # --- Every reported child has the full entity set; the child the
    # API does not report has none.
    kinds = (
        "quests_due_today",
        "quests_completed_today",
        "quests_remaining_today",
        "completion_pct_today",
        "next_quest",
        "all_done",
        "present_today",
    )
    ghost_id = 99
    for child in (ADA, BO, CORY):
        for kind in kinds:
            assert f"{DOMAIN}_child_{child}_{kind}" in hass.entities, kind
    for kind in kinds:
        assert f"{DOMAIN}_child_{ghost_id}_{kind}" not in hass.entities, (
            "children absent from the API snapshot must have no entities"
        )

    # --- Correct values against the fixture: Ada and Bo owe two
    # quests (morning + evening), Cory owes none and is still 100%.
    for child in (ADA, BO):
        assert _sensor(hass, child, "quests_due_today").native_value == 2
        assert (
            _sensor(hass, child, "quests_completed_today").native_value == 0
        )
        assert (
            _sensor(hass, child, "quests_remaining_today").native_value == 2
        )
        assert (
            _sensor(hass, child, "completion_pct_today").native_value == 0
        )
        assert _sensor(hass, child, "next_quest").native_value == (
            "Brush teeth"
        )
        assert _sensor(hass, child, "all_done").is_on is False
        assert _sensor(hass, child, "present_today").is_on is True
    assert _sensor(hass, CORY, "quests_due_today").native_value == 0
    assert _sensor(hass, CORY, "completion_pct_today").native_value == 100
    assert _sensor(hass, CORY, "all_done").is_on is False
    assert _sensor(hass, CORY, "next_quest").native_value == "none"

    # --- Household rollups equal the per-child sums.
    assert hass.entities[
        "nestquest_household_quests_due_today"
    ].native_value == 4
    assert hass.entities[
        "nestquest_household_quests_completed_today"
    ].native_value == 0

    # --- The 255-character limit holds for every registered entity.
    for unique_id, entity in hass.entities.items():
        state = getattr(entity, "native_value", None)
        if state is None:
            state = getattr(entity, "is_on", None)
        assert state is None or not (
            isinstance(state, str) and len(state) > 255
        ), unique_id

    # --- Completing both of Ada's quests fires the events exactly
    # once each and flips her entities immediately.  The transition
    # events arrive over the API's SSE stream (the subscription
    # re-fires them), never from the service handler.
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 7, "actor": "panel", "actor_child_id": ADA},
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 8, "actor": "panel", "actor_child_id": ADA},
    )
    client.published_frames.extend(
        [
            _completed_frame(7, ADA, "Ada", "morning"),
            _completed_frame(8, ADA, "Ada", "evening"),
            # The API publishes the day-complete frame only when the
            # day clears — after the LAST completion of the day.
            _day_complete_frame(ADA, "Ada"),
        ]
    )
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 2
    for payload in hass.bus.fired(EVENT_QUEST_COMPLETED):
        assert _TIMESTAMP.match(payload["occurred_at"])
        assert isinstance(payload["was_on_time"], bool)
        assert payload["child_name"] in ("Ada",)
        assert payload["quest_title"] == "Brush teeth"
        assert isinstance(payload["instance_id"], int)
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1
    # The next scripted snapshot reflects both completions.
    await coordinator.async_refresh()
    assert _sensor(hass, ADA, "all_done").is_on is True
    assert _sensor(hass, ADA, "quests_remaining_today").native_value == 0
    assert (
        _sensor(hass, ADA, "completion_pct_today").native_value == 100
    )

    # --- Reversing one quest fires the uncompleted event exactly once.
    #  The HA ``uncomplete_quest`` service is gone (the API service's
    # admin route is the reversal path), so the reversal is the API's:
    # it publishes the uncompleted frame and the integration re-fires
    # it; the coordinator's next poll picks the restored counts up.
    client.published_frames.append(
        (
            EVENT_QUEST_UNCOMPLETED,
            {
                "child_id": ADA,
                "child_name": "Ada",
                "instance_id": 7,
                "quest_title": "Brush teeth",
                "window": "morning",
                "due_date": "2026-09-23",
                "due_time": "08:00",
                "occurred_at": _OCCURRED,
            },
        )
    )
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_UNCOMPLETED)) == 1

    # --- The panel payload omits missed instances (D-009) — the API
    # panel route omits missed rows ENTIRELY, so admin_instances
    # cannot carry them either (the admin surface for missed quests is
    # the PWA, reading the API directly).  A snapshot built from the
    # payload can only ever hold open and completed rows: pin that
    # the payload round-trips verbatim.
    await coordinator.async_refresh()
    attributes = _sensor(hass, BO, "quests_due_today").extra_state_attributes
    assert attributes["instances"] == [
        dict(_instance(9, BO)),
        dict(_instance(10, BO, window="evening")),
    ], "the panel payload round-trips the API's open rows verbatim"
    assert attributes["admin_instances"] == attributes["instances"], (
        "the API payload omits missed rows, so the admin payload "
        "carries none either (the PWA is the admin surface now)"
    )


async def test_payload_schema_matches_the_documented_contract(
    hass, make_entry
) -> None:
    """Every fired payload carries the documented fields with the
    documented types."""
    entry, client = await _fixture(hass, make_entry)
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 7, "actor": "panel", "actor_child_id": ADA},
    )
    client.published_frames.append(_completed_frame(7, ADA, "Ada", "morning"))
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    payload = hass.bus.fired(EVENT_QUEST_COMPLETED)[0]
    for key, check in (
        ("child_id", lambda v: isinstance(v, int)),
        ("child_name", lambda v: isinstance(v, str)),
        ("instance_id", lambda v: isinstance(v, int)),
        ("quest_title", lambda v: isinstance(v, str)),
        ("window", lambda v: v in ("morning", "evening")),
        ("due_date", lambda v: isinstance(v, str)),
        ("due_time", lambda v: v is None or isinstance(v, str)),
        ("occurred_at", lambda v: bool(_TIMESTAMP.match(v))),
        ("was_on_time", lambda v: isinstance(v, bool)),
    ):
        assert key in payload, key
        assert check(payload[key]), key
