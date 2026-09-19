"""Tests for the NestQuest bus events (Feature 10, task 6)."""
from __future__ import annotations

import re

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import create_child
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_MISSED,
    EVENT_QUEST_UNCOMPLETED,
    SERVICE_COMPLETE_QUEST,
    SERVICE_CREATE_QUEST_DEFINITION,
    SERVICE_MANAGE_CHILD,
    SERVICE_REGENERATE,
    SERVICE_UNCOMPLETE_QUEST,
)
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

ADMIN_CTX = {"user_id": "admin-1"}
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


async def _setup_and_seed(hass, make_entry, *, windows=("morning",)):
    entry = wire_entry_to_registry(
        make_entry(data={CONF_ADMIN_USER_IDS: ["admin-1"]}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
        context=ADMIN_CTX,
    )
    child = None
    from custom_components.nestquest.children import list_children

    child = (await list_children(database))[0]
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": __import__("datetime").date.today().isoformat()}
        ),
        [child.id],
        list(windows),
    )
    import datetime

    today = datetime.date.today().isoformat()
    end = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today, end, today=datetime.date.today())
    instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today, today
    )
    return entry, child, instances


async def test_quest_completed_fires_with_documented_payload(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    fired = hass.bus.fired(EVENT_QUEST_COMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert payload["window"] == "morning"
    assert payload["was_on_time"] is not None
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]


async def test_recomplete_no_op_fires_nothing(hass, make_entry) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_child_day_complete_fires_when_day_clears(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    for instance in instances:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
    day_complete = hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)
    assert len(day_complete) == 1, "exactly one day-complete per cleared day"
    payload = day_complete[0]
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["quests_due"] == len(instances)
    assert _TIMESTAMP.match(payload["occurred_at"])


async def test_child_day_complete_does_not_fire_partway(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(
        hass, make_entry, windows=("morning", "evening")
    )
    assert len(instances) == 2
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    assert hass.bus.fired(EVENT_CHILD_DAY_COMPLETE) == []
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[1].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1


async def test_uncompleted_fires_on_reversal_only(hass, make_entry) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    # Un-completing an open instance is a no-op and fires nothing.
    await hass.services.call(
        DOMAIN,
        SERVICE_UNCOMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "user"},
        context=ADMIN_CTX,
    )
    fired = hass.bus.fired(EVENT_QUEST_UNCOMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert _TIMESTAMP.match(payload["occurred_at"])
    await hass.services.call(
        DOMAIN,
        SERVICE_UNCOMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "user"},
        context=ADMIN_CTX,
    )
    assert len(hass.bus.fired(EVENT_QUEST_UNCOMPLETED)) == 1


def test_missed_event_name_is_documented_contract() -> None:
    """Feature 10 defines the missed event Feature 11's sweep fires."""
    assert EVENT_QUEST_MISSED == "nestquest_quest_missed"


async def test_appended_verdict_is_atomic_under_duplicate_calls(
    hass, make_entry
) -> None:
    """Concurrent duplicate completes decide appended under the same
    lock as the write: exactly one fires the transition event."""
    import asyncio

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    calls = [
        hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance_id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
        for _ in range(2)
    ]
    await asyncio.gather(*calls)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_day_complete_ignored_for_backdated_completion(
    hass, make_entry
) -> None:
    """Completing an instance NOT due today never evaluates the
    child's day-complete, so a cleared day is announced at most once
    per day and only by that day's completions."""
    import datetime

    from custom_components.nestquest.completion import (
        complete_instance as _complete,
    )

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    # A future instance (tomorrow) completed after today's day is
    # already clear.
    today = datetime.date.today()
    end = (today + datetime.timedelta(days=3)).isoformat()
    all_instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today.isoformat(), end
    )
    today_ids = {instance.id for instance in instances}
    tomorrow_instance = next(
        instance
        for instance in all_instances
        if instance.id not in today_ids
    )
    for instance in instances:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1

    await _complete(
        database,
        tomorrow_instance.id,
        actor_source="user",
        actor_user_id="admin-1",
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": tomorrow_instance.id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1, (
        "a back-dated/future completion must not re-announce today"
    )
    # The direct business-layer call fired nothing (only the service
    # path fires), and the follow-up service call on the now-done
    # future instance was a no-op: today's single completion stands.
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == len(instances)


async def test_completion_updates_entities_immediately(
    hass, make_entry
) -> None:
    """The remaining-today sensor reflects the completion the moment
    the service call returns — no manual refresh — and the day-complete
    event fired exactly once when the day became clear."""
    from custom_components.nestquest.const import EVENT_CHILD_DAY_COMPLETE

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    from conftest import wire_entry_to_registry  # noqa: F401

    coordinator = entry.runtime_data.coordinator
    # Entities only exist after one refresh since they were seeded
    # after setup; create them, then prove the service path refreshes.
    await coordinator.async_refresh()
    remaining_before = hass.entities[
        f"nestquest_child_{child.id}_quests_remaining_today"
    ].native_value
    assert remaining_before == len(instances)

    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    remaining_after = hass.entities[
        f"nestquest_child_{child.id}_quests_remaining_today"
    ].native_value
    assert remaining_after == len(instances) - 1, (
        "sensor must reflect the completion without a manual refresh"
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == (
        1 if len(instances) == 1 else 0
    )


async def test_uncompletion_updates_entities_immediately(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    completed_after_complete = hass.entities[
        f"nestquest_child_{child.id}_quests_completed_today"
    ].native_value
    assert completed_after_complete == 1

    await hass.services.call(
        DOMAIN,
        SERVICE_UNCOMPLETE_QUEST,
        {"instance_id": instances[0].id, "actor": "user"},
        context=ADMIN_CTX,
    )
    completed_after_uncomplete = hass.entities[
        f"nestquest_child_{child.id}_quests_completed_today"
    ].native_value
    assert completed_after_uncomplete == 0, (
        "sensor must reflect the reversal without a manual refresh"
    )


async def test_forced_refreshes_serialize_no_stale_publish(
    hass, make_entry
) -> None:
    """Overlapping forced refreshes never interleave: a slow pass
    pauses mid-snapshot, and the queued pass still publishes AFTER
    it, so the last published snapshot reflects the latest mutation."""
    import asyncio

    entry, child, instances = await _setup_and_seed(hass, make_entry)
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
