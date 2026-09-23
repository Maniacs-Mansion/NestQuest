"""Re-export / HA wiring of :mod:`custom_components.nestquest.core.events` for the integration package.

The transition-event payload construction lives in
:mod:`custom_components.nestquest.core.events` (extracted in
task 510c1f78) and is HA-free: it builds and RETURNS the events.  This
shim keeps the integration's old ``fire_quest_completed`` /
``fire_quest_uncompleted`` API for direct callers — since Feature 18
the HA service surface no longer fires transition events itself (the
API service publishes them on its SSE stream and the integration's
subscription re-fires them) — reads the HA-local timezone from
``hass.config.time_zone`` to derive ``today``, asks the core builder
for the events, and fires each on ``hass.bus`` with the documented
payloads.  The four blueprints keep working with identical payloads.

The completed event is fired BEFORE the day-complete rule evaluates:
``fire_quest_completed`` asks
:func:`build_quest_completed_event` for the completed event and fires
it immediately, THEN reads the HA-local ``today``, asks
:func:`build_child_day_complete_event` for the day-complete event, and
fires it (if any) afterwards.  This restores the pre-extraction
ordering — a failure in the day-complete DB reads or the ZoneInfo
lookup cannot suppress the completed event.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from .core.db import NestQuestDatabase
from .core.events import (
    build_child_day_complete_event,
    build_quest_completed_event,
    build_quest_uncompleted_events,
)

__all__ = ["fire_quest_completed", "fire_quest_uncompleted"]


async def fire_quest_completed(
    hass,
    database: NestQuestDatabase,
    instance_id: int,
    *,
    was_on_time: bool | None,
) -> None:
    """Fire ``nestquest_quest_completed`` and, when the completion
    cleared the child's whole day, ``nestquest_child_day_complete``.

    Thin HA wiring over the HA-free
    :func:`custom_components.nestquest.core.events.build_quest_completed_event`
    and
    :func:`build_child_day_complete_event`: the completed event is
    built and fired FIRST (so a failure in the day-complete DB reads
    or the HA-local ``today`` lookup cannot suppress it), then the
    HA-local ``today`` (the day-complete rule's input) is read from
    ``hass.config.time_zone`` and the day-complete builder is asked
    whether the child's whole day cleared.  Identical payloads and
    day-complete rule to the pre-extraction implementation.
    """
    completed = await build_quest_completed_event(
        database,
        instance_id,
        was_on_time=was_on_time,
    )
    hass.bus.async_fire(*completed)

    today = datetime.datetime.now(ZoneInfo(hass.config.time_zone)).date()
    day_complete = await build_child_day_complete_event(
        database, completed[1], today=today
    )
    if day_complete is not None:
        hass.bus.async_fire(*day_complete)


async def fire_quest_uncompleted(
    hass, database: NestQuestDatabase, instance_id: int
) -> None:
    """Fire ``nestquest_quest_uncompleted`` for an actual reversal."""
    events = await build_quest_uncompleted_events(database, instance_id)
    for event_type, payload in events:
        hass.bus.async_fire(event_type, payload)
