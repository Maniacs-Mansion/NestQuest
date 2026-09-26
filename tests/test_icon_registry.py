"""The shared quest-icon registry: one curated source, two identical artefacts.

``tools/icons/curated-icons.json`` is the only hand-edited list; the offline
generator ``tools/icons/generate.mjs`` writes the same module into the admin
PWA and the panel bundle. The admin Vitest suite regenerates and compares
byte-for-byte; these checks need no Node for the core guarantees.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SOURCE = REPO_ROOT / "tools" / "icons" / "curated-icons.json"
GENERATOR = REPO_ROOT / "tools" / "icons" / "generate.mjs"
ARTEFACTS = (
    REPO_ROOT / "admin" / "src" / "icons" / "registry.generated.ts",
    REPO_ROOT / "frontend" / "src" / "icons" / "registry.generated.ts",
)
PANEL_BUNDLE = (
    REPO_ROOT / "custom_components" / "nestquest" / "www" / "nestquest-cards.js"
)


def _curated() -> dict[str, list[dict[str, str]]]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _generated_set(text: str, const: str) -> list[dict]:
    match = re.search(
        rf"export const {const}: readonly GlyphIcon\[\] = (\[.*?\n\]);",
        text,
        re.DOTALL,
    )
    assert match, f"{const} not found in the generated registry"
    return json.loads(match.group(1))


def test_both_artefacts_are_byte_identical() -> None:
    admin, frontend = (path.read_bytes() for path in ARTEFACTS)
    assert admin == frontend


def test_artefacts_carry_exactly_the_curated_names_and_labels() -> None:
    curated = _curated()
    text = ARTEFACTS[0].read_text(encoding="utf-8")
    for namespace, const in (("lucide", "LUCIDE_ICONS"), ("fa", "FA_ICONS")):
        entries = _generated_set(text, const)
        assert [
            {"name": e["name"], "label": e["label"]} for e in entries
        ] == curated[namespace]
        for entry in entries:
            assert entry["kind"] == namespace
            assert entry["key"] == f"{namespace}:{entry['name']}"
            assert re.fullmatch(r"0 0 \d+ \d+", entry["viewBox"])
            assert entry["paths"] and all(entry["paths"])
    assert len(curated["lucide"]) == 36
    assert 15 <= len(curated["fa"]) <= 25


def test_registry_has_no_remote_url_cdn_or_lucide_runtime() -> None:
    for path in (SOURCE, GENERATOR, *ARTEFACTS):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://", text, re.IGNORECASE), path
        assert not re.search(
            r"\bcdn\b|jsdelivr|unpkg|cdnjs|kit\.fontawesome", text, re.IGNORECASE
        ), path
        assert "data-lucide" not in text, path


def test_panel_bundle_embeds_the_registry() -> None:
    bundle = PANEL_BUNDLE.read_text(encoding="utf-8")
    assert "fa:broom" in bundle
    assert "lucide:dog" in bundle
    assert "data-lucide" not in bundle


def test_generator_reproduces_the_committed_artefacts() -> None:
    node = shutil.which("node")
    if node is None or not (REPO_ROOT / "admin" / "node_modules").is_dir():
        pytest.skip("needs node and admin/node_modules (npm ci in admin/)")
    result = subprocess.run(
        [node, str(GENERATOR), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
