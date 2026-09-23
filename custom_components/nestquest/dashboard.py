"""Zero-config panel dashboard registration for NestQuest (Feature 20).

On setup the integration registers ONE storage-mode Lovelace dashboard
whose CONFIG uses the bundle's ``custom:nestquest-party`` strategy (see
``frontend/src/strategy.ts``): the views themselves are GENERATED at
render time from the household roster, so the stored dashboard config
carries nothing but the strategy reference.

Registration mirrors the REAL two-step sequence the lovelace
integration itself uses when it creates the onboarding map dashboard
(``homeassistant/components/lovelace/__init__.py``,
``_create_map_dashboard``):

1. create the dashboard METADATA through the ``DashboardsCollection``
   (``hass.data["lovelace"]["dashboards_collection"]``) — url_path,
   title, icon, sidebar visibility.  The strategy reference is NOT part
   of the create payload: the collection's create schema allows only
   the metadata fields, so a ``strategy`` key there fails the whole
   create (this was the silent no-op the first implementation shipped).
2. save the dashboard CONFIG — ``{"strategy": ...}`` — through the
   per-url_path CONTENT manager that the collection's change listener
   registers under ``hass.data["lovelace"]["dashboards"][url_path]``
   (a ``LovelaceStorage``), exactly the second step HA performs.

Registration is IDEMPOTENT — a dashboard already under the stable
``url_path`` (ours or a user's) skips BOTH steps and its stored config
is never overwritten — and the Lovelace surfaces being unavailable
(YAML mode, lovelace not loaded) is a logged warning, never a setup
failure.
"""
from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant

from .const import (
    DASHBOARD_ICON,
    DASHBOARD_STRATEGY_TYPE,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    LOGGER,
)

_LOGGER = LOGGER

# Single-flight guard for the check-then-create below: HA can set up
# several config entries CONCURRENTLY, and two overlapping setups would
# both pass the exists-check and race on the url_path create.  The lock
# is per hass instance (kept as an attribute on the hass object, since
# hass.data is the integrations' shared registry the unload path
# empties) rather than one module-level asyncio.Lock — a bare
# module-level lock binds to whichever event loop first awaits it and
# raises RuntimeError on any other loop, while the race it must prevent
# only exists between setups running on the SAME hass anyway.
_REGISTRATION_LOCK_ATTR = "_nestquest_dashboard_registration_lock"


def _registration_lock(hass: HomeAssistant) -> asyncio.Lock:
    """Return the per-hass registration lock, creating it on first use."""
    lock = getattr(hass, _REGISTRATION_LOCK_ATTR, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(hass, _REGISTRATION_LOCK_ATTR, lock)
    return lock


def _lovelace_data(hass: HomeAssistant) -> dict | None:
    """Return ``hass.data["lovelace"]`` when it is the real dict shape.

    The lovelace integration stores a plain DICT of surfaces (``mode``,
    ``dashboards``, ``dashboards_collection``, ``resources``,
    ``yaml_dashboards``) under the ``lovelace`` key; anything else
    (missing key, unexpected object) means the surfaces below cannot be
    reached and registration must warn and continue.
    """
    lovelace_data = hass.data.get("lovelace")
    if not isinstance(lovelace_data, dict):
        return None
    return lovelace_data


def _dashboards_collection(hass: HomeAssistant):
    """Return the Lovelace dashboards METADATA collection, or None.

    The collection lives at ``hass.data["lovelace"]
    ["dashboards_collection"]`` — NOT under ``["dashboards"]``, which
    maps url_path to the per-dashboard CONTENT managers
    (``LovelaceStorage``/``LovelaceYAML``).  A missing key (lovelace
    not loaded) and a missing/None entry (YAML mode never sets the
    collection) both mean "cannot create storage dashboards here" —
    callers log and continue.  The presence of the surface is verified
    by capability (``async_create_item`` callable), not by type, so no
    lovelace import is needed.
    """
    lovelace_data = _lovelace_data(hass)
    if lovelace_data is None:
        return None
    collection = lovelace_data.get("dashboards_collection")
    if collection is None or not callable(
        getattr(collection, "async_create_item", None)
    ):
        return None
    return collection


def _dashboard_store(hass: HomeAssistant, url_path: str):
    """Return a url_path's dashboard CONTENT manager, or None.

    After a metadata create, the collection's change listener registers
    a ``LovelaceStorage`` for the new dashboard under
    ``hass.data["lovelace"]["dashboards"][url_path]``; the dashboard
    CONFIG (the strategy reference) is saved through THAT manager —
    the second step of HA's own dashboard creation.
    """
    lovelace_data = _lovelace_data(hass)
    if lovelace_data is None:
        return None
    dashboards = lovelace_data.get("dashboards")
    if not isinstance(dashboards, dict):
        return None
    store = dashboards.get(url_path)
    if store is None or not callable(getattr(store, "async_save", None)):
        return None
    return store


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
    Lovelace surfaces were unavailable or refused.  A dashboard already
    registered under the stable ``url_path`` — whether ours from a
    previous setup or a user's own — skips BOTH steps and is left
    COMPLETELY alone: its stored config is never overwritten, it is
    never deleted, never a duplicate.  The strategy config is saved
    ONLY for the dashboard created in THIS call, whose fresh content
    store is empty, so the save cannot clobber anything.
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
        # Single-flight: two concurrent entry setups must not both pass
        # the exists-check and race on the url_path create.
        async with _registration_lock(hass):
            # async_items() is a SYNC @callback on the real collection
            # (helpers/collection.py ObservableCollection) — not awaited.
            if _existing_dashboard(collection.async_items()):
                return True
            await collection.async_create_item(
                {
                    "url_path": DASHBOARD_URL_PATH,
                    "title": DASHBOARD_TITLE,
                    "icon": DASHBOARD_ICON,
                    "show_in_sidebar": True,
                    "allow_single_word": True,
                }
            )
            # Step two (mirroring HA's _create_map_dashboard): the
            # strategy CONFIG goes through the fresh dashboard's
            # content manager, not through the metadata collection.
            store = _dashboard_store(hass, DASHBOARD_URL_PATH)
            if store is None:
                _LOGGER.warning(
                    "The NestQuest panel dashboard was registered but its "
                    "Lovelace content manager never appeared; add the "
                    "strategy %s to the dashboard manually.",
                    DASHBOARD_STRATEGY_TYPE,
                )
                return False
            await store.async_save(
                {"strategy": {"type": DASHBOARD_STRATEGY_TYPE}}
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
