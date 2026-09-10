"""Tests for the manifest.json file of NestQuest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).parent.parent / "custom_components" / "nestquest" / "manifest.json"


@pytest.fixture
def manifest() -> dict:
    """Load and parse manifest.json."""
    assert MANIFEST_PATH.exists(), f"manifest.json does not exist at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data


def test_manifest_is_valid_json(manifest: dict) -> None:
    """Verify manifest.json is valid JSON and parsed into a dictionary."""
    assert isinstance(manifest, dict)


def test_manifest_domain(manifest: dict) -> None:
    """Verify domain is nestquest."""
    assert manifest.get("domain") == "nestquest"


def test_manifest_config_flow(manifest: dict) -> None:
    """Verify config_flow is True."""
    assert manifest.get("config_flow") is True


def test_manifest_iot_class(manifest: dict) -> None:
    """Verify iot_class is local_polling."""
    assert manifest.get("iot_class") == "local_polling"


def test_manifest_requirements(manifest: dict) -> None:
    """Verify requirements is an empty list."""
    assert manifest.get("requirements") == []


@pytest.mark.parametrize(
    "key",
    ["name", "version", "documentation", "issue_tracker", "codeowners"],
)
def test_manifest_required_keys_exist_and_non_empty(manifest: dict, key: str) -> None:
    """Verify required keys exist and are non-empty."""
    assert key in manifest, f"Key '{key}' missing from manifest.json"
    val = manifest[key]
    assert val is not None, f"Key '{key}' is None"
    assert len(val) > 0, f"Key '{key}' is empty"
