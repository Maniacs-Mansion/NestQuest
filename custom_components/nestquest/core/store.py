"""SQLite storage path resolution for the NestQuest storage layer.

Home-Assistant-free: callers resolve the database file location from
their own config (HA resolves it from ``hass.config.path``) and pass
the full path here; this module ensures the parent directory exists
off-thread via :func:`asyncio.to_thread` and returns the absolute path.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


def _ensure_dir(path: Path) -> None:
    """Create the given directory and any missing parents."""
    path.mkdir(parents=True, exist_ok=True)


async def async_get_db_path(db_path: Path | str) -> Path:
    """Return the absolute path to the NestQuest SQLite database file.

    ``db_path`` is the full path to the database file (the integration
    resolves it from ``hass.config.path(SQLITE_DB_FILENAME)``); the
    parent directory is created off the event loop via
    :func:`asyncio.to_thread` so this module never blocks and never
    imports Home Assistant.
    """
    path = Path(db_path).absolute()
    await asyncio.to_thread(_ensure_dir, path.parent)
    return path
