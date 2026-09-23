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
import re
import sys
import tempfile
import unicodedata
import weakref
from dataclasses import dataclass
from html.entities import name2codepoint
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from unidecode import unidecode as _unidecode

from tests.admin_jwt_harness import ADMIN_KEY, KID, AdminRunner, jwks_for

# ---------------------------------------------------------------------------
# Homeassistant module provisioning (explicitly mock-only).
# ---------------------------------------------------------------------------
_HA_MODULES = (
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.data_entry_flow",
    "homeassistant.exceptions",
    "homeassistant.util",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.event",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.http",
    "homeassistant.components.frontend",
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
    ("homeassistant", "util"),
    ("homeassistant", "helpers"),
    ("homeassistant.helpers", "config_validation"),
    ("homeassistant.helpers", "entity"),
    ("homeassistant.helpers", "event"),
    ("homeassistant.helpers", "update_coordinator"),
    ("homeassistant.helpers", "aiohttp_client"),
    ("homeassistant", "components"),
    ("homeassistant.components", "sensor"),
    ("homeassistant.components", "binary_sensor"),
    ("homeassistant.components", "http"),
    ("homeassistant.components", "frontend"),
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


class HomeAssistantError(Exception):
    """Stand-in mirroring homeassistant.exceptions.HomeAssistantError."""


class ConfigEntryNotReady(HomeAssistantError):
    """Stand-in mirroring homeassistant.exceptions.ConfigEntryNotReady.

    HA retries setup when this is raised; the tests assert the corrupt
    database path raises it instead of crashing with an unrelated error.
    """


class Unauthorized(HomeAssistantError):
    """Stand-in mirroring homeassistant.exceptions.Unauthorized."""


_exceptions_mock.HomeAssistantError = HomeAssistantError
_exceptions_mock.ConfigEntryNotReady = ConfigEntryNotReady
_exceptions_mock.Unauthorized = Unauthorized


# ---------------------------------------------------------------------------
# homeassistant.util.slugify: a faithful stand-in for the real slugifier.
#
# Real HA (2024.6) wraps python-slugify's frozen legacy pipeline and answers
# its "unknown" sentinel when a non-empty name slugs to nothing.  The stub
# mirrors that pipeline step for step — quotes to dashes, NFKD-normalize,
# TRANSLITERATE through unidecode (the backend python-slugify's "auto" mode
# prefers, and a dev dependency here), decode HTML entities, NFKD again,
# lowercase, drop quotes, fold runs of non-[a-z0-9-] to one dash, collapse
# and strip dashes, then map dashes to the requested separator — and was
# verified byte-for-byte against real python-slugify across Latin, Cyrillic,
# CJK and Greek household-name shapes.  Transliteration is the point: HA
# derives the per-child entity ids from a name like "京子" as
# "nestquest_jing_zi_…", so the roster's slugs must transliterate too,
# never dropping characters into "unknown".  Deliberately NOT truncating:
# real slugify caps nothing; the entity registry truncates the full
# entity_id instead.
# ---------------------------------------------------------------------------
_HA_QUOTE_PATTERN = re.compile(r"[']+")
_HA_CHAR_ENTITY_PATTERN = re.compile(r"&(%s);" % "|".join(name2codepoint))
_HA_DECIMAL_PATTERN = re.compile(r"&#(\d+);")
_HA_HEX_PATTERN = re.compile(r"&#x([\da-fA-F]+);")
_HA_NUMBERS_PATTERN = re.compile(r"(?<=\d),(?=\d)")
_HA_DISALLOWED_CHARS_PATTERN = re.compile(r"[^-a-zA-Z0-9]+")
_HA_DUPLICATE_DASH_PATTERN = re.compile(r"-{2,}")


def _ha_slugify(text: str | None, *, separator: str = "_") -> str:
    """Faithful homeassistant.util.slugify stand-in (see section above)."""
    if text == "" or text is None:
        return ""
    text = str(text)
    text = _HA_QUOTE_PATTERN.sub("-", text)
    text = unicodedata.normalize("NFKD", text)
    text = _unidecode(text)
    text = _HA_CHAR_ENTITY_PATTERN.sub(
        lambda match: chr(name2codepoint[match.group(1)]), text
    )
    try:
        text = _HA_DECIMAL_PATTERN.sub(
            lambda match: chr(int(match.group(1))), text
        )
    except (ValueError, OverflowError):
        pass
    try:
        text = _HA_HEX_PATTERN.sub(
            lambda match: chr(int(match.group(1), 16)), text
        )
    except (ValueError, OverflowError):
        pass
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = _HA_QUOTE_PATTERN.sub("", text)
    text = _HA_NUMBERS_PATTERN.sub("", text)
    text = _HA_DISALLOWED_CHARS_PATTERN.sub("-", text)
    text = _HA_DUPLICATE_DASH_PATTERN.sub("-", text).strip("-")
    return "unknown" if text == "" else text.replace("-", separator)


_ha_mock("homeassistant.util").slugify = _ha_slugify


@dataclass
class DeviceInfo:
    """Stand-in for homeassistant.helpers.entity.DeviceInfo.

    The kwargs-only shape the integration builds per-child devices
    with: ``identifiers``, ``name``, ``manufacturer``, ``model``.
    """

    identifiers: object = None
    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None


class Entity:
    """Stand-in for homeassistant.helpers.entity.Entity.

    Mirrors the ``_attr_*`` attribute contract through the ``name``,
    ``unique_id``, ``device_info`` and ``extra_state_attributes``
    properties, and ``async_write_ha_state`` registering the entity
    into the hass entity registry (``hass.entities``, a dict keyed by
    ``unique_id`` storing the live object) — the harness's stand-in
    for HA's state machine, so tests enumerate entities and read
    their state directly off the registered object.
    """

    hass = None
    _attr_name: str | None = None
    _attr_unique_id: str | None = None
    _attr_device_info: DeviceInfo | None = None
    _attr_extra_state_attributes: dict | None = None

    @property
    def name(self) -> str | None:
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo | None:
        return self._attr_device_info

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._attr_extra_state_attributes

    def async_write_ha_state(self) -> None:
        """Register the entity under its unique_id (the mock state write)."""
        if self.hass is not None and self.unique_id is not None:
            self.hass.entities[self.unique_id] = self


class CoordinatorEntity(Entity):
    """Stand-in for homeassistant.helpers.update_coordinator.CoordinatorEntity.

    Real HA subscribes the entity to coordinator notifications in the
    platform-scheduler-driven ``async_added_to_hass`` lifecycle hook;
    the stand-in subscribes eagerly in ``__init__`` so the synchronous
    ``AddEntitiesCallback`` surface stays synchronous (the mock
    harness has no lifecycle scheduler).  ``_handle_coordinator_update``
    mirrors HA: one state write per coordinator notification.
    """

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self.coordinator.async_add_listener(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SensorStateClass:
    """Stand-in namespace for homeassistant.components.sensor.SensorStateClass.

    Only the members the integration uses (plus TOTAL for the
    long-history sensors later tasks add).
    """

    MEASUREMENT = "measurement"
    TOTAL = "total"


class SensorDeviceClass:
    """Stand-in namespace for homeassistant.components.sensor.SensorDeviceClass.

    Only the members the integration uses.
    """

    PERCENTAGE = "percentage"


class SensorEntity(Entity):
    """Stand-in for homeassistant.components.sensor.SensorEntity.

    The ``_attr_*`` passthrough for ``native_value``,
    ``native_unit_of_measurement``, ``state_class``, ``device_class``
    and ``suggested_display_precision``.
    """

    _attr_native_value: object = None
    _attr_native_unit_of_measurement: str | None = None
    _attr_state_class: str | None = None
    _attr_device_class: str | None = None
    _attr_suggested_display_precision: int | None = None

    @property
    def native_value(self) -> object:
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._attr_native_unit_of_measurement

    @property
    def state_class(self) -> str | None:
        return self._attr_state_class

    @property
    def device_class(self) -> str | None:
        return self._attr_device_class

    @property
    def suggested_display_precision(self) -> int | None:
        return self._attr_suggested_display_precision


class BinarySensorEntity(Entity):
    """Stand-in for homeassistant.components.binary_sensor.BinarySensorEntity.

    Wired now so PLATFORMS can grow (task 4's all-done / present
    sensors) without more harness surgery; only the surface the
    integration uses.
    """

    _attr_is_on: bool | None = None
    _attr_device_class: str | None = None

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    @property
    def device_class(self) -> str | None:
        return self._attr_device_class


class UpdateFailed(HomeAssistantError):
    """Stand-in mirroring homeassistant.helpers.update_coordinator.UpdateFailed.

    The exception an update pass raises to report a failed fetch: the
    coordinator records ``last_update_success = False`` instead of
    propagating it out of the refresh.
    """


class DataUpdateCoordinator:
    """Functional stand-in for HA's DataUpdateCoordinator.

    Mirrors the surface NestQuest's coordinator subclass uses:
    ``__init__(hass, logger, name=..., update_interval=...)``,
    ``async_add_listener``/``async_update_listeners`` for entity
    subscription, ``async_refresh``/``async_config_entry_first_refresh``
    driving the subclass's ``_async_update_data``, ``last_update_success``,
    ``last_exception``, and ``data``.  Interval scheduling is NOT
    simulated (no real clock ticks in tests) — tests drive refreshes
    directly.

    The failure contract mirrors real HA exactly (it is the trap this
    harness once hid): an update failure NEVER propagates out of
    ``async_refresh`` — the coordinator records
    ``last_update_success = False``, keeps its last good ``data``, and
    still notifies listeners so entities re-render unavailable — and
    ``async_config_entry_first_refresh`` wraps ANY failed pass in
    :class:`ConfigEntryNotReady`, with the original error only
    surviving as ``__cause__``.  A stand-in that re-raised the raw
    update error would let setup code key on the original exception
    type — a clause real HA can never reach.
    """

    def __init__(self, hass, logger, *, name=None, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None
        self.last_update_success = False
        self.last_exception = None
        self._listeners = []

    def async_add_listener(self, update_callback, context=None):
        """Subscribe; returns an unsubscribe callable like HA's."""
        entry = (update_callback, context)
        self._listeners.append(entry)

        def _remove():
            if entry in self._listeners:
                self._listeners.remove(entry)

        return _remove

    def async_update_listeners(self):
        """Notify every listener (entities schedule their writes)."""
        for callback, _context in list(self._listeners):
            callback()

    async def async_refresh(self):
        """Run one update pass and notify listeners.

        Mirrors HA: a failed update pass is RECORDED, never raised —
        ``last_update_success`` goes False, the exception lands on
        ``last_exception``, and listeners still fire; only cancellation
        propagates.
        """
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
        except Exception as err:
            self.last_update_success = False
            self.last_exception = err
        self.async_update_listeners()

    async def async_config_entry_first_refresh(self):
        """First refresh at config-entry setup, per HA's real contract.

        HA's real ``async_config_entry_first_refresh`` wraps ANY failed
        update pass in ``ConfigEntryNotReady`` — the original error
        survives only as ``__cause__`` — so setup code that must
        tolerate a failed first refresh keys on ConfigEntryNotReady,
        never on the original exception type.
        """
        await self.async_refresh()
        if not self.last_update_success:
            raise ConfigEntryNotReady(
                f"error fetching {self.name} data: {self.last_exception}"
            ) from self.last_exception

    async def async_shutdown(self):
        """Release listeners on teardown."""
        self._listeners.clear()


_update_coordinator_mock = _ha_mock("homeassistant.helpers.update_coordinator")
_update_coordinator_mock.DataUpdateCoordinator = DataUpdateCoordinator
_update_coordinator_mock.CoordinatorEntity = CoordinatorEntity
_update_coordinator_mock.UpdateFailed = UpdateFailed

_entity_mock = _ha_mock("homeassistant.helpers.entity")
_entity_mock.DeviceInfo = DeviceInfo
_entity_mock.Entity = Entity

_sensor_mock = _ha_mock("homeassistant.components.sensor")
_sensor_mock.SensorEntity = SensorEntity
_sensor_mock.SensorDeviceClass = SensorDeviceClass
_sensor_mock.SensorStateClass = SensorStateClass

_binary_sensor_mock = _ha_mock("homeassistant.components.binary_sensor")
_binary_sensor_mock.BinarySensorEntity = BinarySensorEntity


@dataclass(frozen=True)
class StaticPathConfig:
    """Stand-in mirroring homeassistant.components.http.StaticPathConfig."""

    url_path: str
    path: str
    cache_headers: bool = True


def _add_extra_js_url(hass, url, es5=False):
    """Stand-in mirroring homeassistant.components.frontend.add_extra_js_url."""
    urls = getattr(hass, "extra_js_urls", None)
    if urls is None:
        hass.extra_js_urls = []
        urls = hass.extra_js_urls
    urls.append(url)


_ha_mock("homeassistant.components.http").StaticPathConfig = StaticPathConfig
_ha_mock("homeassistant.components.frontend").add_extra_js_url = _add_extra_js_url

import voluptuous as vol


def _multi_select(choices: dict):
    """Mirror homeassistant.helpers.config_validation.multi_select.

    The options flow's admin picker uses HA's supported multi-select
    validator (schema-serializable by HA's frontend); the mock provides
    the same contract: a list whose members are keys of ``choices``.
    """

    def _validate(selected):
        if not isinstance(selected, list):
            raise vol.Invalid("Not a list")
        for value in selected:
            if value not in choices:
                raise vol.Invalid(f"{value} is not a valid option")
        return selected

    return _validate


_ha_mock("homeassistant.helpers.config_validation").multi_select = _multi_select


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


class TimeChangeRegistry:
    """Models HA's time-change listener bookkeeping.

    ``track`` mirrors ``homeassistant.helpers.event.async_track_time_change``:
    each call appends a record (action + hour/minute/second) and returns
    a remove callable that reverses the registration.  Tests inspect
    ``registrations`` and exercise the newest action through :meth:`fire`.
    """

    def __init__(self, hass=None):
        self._hass = hass
        self._registrations: list[dict] = []

    def track(self, action, hour=None, minute=None, second=None):
        record = {
            "action": action,
            "hour": hour,
            "minute": minute,
            "second": second,
        }

        def _remove():
            self._registrations.remove(record)

        record["remove"] = _remove
        self._registrations.append(record)
        return _remove

    @property
    def registrations(self):
        """Return a copy of the live registrations."""
        return list(self._registrations)

    @property
    def size(self) -> int:
        """Number of live registrations."""
        return len(self._registrations)

    async def fire(self, now=None, index: int = -1):
        """Run a registered action as HA's scheduler would, awaiting coroutines."""
        result = self._registrations[index]["action"](now)
        if inspect.isawaitable(result):
            await result


def _async_track_time_change(hass, action, hour=None, minute=None, second=None):
    """Mirror homeassistant.helpers.event.async_track_time_change.

    Exact HA 2024.6 signature — no ``local`` keyword: the local-time
    wrapper is already this function.  Routes to the registry attached to
    ``hass`` (created on demand), so tests reach the registrations via
    ``hass.time_change``.
    """
    registry = getattr(hass, "time_change", None)
    if registry is None:
        registry = TimeChangeRegistry(hass)
        hass.time_change = registry
    return registry.track(action, hour=hour, minute=minute, second=second)


_ha_mock("homeassistant.helpers.event").async_track_time_change = _async_track_time_change


class HttpRegistry:
    """Models HA's ``hass.http`` static-path registration."""

    def __init__(self):
        self.static_paths: list[StaticPathConfig] = []

    async def async_register_static_paths(self, configs):
        self.static_paths.extend(list(configs))


class EventBus:
    """Models HA's ``hass.bus`` event bus.

    ``async_fire`` is SYNCHRONOUS (matching real HA) and records
    ``(event_type, payload)`` pairs in order so tests can assert
    exactly which events fired with which payloads; there is no
    listener dispatch (entities poll the coordinator, and the cards
    are not part of this harness).
    """

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, payload=None):
        self.events.append((event_type, dict(payload or {})))

    def fired(self, event_type: str) -> list[dict]:
        """Return every payload fired for ``event_type``, in order."""
        return [
            payload
            for fired_type, payload in self.events
            if fired_type == event_type
        ]


class ServiceRegistry:
    """Models HA's ``hass.services`` service registry.

    ``async_register`` stores a handler under its (domain, service) key,
    ``has_service`` reports registration, and ``async_remove`` removes it
    — exactly the surface Home Assistant's ``ServiceRegistry`` exposes
    (there is deliberately NO ``async_unregister`` alias here, so a caller
    that uses the wrong method name fails instead of being silently
    papered over).  ``call`` invokes a stored handler the way HA's service
    bus would — awaiting a coroutine result — so tests can exercise a
    registered service end-to-end.
    """

    def __init__(self, hass=None):
        self._hass = hass
        self._services: dict[tuple[str, str], object] = {}

    def async_register(self, domain, service, func, schema=None, supports_response=None):
        self._services[(domain, service)] = (func, schema)
        return None

    def has_service(self, domain, service):
        return (domain, service) in self._services

    def async_remove(self, domain, service):
        self._services.pop((domain, service), None)
        return None

    async def call(self, domain, service, data=None, context=None):
        registered = self._services.get((domain, service))
        if registered is None:
            raise KeyError(f"service {domain}.{service} not registered")
        func, schema = registered
        payload = dict(data or {})
        if schema is not None:
            payload = schema(payload)
        if context is None:
            context_obj = SimpleNamespace(user_id=None)
        elif isinstance(context, dict):
            context_obj = SimpleNamespace(**context)
        else:
            context_obj = context
        call = SimpleNamespace(
            domain=domain,
            service=service,
            data=payload,
            context=context_obj,
        )
        result = func(call)
        if inspect.isawaitable(result):
            await result
        return result

    @property
    def registered_services(self):
        """The registered (domain, service) pairs."""
        return list(self._services)


def make_config_entry(
    entry_id: str = "test_entry",
    options: dict | None = None,
    data: dict | None = None,
    context: dict | None = None,
):
    """Create a stub config entry shaped like HA's ConfigEntry for tests.

    ``context`` mirrors HA's entry context (the flow that created the
    entry carries the acting HA user under ``context["user_id"]``).
    """
    entry = SimpleNamespace(
        entry_id=entry_id,
        options=dict(options or {}),
        data=dict(data or {}),
        context=dict(context or {}),
    )
    entry.add_update_listener = None
    return entry


def wire_entry_to_registry(entry, registry: ListenerRegistry):
    """Attach an update-listener registration function to the entry."""
    entry.add_update_listener = lambda listener: registry.add(entry.entry_id, listener)
    return entry


class StubSnapshotClient:
    """A no-network stand-in for the API client's snapshot surface.

    Answers ``get_snapshot()`` from a scripted queue of outcomes — a
    payload dict or an exception per call, consumed in order — and
    records every call.  When the queue is exhausted it re-serves the
    last outcome, so setup's first refresh and a test's explicit
    refreshes poll the same scripted state.  Register it (or any
    scripted client) with :func:`set_coordinator_client` BEFORE setup.
    """

    def __init__(self, *outcomes) -> None:
        self.calls = 0
        self._outcomes = list(outcomes)
        self._last = outcomes[-1] if outcomes else None
        #: The SSE frames the stand-in "published" (the API service's
        # stream content), drained by :func:`refire_api_transitions`.
        self.published_frames = []

    async def get_snapshot(self):
        self.calls += 1
        if not self._outcomes:
            # Re-serve the last outcome: setup's first refresh and the
            # test's explicit pass both poll the same scripted state.
            outcome = self._last
        else:
            outcome = self._outcomes.pop(0)
            self._last = outcome
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedPanelClient(StubSnapshotClient):
    """Snapshot + completion stand-in for the API service's panel plane.

    Serves the scripted snapshot outcomes (like
    :class:`StubSnapshotClient`), records ``complete_instance`` calls
    the way the panel route receives them, optionally fails them the
    way the client types the failure, and carries the SSE frames the
    API "published" in ``published_frames`` for
    :func:`refire_api_transitions` to deliver.  Everything the
    integration reads over the wire, no network.
    """

    def __init__(self, *outcomes) -> None:
        super().__init__(*outcomes)
        self.complete_calls: list[tuple[int, int]] = []
        self.published_frames: list[tuple[str, dict]] = []
        #: When set, the next ``complete_instance`` raises this instead
        # of succeeding (a typed NestQuestApiError in production).
        self.fail_complete_with: BaseException | None = None

    async def complete_instance(
        self, instance_id: int, actor_child_id: int
    ) -> dict:
        self.complete_calls.append((instance_id, actor_child_id))
        if self.fail_complete_with is not None:
            raise self.fail_complete_with
        return {"status": "done"}


def set_coordinator_client(entry, client):
    """Register a scripted client for ``entry``'s coordinator factory."""
    import custom_components.nestquest.coordinator as coordinator_module

    coordinator_module._COORDINATOR_CLIENT_OVERRIDES[entry.entry_id] = client
    return client


@pytest.fixture(autouse=True)
def coordinator_client_from_test_override():
    """Resolve every entry's coordinator client through the test seam.

    The integration's setup builds its API client through
    ``coordinator_client_from_entry``; this fixture swaps that factory
    for a test one handing out the client registered with
    :func:`set_coordinator_client`, or — for an entry with no scripted
    client — a stub serving an EMPTY but valid household snapshot (the
    shape the API's panel route returns before any child exists; the
    real client would need aiohttp, which this mock-only harness does
    not provide).
    """
    import datetime
    import unittest.mock as mock

    import custom_components.nestquest as nq_mod
    import custom_components.nestquest.coordinator as coordinator_module

    _COORDINATOR_CLIENT_OVERRIDES = (
        coordinator_module._COORDINATOR_CLIENT_OVERRIDES
    )

    def _factory(hass, entry, **kwargs):
        override = _COORDINATOR_CLIENT_OVERRIDES.get(entry.entry_id)
        if override is not None:
            return override
        return StubSnapshotClient(
            {
                "today_iso": datetime.date.today().isoformat(),
                "cycle_day": 0,
                "children": [],
            }
        )

    _COORDINATOR_CLIENT_OVERRIDES.clear()
    patcher = mock.patch.object(
        nq_mod, "coordinator_client_from_entry", _factory
    )
    patcher.start()
    yield
    patcher.stop()
    _COORDINATOR_CLIENT_OVERRIDES.clear()


async def refire_api_transitions(hass, entry, client):
    """Deliver the SSE frames the stand-in client has published so far
    through the integration's SSE subscription — the production event
    path.

    Since Feature 18 the ``complete_quest`` service fires no local
    bus event: the API service builds and publishes the transition
    frames on its SSE stream, and the integration's subscription
    (:mod:`custom_components.nestquest.sse`) re-fires each frame on
    the bus.  This helper streams the frames the stand-in client
    published (``client.published_frames``) through a real
    :class:`~custom_components.nestquest.sse.NestQuestEventStream`
    and waits (bounded) until the bus has re-fired every one of them.
    """
    import asyncio

    from custom_components.nestquest.sse import NestQuestEventStream

    frames, client.published_frames = client.published_frames, []

    class _ScriptedStream:
        """A healthy stream: the frames, then it stays open."""

        def __init__(self, frames) -> None:
            self._frames = frames

        def stream_events(self):
            async def _gen():
                for frame in self._frames:
                    yield frame
                await asyncio.Event().wait()

            return _gen()

    before = {etype: len(hass.bus.fired(etype)) for etype, _ in frames}
    expected = len(frames)
    manager = NestQuestEventStream(hass, _ScriptedStream(frames))
    manager.start()
    try:
        async with asyncio.timeout(2):
            while True:
                delivered = sum(
                    len(hass.bus.fired(etype)) - before[etype]
                    for etype, _ in frames
                )
                if delivered >= expected:
                    break
                await asyncio.sleep(0.01)
    finally:
        await manager.stop()
    return frames


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
    # hass.auth mirrors the real surface the integration reads: an
    # async_get_users list the tests can repoint at will (the setup
    # path resolves HA owner accounts as the last-resort admin seed).
    hass.auth = SimpleNamespace(async_get_users=AsyncMock(return_value=[]))

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
    hass.time_change = TimeChangeRegistry(hass)
    hass.services = ServiceRegistry(hass)
    hass.bus = EventBus()
    hass.http = HttpRegistry()
    hass.extra_js_urls: list[str] = []
    # A valid IANA time zone (the day-rollover listener reads it to
    # compute "today" in HA local time).
    hass.config.time_zone = "UTC"

    # The minimal entity registry: entities self-register through
    # Entity.async_write_ha_state keyed by unique_id, storing the live
    # object; tests enumerate created entities and read their state
    # directly.  entities_by_entry mirrors HA's per-entry platform
    # scoping: unloading an entry's platforms removes exactly that
    # entry's entities.
    hass.entities: dict[str, Entity] = {}
    hass.entities_by_entry: dict[str, dict[str, Entity]] = {}

    def _make_add_entities(entry):
        entry_entities = hass.entities_by_entry.setdefault(entry.entry_id, {})

        def _async_add_entities(new_entities, update_before_add=False):
            """Mirror HA's AddEntitiesCallback: bind hass and register.

            Accepts a single entity or an iterable, mirroring HA's
            permissive call shape; registration goes through each
            entity's async_write_ha_state (the mock state write) and
            is recorded per entry so an unload removes exactly this
            entry's entities.
            """
            if isinstance(new_entities, Entity):
                new_entities = [new_entities]
            for entity in new_entities:
                entity.hass = hass
                entity.async_write_ha_state()
                if entity.unique_id is not None:
                    entry_entities[entity.unique_id] = entity

        return _async_add_entities

    async def _async_forward_entry_setups(entry, platforms):
        """Mirror hass.config_entries.async_forward_entry_setups.

        HA's contract, loosely: import each platform module of the
        entry's integration and drive its ``async_setup_entry`` with a
        per-entry AddEntitiesCallback.  A stub entry without a domain
        defaults to this harness's single integration (NestQuest).
        """
        for platform in list(platforms):
            domain = getattr(entry, "domain", "nestquest")
            module = importlib.import_module(
                f"custom_components.{domain}.{platform}"
            )
            await module.async_setup_entry(
                hass, entry, _make_add_entities(entry)
            )
            hass.config_entries.forwarded_platforms.append(platform)

    async def _async_unload_platforms(entry, platforms):
        """Mirror hass.config_entries.async_unload_platforms.

        Runs each platform module's ``async_unload_entry`` when it
        defines one (per-platform unload is optional, like HA's), then
        removes the entry's entities — unloading an entry's platforms
        removes exactly that entry's entities, never another entry's.
        """
        for platform in list(platforms):
            domain = getattr(entry, "domain", "nestquest")
            module = importlib.import_module(
                f"custom_components.{domain}.{platform}"
            )
            unload = getattr(module, "async_unload_entry", None)
            if unload is not None:
                await unload(hass, entry)
            hass.config_entries.unloaded_platforms.append(platform)
        for unique_id in hass.entities_by_entry.pop(entry.entry_id, {}):
            hass.entities.pop(unique_id, None)

    hass.config_entries.forwarded_platforms: list[str] = []
    hass.config_entries.unloaded_platforms: list[str] = []
    hass.config_entries.async_forward_entry_setups = _async_forward_entry_setups
    hass.config_entries.async_unload_platforms = _async_unload_platforms

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


def executor_for(hass):
    """Return a dynamic executor callable backed by ``hass.async_add_executor_job``.

    The wrapper resolves ``hass.async_add_executor_job`` on every call, so a
    test that swaps it after constructing the database (to gate or fail
    specific jobs) is observed without rebuilding the wrapper — mirroring
    the pre-extraction db.py, which read the attribute dynamically off
    ``hass``.  Use this for cancellation/gating tests that reassign
    ``hass.async_add_executor_job``; plain call sites can pass
    ``hass.async_add_executor_job`` directly.
    """

    async def _executor(fn, *args, **kwargs):
        return await hass.async_add_executor_job(fn, *args, **kwargs)

    return _executor


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

    def _factory(
        entry_id: str = "test_entry",
        options: dict | None = None,
        data: dict | None = None,
        context: dict | None = None,
    ):
        return make_config_entry(
            entry_id=entry_id, options=options, data=data, context=context
        )

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


# ---------------------------------------------------------------------------
# Admin-plane API fixtures (shared by the admin-plane test modules).
#
# The local-key/stubbed-JWKS harness itself lives in
# :mod:`tests.admin_jwt_harness` (imported by name, the same pattern as
# tests.blueprint_helpers); these fixtures hand its runner to every test
# module in tests/ without re-declaring it.
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def admin_client(temp_db_path: str) -> httpx.AsyncClient:
    """An app client whose provider publishes the admin test key."""
    async with AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID)) as client:
        yield client