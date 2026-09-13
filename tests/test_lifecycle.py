"""Tests for the setup/unload lifecycle of NestQuest."""
from __future__ import annotations

import asyncio

from conftest import make_config_entry, make_hass, wire_entry_to_registry

from custom_components.nestquest import DOMAIN, async_setup_entry, async_unload_entry
from custom_components.nestquest.const import DOMAIN as DOMAIN_CONST


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