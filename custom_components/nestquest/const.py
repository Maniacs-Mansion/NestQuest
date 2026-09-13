"""Constants for the NestQuest integration."""
from __future__ import annotations

import logging

DOMAIN = "nestquest"
LOGGER_NAME = "custom_components.nestquest"
LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[str] = []

SQLITE_DB_FILENAME = "nestquest.db"

# Configuration keys and default values
CONF_HORIZON_DAYS = "horizon_days"
DEFAULT_HORIZON_DAYS = 14

CONF_DAY_ROLLOVER_TIME = "day_rollover_time"
DEFAULT_DAY_ROLLOVER_TIME = "00:00"

CONF_PANEL_IDLE_TIMEOUT = "panel_idle_timeout"
DEFAULT_PANEL_IDLE_TIMEOUT = 300
