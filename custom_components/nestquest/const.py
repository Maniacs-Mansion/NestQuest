"""Constants for the NestQuest integration."""
from __future__ import annotations

import logging

DOMAIN = "nestquest"
LOGGER_NAME = "custom_components.nestquest"
LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[str] = []

#: Canonical domain-global service names (design/ENTITIES-AND-SERVICES.md §2
#: plus the existing Feature 07 regenerate service).
SERVICE_COMPLETE_QUEST = "complete_quest"
SERVICE_UNCOMPLETE_QUEST = "uncomplete_quest"
SERVICE_CREATE_QUEST_DEFINITION = "create_quest_definition"
SERVICE_UPDATE_QUEST_DEFINITION = "update_quest_definition"
SERVICE_SET_QUEST_DEFINITION_ACTIVE = "set_quest_definition_active"
SERVICE_SET_PRESENCE_PATTERN = "set_presence_pattern"
SERVICE_CREATE_PRESENCE_OVERRIDE = "create_presence_override"
SERVICE_DELETE_PRESENCE_OVERRIDE = "delete_presence_override"
SERVICE_EXPORT_HISTORY_CSV = "export_history_csv"
SERVICE_MANAGE_CHILD = "manage_child"
SERVICE_REGENERATE = "regenerate"

DOMAIN_SERVICES: tuple[str, ...] = (
    SERVICE_COMPLETE_QUEST,
    SERVICE_UNCOMPLETE_QUEST,
    SERVICE_CREATE_QUEST_DEFINITION,
    SERVICE_UPDATE_QUEST_DEFINITION,
    SERVICE_SET_QUEST_DEFINITION_ACTIVE,
    SERVICE_SET_PRESENCE_PATTERN,
    SERVICE_CREATE_PRESENCE_OVERRIDE,
    SERVICE_DELETE_PRESENCE_OVERRIDE,
    SERVICE_EXPORT_HISTORY_CSV,
    SERVICE_MANAGE_CHILD,
    SERVICE_REGENERATE,
)

SQLITE_DB_FILENAME = "nestquest.db"

# Configuration keys and default values
CONF_HORIZON_DAYS = "horizon_days"
DEFAULT_HORIZON_DAYS = 14

CONF_DAY_ROLLOVER_TIME = "day_rollover_time"
DEFAULT_DAY_ROLLOVER_TIME = "00:00"

CONF_PANEL_IDLE_TIMEOUT = "panel_idle_timeout"
DEFAULT_PANEL_IDLE_TIMEOUT = 300

# Admin allowlist (Feature 03): HA user IDs permitted to call admin-only
# services.  Stored as IDs, never usernames (feature guardrail).  The
# database allowlist is authoritative; the config entry carries the same
# list as a disaster-recovery copy so a lost database can be re-seeded.
CONF_ADMIN_USER_IDS = "admin_user_ids"

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
