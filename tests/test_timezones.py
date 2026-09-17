"""Timezone tests for the single HA-local date source in the generation path.

These pin the done-condition that every "today" read in the generation path
derives from ``hass.config.time_zone`` — not the host clock and not UTC —
and that the rolling horizon ``[today, today + DEFAULT_HORIZON_DAYS]`` and the
no-past guard resolve the correct local dates around midnight and across the
daylight-saving transitions.
"""
from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from custom_components.nestquest.const import DEFAULT_HORIZON_DAYS
from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.quest_definitions import create_quest_definition
from custom_components.nestquest.recurrence import RuleType, ScheduleRule

NOW = "2026-09-14T12:00:00+00:00"
NEW_YORK = "America/New_York"


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


async def _prepare(path):
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    return database


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _freeze_clock(monkeypatch, instant: datetime.datetime) -> datetime.datetime:
    """Freeze the integration's ``datetime`` clock to a fixed aware instant.

    Only ``custom_components.nestquest``'s ``datetime`` binding is patched, so
    the generation path's "today" reads this instant (localized to whatever
    time zone it asks for) while every other module and the test harness keep
    the real clock.  Returns the instant normalized to UTC.
    """
    import custom_components.nestquest as nestquest

    frozen = instant.astimezone(datetime.timezone.utc)

    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    fake_module = SimpleNamespace(
        datetime=_FrozenDatetime,
        timedelta=datetime.timedelta,
        date=datetime.date,
    )
    monkeypatch.setattr(nestquest, "datetime", fake_module)
    return frozen


def _tz_hass(time_zone: str):
    """A minimal hass exposing only the ``config.time_zone`` the walk reads."""
    return SimpleNamespace(config=SimpleNamespace(time_zone=time_zone))


async def _seed_daily(database, start_iso: str) -> int:
    """One always-present child + a daily definition starting ``start_iso``."""
    child = await ChildrenDao(database).create("Ada", NOW)
    await create_quest_definition(
        database,
        "Daily chore",
        ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
        [child.id],
        ["morning"],
    )
    return child.id


def _local_date(instant_utc: datetime.datetime, time_zone: str) -> datetime.date:
    return instant_utc.astimezone(ZoneInfo(time_zone)).date()


def _assert_contiguous_horizon(records, local_today: datetime.date) -> None:
    """The horizon is exactly today..today+horizon, no off-by-one, no gap."""
    expected = {
        (local_today + datetime.timedelta(days=offset)).isoformat()
        for offset in range(DEFAULT_HORIZON_DAYS + 1)
    }
    assert {r.due_date for r in records} == expected
    assert len(records) == DEFAULT_HORIZON_DAYS + 1


