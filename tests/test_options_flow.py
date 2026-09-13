"""Tests for the options flow of NestQuest."""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
# Mock homeassistant modules if not installed in environment
for _mod in (
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.data_entry_flow",
):
    sys.modules.setdefault(_mod, MagicMock())

# Wire parent package attributes to the actual module mocks so that
# "from homeassistant import config_entries" resolves to the mocked module.
sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
sys.modules["homeassistant"].data_entry_flow = sys.modules["homeassistant.data_entry_flow"]


class _OptionsFlowBase:
    """Minimal stand-in for homeassistant OptionsFlow."""

    def __init__(self, config_entry=None):
        self.config_entry = config_entry
        self.hass = None
        self.options = dict(config_entry.options) if config_entry is not None else {}

    def async_show_form(self, *, step_id, **kwargs):
        return {"type": "form", "step_id": step_id, **kwargs}

    def async_create_entry(self, *, title, data, **kwargs):
        return {"type": "create_entry", "title": title, "data": data}


class _ConfigFlowBase:
    """Stand-in for homeassistant ConfigFlow; a superset of test_config_flow's base.

    test_config_flow.py may be imported after this file, so the concrete
    NestQuestConfigFlow can end up bound to this base. It must therefore also
    satisfy that file's tests.
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


sys.modules["homeassistant.config_entries"].OptionsFlow = _OptionsFlowBase
sys.modules["homeassistant.config_entries"].ConfigFlow = _ConfigFlowBase

import pytest

from custom_components.nestquest import config_flow
from custom_components.nestquest import options_flow
from custom_components.nestquest.const import (
    CONF_DAY_ROLLOVER_TIME,
    CONF_HORIZON_DAYS,
    CONF_PANEL_IDLE_TIMEOUT,
    DEFAULT_DAY_ROLLOVER_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_PANEL_IDLE_TIMEOUT,
    DOMAIN,
)

PKG_DIR = Path(options_flow.__file__).parent
STRINGS_PATH = PKG_DIR / "strings.json"
TRANSLATIONS_EN_PATH = PKG_DIR / "translations" / "en.json"

VALID_INPUT = {
    CONF_HORIZON_DAYS: 7,
    CONF_DAY_ROLLOVER_TIME: "03:30",
    CONF_PANEL_IDLE_TIMEOUT: 60,
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _ListenerRegistry:
    """Models HA's update-listener bookkeeping with reload tracking."""

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
        config_entries=SimpleNamespace(async_reload=None),
    )
    registry = _ListenerRegistry(hass)

    async def _async_reload(entry_id: str) -> None:
        registry.reloaded.append(entry_id)

    hass.config_entries.async_reload = MagicMock(side_effect=_async_reload)
    return hass, registry


def _make_entry(entry_id: str = "test_entry", options: dict | None = None, data: dict | None = None):
    entry = SimpleNamespace(
        entry_id=entry_id, options=dict(options or {}), data=dict(data or {})
    )
    entry.add_update_listener = None
    return entry


def _make_flow(entry) -> options_flow.NestQuestOptionsFlow:
    """Create an options flow instance bound to a stubbed config entry."""
    flow = options_flow.NestQuestOptionsFlow(config_entry=entry)
    flow.hass = SimpleNamespace()
    return flow


def test_options_flow_reachable_via_configure_button() -> None:
    """The config flow exposes async_get_options_flow returning the options flow."""
    entry = _make_entry()
    handler = config_flow.NestQuestConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, options_flow.NestQuestOptionsFlow)
    assert handler.config_entry is entry


def test_options_flow_shows_form_initially() -> None:
    """The init step shows a form."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    assert result["type"] == "form"
    assert result["step_id"] == "init"


def test_options_flow_prefills_from_defaults() -> None:
    """Without stored options, the form pre-fills with the constant defaults."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    schema = result["data_schema"]
    assert schema[CONF_HORIZON_DAYS] == DEFAULT_HORIZON_DAYS
    assert schema[CONF_DAY_ROLLOVER_TIME] == DEFAULT_DAY_ROLLOVER_TIME
    assert schema[CONF_PANEL_IDLE_TIMEOUT] == DEFAULT_PANEL_IDLE_TIMEOUT


def test_options_flow_prefills_from_entry_options() -> None:
    """Stored entry options win over entry data and defaults."""
    entry = _make_entry(
        options={
            CONF_HORIZON_DAYS: 21,
            CONF_DAY_ROLLOVER_TIME: "05:45",
            CONF_PANEL_IDLE_TIMEOUT: 120,
        },
        data={
            CONF_HORIZON_DAYS: 99,
            CONF_DAY_ROLLOVER_TIME: "23:59",
            CONF_PANEL_IDLE_TIMEOUT: 999,
        },
    )
    result = _run(_make_flow(entry).async_step_init(None))
    schema = result["data_schema"]
    assert schema[CONF_HORIZON_DAYS] == 21
    assert schema[CONF_DAY_ROLLOVER_TIME] == "05:45"
    assert schema[CONF_PANEL_IDLE_TIMEOUT] == 120


