"""Reusable SSE transition publishers for the API service (task 44c93cfd).

Each helper wraps the ONE publisher on ``app.state.publisher`` with a
single documented transition: it builds the payload through the core
event builders (``nestquest_core.events``) — never hand-built here —
and fans it out with :meth:`~api.events.TransitionPublisher.publish`.

The uncomplete route (follow-up task da0226b3) and the API-side missed
sweep do not exist yet; these helpers are the functions they will call,
and the SSE tests exercise them directly.  Fan-out stays fire-and-forget
(see api/events.py): a slow subscriber drops the event and recovers by
polling the snapshot.
"""
from __future__ import annotations

import datetime

from api.nestquest_core import core_events


async def publish_quest_uncompleted(
    database: object, instance_id: int, publisher: object
) -> None:
    """Publish ONE ``nestquest_quest_uncompleted`` event for an actual
    reversal of ``instance_id``.

    The payload is built by the core builder
    (:func:`nestquest_core.events.build_quest_uncompleted_events`);
    this helper only picks the single event out of the builder's list
    and publishes it.
    """
    events = await core_events.build_quest_uncompleted_events(
        database, instance_id
    )
    for event_type, payload in events:
        publisher.publish(event_type, payload)


async def publish_quest_missed(
    database: object, instance_id: int, publisher: object
) -> None:
    """Publish ONE ``nestquest_quest_missed`` event for ``instance_id``.

    The payload is built by the core builder
    (:func:`nestquest_core.events.build_quest_missed_event`), which
    mirrors the documented sweep payload exactly (§3 of
    design/ENTITIES-AND-SERVICES.md).
    """
    event_type, payload = await core_events.build_quest_missed_event(
        database, instance_id
    )
    publisher.publish(event_type, payload)


async def publish_child_day_complete(
    database: object,
    completed_payload: dict,
    today: datetime.date,
    publisher: object,
) -> bool:
    """Publish ``nestquest_child_day_complete`` when a completion
    cleared the child's whole day; return whether one was published.

    The day-complete rule lives entirely in the core builder
    (:func:`nestquest_core.events.build_child_day_complete_event`):
    it returns ``None`` when the day did not clear (a zero-quest day
    or a non-today instance) and this helper publishes nothing then.
    """
    event = await core_events.build_child_day_complete_event(
        database, completed_payload, today=today
    )
    if event is None:
        return False
    event_type, payload = event
    publisher.publish(event_type, payload)
    return True


__all__ = [
    "publish_child_day_complete",
    "publish_quest_missed",
    "publish_quest_uncompleted",
]
