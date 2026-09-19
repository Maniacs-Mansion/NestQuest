"""HA bus events fired by the NestQuest service paths (Feature 10).

The four documented events (design/ENTITIES-AND-SERVICES.md §3, names
in :mod:`~.const`): ``nestquest_quest_completed`` and
``nestquest_quest_uncompleted`` fire from the completion service
handlers on an actual transition (a no-op re-complete or re-uncomplete
fires nothing), and ``nestquest_child_day_complete`` fires when a
completion clears the child's whole day (quests were owed and none
remain — a zero-quest day can never fire it, matching the all-done
binary sensor's rule).  ``nestquest_quest_missed`` is the documented
contract Feature 11's nightly sweep fires; nothing here fires it.

Payload policy: one dict carrying ``child_id``, ``child_name``,
``instance_id``, ``quest_title``, the instance's ``window``/
``due_date``/``due_time`` so automation authors can filter without a
database lookup, and ``occurred_at`` — the event's own strict UTC
ISO-8601 timestamp.  Completion payloads additionally carry
``was_on_time``.  No other personal data: names and titles are the
household's own records, and nothing beyond them leaks.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from .completion import derive_state
from .const import (
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_UNCOMPLETED,
)
from .dao_children import ChildrenDao
from .dao_instances import CompletionEventsDao, QuestInstancesDao
from .dao_rules import QuestDefinitionsDao
from .db import NestQuestDatabase

#: Strict UTC ISO-8601 timestamp (the DAO layers' policy): one shape,
#: explicit offset, second precision.
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


def _now_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        _UTC_TIMESTAMP_FORMAT
    )


async def _instance_payload(
    database: NestQuestDatabase, instance_id: int, now_stamp: str
) -> dict:
    """Build the shared event payload for one quest instance."""
    instance = await QuestInstancesDao(database).get_by_id(instance_id)
    if instance is None:
        raise ValueError(
            f"instance_id: quest instance {instance_id} does not exist"
        )
    child = await ChildrenDao(database).get(instance.child_id)
    definition = await QuestDefinitionsDao(database).get(
        instance.definition_id
    )
    return {
        "child_id": instance.child_id,
        "child_name": child.display_name if child else None,
        "instance_id": instance.id,
        "quest_title": definition.title if definition else None,
        "window": instance.window,
        "due_date": instance.due_date,
        "due_time": instance.due_time,
        "occurred_at": now_stamp,
    }


async def fire_quest_completed(
    hass, database: NestQuestDatabase, instance_id: int
) -> None:
    """Fire ``nestquest_quest_completed`` and, when the completion
    cleared the child's whole day, ``nestquest_child_day_complete``.

    Called by the complete_quest service handler AFTER an actual
    completion transition; a no-op re-complete never reaches here.
    """
    now_stamp = _now_stamp()
    payload = await _instance_payload(database, instance_id, now_stamp)
    latest = await CompletionEventsDao(database).get_latest_for_instance(
        instance_id
    )
    payload["was_on_time"] = (
        latest.was_on_time if latest is not None else None
    )
    hass.bus.async_fire(EVENT_QUEST_COMPLETED, payload)

    # Day-complete: quests were owed today and none remain (the same
    # rule as the all-done binary sensor; a zero-quest day never fires).
    today = datetime.datetime.now(ZoneInfo(hass.config.time_zone)).date()
    instances = await QuestInstancesDao(database).list_by_date_range(
        payload["child_id"], today.isoformat(), today.isoformat()
    )
    events = CompletionEventsDao(database)
    remaining = 0
    for instance in instances:
        latest_for_instance = await events.get_latest_for_instance(
            instance.id
        )
        if derive_state(instance, latest_for_instance, today) != "done":
            remaining += 1
    if instances and remaining == 0:
        hass.bus.async_fire(
            EVENT_CHILD_DAY_COMPLETE,
            {
                "child_id": payload["child_id"],
                "child_name": payload["child_name"],
                "quests_due": len(instances),
                "quests_completed": len(instances),
                "occurred_at": now_stamp,
            },
        )


async def fire_quest_uncompleted(
    hass, database: NestQuestDatabase, instance_id: int
) -> None:
    """Fire ``nestquest_quest_uncompleted`` for an actual reversal."""
    payload = await _instance_payload(database, instance_id, _now_stamp())
    hass.bus.async_fire(EVENT_QUEST_UNCOMPLETED, payload)
