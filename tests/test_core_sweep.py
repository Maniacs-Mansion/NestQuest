"""Cross-process safety of the missed-sweep watermark claim.

Feature 11's sweep guards its announcement with the watermark; the
original guard was a read-then-set inside a per-PROCESS asyncio lock,
so two PROCESSES sharing one SQLite file (the HA integration's
rollover sweep and the API service's scheduler) could both read the
old watermark and both announce the same missed batch.  These tests
pin the fix:

- :meth:`MetaStateDao.claim` is the atomic, database-level primitive:
  one conditional upsert whose ``rowcount`` says whether THIS caller
  changed the row.  The first claimant of a value wins; a second
  claimant of the same value — even on an INDEPENDENT connection to
  the same file, the shape two processes produce — loses.
- :func:`run_missed_sweep` gates the announcement on that claim: two
  independent ``NestQuestDatabase`` wrappers (two processes' shape)
  racing one seeded database yields exactly one announcer.
- The documented sweep semantics are unchanged: a same-night rerun
  announces nothing, and a run after days of downtime announces the
  accumulated ``[watermark, today)`` window exactly once.

Everything here runs against the bundled HA-free core copy
(``custom_components.nestquest.core``) with a plain
``asyncio.to_thread`` executor — no Home Assistant, no API server.
"""
from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import pytest

from custom_components.nestquest.core.dao_instances import (
    QuestInstancesDao,
)
from custom_components.nestquest.core.dao_meta import MetaStateDao
from custom_components.nestquest.core.db import NestQuestDatabase
from custom_components.nestquest.core.migrations import apply_migrations
from custom_components.nestquest.core.children import create_child
from custom_components.nestquest.core.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.core.materialize import materialize
from custom_components.nestquest.core.recurrence import ScheduleRule
from custom_components.nestquest.core.sweep import (
    SWEEP_WATERMARK_KEY,
    run_missed_sweep,
)

#: One missed event per unswept past-due instance — the sweep's only
#: event type.
EVENT_QUEST_MISSED = "nestquest_quest_missed"


