"""Tests for the per-child binary sensors (Feature 10, task 4)."""
from __future__ import annotations

import datetime

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import create_child
from custom_components.nestquest.const import DOMAIN
from custom_components.nestquest.dao_presence import PresenceSchedulesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule
from custom_components.nestquest.completion import complete_instance

SEED_HORIZON_DAYS = 3


def _binary(hass, child_id: int, kind: str):
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


async def _setup_entry(hass, make_entry):
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    return entry


async def _seed_two_children(database) -> tuple:
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
    return ada, bo


async def test_all_done_off_with_open_quests_and_zero_quests(
    hass, make_entry
) -> None:
    """all_done is OFF while quests are owed AND on a zero-quest day;
    a child with no quests never fires the celebration automation."""
    entry = await _setup_entry(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    ada, _bo = await _seed_two_children(database)
    await create_child(database, "Cory")  # zero quests
    await coordinator.async_refresh()

    assert _binary(hass, ada.id, "all_done").is_on is False
    cory = [
        child for child in coordinator.data.children
        if child.child_name == "Cory"
    ][0]
    assert _binary(hass, cory.child_id, "all_done").is_on is False


async def test_all_done_on_only_when_day_clear(hass, make_entry) -> None:
    entry = await _setup_entry(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    ada, _bo = await _seed_two_children(database)
    await coordinator.async_refresh()
    snapshot_ada = [
        child for child in coordinator.data.children
        if child.child_id == ada.id
    ][0]
    instance_id = snapshot_ada.instances[0].instance_id
    await complete_instance(
        database,
        instance_id,
        actor_source="panel",
        actor_child_id=ada.id,
    )
    await coordinator.async_refresh()
    assert _binary(hass, ada.id, "all_done").is_on is True


async def test_present_today_on_without_schedule_off_when_absent(
    hass, make_entry
) -> None:
    """No schedule means present every day; an all-absent pattern
    today reports OFF."""
    entry = await _setup_entry(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    ada, _bo = await _seed_two_children(database)
    await create_child(database, "Cory")
    today = datetime.date.today()
    await coordinator.async_refresh()
    cory = [
        child for child in coordinator.data.children
        if child.child_name == "Cory"
    ][0]
    await PresenceSchedulesDao(database).upsert_by_child(
        cory.child_id, 1, today.isoformat(), ""
    )
    await coordinator.async_refresh()

    assert _binary(hass, ada.id, "present_today").is_on is True
    assert _binary(hass, cory.child_id, "present_today").is_on is False


async def test_binary_sensor_identity_and_attributes(hass, make_entry) -> None:
    entry = await _setup_entry(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    ada, _bo = await _seed_two_children(database)
    await coordinator.async_refresh()

    all_done = _binary(hass, ada.id, "all_done")
    present = _binary(hass, ada.id, "present_today")
    assert all_done.unique_id == f"nestquest_child_{ada.id}_all_done"
    assert present.unique_id == f"nestquest_child_{ada.id}_present_today"
    assert all_done.name == "NestQuest Ada all done"
    assert present.name == "NestQuest Ada present today"
    for entity in (all_done, present):
        assert entity.device_info.name == "NestQuest Ada"
        assert entity.extra_state_attributes == {
            "child_id": ada.id,
            "child_name": "Ada",
        }