def test_horizon_uses_newyork_local_date_after_local_midnight(
    tmp_path, monkeypatch
) -> None:
    """A run just after New York local midnight uses the local date.

    The frozen instant is 00:05 New York local time on 2026-03-10 (EDT, so
    04:05 UTC).  The horizon must start on 2026-03-10 — the local calendar
    date — not any host/UTC-derived value.
    """
    instant = datetime.datetime(
        2026, 3, 10, 0, 5, tzinfo=ZoneInfo(NEW_YORK)
    )
    local_today = instant.date()

    async def _body(database):
        hass = _tz_hass(NEW_YORK)
        _freeze_clock(monkeypatch, instant)
        import custom_components.nestquest as nestquest

        child_id = await _seed_daily(database, local_today.isoformat())
        await nestquest._run_horizon_materialization(hass, database)
        records = await QuestInstancesDao(database).list_by_date_range(
            child_id,
            local_today.isoformat(),
            (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
        )
        _assert_contiguous_horizon(records, local_today)
        return len(records)

    async def _main():
        database = await _prepare(tmp_path / "tz-midnight.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) == DEFAULT_HORIZON_DAYS + 1


def test_horizon_uses_local_date_not_utc_when_host_ahead(
    tmp_path, monkeypatch
) -> None:
    """The walk's "today" is HA-local, never the UTC/system calendar date.

    FROZEN at 2026-01-15 03:00 UTC: the UTC calendar date is 2026-01-15, but
    New York local is still 2026-01-14 22:00 EST.  The horizon must start on
    2026-01-14 (local), proving the UTC date did not win.
    """
    instant = datetime.datetime(2026, 1, 15, 3, 0, tzinfo=datetime.timezone.utc)
    local_today = _local_date(instant, NEW_YORK)
    assert local_today == datetime.date(2026, 1, 14)
    assert instant.date() == datetime.date(2026, 1, 15)

    async def _body(database):
        hass = _tz_hass(NEW_YORK)
        _freeze_clock(monkeypatch, instant)
        import custom_components.nestquest as nestquest

        child_id = await _seed_daily(database, local_today.isoformat())
        await nestquest._run_horizon_materialization(hass, database)
        records = await QuestInstancesDao(database).list_by_date_range(
            child_id,
            local_today.isoformat(),
            (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
        )
        _assert_contiguous_horizon(records, local_today)
        return len(records)

    async def _main():
        database = await _prepare(tmp_path / "tz-host-ahead.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) == DEFAULT_HORIZON_DAYS + 1


def test_horizon_resolves_spring_forward_day_without_off_by_one(
    tmp_path, monkeypatch
) -> None:
    """Across the 2026-03-08 spring-forward, today and the horizon stay local.

    Before the jump ("01:30 EST") and after it ("03:30 EDT") both resolve to
    2026-03-08 local — the lost hour must not skip or repeat a calendar day —
    and the full horizon remains 15 contiguous days.
    """
    zone = ZoneInfo(NEW_YORK)
    before = datetime.datetime(2026, 3, 8, 1, 30, tzinfo=zone)  # EST
    after = datetime.datetime(2026, 3, 8, 3, 30, tzinfo=zone)   # EDT
    assert before.date() == after.date() == datetime.date(2026, 3, 8)

    async def _body(database):
        hass = _tz_hass(NEW_YORK)
        import custom_components.nestquest as nestquest

        for instant in (before, after):
            _freeze_clock(monkeypatch, instant)
            local_today = instant.date()
            child_id = await _seed_daily(database, local_today.isoformat())
            await nestquest._run_horizon_materialization(hass, database)
            records = await QuestInstancesDao(database).list_by_date_range(
                child_id,
                local_today.isoformat(),
                (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
            )
            _assert_contiguous_horizon(records, local_today)
        return local_today

    async def _main():
        database = await _prepare(tmp_path / "tz-spring-forward.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) == datetime.date(2026, 3, 8)


def test_horizon_resolves_fall_back_day_without_off_by_one(
    tmp_path, monkeypatch
) -> None:
    """Across the 2026-11-01 fall-back, today and the horizon stay local.

    The repeated 01:00-02:00 hour must not resolve to the wrong calendar day:
    "01:30" (ambiguous) and "03:30 EST" (after the jump) both resolve to
    2026-11-01, and the full horizon remains 15 contiguous days.
    """
    zone = ZoneInfo(NEW_YORK)
    ambiguous = datetime.datetime(2026, 11, 1, 1, 30, tzinfo=zone)
    after = datetime.datetime(2026, 11, 1, 3, 30, tzinfo=zone)  # EST
    assert ambiguous.date() == after.date() == datetime.date(2026, 11, 1)

    async def _body(database):
        hass = _tz_hass(NEW_YORK)
        import custom_components.nestquest as nestquest

        for instant in (ambiguous, after):
            _freeze_clock(monkeypatch, instant)
            local_today = instant.date()
            child_id = await _seed_daily(database, local_today.isoformat())
            await nestquest._run_horizon_materialization(hass, database)
            records = await QuestInstancesDao(database).list_by_date_range(
                child_id,
                local_today.isoformat(),
                (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
            )
            _assert_contiguous_horizon(records, local_today)
        return local_today

    async def _main():
        database = await _prepare(tmp_path / "tz-fall-back.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) == datetime.date(2026, 11, 1)