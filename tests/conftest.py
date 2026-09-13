"""Shared pytest fixtures for the NestQuest test suite.

pytest-homeassistant-custom-component could not be adopted: it pins
``pytest==9.0.3`` and ``voluptuous==0.13.1``, which conflicts with the dev
group's ``voluptuous>=0.14`` (used directly by the options flow's schema and
its tests), and its back-releases raise the floor to Python >=3.12 while this
project supports >=3.11.  The documented fallback is therefore used:
``pytest-asyncio`` plus a standard-shaped ``hass`` fixture below.

The tests mock the ``homeassistant`` package via ``sys.modules`` injection;
this conftest wires the mock modules before any test module import and
provides the standard ``hass`` fixture shape (``config``, ``config_entries``,
``data``, ``loop``) that HA's own harness exposes.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Mock homeassistant modules if not installed in the environment.  Runs in
# conftest so it precedes every test module's import of the integration.
for _mod in (
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.data_entry_flow",
):
    sys.modules.setdefault(_mod, MagicMock())

# Wire parent package attributes so "from homeassistant import config_entries"
# resolves to the mocked submodule, mirroring real HA's package layout.
sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
sys.modules["homeassistant"].data_entry_flow = sys.modules["homeassistant.data_entry_flow"]


@pytest.fixture
def hass():
    """Provide a standard-shaped hass fixture.

    Mirrors the surface of Home Assistant's ``hass`` fixture: a ``config``
    namespace, a ``config_entries`` manager, a ``data`` dict for integration
    state, and the running event ``loop``.
    """
    hass = SimpleNamespace(
        data={},
        config=MagicMock(),
        config_entries=MagicMock(),
    )
    hass.loop = asyncio.new_event_loop()
    try:
        yield hass
    finally:
        hass.loop.close()