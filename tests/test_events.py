"""Tests for the NestQuest bus events (Feature 10, task 6).

Since Feature 18 — and, since the DB removal, without any local
business layer — the integration fires NO transition event itself:
``nestquest.complete_quest`` proxies to the API's panel complete
route, the API service builds and publishes the transition frames on
its SSE stream, and the integration's subscription
(:mod:`custom_components.nestquest.sse`) re-fires them.  The tests
below script the API's payloads and frames with
:class:`conftest.ScriptedPanelClient` and deliver them through
:func:`conftest.refire_api_transitions` (the production event path,
driven synchronously) before asserting the bus.  The API's own frame
construction is pinned on the production plane by tests/test_api_sse.py.
"""
from __future__ import annotations

import re

from conftest import ScriptedPanelClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.const import (
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_MISSED,
    EVENT_QUEST_UNCOMPLETED,
    SERVICE_COMPLETE_QUEST,
)

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")

ADA = 1
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


def _payload(children) -> dict:
    return {
        "today_iso": "2026-09-23",
        "cycle_day": 0,
        "children": list(children),
    }


def _open_payload(instance_count: int) -> dict:
    return _payload(
        [
            _child(
                ADA,
                "Ada",
                [_instance(10 + offset, ADA) for offset in range(instance_count)],
            )
        ]
    )


def _completed_frame(instance_id: int, *, window="morning"):
    return (
        EVENT_QUEST_COMPLETED,
        {
            "child_id": ADA,
            "child_name": "Ada",
            "instance_id": instance_id,
            "quest_title": "Brush teeth",
            "window": window,
            "due_date": "2026-09-23",
            "due_time": "08:00" if window == "morning" else "19:00",
            "occurred_at": _OCCURRED,
            "was_on_time": True,
        },
    )


def _day_complete_frame(quests_due: int):
    return (
        EVENT_CHILD_DAY_COMPLETE,
        {
            "child_id": ADA,
            "child_name": "Ada",
            "quests_due": quests_due,
            "quests_completed": quests_due,
            "occurred_at": _OCCURRED,
        },
    )


async def _setup_entry(hass, make_entry, client):
    """Wire, script, and set up an entry serving the scripted household."""
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    return entry


async def test_quest_completed_fires_with_documented_payload(
    hass, make_entry
) -> None:
    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    instance_id = 10
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": ADA},
    )
    # The completed event arrives over the API's SSE stream (the
    # subscription re-fires it), never from the service handler.
    client.published_frames.append(_completed_frame(instance_id))
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    fired = hass.bus.fired(EVENT_QUEST_COMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["child_id"] == ADA
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert payload["window"] == "morning"
    assert payload["was_on_time"] is not None
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]


async def test_recomplete_no_op_fires_nothing(hass, make_entry) -> None:
    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    instance_id = 10
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": ADA},
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": ADA},
    )
    # The no-op verdict is decided in the API's completion layer: the
    # second call appended nothing, so the API published no second
    # frame and the bus stays at exactly one event.
    client.published_frames.append(_completed_frame(instance_id))
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_child_day_complete_fires_when_day_clears(
    hass, make_entry
) -> None:
    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    instance_id = 10
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": ADA},
    )
    client.published_frames.extend(
        [
            _completed_frame(instance_id),
            _day_complete_frame(quests_due=1),
        ]
    )
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    day_complete = hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)
    assert len(day_complete) == 1, "exactly one day-complete per cleared day"
    payload = day_complete[0]
    assert payload["child_id"] == ADA
    assert payload["child_name"] == "Ada"
    assert payload["quests_due"] == 1
    assert _TIMESTAMP.match(payload["occurred_at"])


async def test_child_day_complete_does_not_fire_partway(
    hass, make_entry
) -> None:
    client = ScriptedPanelClient(_open_payload(2))
    entry = await _setup_entry(hass, make_entry, client)
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 10, "actor": "panel", "actor_child_id": ADA},
    )
    # The API publishes the completion but not a day-complete (the
    # child's day is not clear yet); the subscription re-fires only
    # what was published.
    client.published_frames.append(_completed_frame(10))
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    assert hass.bus.fired(EVENT_CHILD_DAY_COMPLETE) == []
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 11, "actor": "panel", "actor_child_id": ADA},
    )
    client.published_frames.extend(
        [
            _completed_frame(11, window="evening"),
            _day_complete_frame(quests_due=2),
        ]
    )
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1


