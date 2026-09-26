"""Constants for the NestQuest integration."""
from __future__ import annotations

import logging
import re

DOMAIN = "nestquest"
LOGGER_NAME = "custom_components.nestquest"
LOGGER = logging.getLogger(LOGGER_NAME)

#: Strict 24-hour ``HH:MM`` pattern shared by the options flow and the
#: settings object's time validation, so a stored option and a freshly
#: validated form submit parse the same way.  Defined here (HA-free) so
#: both the integration's options flow and the core settings module
#: import ONE pattern instead of re-copying it.
TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")

# Platforms set up per config entry (Feature 10): the per-child day
# sensors and binary sensors.
PLATFORMS: list[str] = ["sensor", "binary_sensor"]

# Home Assistant bus events (design/ENTITIES-AND-SERVICES.md §3).  The
# panel and admin cards listen for these; since Feature 18 the
# completed/uncompleted/day-complete transitions are published by the
# API service on its SSE stream and re-fired on the bus by the
# integration's subscription, and Feature 11's nightly sweep fires
# quest_missed.
EVENT_QUEST_COMPLETED = "nestquest_quest_completed"
EVENT_QUEST_UNCOMPLETED = "nestquest_quest_uncompleted"
EVENT_QUEST_MISSED = "nestquest_quest_missed"
EVENT_CHILD_DAY_COMPLETE = "nestquest_child_day_complete"

#: Canonical domain-global service name (design/ENTITIES-AND-SERVICES.md §2).
#: Since Feature 18 only the panel completion service remains: the admin
#: surface is the PWA and the API service's admin routes, so the former
#: HA admin services (uncomplete, quest-definition and presence
#: management, CSV export, child management, regenerate) are gone.
SERVICE_COMPLETE_QUEST = "complete_quest"

DOMAIN_SERVICES: tuple[str, ...] = (
    SERVICE_COMPLETE_QUEST,
)

SQLITE_DB_FILENAME = "nestquest.db"

# Zero-config panel dashboard (Feature 20): ONE storage-mode Lovelace
# dashboard registered on setup whose config carries the bundle's
# ``custom:nestquest-party`` strategy (frontend/src/strategy.ts) — the
# views are generated at render time from the household roster.  The
# url_path IS the domain: the stable key idempotency is keyed on (a
# reload or a second entry never duplicates it, and a dashboard already
# registered under it — ours or the user's — is left untouched).
DASHBOARD_URL_PATH = DOMAIN
DASHBOARD_TITLE = "NestQuest"
DASHBOARD_ICON = "mdi:party-popper"
DASHBOARD_STRATEGY_TYPE = "custom:nestquest-party"

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

# Shared coordinator refresh interval (Feature 10), in SECONDS.  Every
# entity reads one snapshot per refresh; completions push an immediate
# refresh so this poll is only the fallback cadence.
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 300
MIN_UPDATE_INTERVAL = 30

# Last-good snapshot staleness (Feature 18), in SECONDS: how long the
# coordinator keeps SERVING the last good snapshot after the API stops
# answering.  A failed poll whose elapsed time since the last successful
# fetch is within the threshold returns the cached snapshot (the panel
# keeps rendering last-good data, entities stay available); past it the
# poll fails the HA way and the entities go unavailable.  The default is
# 3x the default update interval (900 s = 15 minutes): three consecutive
# failed five-minute polls before the board is declared stale — enough
# to ride out an API service restart, short enough not to render a
# days-old board all day.  Validation floor: the threshold must be at
# least the configured update interval, or the cache could never span
# even one failed poll.
CONF_SNAPSHOT_STALENESS = "snapshot_staleness"
DEFAULT_SNAPSHOT_STALENESS = 3 * DEFAULT_UPDATE_INTERVAL

# Notification automations (Feature 11).  The notify target is a free-text
# Home Assistant service name (e.g. "notify.mobile_app_dads_phone") the
# household fills in — never a hard-coded personal target; the times are
# strict HH:MM local; each of the four automations has an independent
# enable toggle.  Per the owner-settled resolution the end-of-day report
# defaults to 20:00 — deliberately BEFORE the midnight missed sweep —
# and never defaults to the rollover time.
CONF_NOTIFY_TARGET = "notify_target"
CONF_MORNING_SUMMARY_TIME = "morning_summary_time"
DEFAULT_MORNING_SUMMARY_TIME = "08:00"
CONF_AFTERNOON_REMINDER_TIME = "afternoon_reminder_time"
DEFAULT_AFTERNOON_REMINDER_TIME = "15:00"
CONF_END_OF_DAY_REPORT_TIME = "end_of_day_report_time"
DEFAULT_END_OF_DAY_REPORT_TIME = "20:00"
CONF_MORNING_SUMMARY_ENABLED = "morning_summary_enabled"
CONF_AFTERNOON_REMINDER_ENABLED = "afternoon_reminder_enabled"
CONF_END_OF_DAY_REPORT_ENABLED = "end_of_day_report_enabled"
CONF_CELEBRATION_ENABLED = "celebration_enabled"
DEFAULT_AUTOMATION_ENABLED = True
# The household's IANA time zone (e.g. ``America/New_York``) the API
# service reads its clock in.  The empty string keeps the historical
# behaviour — the API host's own local time — so an existing install is
# unchanged until the owner sets it.  The integration itself always uses
# Home Assistant's configured ``time_zone`` and ignores this field.
CONF_TIMEZONE = "timezone"
DEFAULT_TIMEZONE = ""

# Panel-plane API client (Feature 18): the integration reaches the
# NestQuest API service (Feature 16) over HTTP instead of the database.
# The base URL points at the API service host serving ``/api/v1/panel/*``
# (uvicorn's default host/port is the sensible starting point); the panel
# service token is the static Bearer credential the panel plane requires
# (``NESTQUEST_PANEL_TOKEN`` on the API side).  Both are stored on the
# entry like every other setting — options first, then the entry-data
# copy, then defaults.  The TOKEN IS A SECRET: it is never logged, never
# echoed into error messages, and never committed.  The shipped default
# token IS the empty string (DEFAULT_PANEL_TOKEN) — an entry with no
# configured token is therefore NOT a working client: the options flow
# accepts an empty token as "not configured yet" and only rejects
# malformed (padded/whitespace-only/non-string) values — the actual
# non-emptiness guard is enforced at client construction, where
# NestQuestApiClient fails fast on an empty/whitespace token
# (api_client.py).  So a caller building the client from a bare
# entry must either ensure a token is configured first or handle the
# construction ValueError and surface an "API not configured" state —
# an unconfigured entry never yields a client that can only 401.
# This mirrors the API service's fail-closed stance (api/config.py: no
# default token exists).
CONF_API_BASE_URL = "api_base_url"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
CONF_PANEL_TOKEN = "panel_token"
DEFAULT_PANEL_TOKEN = ""

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
