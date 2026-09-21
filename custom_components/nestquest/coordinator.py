"""The shared NestQuest DataUpdateCoordinator (Feature 10).

ONE refresh pass builds the whole entity snapshot: active children,
today's instances with their derived states (open / done / missed via
:func:`~.completion.derive_state`), each child's presence today, and
per-child rollup counts.  Every Feature 10 entity reads
``coordinator.data`` — no entity queries the database itself, so one
refresh updates the whole board coherently.

"Today" and "now" are HA-local (``hass.config.time_zone``), never the
host clock and never UTC, matching the materialization and completion
layers.

The snapshot assembly itself lives in the Home-Assistant-free
:mod:`custom_components.nestquest.core.snapshot` module
(:func:`~core.snapshot.build_snapshot`); this coordinator is now a thin
HA wrapper that resolves the local timezone and settings off the config
entry and delegates to that builder.  The API service's panel snapshot
route shares the same builder, so both consumers render ONE snapshot
shape.

Presence is resolved through the SAME engine the materializer uses
(:class:`~.presence.PresenceEngine`): schedules and overrides are read
with the public DAO methods and the engine's anchor-date arithmetic
answers ``is this child at this house today`` (D-004 — never ISO week
parity).

``cycle_day`` reports where today falls in the custody cycle of the
first active child (display order) that HAS a schedule — 1-based day
``N`` of ``cycle_length_weeks * 7``, computed from that schedule's
anchor date.  ``0`` means no active child has a schedule at all, so
the admin header degrades to a harmless zero instead of guessing.
"""
from __future__ import annotations

import asyncio
import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL,
)
from .core.db import NestQuestDatabase
from .core.settings import NestQuestSettings
from .core.snapshot import (
    ChildDaySnapshot,
    NestQuestSnapshot,
    QuestInstanceView,
    _cycle_day,
    build_snapshot,
)

__all__ = [
    "ChildDaySnapshot",
    "NestQuestCoordinator",
    "NestQuestSnapshot",
    "QuestInstanceView",
    "_cycle_day",
    "build_snapshot",
]


class NestQuestCoordinator(DataUpdateCoordinator):
    """Shared refresh cycle for every NestQuest entity.

    Forced refreshes (the service paths pushing an immediate update
    after a completion) are SERIALIZED per entry: overlapping
    complete/uncomplete calls must not interleave their snapshot
    passes, or an older pass could publish a stale snapshot AFTER a
    newer one and leave entities wrong until the next poll.  Real
    HA's coordinator already serializes internally; the lock keeps
    the same guarantee on the stand-in and costs nothing upstream.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        database: NestQuestDatabase,
        settings: NestQuestSettings,
        update_interval_seconds: int | None = None,
    ) -> None:
        interval = update_interval_seconds
        if (
            not isinstance(interval, int)
            or isinstance(interval, bool)
            or interval < MIN_UPDATE_INTERVAL
        ):
            interval = DEFAULT_UPDATE_INTERVAL
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=interval),
        )
        self.entry_id = entry_id
        self.database = database
        self.settings = settings
        self._refresh_lock = asyncio.Lock()

    async def async_refresh(self) -> None:
        """One refresh at a time; a queued refresh runs AFTER the
        in-flight one publishes, so the last snapshot always reflects
        the latest mutation."""
        async with self._refresh_lock:
            await super().async_refresh()

    def _local_now(self) -> datetime.datetime:
        time_zone = ZoneInfo(self.hass.config.time_zone)
        return datetime.datetime.now(time_zone)

    async def _async_update_data(self) -> NestQuestSnapshot:
        now = self._local_now()
        today = now.date()
        time_zone = ZoneInfo(self.hass.config.time_zone)
        return await build_snapshot(
            self.database, self.settings, today, time_zone
        )
