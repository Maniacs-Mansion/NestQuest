"""Tests for the setup/unload lifecycle of NestQuest."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conftest import make_config_entry, make_hass, wire_entry_to_registry

from custom_components.nestquest import DOMAIN, async_setup_entry, async_unload_entry
from custom_components.nestquest.const import (
    DOMAIN as DOMAIN_CONST,
    SERVICE_COMPLETE_QUEST,
)
from custom_components.nestquest.dashboard import (
    DASHBOARD_STRATEGY_TYPE,
    DASHBOARD_URL_PATH,
)


def _wire(entry, registry):
    return wire_entry_to_registry(entry, registry)


class FakeDashboardsCollection:
    """Stand-in for the Lovelace dashboards collection.

    Records ``async_create_item`` calls the way the real collection
    would persist them, so tests can assert exactly what the setup path
    registered — and that a reload registers nothing more.
    """

    def __init__(self, items=None):
        self.items = list(items or [])
        self.created: list[dict] = []

    async def async_items(self):
        return list(self.items)

    async def async_create_item(self, item_config: dict) -> None:
        self.created.append(dict(item_config))
        self.items.append(dict(item_config))


def _install_dashboard_collection(hass, items=None) -> FakeDashboardsCollection:
    collection = FakeDashboardsCollection(items)
    hass.data["lovelace"] = SimpleNamespace(dashboards=collection)
    return collection


async def test_setup_stores_runtime_data_in_hass_data(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.data[DOMAIN][entry.entry_id] is entry.runtime_data


async def test_setup_runtime_data_has_entry_id_and_coordinator(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    runtime = entry.runtime_data
    assert runtime.entry_id == entry.entry_id
    assert runtime.coordinator is not None
    assert callable(runtime.remove_update_listener)


async def test_setup_registers_no_time_change_listener(hass, make_entry) -> None:
    """The integration owns no database any more: the daily
    day-rollover/materialization listener is gone (the API service
    owns the horizon), so setup registers NOTHING against the
    time-change listener bookkeeping."""
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    assert hass.time_change.size == 0


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
    entry.options = {"update_interval": 60}
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


async def test_setup_registers_the_completion_service(hass, make_entry) -> None:
    """The one domain-global service registers with setup and deregisters
    on the last unload."""
    entry = _wire(make_entry(), hass.registry)
    await async_setup_entry(hass, entry)
    assert hass.services.has_service(DOMAIN, SERVICE_COMPLETE_QUEST)
    await async_unload_entry(hass, entry)
    assert not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_QUEST)


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


async def test_setup_unwinds_when_listener_registration_fails() -> None:
    """A listener-registration failure must not leak partial setup state."""
    from custom_components.nestquest.const import DOMAIN as DOMAIN_CONST

    class _Boom(Exception):
        pass

    entry = make_config_entry(entry_id="listener-boom")
    entry.add_update_listener = lambda listener: (_ for _ in ()).throw(_Boom())
    hass, _registry = make_hass()
    with pytest.raises(_Boom):
        await async_setup_entry(hass, entry)
    assert hass.data.get(DOMAIN_CONST, {}) == {}
    assert not hasattr(entry, "runtime_data")
    assert not hass.services.has_service(DOMAIN_CONST, SERVICE_COMPLETE_QUEST)


async def test_unload_shuts_coordinator_even_when_listener_removal_raises() -> None:
    """A raising update-listener remover must not skip the coordinator
    shutdown: the retained error is re-raised only after the teardown
    ran and the runtime record was cleared."""
    from custom_components.nestquest.const import DOMAIN as DOMAIN_CONST

    class _RemoveBoom(Exception):
        pass

    def _remover():
        raise _RemoveBoom()

    entry = make_config_entry(entry_id="remove-boom")
    entry.add_update_listener = lambda listener: _remover
    hass, _registry = make_hass()
    await async_setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    seen = []

    async def _shutdown():
        seen.append("shutdown")

    coordinator.async_shutdown = _shutdown

    with pytest.raises(_RemoveBoom):
        await async_unload_entry(hass, entry)
    assert seen == ["shutdown"], "coordinator shutdown must have run"
    assert entry.runtime_data is None
    assert DOMAIN_CONST not in hass.data
    assert hass.time_change.size == 0


async def test_setup_creates_the_panel_dashboard(hass, make_entry) -> None:
    """A fresh install gets the storage-mode strategy dashboard, with the
    stable url_path, a title/icon, sidebar visibility and no YAML."""
    collection = _install_dashboard_collection(hass)
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert len(collection.created) == 1
    created = collection.created[0]
    assert created["url_path"] == DASHBOARD_URL_PATH
    assert created["mode"] == "storage"
    assert created["strategy"] == {"type": DASHBOARD_STRATEGY_TYPE}
    assert created["title"]
    assert created["show_in_sidebar"] is True
    assert "icon" in created


async def test_setup_reload_does_not_duplicate_the_dashboard(
    hass, make_entry
) -> None:
    """A reload (or a second entry) must not create a second dashboard:
    the one under the stable url_path is reused as-is."""
    collection = _install_dashboard_collection(hass)
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert len(collection.created) == 1
    # A reload: setup again on the same hass (the reload cycle) —
    # the existing dashboard must be left alone.
    await async_unload_entry(hass, entry)
    assert await async_setup_entry(hass, entry) is True
    assert len(collection.created) == 1
    # And a second entry on the same install.
    other = _wire(make_entry(entry_id="other"), hass.registry)
    assert await async_setup_entry(hass, other) is True
    assert len(collection.created) == 1


async def test_setup_leaves_an_existing_user_dashboard_alone(
    hass, make_entry
) -> None:
    """A dashboard already occupying the stable url_path — the user's
    own — is never overwritten, deleted or duplicated."""
    users_dashboard = {"url_path": DASHBOARD_URL_PATH, "title": "My Board"}
    collection = _install_dashboard_collection(hass, items=[users_dashboard])
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert collection.created == []
    assert collection.items[0] is users_dashboard


async def test_setup_succeeds_without_the_dashboards_collection(
    hass, make_entry, caplog
) -> None:
    """YAML mode / lovelace not loaded: log a warning, continue setup."""
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert entry.entry_id in hass.data[DOMAIN]
    assert any(
        "dashboard" in record.message.lower()
        and record.levelname == "WARNING"
        for record in caplog.records
    )


async def test_setup_survives_a_failing_dashboards_collection(
    hass, make_entry
) -> None:
    """A collection that refuses the create (permissions, admin-only)
    logs a warning and setup still succeeds — entities come up."""
    class _RefusingCollection(FakeDashboardsCollection):
        async def async_create_item(self, item_config):
            raise PermissionError("not an admin")

    collection = _RefusingCollection()
    hass.data["lovelace"] = SimpleNamespace(dashboards=collection)
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert collection.created == []
