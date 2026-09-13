"""The NestQuest integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER

_LOGGER = LOGGER


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the NestQuest integration. YAML configuration is not used, returns True."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NestQuest from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
