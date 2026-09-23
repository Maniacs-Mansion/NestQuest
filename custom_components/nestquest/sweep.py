"""The nightly missed-quest sweep (Feature 11) — the Home Assistant shim.

The sweep's policy is the HA-free core's :mod:`~.core.sweep`: the
watermark read → ``list_missed_unswept`` query → payload build →
watermark span, all inside the per-database sweep lock, shared with
the API plane.  This module is the integration's thin adapter over it:
at the configured day-rollover time (the same HA-local listener that
re-materializes the rolling horizon) and once at setup it calls the
core's :func:`~.core.sweep.run_missed_sweep` and fires each returned
event on ``hass.bus`` — ONE ``nestquest_quest_missed`` per past-due
open instance with the documented payload.  The core never touches
Home Assistant; the firing lives here.

Idempotency is the core's watermark: after a run, ``nestquest_meta_state``
records the HA-local date the sweep ran, and the next run only sweeps
instances due in ``[watermark, today)`` — a second run the same night
fires nothing new, and a run after days of downtime sweeps exactly the
accumulated window once.  An instance swept as missed that is later
completed simply gains its completion event; the sweep is read-only
over the domain tables (``missed`` is derived state, never an
event_type — Feature 08's contract).
"""
from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from .core.sweep import (
    SWEEP_WATERMARK_KEY,
    run_missed_sweep as _run_core_missed_sweep,
)
from .db import NestQuestDatabase

LOGGER = logging.getLogger(__name__)

__all__ = ["SWEEP_WATERMARK_KEY", "run_missed_sweep"]


async def run_missed_sweep(
    hass,
    database: NestQuestDatabase,
    *,
    today: datetime.date | None = None,
) -> int:
    """Fire one missed event per unswept past-due open instance.

    ``today`` optionally pins the HA-local date (threaded like the
    materialization and completion layers); when omitted it is read
    from ``hass.config.time_zone``.  Returns the number of events
    fired.  Fires nothing and returns 0 when the watermark already
    covers ``today`` (a same-night rerun) — the watermark read, the
    query, the payload build and the watermark write all live in the
    core's locked
    :func:`~.core.sweep.run_missed_sweep`; this shim only fires each
    returned event on the bus and counts them.
    """
    today_date = (
        today
        if today is not None
        else datetime.datetime.now(ZoneInfo(hass.config.time_zone)).date()
    )
    events = await _run_core_missed_sweep(database, today=today_date)
    for event_type, payload in events:
        hass.bus.async_fire(event_type, payload)
    fired = len(events)
    LOGGER.info(
        "NestQuest missed sweep for %s fired %d event(s)",
        today_date.isoformat(),
        fired,
    )
    return fired