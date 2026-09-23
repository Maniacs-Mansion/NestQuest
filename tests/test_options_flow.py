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
    CONF_API_BASE_URL,
    CONF_PANEL_IDLE_TIMEOUT,
    CONF_PANEL_TOKEN,
    CONF_SNAPSHOT_STALENESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_BASE_URL,
    DEFAULT_PANEL_IDLE_TIMEOUT,
    DEFAULT_PANEL_TOKEN,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

PKG_DIR = Path(options_flow.__file__).parent
STRINGS_PATH = PKG_DIR / "strings.json"
TRANSLATIONS_EN_PATH = PKG_DIR / "translations" / "en.json"

VALID_INPUT = {
    CONF_PANEL_IDLE_TIMEOUT: 60,
}

#: What a schema-validated submit produces from a bare VALID_INPUT on a
#: fresh entry: the Feature 10 refresh interval, the Feature 18
#: staleness threshold, and the Feature 18 API connection fill from
#: their defaults.
FULL_INPUT = {
    **VALID_INPUT,
    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
    CONF_SNAPSHOT_STALENESS: DEFAULT_SNAPSHOT_STALENESS,
    CONF_API_BASE_URL: DEFAULT_API_BASE_URL,
    CONF_PANEL_TOKEN: DEFAULT_PANEL_TOKEN,
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
    entry = _make_entry(options={CONF_UPDATE_INTERVAL: 90})
    flow = options_flow.NestQuestOptionsFlow(config_entry=entry)
    assert isinstance(flow, _options_flow_base())
    assert flow.config_entry is entry
    assert flow.options == {CONF_UPDATE_INTERVAL: 90}


def test_options_flow_submits_through_2024_6_surface() -> None:
    """The handler can be submitted through the mocked 2024.6-shaped surface."""
    entry = _make_entry()
    handler = config_flow.NestQuestConfigFlow.async_get_options_flow(entry)
    result = _run(handler.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert result["data"] == FULL_INPUT


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
    assert values[CONF_PANEL_IDLE_TIMEOUT] == DEFAULT_PANEL_IDLE_TIMEOUT
    assert values[CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL
    assert values[CONF_SNAPSHOT_STALENESS] == DEFAULT_SNAPSHOT_STALENESS


def test_options_flow_prefills_from_entry_options() -> None:
    """Stored entry options win over entry data and defaults."""
    entry = _make_entry(
        options={
            CONF_PANEL_IDLE_TIMEOUT: 120,
            CONF_UPDATE_INTERVAL: 90,
            CONF_SNAPSHOT_STALENESS: 450,
        },
        data={
            CONF_PANEL_IDLE_TIMEOUT: 999,
            CONF_UPDATE_INTERVAL: 999,
            CONF_SNAPSHOT_STALENESS: 999,
        },
    )
    result = _run(_make_flow(entry).async_step_init(None))
    values = _schema_values(result["data_schema"])
    assert values[CONF_PANEL_IDLE_TIMEOUT] == 120
    assert values[CONF_UPDATE_INTERVAL] == 90
    assert values[CONF_SNAPSHOT_STALENESS] == 450


def test_options_flow_falls_back_to_entry_data() -> None:
    """Pre-upgrade entries without options fall back to entry.data."""
    entry = _make_entry(
        data={
            CONF_PANEL_IDLE_TIMEOUT: 90,
            CONF_UPDATE_INTERVAL: 60,
            CONF_SNAPSHOT_STALENESS: 240,
        }
    )
    result = _run(_make_flow(entry).async_step_init(None))
    values = _schema_values(result["data_schema"])
    assert values[CONF_PANEL_IDLE_TIMEOUT] == 90
    assert values[CONF_UPDATE_INTERVAL] == 60
    assert values[CONF_SNAPSHOT_STALENESS] == 240


def test_options_flow_schema_applies_stored_defaults() -> None:
    """A real voluptuous validate({}) fills every field from the stored defaults."""
    entry = _make_entry(
        options={
            CONF_PANEL_IDLE_TIMEOUT: 120,
            CONF_UPDATE_INTERVAL: 90,
            CONF_SNAPSHOT_STALENESS: 450,
            CONF_API_BASE_URL: "http://panel.lan:8443",
            CONF_PANEL_TOKEN: "stored-token",
        }
    )
    result = _run(_make_flow(entry).async_step_init(None))
    assert result["data_schema"]({}) == {
        CONF_PANEL_IDLE_TIMEOUT: 120,
        CONF_UPDATE_INTERVAL: 90,
        CONF_SNAPSHOT_STALENESS: 450,
        CONF_API_BASE_URL: "http://panel.lan:8443",
        CONF_PANEL_TOKEN: "stored-token",
    }


def test_options_flow_schema_coerces_field_types() -> None:
    """The schema validates the expected field types via voluptuous."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(None))
    schema = result["data_schema"]
    validators = {marker.schema: validator for marker, validator in schema.schema.items()}
    assert validators[CONF_PANEL_IDLE_TIMEOUT] is int
    assert validators[CONF_UPDATE_INTERVAL] is int
    assert validators[CONF_SNAPSHOT_STALENESS] is int
    # The Feature 18 API connection fields are free-text strings.
    assert validators[CONF_API_BASE_URL] is str
    assert validators[CONF_PANEL_TOKEN] is str


@pytest.mark.parametrize("bad_timeout", ["abc", 0, -10, 10])
def test_options_flow_rejects_invalid_idle_timeout(bad_timeout) -> None:
    """Non-numeric or too-low idle timeouts yield a field-level error."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_PANEL_IDLE_TIMEOUT: bad_timeout})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_PANEL_IDLE_TIMEOUT: "invalid"}


@pytest.mark.parametrize("bad_interval", ["abc", True, 0, -10, 29])
def test_options_flow_rejects_invalid_update_interval(bad_interval) -> None:
    """Non-numeric, boolean, and below-floor update intervals reject."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_UPDATE_INTERVAL: bad_interval})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_UPDATE_INTERVAL: "invalid"}


def test_options_flow_creates_entry_with_validated_keys() -> None:
    """A valid submit creates an entry with exactly the validated keys
    (the client-facing settings, filled from defaults where the raw
    submit omitted them)."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert set(result["data"]) == set(FULL_INPUT)
    assert result["data"] == FULL_INPUT


def test_options_flow_create_entry_data_lands_in_entry_options_and_reloads_once() -> None:
    """The flow's created data is written to entry.options and reloads exactly once."""
    hass, registry = _make_hass()
    entry = _make_entry()
    entry.add_update_listener = lambda listener: registry.add(entry.entry_id, listener)

    # Simulate setup registering the lifecycle update listener.
    from custom_components.nestquest import async_setup_entry

    _run(async_setup_entry(hass, entry))

    # Run the options flow and apply its created data to entry.options like HA does.
    flow = _make_flow(entry)
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    entry.options = dict(result["data"])

    _run(registry.dispatch_options_update(entry))
    assert hass.config_entries.async_reload.call_count == 1
    assert registry.reloaded == [entry.entry_id]
    assert entry.options == FULL_INPUT


def test_options_flow_validation_never_raises() -> None:
    """Validation returns errors instead of raising for arbitrary junk input."""
    junk = {CONF_PANEL_IDLE_TIMEOUT: None, CONF_UPDATE_INTERVAL: "abc"}
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(junk))
    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_PANEL_IDLE_TIMEOUT: "invalid",
        CONF_UPDATE_INTERVAL: "invalid",
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
    for key in (CONF_PANEL_IDLE_TIMEOUT,):
        assert data.get(key), f"Missing field name for '{key}'"
    errors = options["errors"]
    for key in ("invalid",):
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


# ---------------------------------------------------------------------------
# Panel-plane API connection section (Feature 18)
# ---------------------------------------------------------------------------


def test_options_flow_api_section_defaults_saved() -> None:
    """A bare submit saves the API connection defaults: the const base
    URL and an EMPTY panel token (no token is ever invented)."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_BASE_URL] == DEFAULT_API_BASE_URL
    assert result["data"][CONF_PANEL_TOKEN] == ""


def test_options_flow_api_base_url_must_be_full_http_url() -> None:
    """Scheme-less, host-less, empty, and non-string base URLs reject
    with a field error — the same rule the client's constructor
    enforces, so a malformed URL fails at the form, not at the first
    request."""
    flow = _make_flow(_make_entry())
    for bad_url in ("api.lan:8000", "http://", "", "   ", 42):
        result = _run(
            flow.async_step_init(
                {**VALID_INPUT, CONF_API_BASE_URL: bad_url}
            )
        )
        assert result["type"] == "form"
        assert result["errors"] == {CONF_API_BASE_URL: "invalid_url"}


def test_options_flow_panel_token_validation() -> None:
    """The EMPTY token is valid (the API connection is simply not
    configured yet); padded and non-string values reject — a padded
    paste would fail the token check at request time instead."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_PANEL_TOKEN: ""})
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_PANEL_TOKEN] == ""

    for bad_token in ("  secret  ", "   ", 42):
        flow = _make_flow(_make_entry())
        result = _run(
            flow.async_step_init(
                {**VALID_INPUT, CONF_PANEL_TOKEN: bad_token}
            )
        )
        assert result["type"] == "form"
        assert result["errors"] == {CONF_PANEL_TOKEN: "invalid"}


def test_options_flow_api_section_stored_values_round_trip() -> None:
    """Stored API settings are the form's defaults and a raw legacy
    submit without them keeps the stored values."""
    entry = _make_entry(
        options={
            **VALID_INPUT,
            CONF_API_BASE_URL: "http://panel.lan:8443",
            CONF_PANEL_TOKEN: "stored-token",
        }
    )
    flow = _make_flow(entry)
    form = _run(flow.async_step_init(None))
    schema_defaults = form["data_schema"]({})
    assert schema_defaults[CONF_API_BASE_URL] == "http://panel.lan:8443"
    assert schema_defaults[CONF_PANEL_TOKEN] == "stored-token"

    # A raw submit carrying only the panel-idle key keeps the stored
    # API connection settings.
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_BASE_URL] == "http://panel.lan:8443"
    assert result["data"][CONF_PANEL_TOKEN] == "stored-token"


