"""Re-export / HA wiring of :mod:`custom_components.nestquest.core.events` for the integration package.

The transition-event payload construction lives in
:mod:`custom_components.nestquest.core.events` (extracted in
task 510c1f78) and is HA-free: it builds and RETURNS the events.  This
shim keeps the integration's old ``fire_quest_completed`` /
``fire_quest_uncompleted`` API (the complete/uncomplete service
handlers call them with ``hass``), reads the HA-local timezone from
``hass.config.time_zone`` to derive ``today``, asks the core builder
for the events, and fires each on ``hass.bus`` with the documented
payloads.  The four blueprints keep working with identical payloads.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from .core.db import NestQuestDatabase
from .core.events import (
    build_quest_completed_events,
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
    :func:`custom_components.nestquest.core.events.build_quest_completed_events`:
    the HA-local ``today`` (the day-complete rule's input) is read
    here from ``hass.config.time_zone``; the core builder does every
    payload-shape and day-complete decision and hands back the events
    to fire.  Identical payloads to the pre-extraction implementation.
    """
    today = datetime.datetime.now(ZoneInfo(hass.config.time_zone)).date()
    events = await build_quest_completed_events(
        database,
        instance_id,
        was_on_time=was_on_time,
        today=today,
    )
    for event_type, payload in events:
        hass.bus.async_fire(event_type, payload)


async def fire_quest_uncompleted(
    hass, database: NestQuestDatabase, instance_id: int
) -> None:
    """Fire ``nestquest_quest_uncompleted`` for an actual reversal."""
    events = await build_quest_uncompleted_events(database, instance_id)
    for event_type, payload in events:
        hass.bus.async_fire(event_type, payload)
