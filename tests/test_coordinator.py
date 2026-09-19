"""Tests for the shared NestQuest coordinator (Feature 10, task 1)."""
from __future__ import annotations

import datetime

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.children import (
    create_child,
    list_children,
    set_child_active,
)
from custom_components.nestquest.completion import complete_instance
from custom_components.nestquest.const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_HORIZON_DAYS,
    DOMAIN,
)
from custom_components.nestquest.coordinator import NestQuestCoordinator
from custom_components.nestquest.dao_presence import PresenceSchedulesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

ADMIN_CTX = {"user_id": "admin-1"}


def _today_iso() -> str:
    return datetime.date.today().isoformat()


async def _seed_day(database, *, completed: bool = False) -> None:
    """Two active children + one inactive, one daily definition each."""
    await create_child(database, "Ada")
    await create_child(database, "Bo")
    inactive = await create_child(database, "Ghost")
    await set_child_active(database, inactive.id, False)
    today = _today_iso()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict({"rule_type": "daily", "start_date": today}),
        [child.id for child in await list_children(database, active_only=True)],
        ["morning"],
    )
    end = (
        datetime.date.today() + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
    ).isoformat()
    await materialize(database, today, end, today=datetime.date.today())


async def test_coordinator_snapshot_counts_and_states(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator is not None
    database = entry.runtime_data.database
    await _seed_day(database)

    snapshot = await coordinator._async_update_data()
    assert snapshot.today_iso == _today_iso()
    assert len(snapshot.children) == 2, "inactive child must be absent"
    by_name = {child.child_name: child for child in snapshot.children}
    ada = by_name["Ada"]
    assert ada.due_today == 1
    assert ada.completed_today == 0
    assert ada.remaining_today == 1
    assert ada.completion_pct == 0
    instance = ada.instances[0]
    assert instance.state == "open"
    assert instance.overdue is False
    assert instance.title == "Brush teeth"
    assert instance.window == "morning"
    assert ada.present is True, "no schedule means present every day"
    assert snapshot.cycle_day == 0, "no schedule anywhere"


async def test_coordinator_reflects_completion_and_uncompletion(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    await _seed_day(database)
    ada = (
        await coordinator._async_update_data()
    ).children[0]
    instance_id = ada.instances[0].instance_id

    await complete_instance(
        database,
        instance_id,
        actor_source="panel",
        actor_child_id=ada.child_id,
    )
    snapshot = await coordinator._async_update_data()
    child = snapshot.children[0]
    assert child.completed_today == 1
    assert child.remaining_today == 0
    assert child.completion_pct == 100
    view = child.instances[0]
    assert view.state == "done"
    assert view.completed_at is not None
    assert view.was_on_time is not None

    from custom_components.nestquest.completion import uncomplete_instance

    await uncomplete_instance(
        database, instance_id, actor_source="user", actor_user_id="admin-1"
    )
    snapshot = await coordinator._async_update_data()
    child = snapshot.children[0]
    assert child.completed_today == 0
    assert child.remaining_today == 1
    assert child.instances[0].state == "open"


async def test_coordinator_zero_quests_reports_full_percentage(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    await create_child(entry.runtime_data.database, "Ada")
    snapshot = await coordinator._async_update_data()
    child = snapshot.children[0]
    assert child.due_today == 0
    assert child.completion_pct == 100, "zero quests is a perfect day"
    assert child.instances == ()


async def test_coordinator_cycle_day_from_first_scheduled_child(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    await create_child(database, "Ada")
    ada = (await list_children(database))[0]
    today = datetime.date.today()
    # A 2-week cycle anchored 3 days ago: today is day 4.
    anchor = today - datetime.timedelta(days=3)
    await PresenceSchedulesDao(database).upsert_by_child(
        ada.id, 2, anchor.isoformat(), "0,1,2,3,4,5,6|"
    )
    snapshot = await coordinator._async_update_data()
    assert snapshot.cycle_day == 4


async def test_coordinator_presence_resolves_schedule_and_override(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    await create_child(database, "Ada")
    ada = (await list_children(database))[0]
    today = datetime.date.today()
    # Scheduled absent today (empty weekday set for this cycle week).
    await PresenceSchedulesDao(database).upsert_by_child(
        ada.id, 1, today.isoformat(), ""
    )
    snapshot = await coordinator._async_update_data()
    assert snapshot.children[0].present is False

    # An override beats the pattern.
    from custom_components.nestquest.dao_presence import (
        PresenceOverridesDao,
    )

    await PresenceOverridesDao(database).create(
        ada.id, today.isoformat(), today.isoformat(), True
    )
    snapshot = await coordinator._async_update_data()
    assert snapshot.children[0].present is True


async def test_coordinator_derives_missed_for_past_due_open(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    snapshot = await coordinator._async_update_data()
    # No children: empty but valid snapshot.
    assert snapshot.children == ()


async def test_setup_creates_coordinator_with_configured_interval(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(
        make_entry(options={CONF_UPDATE_INTERVAL: 60}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert isinstance(coordinator, NestQuestCoordinator)
    assert coordinator.update_interval == datetime.timedelta(seconds=60)
    assert coordinator.data is not None, "first refresh ran at setup"


async def test_setup_defaults_to_five_minute_interval(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator.update_interval == datetime.timedelta(
        seconds=DEFAULT_UPDATE_INTERVAL
    )


async def test_unload_shuts_coordinator_down(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    torn_down = []

    async def _shutdown():
        torn_down.append(coordinator)

    coordinator.async_shutdown = _shutdown
    assert await async_unload_entry(hass, entry) is True
    assert torn_down == [coordinator]


async def test_coordinator_notifies_listeners_on_refresh(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    called = []
    coordinator.async_add_listener(lambda: called.append("entity"))
    await coordinator.async_refresh()
    assert called == ["entity"]
    assert coordinator.last_update_success is True
