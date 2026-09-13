"""SQLite storage path resolution for the NestQuest integration."""
from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import SQLITE_DB_FILENAME


def _ensure_dir(path: Path) -> None:
    """Create the given directory and any missing parents."""
    path.mkdir(parents=True, exist_ok=True)


async def async_get_db_path(hass: HomeAssistant) -> Path:
    """Return the absolute path to the NestQuest SQLite database file."""
    db_path = Path(hass.config.path(SQLITE_DB_FILENAME)).absolute()
    await hass.async_add_executor_job(_ensure_dir, db_path.parent)
    return db_path