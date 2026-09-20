"""Tests for the Lovelace card toolchain and auto-registered resource."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup, async_setup_entry
from custom_components.nestquest.frontend import (
    BUNDLE_FILENAME,
    BUNDLE_URL,
    FRONTEND_URL_BASE,
    WWW_DIR,
    async_register_frontend,
)

REPO_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
BUNDLE_PATH = WWW_DIR / BUNDLE_FILENAME
CARD_TYPES = (
    "nestquest-party-board-card",
    "nestquest-quest-log-card",
    "nestquest-admin-card",
)


def test_frontend_package_documents_vite_lit_build() -> None:
    package = json.loads((FRONTEND_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["build"] == "vite build"
    assert "lit" in package["dependencies"]
    assert "typescript" in package["devDependencies"]
    assert "vite" in package["devDependencies"]


def test_card_modules_exist_as_separate_sources() -> None:
    src = FRONTEND_DIR / "src"
    assert (src / "nestquest-cards.ts").is_file()
    assert (src / "cards" / "party-board.ts").is_file()
    assert (src / "cards" / "quest-log.ts").is_file()
    assert (src / "cards" / "admin.ts").is_file()
    entry = (src / "nestquest-cards.ts").read_text(encoding="utf-8")
    assert "./cards/party-board" in entry
    assert "./cards/quest-log" in entry
    assert "./cards/admin" in entry


def test_card_sources_have_no_visual_editor() -> None:
    for path in (FRONTEND_DIR / "src" / "cards").glob("*.ts"):
        text = path.read_text(encoding="utf-8")
        assert "getConfigElement" not in text
        assert "setConfig" in text
        assert "getCardSize" in text


def test_built_bundle_contains_all_three_cards() -> None:
    assert BUNDLE_PATH.is_file()
    bundle = BUNDLE_PATH.read_text(encoding="utf-8")
    for card_type in CARD_TYPES:
        assert card_type in bundle


async def test_setup_registers_static_path_and_extra_js(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert len(hass.http.static_paths) == 1
    registered = hass.http.static_paths[0]
    assert registered.url_path == FRONTEND_URL_BASE
    assert registered.path == str(WWW_DIR)
    assert hass.extra_js_urls == [BUNDLE_URL]


async def test_async_setup_registers_frontend_without_a_config_entry(hass) -> None:
    assert await async_setup(hass, {}) is True
    assert hass.extra_js_urls == [BUNDLE_URL]
    assert hass.http.static_paths[0].url_path == FRONTEND_URL_BASE


async def test_frontend_registration_is_idempotent(hass, make_entry) -> None:
    await async_register_frontend(hass)
    await async_register_frontend(hass)
    entry_a = wire_entry_to_registry(make_entry(entry_id="a"), hass.registry)
    entry_b = wire_entry_to_registry(make_entry(entry_id="b"), hass.registry)
    assert await async_setup_entry(hass, entry_a) is True
    assert await async_setup_entry(hass, entry_b) is True
    assert len(hass.http.static_paths) == 1
    assert hass.extra_js_urls == [BUNDLE_URL]


def test_readme_documents_npm_build() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "npm run build" in readme
    assert "nestquest-cards.js" in readme
