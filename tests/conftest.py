"""Shared pytest fixtures for the NestQuest test suite.

pytest-homeassistant-custom-component could not be adopted: it pins
``pytest==9.0.3`` and ``voluptuous==0.13.1``, which conflicts with the dev
group's ``voluptuous>=0.14`` (used directly by the options flow's schema and
its tests), and its back-releases raise the floor to Python >=3.12 while this
project supports >=3.11.  The documented fallback is therefore used:
``pytest-asyncio`` plus a standard-shaped ``hass`` fixture below.

conftest.py is the single place where ``homeassistant`` modules are provided:
this harness is explicitly MOCK-ONLY.  It unconditionally installs a coherent
set of MagicMock stand-ins via ``sys.modules`` and wires the parent-package
attributes.  All of that happens here, before any test module imports the
integration, so no test module needs its own ``sys.modules`` setup.  It also
provides the ``hass`` fixture plus shared helpers used by the behavior tests
(config-entry factory, listener registry).

Run this suite in its own venv *without* homeassistant installed (``uv run
pytest -q``); it is never meant to run against a real HA install.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import tempfile
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Homeassistant module provisioning (explicitly mock-only).
# ---------------------------------------------------------------------------
_HA_MODULES = (
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.data_entry_flow",
    "homeassistant.exceptions",
)

def _find_spec(name: str):
    """find_spec that returns None when the module (or its parent) is absent."""
    try:
        return importlib.util.find_spec(name)
    except (ModuleNotFoundError, ValueError):
        return None


def _ensure_mock_only():
    """Fail fast if real homeassistant is importable: this harness is mock-only."""
    for _mod in _HA_MODULES:
        # Anything already in sys.modules at load time is real HA; our mocks
        # are only installed after this check.
        if _mod in sys.modules or _find_spec(_mod) is not None:
            raise pytest.UsageError(
                "The NestQuest test harness is mock-only: real homeassistant is "
                f"importable ({_mod!r} found), and mixing real HA modules with the "
                "shaped mocks is not supported. Run the suite in its own venv "
                "without homeassistant installed, e.g. `uv run pytest -q`."
            )


_ensure_mock_only()

for _mod in _HA_MODULES:
    sys.modules.setdefault(_mod, MagicMock())

# Wire parent package attributes so "from homeassistant import
# config_entries" resolves to the mocked submodule, mirroring real HA's
# package layout.
for _parent, _child in (
    ("homeassistant", "config_entries"),
    ("homeassistant", "data_entry_flow"),
    ("homeassistant", "core"),
    ("homeassistant", "exceptions"),
):
    setattr(sys.modules[_parent], _child, sys.modules[f"{_parent}.{_child}"])


def _ha_mock(name: str):
    """Return the shaped mock module object for a homeassistant module."""
    return sys.modules[name]


def options_flow_base():
    """Return the mocked OptionsFlowWithConfigEntry class."""
    return getattr(sys.modules["homeassistant.config_entries"], "OptionsFlowWithConfigEntry")


class _ConfigFlowBase:
    """Stand-in for homeassistant.config_entries.ConfigFlow.

    A superset covering both the config-flow and options-flow tests: it must
    satisfy every consumer of the mocked surface.
    """

    VERSION = 1

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._domain = domain

    def __init__(self):
        self.context = {}

    def async_show_form(self, *, step_id, **kwargs):
        return {"type": "form", "step_id": step_id, **kwargs}

    def async_abort(self, *, reason, **kwargs):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, *, title, data, **kwargs):
        """Return the flow result only; the flow manager persists the entry."""
        return {"type": "create_entry", "title": title, "data": data}

    async def async_set_unique_id(self, unique_id, raise_on_progress=True):
        self.context["unique_id"] = unique_id
        return None

    def _async_current_entries(self):
        return self.hass.config_entries.async_entries(self._domain)

    def _async_in_progress(self):
        return []

    @staticmethod
    def async_get_options_flow(config_entry):
        raise NotImplementedError


class _OptionsFlowWithConfigEntryBase:
    """Stand-in mirroring HA 2024.6 config_entries.OptionsFlowWithConfigEntry."""

    def __init__(self, config_entry=None):
        self.config_entry = config_entry
        self.hass = None
        self.options = dict(config_entry.options) if config_entry is not None else {}

    def async_show_form(self, *, step_id, **kwargs):
        return {"type": "form", "step_id": step_id, **kwargs}

    def async_create_entry(self, *, title, data, **kwargs):
        return {"type": "create_entry", "title": title, "data": data}


def _callback_decorator(fn):
    """Mirror homeassistant.core.callback: flags the fn and returns it unchanged."""
    fn.__ha_callback__ = True
    return fn


# The concrete 2024.6-shaped surface the integration is written against
# (mirrors the shapes the tests previously installed per module).
_config_entries_mock = _ha_mock("homeassistant.config_entries")
_core_mock = _ha_mock("homeassistant.core")
_data_entry_flow_mock = _ha_mock("homeassistant.data_entry_flow")
_exceptions_mock = _ha_mock("homeassistant.exceptions")

_config_entries_mock.ConfigFlow = _ConfigFlowBase
_config_entries_mock.OptionsFlowWithConfigEntry = _OptionsFlowWithConfigEntryBase
_core_mock.callback = _callback_decorator
_data_entry_flow_mock.RESULT_TYPE_FORM = "form"
_data_entry_flow_mock.RESULT_TYPE_CREATE_ENTRY = "create_entry"
_data_entry_flow_mock.RESULT_TYPE_ABORT = "abort"
_data_entry_flow_mock.FlowResult = dict


class ConfigEntryNotReady(Exception):
    """Stand-in mirroring homeassistant.exceptions.ConfigEntryNotReady.

    HA retries setup when this is raised; the tests assert the corrupt
    database path raises it instead of crashing with an unrelated error.
    """


_exceptions_mock.ConfigEntryNotReady = ConfigEntryNotReady


# ---------------------------------------------------------------------------
# Shared helpers for the behavior tests.
# ---------------------------------------------------------------------------
class ListenerRegistry:
    """Models HA's update-listener bookkeeping: appends to a list per entry, with per-listener removers."""

    def __init__(self, hass=None):
        self._hass = hass
        self._listeners: dict[str, list[object]] = {}
        self.reloaded: list[str] = []

    def add(self, entry_id: str, listener) -> object:
        def _remove():
            self._listeners.get(entry_id, []).remove(listener)

        self._listeners.setdefault(entry_id, []).append(listener)
        return _remove

    async def dispatch_options_update(self, entry) -> None:
        """Dispatch on the running loop; sync listeners run inline, async ones awaited."""
        for listener in list(self._listeners.get(entry.entry_id, [])):
            result = listener(self._hass, entry)
            if inspect.isawaitable(result):
                await result

    async_dispatch_options_update = dispatch_options_update

    @property
    def size(self) -> int:
        return sum(len(listeners) for listeners in self._listeners.values())


