"""Tests for the NestQuest services.yaml declaration file."""
from __future__ import annotations

import re
from pathlib import Path

SERVICES_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "nestquest"
    / "services.yaml"
)


def test_services_yaml_exists() -> None:
    assert SERVICES_PATH.exists(), f"services.yaml missing at {SERVICES_PATH}"


def test_services_yaml_declares_regenerate() -> None:
    text = SERVICES_PATH.read_text(encoding="utf-8")
    assert re.search(r"^regenerate:\s*$", text, re.MULTILINE), (
        "services.yaml must declare the 'regenerate' service"
    )


def test_services_yaml_regenerate_has_description_and_no_fields() -> None:
    """The regenerate service is documented with a clear description and no
    required fields (there is no ``fields`` block under it)."""
    text = SERVICES_PATH.read_text(encoding="utf-8")
    match = re.search(r"^regenerate:\s*$", text, re.MULTILINE)
    assert match is not None
    section = text[match.end():]
    next_service = re.search(r"^(?![#\s])\w+:\s*$", section, re.MULTILINE)
    if next_service is not None:
        section = section[: next_service.start()]
    assert re.search(r"description:", section), (
        "regenerate must carry a description"
    )
    assert "fields:" not in section, (
        "regenerate declares no required fields"
    )