"""Transition-event payload construction for the NestQuest service paths (Feature 10).

This module is PAYLOAD CONSTRUCTION ONLY: it builds and RETURNS the
transition events (event type + payload dict) and never touches the
Home Assistant event bus or config.  The caller decides how to fire
them (the integration's re-export shim wires the returned events to
``hass.bus.async_fire``).

The four documented events (design/ENTITIES-AND-SERVICES.md §3, names
in :mod:`~.const`): ``nestquest_quest_completed`` and
``nestquest_quest_uncompleted`` fire from the completion service
handlers on an actual transition (a no-op re-complete or re-uncomplete
fires nothing), and ``nestquest_child_day_complete`` fires when a
completion clears the child's whole day (quests were owed and none
remain — a zero-quest day can never fire it, matching the all-done
binary sensor's rule).  ``nestquest_quest_missed`` is the documented
contract Feature 11's nightly sweep fires; :func:`build_quest_missed_event`
builds it with exactly the payload the sweep hand-builds (§3), so the
API plane can publish the same shape without re-deriving it.

The completed-event and day-complete-event builders are split so the
shim can fire ``nestquest_quest_completed`` BEFORE it evaluates the
day-complete rule (the pre-extraction implementation fired the
completed event on the bus first, then ran the day-complete DB reads;
a failure in those reads or the ZoneInfo lookup must not suppress the
completed event).  :func:`build_quest_completed_event` builds the
completed event from the instance and its child/definition only;
:func:`build_child_day_complete_event` runs the day-complete DB reads
and returns the day-complete event (or ``None``).  The shim fires the
completed event, then calls the day-complete builder and fires its
result.  :func:`build_quest_uncompleted_events` builds the single
uncompleted event.

Payload policy: one dict carrying ``child_id``, ``child_name``,
``instance_id``, ``quest_title``, the instance's ``window``/
``due_date``/``due_time`` so automation authors can filter without a
database lookup, and ``occurred_at`` — the event's own strict UTC
ISO-8601 timestamp.  Completion payloads additionally carry
``was_on_time``.  No other personal data: names and titles are the
household's own records, and nothing beyond them leaks.

Timezone policy: the day-complete check needs the HA-local "today",
which the caller passes in as a plain :class:`datetime.date`.  Nothing
here reads ``hass.config.time_zone`` — the integration owns HA
timezone, the core owns the calendar arithmetic.
"""
from __future__ import annotations

import datetime

from .completion import derive_state
from .const import (
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_MISSED,
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


async def build_quest_completed_event(
    database: NestQuestDatabase,
    instance_id: int,
    *,
    was_on_time: bool | None,
) -> tuple[str, dict]:
    """Build the ``nestquest_quest_completed`` event for an actual
    completion.

    Called by the complete_quest service handler AFTER an actual
    completion transition, with the completion's ``was_on_time`` —
    computed under the completion lock and carried on the result — so
    the payload never re-reads mutable latest state a racing reversal
    could have replaced.  A no-op re-complete never reaches here.

    Returns the ``(event_type, payload)`` tuple to fire.  This builder
    touches NO day-complete state: it only reads the instance, its
    child, and its definition, so a failure in the day-complete
    evaluation (DB reads, timezone lookup in the shim) cannot suppress
    the completed event.  The caller fires this BEFORE asking
    :func:`build_child_day_complete_event` for the day-complete event.
    """
    now_stamp = _now_stamp()
    payload = await _instance_payload(database, instance_id, now_stamp)
    payload["was_on_time"] = was_on_time
    return (EVENT_QUEST_COMPLETED, payload)


async def build_child_day_complete_event(
    database: NestQuestDatabase,
    completed_payload: dict,
    *,
    today: datetime.date,
) -> tuple[str, dict] | None:
    """Build the ``nestquest_child_day_complete`` event for a
    completion that cleared the child's whole day, or ``None`` when no
    day-complete event should fire.

    Called by the complete_quest service handler AFTER the
    ``nestquest_quest_completed`` event has already been fired, with
    that event's payload (so this builder reuses the same
    ``occurred_at`` stamp and the same ``child_id`` / ``child_name``
    the completed event carried — one transition, one shared
    timestamp, matching the pre-extraction implementation).

    Day-complete rule (identical to the pre-extraction implementation
    and to the all-done binary sensor): quests were owed today and
    none remain — a zero-quest day can never fire it.  Only a
    completion of TODAY'S instance evaluates it: completing a
    back-dated or future instance must not announce a cleared day.

    ``today`` is the HA-local calendar date the day-complete rule is
    evaluated against; the integration reads it from
    ``hass.config.time_zone`` and passes it in, so this module never
    touches HA config.
    """
    # Only a completion of TODAY'S instance evaluates the day-complete
    # rule: completing a back-dated or future instance must not
    # announce a cleared day.
    if completed_payload["due_date"] != today.isoformat():
        return None
    instances = await QuestInstancesDao(database).list_by_date_range(
        completed_payload["child_id"], today.isoformat(), today.isoformat()
    )
    completion_events = CompletionEventsDao(database)
    remaining = 0
    for instance in instances:
        latest_for_instance = await completion_events.get_latest_for_instance(
            instance.id
        )
        if derive_state(instance, latest_for_instance, today) != "done":
            remaining += 1
    if not instances or remaining:
        return None
    return (
        EVENT_CHILD_DAY_COMPLETE,
        {
            "child_id": completed_payload["child_id"],
            "child_name": completed_payload["child_name"],
            "quests_due": len(instances),
            "quests_completed": len(instances),
            "occurred_at": completed_payload["occurred_at"],
        },
    )


async def build_quest_uncompleted_events(
    database: NestQuestDatabase, instance_id: int
) -> list[tuple[str, dict]]:
    """Build the ``nestquest_quest_uncompleted`` event for an actual reversal.

    Returns a one-element list of ``(event_type, payload)`` to fire.
    """
    payload = await _instance_payload(database, instance_id, _now_stamp())
    return [(EVENT_QUEST_UNCOMPLETED, payload)]


async def build_quest_missed_event(
    database: NestQuestDatabase, instance_id: int
) -> tuple[str, dict]:
    """Build the ``nestquest_quest_missed`` event for one instance.

    The payload mirrors the nightly sweep's hand-built payload exactly
    (the shared :func:`_instance_payload` shape: ``child_id``,
    ``child_name``, ``instance_id``, ``quest_title``, ``window``,
    ``due_date``, ``due_time``, ``occurred_at``), so the API plane's
    missed path publishes the same event shape the integration's sweep
    fires.  Like the sweep, this builder never mutates the instance or
    writes a completion event — it reads only.
    """
    payload = await _instance_payload(database, instance_id, _now_stamp())
    return (EVENT_QUEST_MISSED, payload)
