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
from custom_components.nestquest.quest_definitions import (
    assign_child,
    create_quest_definition,
    edit_quest_definition,
)
from custom_components.nestquest.recurrence import RuleType, ScheduleRule

NOW = "2026-09-14T12:00:00+00:00"
NEW_YORK = "America/New_York"


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


async def _prepare(path):
    database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
    await database.open(path)
    await apply_migrations(database)
    return database


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _freeze_clock(
    monkeypatch, instant: datetime.datetime
) -> tuple[datetime.datetime, list]:
    """Freeze the integration's ``datetime`` clock to a fixed aware instant.

    Only ``custom_components.nestquest``'s ``datetime`` binding is patched, so
    the generation path's "today" reads this instant (localized to whatever
    time zone it asks for) while every other module and the test harness keep
    the real clock.  Returns ``(frozen, requested)`` where ``frozen`` is the
    instant normalized to UTC and ``requested`` is the list of ``tzinfo``
    objects the code under test passed to ``now`` — so a test can prove the
    generation path actually requested the configured HA time zone rather
    than silently reading UTC.
    """
    import custom_components.nestquest as nestquest

    frozen = instant.astimezone(datetime.timezone.utc)
    requested: list = []

    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            requested.append(tz)
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    fake_module = SimpleNamespace(
        datetime=_FrozenDatetime,
        timedelta=datetime.timedelta,
        date=datetime.date,
    )
    monkeypatch.setattr(nestquest, "datetime", fake_module)
    return frozen, requested


def _assert_requested_ha_timezone(requested, time_zone: str) -> None:
    """Assert ``now`` was called with (only) the configured HA time zone.

    This is what turns the DST tests into a real proof of the HA-local date
    source: if the generation path regressed to ``now(timezone.utc)``, its
    requested tz would be UTC and this fails.
    """
    assert requested, "the generation path never called now(tz)"
    assert all(tz == ZoneInfo(time_zone) for tz in requested)


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
        _frozen, requested = _freeze_clock(monkeypatch, instant)
        import custom_components.nestquest as nestquest

        child_id = await _seed_daily(database, local_today.isoformat())
        await nestquest._run_horizon_materialization(hass, database)
        records = await QuestInstancesDao(database).list_by_date_range(
            child_id,
            local_today.isoformat(),
            (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
        )
        _assert_contiguous_horizon(records, local_today)
        _assert_requested_ha_timezone(requested, NEW_YORK)
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
        _frozen, requested = _freeze_clock(monkeypatch, instant)
        import custom_components.nestquest as nestquest

        child_id = await _seed_daily(database, local_today.isoformat())
        await nestquest._run_horizon_materialization(hass, database)
        records = await QuestInstancesDao(database).list_by_date_range(
            child_id,
            local_today.isoformat(),
            (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
        )
        _assert_contiguous_horizon(records, local_today)
        _assert_requested_ha_timezone(requested, NEW_YORK)
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

        requested_batches: list[list] = []
        for instant in (before, after):
            _frozen, requested = _freeze_clock(monkeypatch, instant)
            requested_batches.append(requested)
            local_today = instant.date()
            child_id = await _seed_daily(database, local_today.isoformat())
            await nestquest._run_horizon_materialization(hass, database)
            records = await QuestInstancesDao(database).list_by_date_range(
                child_id,
                local_today.isoformat(),
                (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
            )
            _assert_contiguous_horizon(records, local_today)
        requested_all = [tz for batch in requested_batches for tz in batch]
        _assert_requested_ha_timezone(requested_all, NEW_YORK)
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

    The repeated 01:00-02:00 hour must not resolve to the wrong calendar
    day: the first 01:30 (``fold=0``, EDT) and the repeated 01:30
    (``fold=1``, EST) are distinct instants yet both resolve to 2026-11-01
    — and both, along with 03:30 EST after the jump, materialize the same
    15 contiguous-day horizon with no off-by-one.
    """
    zone = ZoneInfo(NEW_YORK)
    first = datetime.datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)  # EDT
    second = datetime.datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)  # EST
    after = datetime.datetime(2026, 11, 1, 3, 30, tzinfo=zone)  # EST
    assert first.date() == second.date() == after.date() == datetime.date(2026, 11, 1)
    assert first.utcoffset() != second.utcoffset()  # the two repeated-hour folds

    async def _body(database):
        hass = _tz_hass(NEW_YORK)
        import custom_components.nestquest as nestquest

        requested_batches: list[list] = []
        for instant in (first, second, after):
            _frozen, requested = _freeze_clock(monkeypatch, instant)
            requested_batches.append(requested)
            local_today = instant.date()
            child_id = await _seed_daily(database, local_today.isoformat())
            await nestquest._run_horizon_materialization(hass, database)
            records = await QuestInstancesDao(database).list_by_date_range(
                child_id,
                local_today.isoformat(),
                (local_today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
            )
            _assert_contiguous_horizon(records, local_today)
        requested_all = [tz for batch in requested_batches for tz in batch]
        _assert_requested_ha_timezone(requested_all, NEW_YORK)
        return local_today

    async def _main():
        database = await _prepare(tmp_path / "tz-fall-back.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) == datetime.date(2026, 11, 1)


def test_definition_business_regeneration_uses_pinned_today_not_host(
    tmp_path, monkeypatch
) -> None:
    """``edit_quest_definition``/``assign_child`` anchor regeneration on
    the caller-pinned HA-local ``today``, not the host clock.

    The host clock (the ``_today`` fallback) is pinned one day AHEAD of the
    HA-local ``today``; the guard would reject the local "today" as past
    (and the horizon would skip it) if it consulted the host clock.  Both
    business operations must regenerate against the pinned date and keep
    that first local day, proving the threaded ``today`` wins.
    """
    import core.dao_instances as dao_instances_module

    pinned = datetime.date(2026, 1, 14)
    host_today = datetime.date(2026, 1, 15)
    monkeypatch.setattr(dao_instances_module, "_today", lambda: host_today)

    async def _body(database):
        children = ChildrenDao(database)
        dao = QuestInstancesDao(database)
        horizon_end = pinned + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)

        a = await children.create("Ada", NOW)
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=pinned.isoformat()),
            [a.id],
            [("morning", "09:00")],
        )
        definition_id = created.definition.id

        # edit anchors on pinned: the horizon starts at the local day the
        # host clock calls "past", so its presence proves pinned won.
        await edit_quest_definition(
            database,
            definition_id,
            windows=[("morning", "10:15")],
            today=pinned,
        )
        a_records = await dao.list_by_date_range(
            a.id, pinned.isoformat(), horizon_end.isoformat()
        )
        assert [r.due_date for r in a_records][0] == pinned.isoformat()
        assert {r.due_time for r in a_records} == {"10:15"}
        assert len(a_records) == DEFAULT_HORIZON_DAYS + 1

        # assign anchors on pinned too: the new child's regeneration keeps
        # the same pinned-local first day rather than skipping to the host day.
        b = await children.create("Bo", NOW)
        await assign_child(database, definition_id, b.id, today=pinned)
        b_records = await dao.list_by_date_range(
            b.id, pinned.isoformat(), horizon_end.isoformat()
        )
        assert [r.due_date for r in b_records][0] == pinned.isoformat()
        assert len(b_records) == DEFAULT_HORIZON_DAYS + 1
        return definition_id

    async def _main():
        database = await _prepare(tmp_path / "tz-definition-regen.db")
        try:
            return await _body(database)
        finally:
            await database.close()

    assert _run(_main()) is not None
