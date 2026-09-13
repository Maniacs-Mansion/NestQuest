"""Tests for the config flow of NestQuest."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from custom_components.nestquest import config_flow
from custom_components.nestquest.const import DOMAIN

PKG_DIR = Path(config_flow.__file__).parent
STRINGS_PATH = PKG_DIR / "strings.json"
TRANSLATIONS_EN_PATH = PKG_DIR / "translations" / "en.json"


async def test_flow_shows_form_initially(hass, make_flow) -> None:
    """The initial user step shows a form."""
    flow = make_flow(hass)
    result = await flow.async_step_user(None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_flow_creates_entry_on_submit(hass, make_flow) -> None:
    """Submitting the user step creates a config entry."""
    flow = make_flow(hass)
    result = await flow.async_step_user({})
    assert result["type"] == "create_entry"
    assert result["title"] == "NestQuest"
    assert result["data"] == {}


async def test_second_flow_aborts_single_instance(
    hass, make_flow, make_config_flow_entry
) -> None:
    """A second flow aborts with single_instance_allowed."""
    flow = make_flow(hass, existing_entries=[make_config_flow_entry(DOMAIN)])
    result = await flow.async_step_user(None)
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


async def test_flow_aborts_when_in_progress(hass, make_flow) -> None:
    """A concurrent flow in progress aborts with single_instance_allowed."""
    flow = make_flow(hass, in_progress=[{"flow_id": "other"}])
    result = await flow.async_step_user(None)
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


async def test_flow_sets_stable_unique_id(hass, make_flow) -> None:
    """The flow assigns a stable unique id equal to the domain."""
    flow = make_flow(hass)
    assert flow.context.get("unique_id") is None
    await flow.async_step_user(None)
    assert flow.context["unique_id"] == DOMAIN


async def test_flow_ignores_other_domain_entries(hass, make_flow, make_config_flow_entry) -> None:
    """Entries of other domains do not trigger the abort."""
    flow = make_flow(hass, existing_entries=[make_config_flow_entry("other_domain")])
    result = await flow.async_step_user(None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"


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