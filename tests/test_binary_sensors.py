"""Tests for the per-child binary sensors (Feature 10, task 4).

The snapshot comes from the API service's panel route (the presence
engine resolves server-side), so these tests script the route's
payload through :class:`conftest.StubSnapshotClient` instead of
seeding a local database.
"""
from __future__ import annotations

from conftest import StubSnapshotClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.const import DOMAIN


def _binary(hass, child_id: int, kind: str):
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


def _child(
    child_id: int,
    name: str,
    *,
    present=True,
    next_present=None,
    instances=(),
):
    completed = sum(1 for i in instances if i["state"] == "completed")
    due = len(instances)
    return {
        "child_id": child_id,
        "child_name": name,
        "present": present,
        "next_present": next_present,
        "due_today": due,
        "completed_today": completed,
        "remaining_today": due - completed,
        "completion_pct": 100 if due == 0 else round(completed / due * 100),
        "instances": list(instances),
    }


def _instance(instance_id: int, child_id: int, *, state="open") -> dict:
    return {
        "id": instance_id,
        "definition_id": 3,
        "child_id": child_id,
        "title": "Brush teeth",
        "icon": "🦷",
        "window": "morning",
        "due_time": "08:00",
        "state": state,
        "overdue": False,
        "completed_at": None if state == "open" else "2026-09-23T07:55:00+00:00",
        "on_time": None if state == "open" else True,
    }


def _payload(children) -> dict:
    return {
        "today_iso": "2026-09-23",
        "cycle_day": 0,
        "children": list(children),
    }


ADA = 1
BO = 2
CORY = 3


async def _setup_entry(hass, make_entry, *payloads):
    """Set up the integration with a scripted snapshot client."""
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    set_coordinator_client(entry, StubSnapshotClient(*payloads))
    assert await async_setup_entry(hass, entry) is True
    return entry, entry.runtime_data.coordinator


async def test_all_done_off_with_open_quests_and_zero_quests(
    hass, make_entry
) -> None:
    """all_done is OFF while quests are owed AND on a zero-quest day;
    a child with no quests never fires the celebration automation."""
    _entry, coordinator = await _setup_entry(
        hass,
        make_entry,
        _payload(
            [
                _child(ADA, "Ada", instances=[_instance(7, ADA)]),
                _child(BO, "Bo", instances=[_instance(8, BO)]),
                _child(CORY, "Cory"),
            ]
        ),
    )

    assert _binary(hass, ADA, "all_done").is_on is False
    assert _binary(hass, BO, "all_done").is_on is False
    assert _binary(hass, CORY, "all_done").is_on is False


async def test_all_done_on_only_when_day_clear(hass, make_entry) -> None:
    _entry, coordinator = await _setup_entry(
        hass,
        make_entry,
        _payload([_child(ADA, "Ada", instances=[_instance(7, ADA)])]),
        _payload(
            [
                _child(
                    ADA,
                    "Ada",
                    instances=[_instance(7, ADA, state="completed")],
                )
            ]
        ),
    )
    await coordinator.async_refresh()
    assert _binary(hass, ADA, "all_done").is_on is True


async def test_present_today_on_without_schedule_off_when_absent(
    hass, make_entry
) -> None:
    """Presence is resolved by the API's presence engine: present=True
    renders ON, present=False renders OFF."""
    _entry, _coordinator = await _setup_entry(
        hass,
        make_entry,
        _payload([_child(ADA, "Ada"), _child(CORY, "Cory", present=False)]),
    )

    assert _binary(hass, ADA, "present_today").is_on is True
    assert _binary(hass, CORY, "present_today").is_on is False


async def test_binary_sensor_identity_and_attributes(hass, make_entry) -> None:
    _entry, _coordinator = await _setup_entry(
        hass, make_entry, _payload([_child(ADA, "Ada")])
    )

    all_done = _binary(hass, ADA, "all_done")
    present = _binary(hass, ADA, "present_today")
    assert all_done.unique_id == f"nestquest_child_{ADA}_all_done"
    assert present.unique_id == f"nestquest_child_{ADA}_present_today"
    assert all_done.name == "NestQuest Ada all done"
    assert present.name == "NestQuest Ada present today"
    for entity in (all_done, present):
        assert entity.device_info.name == "NestQuest Ada"
        assert all_done.extra_state_attributes == {
            "child_id": ADA,
            "child_name": "Ada",
        }
        assert present.extra_state_attributes == {
            "child_id": ADA,
            "child_name": "Ada",
            "next_present": None,
        }


async def test_present_today_carries_next_present_when_away(
    hass, make_entry
) -> None:
    """A child away today carries the ISO date of their next present
    day (the panel's away plate renders ``Returns <weekday>, <Mon D>``
    from it); an always-absent pattern carries ``None``."""
    _entry, _coordinator = await _setup_entry(
        hass,
        make_entry,
        _payload(
            [
                _child(
                    ADA,
                    "Ada",
                    present=False,
                    next_present="2026-09-24",
                ),
                _child(CORY, "Cory", present=False, next_present=None),
            ]
        ),
    )

    assert _binary(hass, ADA, "present_today").is_on is False
    assert _binary(hass, ADA, "present_today").extra_state_attributes[
        "next_present"
    ] == "2026-09-24"

    assert _binary(hass, CORY, "present_today").is_on is False
    assert _binary(hass, CORY, "present_today").extra_state_attributes[
        "next_present"
    ] is None
