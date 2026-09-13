"""Tests verifying HACS repository metadata, documentation, and licensing."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
HACS_JSON_PATH = REPO_ROOT / "hacs.json"
LICENSE_PATH = REPO_ROOT / "LICENSE"
README_PATH = REPO_ROOT / "README.md"
MANIFEST_PATH = REPO_ROOT / "custom_components" / "nestquest" / "manifest.json"


@pytest.fixture
def hacs_config() -> dict:
    """Load and parse hacs.json."""
    assert HACS_JSON_PATH.exists(), f"hacs.json does not exist at {HACS_JSON_PATH}"
    with open(HACS_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data


def test_hacs_json_exists_and_is_valid(hacs_config: dict) -> None:
    """Verify hacs.json exists and is valid JSON."""
    assert isinstance(hacs_config, dict)
    assert hacs_config.get("name") == "NestQuest"
    assert hacs_config.get("homeassistant") == "2024.1.0"
    assert hacs_config.get("render_readme") is True


def test_license_exists_and_non_empty() -> None:
    """Verify LICENSE file exists and is non-empty."""
    assert LICENSE_PATH.exists(), f"LICENSE file does not exist at {LICENSE_PATH}"
    content = LICENSE_PATH.read_text(encoding="utf-8").strip()
    assert len(content) > 0
    assert "MIT License" in content
    assert "NestQuest Contributors / Maniacs Mansion" in content


def test_readme_exists_and_contains_required_sections() -> None:
    """Verify README.md exists and documents HACS installation, manual installation, and test commands."""
    assert README_PATH.exists(), f"README.md does not exist at {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")
    assert len(content.strip()) > 0

    # Title and overview
    assert "NestQuest - House Chaos Coordination" in content
    assert "Home Assistant custom integration" in content

    # Installation methods
    assert "HACS" in content
    assert "Manual Installation" in content or "manual installation" in content.lower()
    assert "custom_components/nestquest" in content

    # Developer Setup and Testing commands
    assert "uv sync" in content
    assert "uv run pytest" in content


def test_hacs_directory_structure() -> None:
    """Verify directory structure matches HACS integration expectations."""
    assert MANIFEST_PATH.exists(), f"Integration manifest does not exist at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("domain") == "nestquest"
