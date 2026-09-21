"""Contract test for the mock-only homeassistant harness in conftest.py."""

from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import sys
from unittest.mock import MagicMock

import pytest

import conftest

from conftest import _HA_MODULES, _ensure_mock_only


def test_mock_only_harness_contract(monkeypatch):
    """The harness is mock-only: shaped mocks everywhere, fail-fast on real HA."""
    # Every required homeassistant module in sys.modules is a mock stand-in
    # with the shaped surface, and parent-package attributes point at them.
    for name in _HA_MODULES:
        assert isinstance(sys.modules[name], MagicMock), f"{name} is not a mock"

    config_entries = sys.modules["homeassistant.config_entries"]
    assert config_entries.ConfigFlow is conftest._ConfigFlowBase
    assert config_entries.OptionsFlowWithConfigEntry is (
        conftest._OptionsFlowWithConfigEntryBase
    )
    assert sys.modules["homeassistant"].config_entries is config_entries
    assert sys.modules["homeassistant.core"].callback is conftest._callback_decorator
    assert sys.modules["homeassistant.data_entry_flow"].RESULT_TYPE_FORM == "form"

    # Entity-platform stand-ins are wired with the shaped classes, and
    # parent-package attributes resolve to the mocked submodules.
    entity_module = sys.modules["homeassistant.helpers.entity"]
    assert entity_module.DeviceInfo is conftest.DeviceInfo
    assert entity_module.Entity is conftest.Entity
    sensor_module = sys.modules["homeassistant.components.sensor"]
    assert sensor_module.SensorEntity is conftest.SensorEntity
    assert sensor_module.SensorStateClass.MEASUREMENT == "measurement"
    assert sensor_module.SensorDeviceClass.PERCENTAGE == "percentage"
    assert sys.modules[
        "homeassistant.components.binary_sensor"
    ].BinarySensorEntity is conftest.BinarySensorEntity
    assert sys.modules[
        "homeassistant.helpers.update_coordinator"
    ].CoordinatorEntity is conftest.CoordinatorEntity
    assert sys.modules["homeassistant"].components.sensor is sensor_module

    # No homeassistant distribution is installed in this suite's own venv.
    with pytest.raises(importlib.metadata.PackageNotFoundError):
        importlib.metadata.version("homeassistant")

    # Fail-fast paths: a findable real HA module, or one preloaded in
    # sys.modules, both abort collection with a UsageError.
    real_spec = MagicMock(origin="/fake/site-packages/homeassistant/__init__.py")
    monkeypatch.setattr(conftest, "_find_spec", lambda name: real_spec)
    with pytest.raises(pytest.UsageError, match="mock-only"):
        _ensure_mock_only()

    monkeypatch.setattr(conftest, "_find_spec", lambda name: None)
    monkeypatch.setitem(sys.modules, "homeassistant", MagicMock(name="real-module"))
    with pytest.raises(pytest.UsageError, match="mock-only"):
        _ensure_mock_only()


async def test_hass_and_registry_run_on_the_running_test_loop(hass, make_entry):
    """hass.loop is the test's own loop and the registry spins no private loop."""
    # hass.loop is the very loop the async test runs on (HA running-loop
    # contract): code scheduling on hass.loop lands on the test loop itself.
    assert hass.loop is asyncio.get_running_loop()
    ran = []

    async def _scheduled():
        ran.append(True)

    await hass.loop.create_task(_scheduled())
    assert ran == [True]

    # ListenerRegistry never spins its own event loop (no resource leak) and
    # dispatch is a plain coroutine: sync listeners run inline, async awaited.
    registry = hass.registry
    assert not hasattr(registry, "_loop")
    assert inspect.iscoroutinefunction(registry.dispatch_options_update)

    calls = []

    def _sync_listener(h, entry):
        calls.append(("sync", entry.entry_id, h is hass))

    entry = make_entry(entry_id="disp")
    registry.add("disp", _sync_listener)
    await registry.dispatch_options_update(entry)
    assert calls == [("sync", "disp", True)]

    async def _async_listener(h, entry):
        calls.append(("async", entry.entry_id))

    registry.add("disp", _async_listener)
    calls.clear()
    await registry.async_dispatch_options_update(entry)
    assert calls == [("sync", "disp", True), ("async", "disp")]