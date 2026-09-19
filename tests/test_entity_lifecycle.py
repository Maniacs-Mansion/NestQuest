"""Entity lifecycle across child add/deactivate/reactivate (Feature 10, task 8)."""
from __future__ import annotations

import datetime

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.children import (
    create_child,
    list_children,
    set_child_active,
)
from custom_components.nestquest.const import DOMAIN
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

SEED_HORIZON_DAYS = 3
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


async def _reload(hass, entry) -> None:
    """Unload then set up: the harness's restart/reload equivalent."""
    assert await async_unload_entry(hass, entry) is True
    assert await async_setup_entry(hass, entry) is True


def _child_unique_ids(child_id: int) -> set[str]:
    return {f"nestquest_child_{child_id}_{kind}" for kind in PER_CHILD_KINDS}


async def _setup_and_seed(hass, make_entry):
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")
    today = datetime.date.today()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today.isoformat()}
        ),
        [ada.id, bo.id],
        ["morning"],
    )
    end = (today + datetime.timedelta(days=SEED_HORIZON_DAYS)).isoformat()
    await materialize(database, today.isoformat(), end, today=today)
    await entry.runtime_data.coordinator.async_refresh()
    return entry, ada, bo


async def test_deactivated_child_entities_removed_on_reload(
    hass, make_entry
) -> None:
    entry, ada, bo = await _setup_and_seed(hass, make_entry)
    assert _child_unique_ids(ada.id) <= set(hass.entities)
    assert _child_unique_ids(bo.id) <= set(hass.entities)

    await set_child_active(entry.runtime_data.database, bo.id, False)
    await _reload(hass, entry)

    assert _child_unique_ids(ada.id) <= set(hass.entities), (
        "the surviving child's entities must be untouched"
    )
    assert not (_child_unique_ids(bo.id) & set(hass.entities)), (
        "the deactivated child's entities must be gone after reload"
    )


async def test_reactivation_restores_entities_with_original_unique_ids(
    hass, make_entry
) -> None:
    entry, ada, bo = await _setup_and_seed(hass, make_entry)
    original = _child_unique_ids(bo.id)
    await set_child_active(entry.runtime_data.database, bo.id, False)
    await _reload(hass, entry)
    assert not (original & set(hass.entities))

    await set_child_active(entry.runtime_data.database, bo.id, True)
    await _reload(hass, entry)

    assert original <= set(hass.entities), (
        "reactivation must restore the exact original unique_ids"
    )
    bo_due = hass.entities[f"nestquest_child_{bo.id}_quests_due_today"]
    assert bo_due.native_value == 1, "restored entities carry live state"


async def test_new_child_gets_entities_without_disturbing_existing(
    hass, make_entry
) -> None:
    entry, ada, bo = await _setup_and_seed(hass, make_entry)
    before_ada = set(hass.entities) & _child_unique_ids(ada.id)

    cory = await create_child(entry.runtime_data.database, "Cory")
    await _reload(hass, entry)

    assert before_ada <= set(hass.entities), "existing entities untouched"
    assert _child_unique_ids(cory.id) <= set(hass.entities), (
        "the new child's entities appear after reload"
    )
    assert hass.entities[f"nestquest_child_{cory.id}_quests_due_today"].native_value == 0


async def test_restart_equivalent_restores_all_entity_states(
    hass, make_entry
) -> None:
    """Unload + setup (the restart equivalent) restores every active
    child's entities with correct states and the household rollups."""
    from custom_components.nestquest.completion import complete_instance

    entry, ada, bo = await _setup_and_seed(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    snapshot_ada = next(
        child
        for child in coordinator.data.children
        if child.child_id == ada.id
    )
    await complete_instance(
        entry.runtime_data.database,
        snapshot_ada.instances[0].instance_id,
        actor_source="panel",
        actor_child_id=ada.id,
    )
    await coordinator.async_refresh()
    assert hass.entities[
        f"nestquest_child_{ada.id}_quests_completed_today"
    ].native_value == 1

    await _reload(hass, entry)

    assert hass.entities[
        f"nestquest_child_{ada.id}_quests_completed_today"
    ].native_value == 1, "completed count survives the restart"
    assert hass.entities[
        f"nestquest_child_{bo.id}_quests_completed_today"
    ].native_value == 0
    assert set(HOUSEHOLD_UNIQUE_IDS) <= set(hass.entities)
    assert hass.entities[
        "nestquest_household_quests_completed_today"
    ].native_value == 1


async def test_unload_shuts_coordinator_before_closing_database(
    hass, make_entry
) -> None:
    """The coordinator's listeners are cleared while the database is
    still connected: a scheduled refresh must never race the close."""
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    seen_connected = []

    async def _probe_shutdown():
        seen_connected.append(database.connected)

    original_close = database.close

    async def _recording_close():
        seen_connected.append("closing")
        await original_close()

    coordinator.async_shutdown = _probe_shutdown
    database.close = _recording_close
    assert await async_unload_entry(hass, entry) is True
    assert seen_connected == [True, "closing"], (
        "coordinator shutdown must precede the database close"
    )
