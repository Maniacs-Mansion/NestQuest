"""The nightly missed-quest sweep (Feature 11).

At the configured day-rollover time (the same HA-local listener that
re-materializes the rolling horizon) this job finds every instance
whose ``due_date`` is before the HA-local date, that has NO completion
event, and that falls after the persisted sweep watermark — and fires
ONE ``nestquest_quest_missed`` event per instance with the documented
payload.  The sweep is read-only over the domain tables: it never
mutates an instance and never writes a completion event (``missed``
is derived state, never an event_type — Feature 08's contract).

Idempotency is the watermark: after a run, ``nestquest_meta_state``
records the HA-local date the sweep ran, and the next run only
sweeps instances due in ``[watermark, today)``.  A second run the
same night therefore fires nothing new, and a run after days of
downtime sweeps exactly the accumulated window once — no
per-instance journal, no re-announcing old misses.  An instance swept
as missed that is later completed simply gains its completion event;
history keeps both rows (append-only), and the sweep's later runs
skip it via the no-completion-event rule.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

from .const import EVENT_QUEST_MISSED
from .dao_children import ChildrenDao
from .dao_instances import QuestInstancesDao
from .dao_meta import MetaStateDao
from .dao_rules import QuestDefinitionsDao
from .db import NestQuestDatabase

LOGGER = logging.getLogger(__name__)

#: meta_state key holding the HA-local date the sweep last ran.
SWEEP_WATERMARK_KEY = "missed_sweep_last_run_date"

#: One asyncio.Lock per (connection wrapper, running loop), mirroring
#: the migration runner's pattern: the whole watermark read → query →
#: fire → write span is one critical section, so an overlapping startup
#: sweep and rollover sweep queue instead of double-announcing.  The
#: loser re-reads the watermark INSIDE the lock, sees the winner's
#: date, and fires nothing.
_SWEEP_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def _sweep_lock(database: NestQuestDatabase) -> asyncio.Lock:
    """Return the sweep lock bound to ``database``'s running loop."""
    loop = asyncio.get_running_loop()
    key = (id(database), id(loop))
    lock = _SWEEP_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SWEEP_LOCKS[key] = lock
    return lock

#: UTC ISO-8601 timestamp policy shared with the DAO layers.
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


def _now_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        _UTC_TIMESTAMP_FORMAT
    )


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
    covers ``today`` (a same-night rerun).

    The whole watermark read → query → fire → write span runs inside
    the per-database sweep lock: an overlapping startup sweep and a
    rollover sweep queue instead of interleaving, and the loser
    re-reads the watermark inside the lock — sees the winner's date —
    and announces nothing twice.
    """
    today_date = (
        today
        if today is not None
        else datetime.datetime.now(ZoneInfo(hass.config.time_zone)).date()
    )
    today_iso = today_date.isoformat()
    dao = MetaStateDao(database)
    async with _sweep_lock(database):
        watermark = await dao.get(SWEEP_WATERMARK_KEY)
        if watermark == today_iso:
            LOGGER.debug(
                "NestQuest missed sweep already ran for %s", today_iso
            )
            return 0

        instances_dao = QuestInstancesDao(database)
        rows = await instances_dao.list_missed_unswept(today_iso, watermark)
        children_dao = ChildrenDao(database)
        definitions_dao = QuestDefinitionsDao(database)
        now_stamp = _now_stamp()
        fired = 0
        for instance in rows:
            child = await children_dao.get(instance.child_id)
            definition = await definitions_dao.get(instance.definition_id)
            hass.bus.async_fire(
                EVENT_QUEST_MISSED,
                {
                    "child_id": instance.child_id,
                    "child_name": child.display_name if child else None,
                    "instance_id": instance.id,
                    "quest_title": definition.title if definition else None,
                    "window": instance.window,
                    "due_date": instance.due_date,
                    "due_time": instance.due_time,
                    "occurred_at": now_stamp,
                },
            )
            fired += 1
        await dao.set(SWEEP_WATERMARK_KEY, today_iso)
    LOGGER.info(
        "NestQuest missed sweep for %s fired %d event(s)", today_iso, fired
    )
    return fired