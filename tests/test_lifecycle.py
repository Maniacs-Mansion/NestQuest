"""Tests for the setup/unload lifecycle of NestQuest."""
from __future__ import annotations

import asyncio
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# Mock homeassistant modules if not installed in environment
for _mod in (
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
):
    sys.modules.setdefault(_mod, MagicMock())

# Wire parent package attributes to the actual module mocks so that
# "from homeassistant import config_entries" resolves to the mocked module.
sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]

import pytest

from custom_components.nestquest import DOMAIN, async_setup_entry, async_unload_entry
from custom_components.nestquest.const import DOMAIN as DOMAIN_CONST


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _ListenerRegistry:
    """Models HA's update-listener bookkeeping: appends to a list per entry, with per-listener removers."""

    def __init__(self, hass=None):
        self._hass = hass
        self._listeners: dict[str, list[object]] = {}
        self.reloaded: list[str] = []
        self._loop = asyncio.new_event_loop()

    def add(self, entry_id: str, listener) -> object:
        def _remove():
            self._listeners.get(entry_id, []).remove(listener)

        self._listeners.setdefault(entry_id, []).append(listener)
        return _remove

    def dispatch_options_update(self, entry) -> None:
        for listener in list(self._listeners.get(entry.entry_id, [])):
            result = listener(self._hass, entry)
            if inspect.isawaitable(result):
                self._loop.run_until_complete(result)

    @property
    def size(self) -> int:
        return sum(len(listeners) for listeners in self._listeners.values())


def _make_hass():
    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(
            async_reload=None,
        ),
    )
    registry = _ListenerRegistry(hass)
    async def _async_reload(entry_id: str) -> None:
        registry.reloaded.append(entry_id)

    hass.config_entries.async_reload = MagicMock(side_effect=_async_reload)
    return hass, registry


def _make_entry(entry_id: str = "test_entry", options: dict | None = None):
    entry = SimpleNamespace(entry_id=entry_id, options=dict(options or {}))
    entry.add_update_listener = None
    return entry


def _wire_entry(entry, registry: _ListenerRegistry):
    entry.add_update_listener = lambda listener: registry.add(entry.entry_id, listener)
    return entry


def test_setup_stores_runtime_data_in_hass_data() -> None:
    hass, _ = _make_hass()
    entry = _wire_entry(_make_entry(), _ListenerRegistry())
    assert _run(async_setup_entry(hass, entry)) is True
    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.data[DOMAIN][entry.entry_id] is entry.runtime_data


def test_setup_runtime_data_has_entry_id_and_options() -> None:
    hass, _ = _make_hass()
    entry = _wire_entry(_make_entry(options={"horizon_days": 7}), _ListenerRegistry())
    _run(async_setup_entry(hass, entry))
    runtime = entry.runtime_data
    assert runtime.entry_id == entry.entry_id
    assert runtime.options == {"horizon_days": 7}
    assert callable(runtime.remove_update_listener)


def test_unload_returns_true_and_removes_hass_data() -> None:
    hass, _ = _make_hass()
    registry = _ListenerRegistry()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    assert _run(async_unload_entry(hass, entry)) is True
    assert entry.entry_id not in hass.data[DOMAIN]


def test_unload_is_idempotent() -> None:
    hass, _ = _make_hass()
    registry = _ListenerRegistry()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    assert _run(async_unload_entry(hass, entry)) is True
    assert _run(async_unload_entry(hass, entry)) is True
    assert entry.entry_id not in hass.data[DOMAIN]


def test_unload_without_setup_returns_true() -> None:
    hass, _ = _make_hass()
    entry = _make_entry()
    assert _run(async_unload_entry(hass, entry)) is True
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]


def test_unload_clears_entry_runtime_data() -> None:
    hass, _ = _make_hass()
    registry = _ListenerRegistry()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    _run(async_unload_entry(hass, entry))
    assert entry.runtime_data is None


def test_unload_removes_update_listener() -> None:
    hass, _ = _make_hass()
    registry = _ListenerRegistry()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    assert registry.size == 1
    _run(async_unload_entry(hass, entry))
    assert registry.size == 0


def test_options_update_triggers_reload_once() -> None:
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    entry.options = {"horizon_days": 30}
    registry.dispatch_options_update(entry)
    assert hass.config_entries.async_reload.call_count == 1
    assert registry.reloaded == [entry.entry_id]


def test_no_reload_after_unload() -> None:
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    _run(async_setup_entry(hass, entry))
    _run(async_unload_entry(hass, entry))
    registry.dispatch_options_update(entry)
    assert hass.config_entries.async_reload.call_count == 0


def test_three_reload_cycles_keep_single_listener() -> None:
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    for _ in range(3):
        assert _run(async_setup_entry(hass, entry)) is True
        assert registry.size == 1
        assert _run(async_unload_entry(hass, entry)) is True
        assert registry.size == 0
    assert hass.config_entries.async_reload.call_count == 0


def test_three_setup_unload_cycles_leave_no_listeners() -> None:
    """Listeners accumulate per entry (HA semantics); unload must remove them all."""
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    for _ in range(3):
        _run(async_setup_entry(hass, entry))
        _run(async_unload_entry(hass, entry))
    assert registry._listeners.get(entry.entry_id, []) == []
    assert registry.size == 0


def test_options_update_after_each_setup_invokes_exactly_one_listener() -> None:
    """After each setup, an options update dispatches to exactly one listener."""
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    for _ in range(3):
        _run(async_setup_entry(hass, entry))
        registry.dispatch_options_update(entry)
        assert hass.config_entries.async_reload.call_count == 1
        assert registry.reloaded == [entry.entry_id]
        _run(async_unload_entry(hass, entry))
        hass.config_entries.async_reload.reset_mock()
        registry.reloaded.clear()


def test_reload_setup_cycles_dispatch_reload_each_time() -> None:
    hass, registry = _make_hass()
    entry = _wire_entry(_make_entry(), registry)
    for _ in range(3):
        _run(async_setup_entry(hass, entry))
        registry.dispatch_options_update(entry)
        _run(async_unload_entry(hass, entry))
    assert hass.config_entries.async_reload.call_count == 3
    assert registry.size == 0


def test_no_orphaned_tasks_after_unload() -> None:
    async def _scenario():
        hass, registry = _make_hass()
        entry = _wire_entry(_make_entry(), registry)
        await async_setup_entry(hass, entry)
        await async_unload_entry(hass, entry)
        pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        assert pending == []

    _run(_scenario())


def test_setup_entry_uses_domain_constant() -> None:
    hass, _ = _make_hass()
    entry = _wire_entry(_make_entry(), _ListenerRegistry())
    _run(async_setup_entry(hass, entry))
    assert set(hass.data) == {DOMAIN_CONST}


def test_setup_awaitable_listener_removal_supported() -> None:
    """A coroutine-returning remover is awaited during unload."""

    async def _scenario():
        removed = []

        async def _remover():
            removed.append(True)

        entry = SimpleNamespace(entry_id="awaitable", options={})
        entry.add_update_listener = lambda listener: _remover
        hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_reload=None))
        await async_setup_entry(hass, entry)
        result = await async_unload_entry(hass, entry)
        assert result is True
        assert removed == [True]

    _run(_scenario())