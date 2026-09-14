"""The NestQuest integration."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER
from .db import NestQuestDatabase
from .migrations import apply_migrations
from .store import async_get_db_path

_LOGGER = LOGGER


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

    database = await NestQuestDatabase(hass).open(await async_get_db_path(hass))
    try:
        await apply_migrations(database)
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
