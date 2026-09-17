"""Tests for the setup/unload lifecycle of NestQuest."""
from __future__ import annotations

import asyncio

import pytest

from conftest import make_config_entry, make_hass, wire_entry_to_registry

from custom_components.nestquest import DOMAIN, async_setup_entry, async_unload_entry
from custom_components.nestquest.const import (
    CONF_DAY_ROLLOVER_TIME,
    DEFAULT_HORIZON_DAYS,
    DOMAIN as DOMAIN_CONST,
)


def _wire(entry, registry):
    return wire_entry_to_registry(entry, registry)


async def test_setup_stores_runtime_data_in_hass_data(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.data[DOMAIN][entry.entry_id] is entry.runtime_data


async def test_setup_runtime_data_has_entry_id_and_options(hass, make_entry) -> None:
    entry = _wire(make_entry(options={"horizon_days": 7}), hass.registry)
    await async_setup_entry(hass, entry)
    runtime = entry.runtime_data
    assert runtime.entry_id == entry.entry_id
    assert runtime.options == {"horizon_days": 7}
    assert callable(runtime.remove_update_listener)


async def test_unload_returns_true_and_removes_hass_data(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    assert await async_setup_entry(hass, entry) is True
    assert registry.size == 1
    assert await async_unload_entry(hass, entry) is True
    assert hass.data == {}
    assert DOMAIN not in hass.data
    assert entry.runtime_data is None
    assert registry.size == 0


async def test_unload_of_one_entry_keeps_domain_while_other_remains(
    hass, make_entry
) -> None:
    """Unloading one of two entries keeps DOMAIN alive with the other entry."""
    registry = hass.registry
    entry_a = _wire(make_entry(entry_id="entry_a"), registry)
    entry_b = _wire(make_entry(entry_id="entry_b"), registry)
    assert await async_setup_entry(hass, entry_a) is True
    assert await async_setup_entry(hass, entry_b) is True
    assert set(hass.data[DOMAIN]) == {"entry_a", "entry_b"}

    assert await async_unload_entry(hass, entry_a) is True
    assert DOMAIN in hass.data
    assert set(hass.data[DOMAIN]) == {"entry_b"}
    assert hass.data[DOMAIN]["entry_b"] is entry_b.runtime_data
    assert entry_a.runtime_data is None
    assert entry_b.runtime_data is not None
    assert registry.size == 1

    assert await async_unload_entry(hass, entry_b) is True
    assert DOMAIN not in hass.data
    assert hass.data == {}
    assert entry_b.runtime_data is None
    assert registry.size == 0


async def test_unload_is_idempotent(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    assert DOMAIN not in hass.data
    assert hass.data == {}


async def test_unload_without_setup_returns_true(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_unload_entry(hass, entry) is True
    assert DOMAIN not in hass.data
    assert hass.data == {}


async def test_unload_clears_entry_runtime_data(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    await async_unload_entry(hass, entry)
    assert entry.runtime_data is None


async def test_unload_removes_update_listener(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    await async_setup_entry(hass, entry)
    assert registry.size == 1
    await async_unload_entry(hass, entry)
    assert registry.size == 0


async def test_options_update_triggers_reload_once(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    await async_setup_entry(hass, entry)
    entry.options = {"horizon_days": 30}
    await registry.async_dispatch_options_update(entry)
    assert hass.config_entries.async_reload.call_count == 1
    assert registry.reloaded == [entry.entry_id]


async def test_no_reload_after_unload(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    await async_setup_entry(hass, entry)
    await async_unload_entry(hass, entry)
    await registry.async_dispatch_options_update(entry)
    assert hass.config_entries.async_reload.call_count == 0


async def test_three_reload_cycles_keep_single_listener(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    for _ in range(3):
        assert await async_setup_entry(hass, entry) is True
        assert registry.size == 1
        assert await async_unload_entry(hass, entry) is True
        assert registry.size == 0
    assert hass.config_entries.async_reload.call_count == 0


async def test_three_setup_unload_cycles_leave_no_listeners(hass, make_entry) -> None:
    """Listeners accumulate per entry (HA semantics); unload must remove them all."""
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    for _ in range(3):
        await async_setup_entry(hass, entry)
        await async_unload_entry(hass, entry)
    assert registry._listeners.get(entry.entry_id, []) == []
    assert registry.size == 0


async def test_options_update_after_each_setup_invokes_exactly_one_listener(
    hass, make_entry
) -> None:
    """After each setup, an options update dispatches to exactly one listener."""
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    for _ in range(3):
        await async_setup_entry(hass, entry)
        await registry.async_dispatch_options_update(entry)
        assert hass.config_entries.async_reload.call_count == 1
        assert registry.reloaded == [entry.entry_id]
        await async_unload_entry(hass, entry)
        hass.config_entries.async_reload.reset_mock()
        registry.reloaded.clear()


async def test_reload_setup_cycles_dispatch_reload_each_time(hass, make_entry) -> None:
    registry = hass.registry
    entry = _wire(make_entry(), registry)
    for _ in range(3):
        await async_setup_entry(hass, entry)
        await registry.async_dispatch_options_update(entry)
        await async_unload_entry(hass, entry)
    assert hass.config_entries.async_reload.call_count == 3
    assert registry.size == 0


async def test_no_orphaned_tasks_after_unload(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    await async_unload_entry(hass, entry)
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    assert pending == []


async def test_setup_entry_uses_domain_constant(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    assert set(hass.data) == {DOMAIN_CONST}


async def test_setup_awaitable_listener_removal_supported() -> None:
    """A coroutine-returning remover is awaited during unload."""
    removed = []

    async def _remover():
        removed.append(True)

    entry = make_config_entry(entry_id="awaitable")
    entry.add_update_listener = lambda listener: _remover
    hass, _registry = make_hass()
    await async_setup_entry(hass, entry)
    result = await async_unload_entry(hass, entry)
    assert result is True
    assert removed == [True]
    assert hass.data == {}
    assert entry.runtime_data is None


async def test_setup_closes_database_when_listener_registration_fails() -> None:
    """A listener-registration failure must not leak the opened database."""
    from custom_components.nestquest.db import NestQuestDatabase

    class _Boom(Exception):
        pass

    entry = make_config_entry(entry_id="listener-boom")
    entry.add_update_listener = lambda listener: (_ for _ in ()).throw(_Boom())
    hass, _registry = make_hass()
    with pytest.raises(_Boom):
        await async_setup_entry(hass, entry)
    assert hass.data.get(DOMAIN, {}) == {}
    assert not hasattr(entry, "runtime_data")


async def test_unload_closes_database_even_when_listener_removal_raises() -> None:
    """Unload removes the listener, closes the DB in a finally, then raises."""
    from custom_components.nestquest.db import NestQuestDatabase

    class _RemoveBoom(Exception):
        pass

    def _remover():
        raise _RemoveBoom()

    entry = make_config_entry(entry_id="remove-boom")
    entry.add_update_listener = lambda listener: _remover
    hass, _registry = make_hass()
    await async_setup_entry(hass, entry)
    database = entry.runtime_data.database
    with pytest.raises(_RemoveBoom):
        await async_unload_entry(hass, entry)
    assert database.connected is False, "database leaked despite remover error"
    assert entry.runtime_data is None
    assert DOMAIN not in hass.data


async def test_setup_registers_day_rollover_listener(hass, make_entry) -> None:
    """Setup registers a daily rollover listener and stores its cancel fn."""
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert hass.time_change.size == 1
    registration = hass.time_change.registrations[0]
    assert registration["hour"] == 0
    assert registration["minute"] == 0
    assert registration["local"] is True
    assert callable(entry.runtime_data.remove_time_change_listener)


async def test_setup_registers_day_rollover_at_configured_time(hass, make_entry) -> None:
    """The listener fires at the entry option's rollover time, not the default."""
    entry = _wire(make_entry(options={CONF_DAY_ROLLOVER_TIME: "06:30"}), hass.registry)
    await async_setup_entry(hass, entry)
    registration = hass.time_change.registrations[0]
    assert registration["hour"] == 6
    assert registration["minute"] == 30


async def test_unload_cancels_day_rollover_listener(hass, make_entry) -> None:
    """Unload removes the time-change listener alongside the update listener."""
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    assert hass.time_change.size == 1
    assert await async_unload_entry(hass, entry) is True
    assert hass.time_change.size == 0


async def test_rollover_time_change_reregisters_listener_at_new_time(
    hass, make_entry
) -> None:
    """A rollover-time options change re-registers the listener at the new time."""
    entry = _wire(
        make_entry(options={CONF_DAY_ROLLOVER_TIME: "00:00"}), hass.registry
    )
    await async_setup_entry(hass, entry)
    assert (hass.time_change.registrations[0]["hour"], hass.time_change.registrations[0]["minute"]) == (0, 0)

    # The options flow writes the new rollover time, then HA reloads the
    # entry: unload tears down the old listener, setup re-registers it.
    entry.options = {CONF_DAY_ROLLOVER_TIME: "06:30"}
    await async_unload_entry(hass, entry)
    assert hass.time_change.size == 0

    assert await async_setup_entry(hass, entry) is True
    assert hass.time_change.size == 1
    registration = hass.time_change.registrations[0]
    assert (registration["hour"], registration["minute"]) == (6, 30)


async def test_day_rollover_listener_materializes_ha_local_horizon(
    hass, make_entry, monkeypatch
) -> None:
    """Firing the listener materializes today..today+horizon in HA local time."""
    import datetime
    from unittest.mock import AsyncMock
    from zoneinfo import ZoneInfo

    import custom_components.nestquest as nestquest

    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    database = entry.runtime_data.database

    fake = AsyncMock()
    monkeypatch.setattr(nestquest, "_materialize_run", fake)

    time_zone = ZoneInfo(hass.config.time_zone)
    today = datetime.datetime.now(time_zone).date()
    expected_start = today.isoformat()
    expected_end = (today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat()

    await hass.time_change.fire()

    fake.assert_awaited_once_with(database, expected_start, expected_end)


async def test_setup_applies_all_v1_tables(hass, make_entry) -> None:
    """Setup applies the full v1 DDL: all four v1 tables exist afterwards."""
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    rows = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name IN ('children', 'admin_users', 'schedule_rules', "
        "'quest_definitions') ORDER BY name"
    )
    assert [row[0] for row in rows] == [
        "admin_users",
        "children",
        "quest_definitions",
        "schedule_rules",
    ]
    await async_unload_entry(hass, entry)