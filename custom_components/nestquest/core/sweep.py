"""The nightly missed-quest sweep, Home-Assistant-free (Feature 11).

This is the HA-free heart of the missed sweep, shared by the two
planes: the Home Assistant integration's :mod:`~..sweep` shim (which
fires the returned events on ``hass.bus``) and the API service (which
publishes them on the SSE stream and can also trigger the run on
demand).  It owns the ONE sweep policy:

At the configured day-rollover time (or on an explicit trigger) this
job finds every instance whose ``due_date`` is before the
household-local date, that has NO completion event, and that falls
after the persisted sweep watermark — and RETURNS one
``nestquest_quest_missed`` event per instance with the documented
payload.  Like every core module, it never touches the Home Assistant
event bus and never mutates an instance: ``missed`` is derived state,
never an event_type (Feature 08's contract), so the sweep is read-only
over the domain tables.

Idempotency is the watermark: after a run, ``nestquest_meta_state``
records the household-local date the sweep ran, and the next run only
sweeps instances due in ``[watermark, today)``.  A second run the same
night therefore fires nothing new, and a run after days of downtime
sweeps exactly the accumulated window once — no per-instance journal,
no re-announcing old misses.  An instance swept as missed that is
later completed simply gains its completion event; history keeps both
rows (append-only), and the sweep's later runs skip it via the
no-completion-event rule.

The whole watermark read → query → build span runs inside the
per-database sweep lock (one lock per connection wrapper and running
loop, the settings store's pattern): an overlapping startup sweep and
a rollover sweep of the SAME process queue instead of interleaving.
The announce decision itself is the DATABASE-level claim
(:meth:`MetaStateDao.claim`), so two PROCESSES sharing one SQLite file
(the integration's rollover sweep and the API service's scheduler)
cannot both announce the same missed batch either: both may read the
old watermark and build the events, but the single conditional upsert
lets exactly one of them win the claim — the loser returns [] and
announces nothing.

The caller supplies ``today`` as a plain :class:`datetime.date`: the
household-local calendar date, read from ``hass.config.time_zone`` by
the integration or from the API host's local clock by the API.  This
module never reads a timezone database or config of its own.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from .const import EVENT_QUEST_MISSED
from .dao_meta import MetaStateDao
from .dao_instances import QuestInstancesDao
from .db import NestQuestDatabase
# Intentional intra-package reuse of the shared payload builder: the
# missed event's payload is the documented §3 instance payload, and
# building it through the ONE builder keeps this sweep's payloads from
# drifting from the completion/uncompleted builders' shape.
from .events import _instance_payload

LOGGER = logging.getLogger(__name__)

#: meta_state key holding the household-local date the sweep last ran.
SWEEP_WATERMARK_KEY = "missed_sweep_last_run_date"

#: One asyncio.Lock per (connection wrapper, running loop), mirroring
#: the settings store's pattern: the watermark read → query → build
#: span is one critical section, so an overlapping startup sweep and
#: rollover sweep of the SAME process queue instead of interleaving.
#: Same-process callers are fully serialised by it; the cross-process
#: case is closed by the database-level claim, not by this lock.
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


#: Strict UTC ISO-8601 timestamp (the DAO layers' policy): one shape,
#: explicit offset, second precision.
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


async def run_missed_sweep(
    database: NestQuestDatabase,
    *,
    today: datetime.date,
) -> list[tuple[str, dict]]:
    """Build one missed event per unswept past-due open instance.

    ``today`` is the household-local calendar date the sweep runs for
    (the caller owns the clock: the integration reads it from
    ``hass.config.time_zone``, the API from its host's local time).
    Returns the ``(event_type, payload)`` tuples to announce, EMPTY
    when the watermark already covers ``today`` (a same-night rerun) —
    the caller decides how to publish them and announces nothing on
    its own.

    The watermark read → query → build span runs inside the
    per-database sweep lock, so overlapping callers of ONE process
    queue instead of interleaving.  The announce decision is the
    DATABASE-level claim (:meth:`MetaStateDao.claim` — a single
    conditional upsert on the watermark, atomic across processes):
    every caller builds the events optimistically, then only the
    caller whose claim actually advanced the watermark returns them;
    a loser (another process already announced for ``today``) returns
    [] and announces nothing twice.  Every event in one run shares one
    ``occurred_at`` stamp (one run, one announcement moment), and the
    payload comes from the shared
    :func:`~.events._instance_payload` builder so the shape can never
    drift from the documented §3 contract.

    Failure ordering: the watermark is advanced ONLY by the claim,
    AFTER the events are fully built — a failure before the claim
    leaves the watermark unadvanced, so a later run re-sweeps the same
    window and nothing is lost.
    """
    today_iso = today.isoformat()
    dao = MetaStateDao(database)
    async with _sweep_lock(database):
        watermark = await dao.get(SWEEP_WATERMARK_KEY)
        if watermark == today_iso:
            LOGGER.debug(
                "NestQuest missed sweep already ran for %s", today_iso
            )
            return []

        instances_dao = QuestInstancesDao(database)
        rows = await instances_dao.list_missed_unswept(today_iso, watermark)
        now_stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            _UTC_TIMESTAMP_FORMAT
        )
        events: list[tuple[str, dict]] = []
        for instance in rows:
            events.append(
                (
                    EVENT_QUEST_MISSED,
                    await _instance_payload(
                        database, instance.id, now_stamp
                    ),
                )
            )
        # The database-level claim gates the announcement: only the
        # caller that actually advanced the watermark may publish the
        # built events, so two processes racing one SQLite file cannot
        # both announce the same missed batch.  A same-value loser's
        # claim matches zero rows and this run announces nothing.
        claimed = await dao.claim(SWEEP_WATERMARK_KEY, today_iso)
        if not claimed:
            LOGGER.info(
                "NestQuest missed sweep for %s lost the watermark claim; "
                "announcing nothing",
                today_iso,
            )
            return []
    LOGGER.info(
        "NestQuest missed sweep for %s built %d event(s)",
        today_iso,
        len(events),
    )
    return events