async def test_uncompleted_fires_on_reversal_only(hass, make_entry) -> None:
    """An actual reversal fires the uncompleted event — but only once,
    and only through the API service's transition stream: the HA
    ``uncomplete_quest`` service is gone, so the reversal is the API's
    admin route; its published frame is delivered by the SSE
    subscription."""
    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    instance_id = 10
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": ADA},
    )
    client.published_frames.extend(
        [
            _completed_frame(instance_id),
            # The API's admin uncomplete route publishes the reversal
            # the same way the panel completion publishes its event.
            (
                EVENT_QUEST_UNCOMPLETED,
                {
                    "child_id": ADA,
                    "child_name": "Ada",
                    "instance_id": instance_id,
                    "quest_title": "Brush teeth",
                    "window": "morning",
                    "due_date": "2026-09-23",
                    "due_time": "08:00",
                    "occurred_at": _OCCURRED,
                },
            ),
        ]
    )
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    fired = hass.bus.fired(EVENT_QUEST_UNCOMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert _TIMESTAMP.match(payload["occurred_at"])
    # Un-completing an already-open instance is a no-op: nothing is
    # appended, nothing is published, and nothing further fires.
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_UNCOMPLETED)) == 1


def test_missed_event_name_is_documented_contract() -> None:
    """Feature 10 defines the missed event Feature 11's sweep fires."""
    assert EVENT_QUEST_MISSED == "nestquest_quest_missed"


async def test_appended_verdict_is_atomic_under_duplicate_calls(
    hass, make_entry
) -> None:
    """Concurrent duplicate completes each reach the API, whose
    completion layer decides the appended verdict: exactly one
    appended, so the API published exactly one frame and the bus
    carries one event."""
    import asyncio

    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    instance_id = 10
    calls = [
        hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance_id,
                "actor": "panel",
                "actor_child_id": ADA,
            },
        )
        for _ in range(2)
    ]
    await asyncio.gather(*calls)
    assert len(client.complete_calls) == 2
    # The API's completion layer decides the verdict: one call
    # appended, the duplicate did not — so the API published exactly
    # one frame and the bus carries one event.
    client.published_frames.append(_completed_frame(instance_id))
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_completion_updates_entities_immediately(
    hass, make_entry
) -> None:
    """The remaining-today sensor reflects the completion the moment
    the service call returns — no manual refresh — and the day-complete
    event fired exactly once when the day became clear."""
    client = ScriptedPanelClient(
        _open_payload(1),
        _payload([_child(ADA, "Ada", [_instance(10, ADA, state="completed")])]),
    )
    entry = await _setup_entry(hass, make_entry, client)
    remaining_before = hass.entities[
        f"nestquest_child_{ADA}_quests_remaining_today"
    ].native_value
    assert remaining_before == 1

    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": 10, "actor": "panel", "actor_child_id": ADA},
    )
    remaining_after = hass.entities[
        f"nestquest_child_{ADA}_quests_remaining_today"
    ].native_value
    assert remaining_after == 0, (
        "sensor must reflect the completion without a manual refresh"
    )
    client.published_frames.extend(
        [
            _completed_frame(10),
            _day_complete_frame(quests_due=1),
        ]
    )
    from conftest import refire_api_transitions

    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1


async def test_forced_refreshes_serialize_no_stale_publish(
    hass, make_entry
) -> None:
    """Overlapping forced refreshes never interleave: a slow pass
    pauses mid-snapshot, and the queued pass still publishes AFTER
    it, so the last published snapshot reflects the latest mutation."""
    import asyncio

    client = ScriptedPanelClient(_open_payload(1))
    entry = await _setup_entry(hass, make_entry, client)
    coordinator = entry.runtime_data.coordinator
    order: list[str] = []

    async def _slow_update():
        order.append("start")
        await asyncio.sleep(0.01)
        order.append("end")
        return coordinator.data

    coordinator._async_update_data = _slow_update
    await asyncio.gather(coordinator.async_refresh(), coordinator.async_refresh())
    assert order == ["start", "end", "start", "end"], (
        "overlapping refreshes must serialize: " + str(order)
    )