def test_options_flow_falls_back_to_entry_data() -> None:
    """Pre-upgrade entries without options fall back to entry.data."""
    entry = _make_entry(
        data={
            CONF_HORIZON_DAYS: 10,
            CONF_DAY_ROLLOVER_TIME: "01:15",
            CONF_PANEL_IDLE_TIMEOUT: 90,
        }
    )
    result = _run(_make_flow(entry).async_step_init(None))
    schema = result["data_schema"]
    assert schema[CONF_HORIZON_DAYS] == 10
    assert schema[CONF_DAY_ROLLOVER_TIME] == "01:15"
    assert schema[CONF_PANEL_IDLE_TIMEOUT] == 90


@pytest.mark.parametrize("bad_horizon", [0, -5])
def test_options_flow_rejects_non_positive_horizon(bad_horizon: int) -> None:
    """Zero or negative horizon values yield a field-level error, no exception."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_HORIZON_DAYS: bad_horizon})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_HORIZON_DAYS: "invalid"}


def test_options_flow_rejects_malformed_time_not_a_time() -> None:
    """Non-HH:MM strings are rejected with invalid_time."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_DAY_ROLLOVER_TIME: "noon"})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_DAY_ROLLOVER_TIME: "invalid_time"}


def test_options_flow_rejects_malformed_time_out_of_range() -> None:
    """Out-of-range HH:MM values are rejected with invalid_time."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_DAY_ROLLOVER_TIME: "25:99"})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_DAY_ROLLOVER_TIME: "invalid_time"}


@pytest.mark.parametrize("bad_timeout", ["abc", 0, -10, 10])
def test_options_flow_rejects_invalid_idle_timeout(bad_timeout) -> None:
    """Non-numeric or too-low idle timeouts yield a field-level error."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_PANEL_IDLE_TIMEOUT: bad_timeout})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_PANEL_IDLE_TIMEOUT: "invalid"}


def test_options_flow_creates_entry_with_three_keys() -> None:
    """A valid submit creates an entry with exactly the three validated keys."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert set(result["data"]) == {
        CONF_HORIZON_DAYS,
        CONF_DAY_ROLLOVER_TIME,
        CONF_PANEL_IDLE_TIMEOUT,
    }
    assert result["data"] == VALID_INPUT


def test_options_flow_create_entry_data_lands_in_entry_options_and_reloads_once() -> None:
    """The flow's created data is written to entry.options and reloads exactly once."""
    hass, registry = _make_hass()
    entry = _make_entry()
    entry.add_update_listener = lambda listener: registry.add(entry.entry_id, listener)

    # Simulate setup registering the merged lifecycle update listener.
    from custom_components.nestquest import async_setup_entry

    _run(async_setup_entry(hass, entry))

    # Run the options flow and apply its created data to entry.options like HA does.
    flow = _make_flow(entry)
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    entry.options = dict(result["data"])

    registry.dispatch_options_update(entry)
    assert hass.config_entries.async_reload.call_count == 1
    assert registry.reloaded == [entry.entry_id]
    assert entry.options == VALID_INPUT


def test_options_flow_validation_never_raises() -> None:
    """Validation returns errors instead of raising for arbitrary junk input."""
    junk = {CONF_HORIZON_DAYS: None, CONF_DAY_ROLLOVER_TIME: None, CONF_PANEL_IDLE_TIMEOUT: None}
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(junk))
    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_HORIZON_DAYS: "invalid",
        CONF_DAY_ROLLOVER_TIME: "invalid_time",
        CONF_PANEL_IDLE_TIMEOUT: "invalid",
    }


@pytest.fixture
def strings() -> dict:
    """Load and parse strings.json."""
    assert STRINGS_PATH.exists(), f"strings.json does not exist at {STRINGS_PATH}"
    with open(STRINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def translations_en() -> dict:
    """Load and parse translations/en.json."""
    assert TRANSLATIONS_EN_PATH.exists(), (
        f"translations/en.json does not exist at {TRANSLATIONS_EN_PATH}"
    )
    with open(TRANSLATIONS_EN_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_options_strings_present_and_matching(strings: dict, translations_en: dict) -> None:
    """Both string files carry identical options step/error strings."""
    assert strings.get("options") == translations_en.get("options")
    options = strings["options"]
    init = options["step"]["init"]
    assert init["title"]
    assert init["description"]
    data = init["data"]
    for key in (CONF_HORIZON_DAYS, CONF_DAY_ROLLOVER_TIME, CONF_PANEL_IDLE_TIMEOUT):
        assert data.get(key), f"Missing field name for '{key}'"
    errors = options["errors"]
    for key in ("invalid", "invalid_time"):
        assert errors.get(key), f"Missing error string for '{key}'"


def test_options_strings_no_raw_keys(strings: dict, translations_en: dict) -> None:
    """No placeholder/raw keys appear in the options strings."""

    def check(value) -> None:
        if isinstance(value, dict):
            for key, val in value.items():
                assert val, f"Empty string value for key '{key}'"
                check(val)
        elif isinstance(value, str):
            assert value.strip() != ""

    check(strings["options"])
    check(translations_en["options"])


def test_options_flow_no_hardcoded_domain_or_db_filename() -> None:
    """The options flow module does not hardcode the domain or db filename."""
    py_file = Path(options_flow.__file__)
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value != DOMAIN, (
                f"Hard-coded domain string in {py_file.name}:{node.lineno}"
            )
            assert node.value != "nestquest.db", (
                f"Hard-coded database filename in {py_file.name}:{node.lineno}"
            )