async def _executor(fn, *args, **kwargs):
    """Run a synchronous callable on a worker thread and await it.

    The :class:`NestQuestDatabase` executor contract (the shape of
    ``hass.async_add_executor_job``), so sqlite3 calls never block the
    event loop.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _open_database(db_path: str) -> NestQuestDatabase:
    """Open (without migrating) one independent connection wrapper."""
    database = NestQuestDatabase(_executor)
    await database.open(db_path)
    return database


async def _seed_missed_household(
    db_path: str, today: datetime.date
) -> SimpleNamespace:
    """Seed a household with two past-due open instances on ``db_path``.

    One child, two quests whose ONLY instances are due YESTERDAY
    (materialized with ``today`` pinned to yesterday, ``end_date``
    closing the rules so the later today-walk cannot duplicate them).
    Seeding uses its OWN connection, opened and closed here, so the
    connections the tests race with start fresh.
    """
    database = await _open_database(db_path)
    try:
        await apply_migrations(database)
        today_iso = today.isoformat()
        yesterday = today - datetime.timedelta(days=1)
        yesterday_iso = yesterday.isoformat()
        rule = ScheduleRule.from_dict(
            {
                "rule_type": "daily",
                "start_date": yesterday_iso,
                "end_date": yesterday_iso,
            }
        )
        ada = await create_child(database, "Ada", sort_order=0)
        await create_quest_definition(
            database, "Stale chore", rule, [ada.id], [("morning", "09:00")]
        )
        await create_quest_definition(
            database, "Old chore", rule, [ada.id], [("evening", "18:30")]
        )
        await materialize(database, yesterday_iso, yesterday_iso, today=yesterday)
        # A quest due TODAY only (created after the yesterday walk so it
        # has no past-due instance; ``end_date`` keeps create's horizon
        # regeneration to today): the post-downtime catch-up run's
        # target — inside [watermark=today, later_today) but not
        # inside the day-one sweep's window.
        await create_quest_definition(
            database,
            "Recoverable chore",
            ScheduleRule.from_dict(
                {
                    "rule_type": "daily",
                    "start_date": today_iso,
                    "end_date": today_iso,
                }
            ),
            [ada.id],
            [("afternoon", "17:00")],
        )
        await materialize(database, today_iso, today_iso, today=today)
        instances = QuestInstancesDao(database)
        rows = await instances.list_by_child_and_date(ada.id, yesterday_iso)
        assert len(rows) == 2
        today_rows = await instances.list_by_child_and_date(
            ada.id, today_iso
        )
        assert len(today_rows) == 1
        return SimpleNamespace(
            child=ada,
            instances=rows,
            recoverable_instance=today_rows[0],
            yesterday_iso=yesterday_iso,
            today_iso=today_iso,
        )
    finally:
        await database.close()


# --- the claim primitive: atomic at the database level ------------------


async def test_claim_first_caller_wins_and_second_same_value_loses(
    temp_db_path: str,
) -> None:
    """claim() is a conditional upsert: first True, same-value second False.

    A different value always wins (an advance re-arms the check), and
    the stored value follows the winner.
    """
    database = await _open_database(temp_db_path)
    try:
        await apply_migrations(database)
        dao = MetaStateDao(database)
        assert await dao.get(SWEEP_WATERMARK_KEY) is None

        assert await dao.claim(SWEEP_WATERMARK_KEY, "2026-09-01") is True
        # Same value again: the row is already there — nothing changed.
        assert await dao.claim(SWEEP_WATERMARK_KEY, "2026-09-01") is False
        assert await dao.get(SWEEP_WATERMARK_KEY) == "2026-09-01"
        # A DIFFERENT value is an advance, not a re-claim: it wins.
        assert await dao.claim(SWEEP_WATERMARK_KEY, "2026-09-02") is True
        assert await dao.get(SWEEP_WATERMARK_KEY) == "2026-09-02"
        assert await dao.claim(SWEEP_WATERMARK_KEY, "2026-09-02") is False
    finally:
        await database.close()


async def test_claim_is_atomic_across_independent_connections(
    temp_db_path: str,
) -> None:
    """Two connections to one file cannot both claim the same value.

    This is the two-process shape: independent sqlite3 connections (one
    per ``NestQuestDatabase`` wrapper), racing the SAME key on the SAME
    event loop with no shared lock.  The single conditional upsert is
    serialized by SQLite itself, so exactly one caller's rowcount is 1.
    """
    first = await _open_database(temp_db_path)
    second = await _open_database(temp_db_path)
    try:
        await apply_migrations(first)
        won = await asyncio.gather(
            MetaStateDao(first).claim(SWEEP_WATERMARK_KEY, "2026-09-01"),
            MetaStateDao(second).claim(SWEEP_WATERMARK_KEY, "2026-09-01"),
        )
        assert sorted(won) == [False, True]
        # One stored row, holding the winner's value.
        assert await MetaStateDao(first).get(SWEEP_WATERMARK_KEY) == (
            "2026-09-01"
        )
        assert await MetaStateDao(second).get(SWEEP_WATERMARK_KEY) == (
            "2026-09-01"
        )
    finally:
        await first.close()
        await second.close()


# --- the sweep: the announcement is gated by the atomic claim -----------


async def test_two_process_shape_race_exactly_one_announces(
    temp_db_path: str,
) -> None:
    """Two independent connections racing the sweep: ONE announcer.

    Each wrapper carries its own connection AND its own per-process
    sweep lock, so nothing in-process serialises the two runs — the
    only guard left is the database-level claim.  Both read the unset
    watermark and both build the events, but exactly one claim wins:
    one run returns the missed events, the loser returns [].
    """
    today = datetime.datetime.now().astimezone().date()
    seed = await _seed_missed_household(temp_db_path, today)
    first = await _open_database(temp_db_path)
    second = await _open_database(temp_db_path)
    try:
        results = await asyncio.gather(
            run_missed_sweep(first, today=today),
            run_missed_sweep(second, today=today),
        )
        announcers = [r for r in results if r]
        assert len(announcers) == 1
        event_type, payload = announcers[0][0]
        assert event_type == EVENT_QUEST_MISSED
        assert payload["due_date"] == seed.yesterday_iso
        # Both instances of the seeded window, one event each.
        assert len(announcers[0]) == 2
        losers = [r for r in results if not r]
        assert losers == [[]]
        # The watermark holds the run's date for whoever looks next.
        assert (
            await MetaStateDao(first).get(SWEEP_WATERMARK_KEY)
            == seed.today_iso
        )
    finally:
        await first.close()
        await second.close()


async def test_same_night_rerun_announces_nothing(temp_db_path: str) -> None:
    """A second sweep for the same date is an empty no-op (the watermark)."""
    today = datetime.datetime.now().astimezone().date()
    await _seed_missed_household(temp_db_path, today)
    database = await _open_database(temp_db_path)
    try:
        first = await run_missed_sweep(database, today=today)
        assert len(first) == 2
        second = await run_missed_sweep(database, today=today)
        assert second == []
    finally:
        await database.close()


async def test_post_downtime_run_announces_accumulated_window_once(
    temp_db_path: str,
) -> None:
    """After days of downtime the catch-up run sweeps the window once.

    The first run sweeps yesterday's instances (watermark := today);
    ``today`` then jumps two days and the catch-up run — on a
    DIFFERENT connection, the two-process shape — announces the
    accumulated ``[watermark, later_today)`` window exactly once, and
    a rerun on the original connection is silent again.
    """
    today = datetime.datetime.now().astimezone().date()
    later_today = today + datetime.timedelta(days=2)
    seed = await _seed_missed_household(temp_db_path, today)
    first = await _open_database(temp_db_path)
    second = await _open_database(temp_db_path)
    try:
        # Day one: yesterday's two instances fire once.
        day_one = await run_missed_sweep(first, today=today)
        assert len(day_one) == 2
        assert all(
            payload["due_date"] == seed.yesterday_iso
            for _, payload in day_one
        )

        # The downtime catch-up: the window is [watermark, later_today).
        catchup = await run_missed_sweep(second, today=later_today)
        assert len(catchup) == 1
        event_type, payload = catchup[0]
        assert event_type == EVENT_QUEST_MISSED
        assert payload["due_date"] == seed.today_iso
        assert payload["instance_id"] == seed.recoverable_instance.id
        assert payload["child_id"] == seed.child.id

        # A further rerun announces nothing.
        assert await run_missed_sweep(first, today=later_today) == []
        assert (
            await MetaStateDao(first).get(SWEEP_WATERMARK_KEY)
            == later_today.isoformat()
        )
    finally:
        await first.close()
        await second.close()