def test_options_flow_strings_cover_api_section(
    strings: dict, translations_en: dict
) -> None:
    """Both string files name the API fields and the URL error."""
    data = strings["options"]["step"]["init"]["data"]
    for key in (CONF_API_BASE_URL, CONF_PANEL_TOKEN):
        assert data.get(key), f"Missing field name for '{key}'"
    assert strings["options"]["errors"]["invalid_url"]
    assert translations_en["options"] == strings["options"]


# ---------------------------------------------------------------------------
# Last-good snapshot staleness section (Feature 18)
# ---------------------------------------------------------------------------


def test_options_flow_staleness_below_update_interval_refused() -> None:
    """A staleness threshold shorter than the submit's update interval
    is refused with the dedicated error: such a threshold could never
    serve even one cached snapshot."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init(
            {
                **VALID_INPUT,
                CONF_UPDATE_INTERVAL: 300,
                CONF_SNAPSHOT_STALENESS: 60,
            }
        )
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_SNAPSHOT_STALENESS: "invalid_staleness"}


def test_options_flow_staleness_below_stored_interval_refused() -> None:
    """A raw submit setting the staleness but omitting the update
    interval is checked against the STORED interval, not the default."""
    entry = _make_entry(options={CONF_UPDATE_INTERVAL: 300})
    flow = _make_flow(entry)
    result = _run(
        flow.async_step_init({**VALID_INPUT, CONF_SNAPSHOT_STALENESS: 60})
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_SNAPSHOT_STALENESS: "invalid_staleness"}


def test_options_flow_staleness_must_be_positive_int() -> None:
    """Non-int, boolean, and non-positive staleness values reject with
    the plain invalid error."""
    flow = _make_flow(_make_entry())
    for bad_staleness in ("900", True, 0, -10):
        result = _run(
            flow.async_step_init(
                {**VALID_INPUT, CONF_SNAPSHOT_STALENESS: bad_staleness}
            )
        )
        assert result["type"] == "form"
        assert result["errors"] == {CONF_SNAPSHOT_STALENESS: "invalid"}


def test_options_flow_staleness_equal_to_interval_saves() -> None:
    """A threshold exactly as long as the update interval is valid (the
    boundary is inclusive)."""
    flow = _make_flow(_make_entry())
    result = _run(
        flow.async_step_init(
            {
                **VALID_INPUT,
                CONF_UPDATE_INTERVAL: 300,
                CONF_SNAPSHOT_STALENESS: 300,
            }
        )
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SNAPSHOT_STALENESS] == 300


def test_options_flow_staleness_defaults_saved() -> None:
    """A bare submit saves the staleness default (three update
    intervals) alongside the other defaults."""
    flow = _make_flow(_make_entry())
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SNAPSHOT_STALENESS] == DEFAULT_SNAPSHOT_STALENESS


def test_options_flow_staleness_stored_values_round_trip() -> None:
    """A stored staleness is the form's default and a raw legacy submit
    without it keeps the stored value."""
    entry = _make_entry(
        options={
            **VALID_INPUT,
            CONF_UPDATE_INTERVAL: 300,
            CONF_SNAPSHOT_STALENESS: 1200,
        }
    )
    flow = _make_flow(entry)
    form = _run(flow.async_step_init(None))
    schema_defaults = form["data_schema"]({})
    assert schema_defaults[CONF_SNAPSHOT_STALENESS] == 1200

    # A raw submit carrying only the panel-idle key keeps the stored
    # staleness (and never trips the interval cross-check).
    result = _run(flow.async_step_init(dict(VALID_INPUT)))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SNAPSHOT_STALENESS] == 1200


def test_options_flow_strings_cover_staleness_section(
    strings: dict, translations_en: dict
) -> None:
    """Both string files name the staleness field and its error."""
    data = strings["options"]["step"]["init"]["data"]
    assert data.get(CONF_SNAPSHOT_STALENESS), (
        f"Missing field name for '{CONF_SNAPSHOT_STALENESS}'"
    )
    assert strings["options"]["errors"]["invalid_staleness"]
    assert translations_en["options"] == strings["options"]
