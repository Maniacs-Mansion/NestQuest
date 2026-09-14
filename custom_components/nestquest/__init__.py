"""The NestQuest integration."""
from __future__ import annotations

import asyncio
import inspect
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, LOGGER
from .db import NestQuestDatabase
from .migrations import apply_migrations
from .store import async_get_db_path

_LOGGER = LOGGER

#: SQLite reports "file is not a database" for corruption in every
#: sqlite3 version this integration targets; the version-specific
#: "encrypted or malformed" spelling (3.41+) maps to the same failure.
_CORRUPTION_MARKERS = (
    "file is not a database",
    "encrypted or malformed",
)


def _is_corruption_error(error: BaseException) -> bool:
    """Return True when ``error`` indicates a corrupt database file.

    Matching happens on the message: sqlite3.DatabaseError is the base
    of several non-corruption errors too (e.g. OperationalError), and
    only the corruption spellings warrant refusing to open.
    """
    message = str(error).lower()
    return isinstance(error, sqlite3.DatabaseError) and any(
        marker in message for marker in _CORRUPTION_MARKERS
    )

async def _async_open_database(
    hass: HomeAssistant, db_path: Path
) -> NestQuestDatabase:
    """Open the NestQuest database, mapping failure modes for setup.

    Three startup cases (Feature 02 done-condition):

    - file missing: SQLite creates it fresh on open — no special path,
      migrations stamp version 1 on the next step.
    - file present and valid: opens normally.
    - file present but corrupt: log an ERROR with the path, close
      anything opened, and raise ConfigEntryNotReady so HA retries —
      the file is left byte-for-byte untouched so the owner can
      restore a backup.  No code path here deletes or overwrites an
      existing database file.

    Corruption can surface at EITHER stage: a truncated header fails
    inside open() (the WAL-mode PRAGMA reads the header), while
    damaged pages fail later, inside migrations.  Both are classified
    the same way.
    """
    try:
        database = await NestQuestDatabase(hass).open(db_path)
    except asyncio.CancelledError:
        raise
    except sqlite3.DatabaseError as err:
        if _is_corruption_error(err):
            _LOGGER.error(
                "NestQuest database at %s is corrupt: %s. Refusing to "
                "start with a corrupt database; the file was left "
                "untouched so a backup can be restored. Home Assistant "
                "will retry setup.",
                db_path,
                err,
            )
            raise ConfigEntryNotReady(
                f"NestQuest database corrupt: {db_path}"
            ) from err
        # open() failed for a non-corruption reason (locked file,
        # permission problem): retryable, but nothing was opened.
        _LOGGER.error(
            "NestQuest database at %s failed to open: %s. Home "
            "Assistant will retry setup.",
            db_path,
            err,
        )
        raise ConfigEntryNotReady(
            f"NestQuest database unavailable: {db_path}"
        ) from err
    try:
        await apply_migrations(database)
    except (sqlite3.DatabaseError, RuntimeError) as err:
        await database.close()
        if _is_corruption_error(err):
            _LOGGER.error(
                "NestQuest database at %s is corrupt: %s. Refusing to "
                "start with a corrupt database; the file was left "
                "untouched so a backup can be restored. Home Assistant "
                "will retry setup.",
                db_path,
                err,
            )
            raise ConfigEntryNotReady(
                f"NestQuest database corrupt: {db_path}"
            ) from err
        # A non-corruption failure (e.g. a locked file, a future schema
        # version) is also a retryable setup problem, but without the
        # corruption framing.
        _LOGGER.error(
            "NestQuest database at %s failed to open: %s. Home "
            "Assistant will retry setup.",
            db_path,
            err,
        )
        raise ConfigEntryNotReady(
            f"NestQuest database unavailable: {db_path}"
        ) from err
    except asyncio.CancelledError:
        await database.close()
        raise
    return database


@dataclass
class NestQuestRuntimeData:
    """Runtime data stored on a NestQuest config entry."""

    entry_id: str
    options: dict[str, Any]
    database: NestQuestDatabase
    remove_update_listener: Callable[[], Any]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the NestQuest integration. YAML configuration is not used, returns True."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NestQuest from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    existing = hass.data[DOMAIN].get(entry.entry_id)
    if existing is not None:
        db = getattr(existing, "database", None)
        if db is None:
            db = await NestQuestDatabase(hass).open(await async_get_db_path(hass))
            existing.database = db
        entry.runtime_data = existing
        return True

    async def _async_update_listener(
        listener_hass: HomeAssistant, listener_entry: ConfigEntry
    ) -> None:
        """Reload the entry when its options change."""
        await listener_hass.config_entries.async_reload(listener_entry.entry_id)

    database = await _async_open_database(hass, await async_get_db_path(hass))
    try:
        remove_update_listener = entry.add_update_listener(_async_update_listener)
    except BaseException:
        await database.close()
        raise
    runtime_data = NestQuestRuntimeData(
        entry_id=entry.entry_id,
        options=dict(entry.options),
        database=database,
        remove_update_listener=remove_update_listener,
    )
    entry.runtime_data = runtime_data
    hass.data[DOMAIN][entry.entry_id] = runtime_data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime_data = domain_data.pop(entry.entry_id, None)
    if not domain_data:
        hass.data.pop(DOMAIN, None)
    if runtime_data is None:
        runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is not None:
        remove_update_listener = getattr(runtime_data, "remove_update_listener", None)
        unload_error: BaseException | None = None
        try:
            if remove_update_listener is not None:
                result = remove_update_listener()
                if inspect.isawaitable(result):
                    await result
        except BaseException as err:
            unload_error = err
        finally:
            database = getattr(runtime_data, "database", None)
            if database is not None:
                await database.close()
        if unload_error is not None:
            if getattr(entry, "runtime_data", None) is not None:
                entry.runtime_data = None
            raise unload_error
    if getattr(entry, "runtime_data", None) is not None:
        entry.runtime_data = None
    return True