def make_config_entry(
    entry_id: str = "test_entry",
    options: dict | None = None,
    data: dict | None = None,
):
    """Create a stub config entry shaped like HA's ConfigEntry for tests."""
    entry = SimpleNamespace(
        entry_id=entry_id,
        options=dict(options or {}),
        data=dict(data or {}),
    )
    entry.add_update_listener = None
    return entry


def wire_entry_to_registry(entry, registry: ListenerRegistry):
    """Attach an update-listener registration function to the entry."""
    entry.add_update_listener = lambda listener: registry.add(entry.entry_id, listener)
    return entry


class _HassNamespace(SimpleNamespace):
    """SimpleNamespace subclass so the hass stub can hold weak references."""


def make_hass() -> tuple:
    """Create a hass stub plus its listener registry, mirroring HA's shape."""
    config_dir = Path(tempfile.mkdtemp(prefix="nestquest-hass-"))
    hass = _HassNamespace(
        data={},
        config=MagicMock(),
        config_entries=SimpleNamespace(async_reload=None),
    )

    def _cleanup_config_dir():
        import shutil

        shutil.rmtree(config_dir, ignore_errors=True)

    weakref.finalize(hass, _cleanup_config_dir)
    hass.config.path = MagicMock(
        side_effect=lambda name: str(config_dir / (name or "config"))
    )

    def _run_executor_job(fn, *args, **kwargs):
        return asyncio.get_running_loop().run_in_executor(
            None, lambda: fn(*args, **kwargs)
        )

    hass.async_add_executor_job = _run_executor_job
    registry = ListenerRegistry(hass)

    async def _async_reload(entry_id: str) -> None:
        registry.reloaded.append(entry_id)

    hass.config_entries.async_reload = MagicMock(side_effect=_async_reload)
    hass.config_entries._entries = []
    hass.config_entries.async_add = (
        lambda entry: hass.config_entries._entries.append(entry)
    )

    def _async_entries(domain: str):
        return [e for e in hass.config_entries._entries if e.domain == domain]

    hass.config_entries.async_entries = _async_entries
    return hass, registry


@pytest.fixture
async def hass():
    """Provide a standard-shaped hass fixture bound to the running test loop.

    Mirrors the surface of Home Assistant's ``hass`` fixture: a ``config``
    namespace, a ``config_entries`` manager wired to a listener registry, a
    ``data`` dict for integration state, and a ``loop`` bound to the
    pytest-asyncio loop the test itself runs on (HA's running-loop contract),
    so code scheduling on ``hass.loop`` runs on the actual test loop.
    """
    _hass, registry = make_hass()
    _hass.registry = registry
    _hass.loop = asyncio.get_running_loop()
    yield _hass


@pytest.fixture
def make_entry():
    """Provide the config-entry factory as a fixture."""

    def _factory(entry_id: str = "test_entry", options: dict | None = None, data: dict | None = None):
        return make_config_entry(entry_id=entry_id, options=options, data=data)

    return _factory


@pytest.fixture
def listener_registry():
    """Provide a fresh listener registry for manual wiring."""

    def _factory(hass=None):
        return ListenerRegistry(hass)

    return _factory


@pytest.fixture
def make_flow():
    """Provide a factory for a stubbed NestQuestConfigFlow bound to hass."""

    def _factory(hass=None, existing_entries=None, in_progress=None):
        from custom_components.nestquest import config_flow

        flow = config_flow.NestQuestConfigFlow()
        flow.hass = hass if hass is not None else make_hass()[0]
        for entry in existing_entries or []:
            if getattr(entry, "domain", None) == flow._domain:
                flow.hass.config_entries.async_add(entry)
        if in_progress:
            flow._async_in_progress = lambda: in_progress
        return flow

    return _factory


@pytest.fixture
def make_config_flow_entry():
    """Provide an entry stub carrying a domain, for current-entries checks."""

    def _factory(domain: str, entry_id: str = "existing"):
        return SimpleNamespace(domain=domain, entry_id=entry_id)

    return _factory