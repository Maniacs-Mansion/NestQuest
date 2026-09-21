"""Lovelace card bundle registration for NestQuest."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

WWW_DIR = Path(__file__).parent / "www"
FRONTEND_URL_BASE = "/nestquest-static"
BUNDLE_FILENAME = "nestquest-cards.js"
BUNDLE_URL = f"{FRONTEND_URL_BASE}/{BUNDLE_FILENAME}"
_REGISTERED_ATTR = "_nestquest_frontend_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card bundle and inject it into every Lovelace page.

    Idempotent across config entries: static paths and extra JS URLs are
    process-global, so a second entry must not register them again.
    """
    if getattr(hass, _REGISTERED_ATTR, False):
        return
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL_BASE,
                str(WWW_DIR),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, BUNDLE_URL)
    setattr(hass, _REGISTERED_ATTR, True)
