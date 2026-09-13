"""Tests for the config flow of NestQuest."""
from __future__ import annotations

import ast
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


class _ConfigFlowBase:
    """Minimal stand-in for homeassistant ConfigFlow."""

    VERSION = 1

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, *, step_id, **kwargs):
        return {"type": "form", "step_id": step_id}

    def async_abort(self, *, reason, **kwargs):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, *, title, data, **kwargs):
        return {"type": "create_entry", "title": title, "data": data}


sys.modules["homeassistant.config_entries"].ConfigFlow = _ConfigFlowBase

import pytest

from custom_components.nestquest import config_flow
from custom_components.nestquest.const import DOMAIN

PKG_DIR = Path(config_flow.__file__).parent
STRINGS_PATH = PKG_DIR / "strings.json"
TRANSLATIONS_EN_PATH = PKG_DIR / "translations" / "en.json"


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def _make_flow(existing_entries: list | None = None):
    """Create a config flow instance with a stubbed hass."""
    flow = config_flow.NestQuestConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda _domain: existing_entries or []
        )
    )
    return flow


def _make_entry(domain: str):
    """Create a stub config entry with the given domain."""
    return SimpleNamespace(domain=domain)


def test_flow_shows_form_initially() -> None:
    """The initial user step shows a form."""
    flow = _make_flow()
    result = _run(flow.async_step_user(None))
    assert result["type"] == "form"
    assert result["step_id"] == "user"


def test_flow_creates_entry_on_submit() -> None:
    """Submitting the user step creates a config entry."""
    flow = _make_flow()
    result = _run(flow.async_step_user({}))
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert result["data"] == {}


def test_second_flow_aborts_single_instance() -> None:
    """A second flow aborts with single_instance_allowed."""
    flow = _make_flow([_make_entry(DOMAIN)])
    result = _run(flow.async_step_user(None))
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


def test_flow_ignores_other_domain_entries() -> None:
    """Entries of other domains do not trigger the abort."""
    flow = _make_flow([_make_entry("other_domain")])
    result = _run(flow.async_step_user(None))
    assert result["type"] == "form"
    assert result["step_id"] == "user"


def test_setup_entry_records_entry_in_hass_data() -> None:
    """async_setup_entry stores the entry under hass.data[DOMAIN]."""
    from custom_components.nestquest import async_setup_entry, async_unload_entry

    hass = MagicMock()
    hass.data = {}
    entry = SimpleNamespace(entry_id="abc123")

    _run(async_setup_entry(hass, entry))
    assert hass.data[DOMAIN][entry.entry_id] is entry

    _run(async_unload_entry(hass, entry))
    assert entry.entry_id not in hass.data[DOMAIN]


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


@pytest.mark.parametrize("fixture_name", ["strings", "translations_en"])
def test_flow_strings_valid_json(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """strings.json and translations/en.json are valid JSON objects."""
    content = request.getfixturevalue(fixture_name)
    assert isinstance(content, dict)


@pytest.mark.parametrize("fixture_name", ["strings", "translations_en"])
def test_flow_strings_structure(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """Config flow strings contain title, user step, and abort reasons."""
    content = request.getfixturevalue(fixture_name)
    assert content.get("title")
    config = content.get("config", {})
    assert config.get("step", {}).get("user", {}).get("title")
    assert config.get("step", {}).get("user", {}).get("description")
    abort = config.get("abort", {})
    assert "single_instance_allowed" in abort
    assert abort["single_instance_allowed"]


@pytest.mark.parametrize("fixture_name", ["strings", "translations_en"])
def test_flow_strings_no_raw_keys(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """No placeholder/raw keys appear in the flow strings."""
    content = request.getfixturevalue(fixture_name)

    def check(value) -> None:
        if isinstance(value, dict):
            for key, val in value.items():
                assert val, f"Empty string value for key '{key}'"
                check(val)
        elif isinstance(value, str):
            assert value.strip() != ""

    check(content)


def test_flow_strings_match_translations(
    strings: dict, translations_en: dict
) -> None:
    """strings.json and translations/en.json carry identical flow strings."""
    assert strings == translations_en


def test_no_hardcoded_domain_or_db_filename_in_new_modules() -> None:
    """Ensure no module other than const.py hardcodes the domain or db filename."""
    pkg_dir = Path(config_flow.__file__).parent
    py_files = [f for f in pkg_dir.glob("*.py") if f.name not in ("const.py",)]

    assert len(py_files) > 0, "No python modules found in package to check"

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == "nestquest":
                    raise AssertionError(
                        f"Found hard-coded domain string in {py_file.name}:{node.lineno}"
                    )
                assert node.value != "nestquest.db", (
                    f"Found hard-coded database filename in {py_file.name}:{node.lineno}"
                )