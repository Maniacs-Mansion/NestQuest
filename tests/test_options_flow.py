"""Tests for the options flow of NestQuest."""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_config_entry, make_hass, options_flow_base as _options_flow_base

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


def _make_hass():
    return make_hass()


def _make_entry(entry_id: str = "test_entry", options: dict | None = None, data: dict | None = None):
    return make_config_entry(entry_id=entry_id, options=options, data=data)


def _make_flow(entry) -> options_flow.NestQuestOptionsFlow:
    """Create an options flow instance bound to a stubbed config entry."""
    flow = options_flow.NestQuestOptionsFlow(config_entry=entry)
    flow.hass = SimpleNamespace()
    return flow


def _schema_values(schema) -> dict:
    """Extract the per-field default values from a real voluptuous schema."""
    return {
        marker.schema: marker.default()
        for marker in schema.schema
        if hasattr(marker, "schema")
    }


def test_options_flow_reachable_via_configure_button() -> None:
    """The config flow exposes async_get_options_flow returning the options flow."""
    entry = _make_entry()
    handler = config_flow.NestQuestConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, options_flow.NestQuestOptionsFlow)
    assert handler.config_entry is entry


def test_options_flow_get_options_flow_is_ha_callback() -> None:
    """async_get_options_flow is wrapped by the homeassistant.core.callback decorator."""
    assert getattr(
        config_flow.NestQuestConfigFlow.async_get_options_flow, "__ha_callback__", False
    ) is True


def test_options_flow_constructs_through_2024_6_surface() -> None:
    """The handler constructs against the mocked 2024.6 base and inherits its contract."""
    entry = _make_entry(options={CONF_HORIZON_DAYS: 21})
    flow = options_flow.NestQuestOptionsFlow(config_entry=entry)
    assert isinstance(flow, _options_flow_base())
    assert flow.config_entry is entry
    assert flow.options == {CONF_HORIZON_DAYS: 21}


def test_options_flow_submits_through_2024_6_surface() -> None:
    """The handler can be submitted through the mocked 2024.6-shaped surface."""
    entry = _make_entry()
    handler = config_flow.NestQuestConfigFlow.async_get_options_flow(entry)
    result = _run(handler.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert result["data"] == VALID_INPUT


def test_options_flow_shows_form_initially() -> None:
    """The init step shows a form."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    assert result["type"] == "form"
    assert result["step_id"] == "init"


def test_options_flow_schema_is_voluptuous() -> None:
    """The form's data_schema is a real voluptuous Schema (no dict fallback)."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    import voluptuous as vol

    assert isinstance(result["data_schema"], vol.Schema)


def test_options_flow_prefills_from_defaults() -> None:
    """Without stored options, the form pre-fills with the constant defaults."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    values = _schema_values(result["data_schema"])
    assert values[CONF_HORIZON_DAYS] == DEFAULT_HORIZON_DAYS
    assert values[CONF_DAY_ROLLOVER_TIME] == DEFAULT_DAY_ROLLOVER_TIME
    assert values[CONF_PANEL_IDLE_TIMEOUT] == DEFAULT_PANEL_IDLE_TIMEOUT


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
    values = _schema_values(result["data_schema"])
    assert values[CONF_HORIZON_DAYS] == 21
    assert values[CONF_DAY_ROLLOVER_TIME] == "05:45"
    assert values[CONF_PANEL_IDLE_TIMEOUT] == 120


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
    values = _schema_values(result["data_schema"])
    assert values[CONF_HORIZON_DAYS] == 10
    assert values[CONF_DAY_ROLLOVER_TIME] == "01:15"
    assert values[CONF_PANEL_IDLE_TIMEOUT] == 90


def test_options_flow_schema_applies_stored_defaults() -> None:
    """A real voluptuous validate({}) fills every field from the stored defaults."""
    entry = _make_entry(
        options={
            CONF_HORIZON_DAYS: 21,
            CONF_DAY_ROLLOVER_TIME: "05:45",
            CONF_PANEL_IDLE_TIMEOUT: 120,
        }
    )
    result = _run(_make_flow(entry).async_step_init(None))
    assert result["data_schema"]({}) == {
        CONF_HORIZON_DAYS: 21,
        CONF_DAY_ROLLOVER_TIME: "05:45",
        CONF_PANEL_IDLE_TIMEOUT: 120,
    }


def test_options_flow_schema_coerces_field_types() -> None:
    """The schema validates the expected field types via voluptuous."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    schema = result["data_schema"]
    validators = {marker.schema: validator for marker, validator in schema.schema.items()}
    assert validators[CONF_HORIZON_DAYS] is int
    assert validators[CONF_DAY_ROLLOVER_TIME] is str
    assert validators[CONF_PANEL_IDLE_TIMEOUT] is int


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


def test_options_flow_rejects_pasted_unicode_superscript_time() -> None:
    """Pasted Unicode digits like '²²:²²' yield a field-level error, no exception."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_DAY_ROLLOVER_TIME: "²²:²²"})
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


def test_options_flow_no_plain_dict_schema_fallback() -> None:
    """No try/except ImportError fallback for voluptuous in the options flow module."""
    py_file = Path(options_flow.__file__)
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handlers = node.handlers or []
            has_import_error_handler = any(
                getattr(handler.type, "id", getattr(handler.type, "attr", None))
                == "ImportError"
                for handler in handlers
            )
            assert not has_import_error_handler, (
                f"Plain-dict schema fallback (try/except ImportError) found in {py_file.name}:{node.lineno}"
            )


def test_options_flow_subclasses_options_flow_with_config_entry() -> None:
    """NestQuestOptionsFlow subclasses config_entries.OptionsFlowWithConfigEntry."""
    base = _options_flow_base()
    assert issubclass(options_flow.NestQuestOptionsFlow, base)
    assert options_flow.NestQuestOptionsFlow.__bases__ == (base,)


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