"""Re-export of :mod:`core.store` for the integration package.

The path resolver lives in :mod:`core.store` (extracted in task
d0b691d8) and is Home-Assistant-free: :func:`core.store.async_get_db_path`
takes the full database path.  This module re-exports it and provides
the original ``async_get_db_path(hass)`` signature so the integration
resolves the path from ``hass.config.path`` exactly as before.
"""
from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from core.const import SQLITE_DB_FILENAME
from core.store import async_get_db_path as _core_async_get_db_path
from core.store import _ensure_dir

__all__ = ["async_get_db_path", "_ensure_dir"]


async def async_get_db_path(hass: HomeAssistant) -> Path:
    """Return the absolute path to the NestQuest SQLite database file.

    Resolves the database file from ``hass.config.path`` and delegates to
    :func:`core.store.async_get_db_path`, which ensures the parent
    directory exists off the event loop via :func:`asyncio.to_thread`.
    """
    return await _core_async_get_db_path(hass.config.path(SQLITE_DB_FILENAME))
