"""Entity lifecycle across child add/deactivate/reactivate (Feature 10, task 8).

The household state the entities mirror comes from the API service's
panel route, so a deactivate/reactivate/add is scripted as a payload
change served by :class:`conftest.StubSnapshotClient`; the reload
(unload + setup) re-polls it, exactly as production does.
"""
from __future__ import annotations

from conftest import StubSnapshotClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry

PER_CHILD_KINDS = (
    "quests_due_today",
    "quests_completed_today",
    "quests_remaining_today",
    "completion_pct_today",
    "next_quest",
    "all_done",
    "present_today",
)
HOUSEHOLD_UNIQUE_IDS = (
    "nestquest_household_quests_due_today",
    "nestquest_household_quests_completed_today",
    "nestquest_cycle_day",
)

ADA = 1
BO = 2
CORY_ID = 4


def _child(child_id: int, name: str, *, present=True, instances=()):
    completed = sum(1 for i in instances if i["state"] == "completed")
    due = len(instances)
    return {
        "child_id": child_id,
        "child_name": name,
        "present": present,
        "next_present": None,
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


#: The full household (Ada + Bo, one daily quest each) and the states
#: the lifecycle walks through: Bo deactivated, reactivated, completed.
_BOTH = _payload(
    [
        _child(ADA, "Ada", instances=[_instance(7, ADA)]),
        _child(BO, "Bo", instances=[_instance(8, BO)]),
    ]
)
_BO_GONE = _payload([_child(ADA, "Ada", instances=[_instance(7, ADA)])])
_BO_DONE = _payload(
    [
        _child(ADA, "Ada", instances=[_instance(7, ADA)]),
        _child(BO, "Bo", instances=[_instance(8, BO, state="completed")]),
    ]
)
_ADA_ONLY = _payload([_child(ADA, "Ada", instances=[_instance(7, ADA)])])
_ADA_AND_CORY = _payload(
    [
        _child(ADA, "Ada", instances=[_instance(7, ADA)]),
        _child(CORY_ID, "Cory"),
    ]
)


def _child_unique_ids(child_id: int) -> set[str]:
    return {f"nestquest_child_{child_id}_{kind}" for kind in PER_CHILD_KINDS}


async def _reload(hass, entry) -> None:
    """Unload then set up: the harness's restart/reload equivalent."""
    assert await async_unload_entry(hass, entry) is True
    assert await async_setup_entry(hass, entry) is True


async def _setup_with_household(hass, make_entry, *payloads):
    """Set up the entry with a scripted, ordered snapshot history."""
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    client = set_coordinator_client(entry, StubSnapshotClient(*payloads))
    assert await async_setup_entry(hass, entry) is True
    return entry, entry.runtime_data.coordinator, client


async def test_deactivated_child_entities_removed_on_reload(
    hass, make_entry
) -> None:
    """A child absent from the API's snapshot loses its entities on
    reload; the surviving child's entities are untouched."""
    entry, _coordinator, _client = await _setup_with_household(
        hass, make_entry, _BOTH, _BO_GONE
    )
    assert _child_unique_ids(ADA) <= set(hass.entities)
    assert _child_unique_ids(BO) <= set(hass.entities)

    await _reload(hass, entry)

    assert _child_unique_ids(ADA) <= set(hass.entities), (
        "the surviving child's entities must be untouched"
    )
    assert not (_child_unique_ids(BO) & set(hass.entities)), (
        "the deactivated child's entities must be gone after reload"
    )


async def test_reactivation_restores_entities_with_original_unique_ids(
    hass, make_entry
) -> None:
    original = _child_unique_ids(BO)
    entry, _coordinator, _client = await _setup_with_household(
        hass, make_entry, _BOTH, _BO_GONE, _BOTH
    )
    await _reload(hass, entry)
    assert not (original & set(hass.entities))

    await _reload(hass, entry)

    assert original <= set(hass.entities), (
        "reactivation must restore the exact original unique_ids"
    )
    bo_due = hass.entities[f"nestquest_child_{BO}_quests_due_today"]
    assert bo_due.native_value == 1, "restored entities carry live state"


async def test_new_child_gets_entities_without_disturbing_existing(
    hass, make_entry
) -> None:
    """A child ADDED to the API's snapshot gains its entities on
    reload; the existing children's entities are untouched."""
    entry, _coordinator, _client = await _setup_with_household(
        hass, make_entry, _ADA_ONLY, _ADA_AND_CORY
    )
    before_ada = set(hass.entities) & _child_unique_ids(ADA)

    await _reload(hass, entry)

    assert before_ada <= set(hass.entities), "existing entities untouched"
    assert _child_unique_ids(CORY_ID) <= set(hass.entities), (
        "the new child's entities appear after reload"
    )
    assert hass.entities[
        f"nestquest_child_{CORY_ID}_quests_due_today"
    ].native_value == 0


async def test_restart_equivalent_restores_all_entity_states(
    hass, make_entry
) -> None:
    """Unload + setup (the restart equivalent) restores every active
    child's entities with the API's current states and the household
    rollups."""
    entry, _coordinator, _client = await _setup_with_household(
        hass, make_entry, _BOTH, _BO_DONE
    )
    await _reload(hass, entry)

    assert hass.entities[
        f"nestquest_child_{ADA}_quests_completed_today"
    ].native_value == 0
    assert hass.entities[
        f"nestquest_child_{BO}_quests_completed_today"
    ].native_value == 1, "the API's recorded completion survives the restart"
    assert set(HOUSEHOLD_UNIQUE_IDS) <= set(hass.entities)
    assert hass.entities[
        "nestquest_household_quests_completed_today"
    ].native_value == 1
