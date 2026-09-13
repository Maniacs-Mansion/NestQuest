"""Contract test for the mock-only homeassistant harness in conftest.py."""

from __future__ import annotations

import importlib.metadata
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