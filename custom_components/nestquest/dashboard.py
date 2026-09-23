"""Zero-config panel dashboard registration for NestQuest (Feature 20).

On setup the integration registers ONE storage-mode Lovelace dashboard
whose config uses the bundle's ``custom:nestquest-party`` strategy (see
``frontend/src/strategy.ts``): the views themselves are GENERATED at
render time from the household roster, so the stored dashboard carries
nothing but the strategy reference.  Registration is IDEMPOTENT — a
dashboard with the stable ``url_path`` (ours or a user's) is never
touched, and the Lovelace dashboards collection being unavailable
(YAML mode, lovelace not loaded) is a logged warning, never a setup
failure.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import (
    DASHBOARD_ICON,
    DASHBOARD_STRATEGY_TYPE,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    LOGGER,
)

_LOGGER = LOGGER


def _dashboards_collection(hass: HomeAssistant):
    """Return the Lovelace dashboards collection, or None when absent.

    The lovelace integration stashes its collections on
    ``hass.data["lovelace"]``; a missing key (lovelace not loaded) and a
    collection-less LovelaceData both mean "cannot create storage
    dashboards here" — callers log and continue.  The presence of the
    surface is verified by capability (``async_create_item`` callable),
    not by type, so no lovelace import is needed.
    """
    lovelace_data = hass.data.get("lovelace")
    collection = getattr(lovelace_data, "dashboards", None)
    if collection is None or not callable(
        getattr(collection, "async_create_item", None)
    ):
        return None
    return collection


def _item_url_path(item) -> str | None:
    """Read a dashboard item's ``url_path`` through either access shape.

    The collection hands back storage items as dicts while builtin
    dashboards come back as config objects; the url_path is reachable
    through ``item["url_path"]`` or ``item.url_path`` respectively.
    """
    url_path = getattr(item, "url_path", None)
    if isinstance(url_path, str):
        return url_path
    get_url_path = getattr(item, "get", None)
    if callable(get_url_path):
        value = get_url_path("url_path")
        if isinstance(value, str):
            return value
    return None


def _existing_dashboard(items) -> bool:
    """Whether a dashboard under the stable url_path already exists."""
    return any(_item_url_path(item) == DASHBOARD_URL_PATH for item in items)


async def async_register_dashboard(hass: HomeAssistant) -> bool:
    """Register the NestQuest panel dashboard exactly once.

    Returns True when a dashboard under the stable ``url_path`` exists
    after the call (pre-existing or created here), False when the
    Lovelace dashboards collection was unavailable or refused.  A
    dashboard already registered under the stable ``url_path`` — whether
    ours from a previous setup or a user's own — is left COMPLETELY
    alone: never overwritten, never deleted, never a duplicate.
    """
    collection = _dashboards_collection(hass)
    if collection is None:
        _LOGGER.warning(
            "Lovelace dashboards collection unavailable; the NestQuest "
            "panel dashboard was not registered. Enable the Lovelace "
            "integration in storage mode or create a dashboard with "
            "strategy %s manually.",
            DASHBOARD_STRATEGY_TYPE,
        )
        return False
    try:
        items = await collection.async_items()
        if _existing_dashboard(items):
            return True
        await collection.async_create_item(
            {
                "url_path": DASHBOARD_URL_PATH,
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "mode": "storage",
                "strategy": {"type": DASHBOARD_STRATEGY_TYPE},
            }
        )
    except Exception:
        _LOGGER.warning(
            "Registering the NestQuest panel dashboard in the Lovelace "
            "dashboards collection failed; set it up manually with "
            "strategy %s.",
            DASHBOARD_STRATEGY_TYPE,
            exc_info=True,
        )
        return False
    return True
