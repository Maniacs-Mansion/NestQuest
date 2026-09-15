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

# Quest windows (D-008): a definition may declare several day windows;
# each produces its own instance per day and groups the panel's Quest
# Log into three columns.  The clock ranges are stored here so they stay
# configurable later.  Boundaries: a window's end equals the next
# window's start; classification (Feature 07 materialisation) treats a
# due time exactly on the boundary as belonging to the LATER window, so
# 12:00 is afternoon (not morning) and 17:00 is evening (not
# afternoon).  Times after 21:00 belong to no window.
WINDOW_MORNING = "morning"
WINDOW_AFTERNOON = "afternoon"
WINDOW_EVENING = "evening"

QUEST_WINDOWS: tuple[str, ...] = (
    WINDOW_MORNING,
    WINDOW_AFTERNOON,
    WINDOW_EVENING,
)

#: Inclusive "HH:MM" bounds per window, in 24-hour local time.
WINDOW_CLOCK_RANGES: dict[str, tuple[str, str]] = {
    WINDOW_MORNING: ("00:00", "11:59"),
    WINDOW_AFTERNOON: ("12:00", "17:00"),
    WINDOW_EVENING: ("17:00", "21:00"),
}
