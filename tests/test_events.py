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
