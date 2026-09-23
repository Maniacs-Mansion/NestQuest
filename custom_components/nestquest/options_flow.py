"""Options flow for NestQuest post-setup settings."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ADMIN_USER_IDS,
    CONF_AFTERNOON_REMINDER_ENABLED,
    CONF_AFTERNOON_REMINDER_TIME,
    CONF_API_BASE_URL,
    CONF_CELEBRATION_ENABLED,
    CONF_DAY_ROLLOVER_TIME,
    CONF_END_OF_DAY_REPORT_ENABLED,
    CONF_END_OF_DAY_REPORT_TIME,
    CONF_HORIZON_DAYS,
    CONF_MORNING_SUMMARY_ENABLED,
    CONF_MORNING_SUMMARY_TIME,
    CONF_NOTIFY_TARGET,
    CONF_PANEL_IDLE_TIMEOUT,
    CONF_PANEL_TOKEN,
    CONF_SNAPSHOT_STALENESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_BASE_URL,
    DEFAULT_AFTERNOON_REMINDER_TIME,
    DEFAULT_AUTOMATION_ENABLED,
    DEFAULT_DAY_ROLLOVER_TIME,
    DEFAULT_END_OF_DAY_REPORT_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_MORNING_SUMMARY_TIME,
    DEFAULT_PANEL_IDLE_TIMEOUT,
    DEFAULT_PANEL_TOKEN,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    TIME_PATTERN,
)
from .admin_allowlist import list_admin_ids, set_admin_ids
from .api_client import is_valid_base_url

MIN_HORIZON_DAYS = 1
MIN_PANEL_IDLE_TIMEOUT = 30


def _parse_time(value: str) -> bool:
    """Return True when value is a valid 24-hour HH:MM string."""
    return TIME_PATTERN.fullmatch(value) is not None


def _async_validate(
    user_input: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Validate user input and return field-level errors instead of raising.

    ``current`` carries the stored values (entry options → entry data →
    defaults) so a raw submit that sets one field but omits a sibling it
    is validated against (the staleness threshold vs. the update
    interval) can still check the effective pair; raw submits omitting
    BOTH keys keep their stored values untouched.
    """
    errors: dict[str, str] = {}

    horizon_days = user_input.get(CONF_HORIZON_DAYS)
    if (
        isinstance(horizon_days, bool)
        or not isinstance(horizon_days, int)
        or horizon_days < MIN_HORIZON_DAYS
    ):
        errors[CONF_HORIZON_DAYS] = "invalid"

    day_rollover_time = user_input.get(CONF_DAY_ROLLOVER_TIME)
    if not isinstance(day_rollover_time, str) or not _parse_time(day_rollover_time):
        errors[CONF_DAY_ROLLOVER_TIME] = "invalid_time"

    panel_idle_timeout = user_input.get(CONF_PANEL_IDLE_TIMEOUT)
    if (
        isinstance(panel_idle_timeout, bool)
        or not isinstance(panel_idle_timeout, int)
        or panel_idle_timeout < MIN_PANEL_IDLE_TIMEOUT
    ):
        errors[CONF_PANEL_IDLE_TIMEOUT] = "invalid"

    # The coordinator refresh interval (Feature 10) is OPTIONAL in raw
    # submits: a missing key keeps the current value, so pre-Feature-10
    # form payloads (and API callers) are unaffected.  Schema-validated
    # submits always carry it.
    update_interval = user_input.get(CONF_UPDATE_INTERVAL)
    if update_interval is not None and (
        isinstance(update_interval, bool)
        or not isinstance(update_interval, int)
        or update_interval < MIN_UPDATE_INTERVAL
    ):
        errors[CONF_UPDATE_INTERVAL] = "invalid"

    # The last-good staleness threshold (Feature 18) is OPTIONAL in raw
    # submits the same way: a missing key keeps the current value.  It
    # must be a positive int, and at least the EFFECTIVE update interval
    # (the one this submit carries, else the stored or default one) — a
    # threshold shorter than the poll cadence could never serve even one
    # cached snapshot.
    staleness = user_input.get(CONF_SNAPSHOT_STALENESS)
    if staleness is not None and (
        isinstance(staleness, bool)
        or not isinstance(staleness, int)
        or staleness < 1
    ):
        errors[CONF_SNAPSHOT_STALENESS] = "invalid"
    elif staleness is not None and not errors.get(CONF_UPDATE_INTERVAL):
        stored_interval = (current or {}).get(CONF_UPDATE_INTERVAL)
        effective_interval = update_interval
        if effective_interval is None and (
            isinstance(stored_interval, int)
            and not isinstance(stored_interval, bool)
            and stored_interval >= MIN_UPDATE_INTERVAL
        ):
            effective_interval = stored_interval
        if effective_interval is None:
            effective_interval = DEFAULT_UPDATE_INTERVAL
        if staleness < effective_interval:
            errors[CONF_SNAPSHOT_STALENESS] = "invalid_staleness"

    # The notification section (Feature 11) is OPTIONAL in raw submits
    # the same way: a missing key keeps the current value.  The three
    # times are strict HH:MM; the notify target is a non-empty HA
    # service name; the toggles are real booleans.
    for time_key in (
        CONF_MORNING_SUMMARY_TIME,
        CONF_AFTERNOON_REMINDER_TIME,
        CONF_END_OF_DAY_REPORT_TIME,
    ):
        time_value = user_input.get(time_key)
        if time_value is not None and (
            not isinstance(time_value, str) or not _parse_time(time_value)
        ):
            errors[time_key] = "invalid_time"
    notify_target = user_input.get(CONF_NOTIFY_TARGET)
    if notify_target is not None and not isinstance(notify_target, str):
        errors[CONF_NOTIFY_TARGET] = "invalid"
    elif isinstance(notify_target, str) and notify_target != (
        notify_target.strip()
    ):
        # An EMPTY target is valid — it means "no notifications
        # configured yet" and is the shipped default; a value that
        # differs from its own trim (padded or whitespace-only) is
        # malformed and rejected.
        errors[CONF_NOTIFY_TARGET] = "invalid"
    for toggle_key in (
        CONF_MORNING_SUMMARY_ENABLED,
        CONF_AFTERNOON_REMINDER_ENABLED,
        CONF_END_OF_DAY_REPORT_ENABLED,
        CONF_CELEBRATION_ENABLED,
    ):
        toggle_value = user_input.get(toggle_key)
        if toggle_value is not None and not isinstance(toggle_value, bool):
            errors[toggle_key] = "invalid"

    # The panel-plane API connection (Feature 18) is OPTIONAL in raw
    # submits the same way: a missing key keeps the current value.  The
    # base URL must be a full http(s) URL with a host — the same check
    # the client's constructor enforces, so a malformed URL fails at
    # the form, not at the first request.  The token may be EMPTY (the
    # API connection is simply not configured yet) but a non-empty one
    # must be pasted unpadded: a padded or whitespace-only value is a
    # clipboard mistake that would fail the token check at request
    # time.
    api_base_url = user_input.get(CONF_API_BASE_URL)
    if api_base_url is not None and not is_valid_base_url(api_base_url):
        errors[CONF_API_BASE_URL] = "invalid_url"
    panel_token = user_input.get(CONF_PANEL_TOKEN)
    if panel_token is not None and (
        not isinstance(panel_token, str)
        or panel_token != panel_token.strip()
    ):
        errors[CONF_PANEL_TOKEN] = "invalid"

    return errors


def _strict_bool(value: object) -> bool:
    """Require a real bool; voluptuous ``bool`` would coerce strings."""
    if not isinstance(value, bool):
        raise vol.Invalid(f"expected a boolean, got {value!r}")
    return value


def _build_schema(
    current: dict[str, Any],
    *,
    admin_choices: dict[str, str] | None = None,
    admin_default: list[str] | None = None,
) -> vol.Schema:
    """Build the form schema, pre-filled with the current values.

    The admin picker is a multi-select of EXISTING Home Assistant users
    (never a free-text field — the allowlist stores user IDs); its
    default is the current database allowlist, so an untouched submit
    re-saves exactly who is already allowed.  The notification section
    (Feature 11) carries the household's notify target, the three
    automation times, and four enable toggles — defaults from
    :mod:`~.const`, never a hard-coded personal target.
    """
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_HORIZON_DAYS, default=current[CONF_HORIZON_DAYS]
        ): int,
        vol.Required(
            CONF_DAY_ROLLOVER_TIME, default=current[CONF_DAY_ROLLOVER_TIME]
        ): str,
        vol.Required(
            CONF_PANEL_IDLE_TIMEOUT, default=current[CONF_PANEL_IDLE_TIMEOUT]
        ): int,
        vol.Required(
            CONF_UPDATE_INTERVAL, default=current[CONF_UPDATE_INTERVAL]
        ): int,
        # The last-good staleness threshold (Feature 18): how long the
        # coordinator keeps serving the cached snapshot after the API
        # stops answering.  Schema-validated submits always carry it
        # (the default pre-fills from the stored value); raw callers
        # omitting it keep their stored value (see _async_validate).
        vol.Required(
            CONF_SNAPSHOT_STALENESS, default=current[CONF_SNAPSHOT_STALENESS]
        ): int,
        vol.Required(
            CONF_NOTIFY_TARGET, default=current[CONF_NOTIFY_TARGET]
        ): str,
        vol.Required(
            CONF_MORNING_SUMMARY_TIME,
            default=current[CONF_MORNING_SUMMARY_TIME],
        ): str,
        vol.Required(
            CONF_AFTERNOON_REMINDER_TIME,
            default=current[CONF_AFTERNOON_REMINDER_TIME],
        ): str,
        vol.Required(
            CONF_END_OF_DAY_REPORT_TIME,
            default=current[CONF_END_OF_DAY_REPORT_TIME],
        ): str,
        vol.Required(
            CONF_MORNING_SUMMARY_ENABLED,
            default=current[CONF_MORNING_SUMMARY_ENABLED],
        ): _strict_bool,
        vol.Required(
            CONF_AFTERNOON_REMINDER_ENABLED,
            default=current[CONF_AFTERNOON_REMINDER_ENABLED],
        ): _strict_bool,
        vol.Required(
            CONF_END_OF_DAY_REPORT_ENABLED,
            default=current[CONF_END_OF_DAY_REPORT_ENABLED],
        ): _strict_bool,
        vol.Required(
            CONF_CELEBRATION_ENABLED,
            default=current[CONF_CELEBRATION_ENABLED],
        ): _strict_bool,
        # Panel-plane API connection (Feature 18): the base URL the API
        # client talks to and the panel service token it presents as
        # the Bearer credential.  Schema-validated submits always carry
        # both (the defaults pre-fill from the stored values); raw
        # callers omitting them keep their stored values (see
        # _async_validate).
        vol.Required(
            CONF_API_BASE_URL, default=current[CONF_API_BASE_URL]
        ): str,
        vol.Required(
            CONF_PANEL_TOKEN, default=current[CONF_PANEL_TOKEN]
        ): str,
    }
    if admin_choices is not None:
        # HA's supported multi-select validator: the frontend can
        # serialize the field as a real picker of the given choices.
        fields[
            vol.Optional(
                CONF_ADMIN_USER_IDS, default=list(admin_default or [])
            )
        ] = cv.multi_select(admin_choices)
    return vol.Schema(fields)


class NestQuestOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle the options flow for NestQuest."""

    def _async_database(self):
        """Return the runtime database for this entry, or None.

        Real HA only opens the options flow for an existing entry, so
        the runtime record (and its database) exists; the None branch
        covers direct construction in tests and degraded states.
        """
        hass_data = getattr(self.hass, "data", None)
        if not isinstance(hass_data, dict):
            return None
        record = hass_data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        database = getattr(record, "database", None)
        return database if getattr(database, "connected", False) else None

    async def _async_admin_choices(self) -> dict[str, str]:
        """Map HA user id -> display name for the picker.

        Real Home Assistant always provides ``hass.auth``; a missing
        one (direct construction in tests, degraded harness) degrades
        to an empty picker rather than crashing the form.
        """
        auth = getattr(self.hass, "auth", None)
        if auth is None:
            return {}
        users = await auth.async_get_users()
        return {
            user.id: user.name
            for user in users
            if getattr(user, "id", None)
        }

    async def _async_current_admin_ids(self) -> list[str]:
        """Return the current allowlist, or [] without a database."""
        database = self._async_database()
        if database is None:
            return []
        return await list_admin_ids(database)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the NestQuest options."""
        admin_choices = await self._async_admin_choices()
        admin_default = await self._async_current_admin_ids()
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(
                    self._current_values(),
                    admin_choices=admin_choices,
                    admin_default=admin_default,
                ),
            )

        errors = _async_validate(user_input, self._current_values())
        # The admin ids are validated only when the key is present:
        # schema-validated submits always carry it (vol.Optional's
        # default fills from the current allowlist), while raw callers
        # omitting the key keep the field untouched.
        admin_ids_present = CONF_ADMIN_USER_IDS in user_input
        admin_ids = user_input.get(CONF_ADMIN_USER_IDS)
        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(
                    self._current_values(),
                    admin_choices=admin_choices,
                    admin_default=admin_default,
                ),
                errors=errors,
            )
        if admin_ids_present and (
            not isinstance(admin_ids, list)
            or any(not isinstance(value, str) for value in admin_ids)
        ):
            errors[CONF_ADMIN_USER_IDS] = "invalid_admin"
        elif admin_ids_present and not admin_ids:
            # An empty allowlist fails closed: saving zero admins is
            # refused, never silently applied.
            errors[CONF_ADMIN_USER_IDS] = "no_admins"
        elif admin_ids_present and any(
            value not in admin_choices for value in admin_ids
        ):
            # The schema enforces membership for real HA submits; this
            # backs the raw-input path up so an unknown id can never
            # reach the allowlist.
            errors[CONF_ADMIN_USER_IDS] = "invalid_admin"
        elif admin_ids_present and len(set(admin_ids)) != len(admin_ids):
            # set_admin_ids refuses duplicates with ValueError; a flow
            # submission must surface that as a field error instead of
            # an unhandled crash.
            errors[CONF_ADMIN_USER_IDS] = "invalid_admin"
        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(
                    self._current_values(),
                    admin_choices=admin_choices,
                    admin_default=admin_default,
                ),
                errors=errors,
            )

        # Apply the picker's selection to the allowlist when the
        # runtime database is reachable; the selection is always
        # stored on the entry as the disaster-recovery copy.
        database = self._async_database()
        if database is not None and admin_ids_present:
            await set_admin_ids(database, admin_ids)
        data = {
            CONF_HORIZON_DAYS: user_input[CONF_HORIZON_DAYS],
            CONF_DAY_ROLLOVER_TIME: user_input[CONF_DAY_ROLLOVER_TIME],
            CONF_PANEL_IDLE_TIMEOUT: user_input[CONF_PANEL_IDLE_TIMEOUT],
            CONF_UPDATE_INTERVAL: user_input.get(
                CONF_UPDATE_INTERVAL,
                self._current_values()[CONF_UPDATE_INTERVAL],
            ),
            CONF_SNAPSHOT_STALENESS: user_input.get(
                CONF_SNAPSHOT_STALENESS,
                self._current_values()[CONF_SNAPSHOT_STALENESS],
            ),
        }
        # The notification section (Feature 11) stores the household's
        # choices the same fall-back-to-current way, so raw submits
        # that predate the section keep their stored values.
        current = self._current_values()
        for notification_key in (
            CONF_NOTIFY_TARGET,
            CONF_MORNING_SUMMARY_TIME,
            CONF_AFTERNOON_REMINDER_TIME,
            CONF_END_OF_DAY_REPORT_TIME,
            CONF_MORNING_SUMMARY_ENABLED,
            CONF_AFTERNOON_REMINDER_ENABLED,
            CONF_END_OF_DAY_REPORT_ENABLED,
            CONF_CELEBRATION_ENABLED,
        ):
            data[notification_key] = user_input.get(
                notification_key, current[notification_key]
            )
        # The API connection section (Feature 18) stores the base URL
        # and panel token the same fall-back-to-current way, so raw
        # submits that predate the section keep their stored values.
        for api_key in (CONF_API_BASE_URL, CONF_PANEL_TOKEN):
            data[api_key] = user_input.get(api_key, current[api_key])
        if admin_ids_present:
            data[CONF_ADMIN_USER_IDS] = admin_ids
        elif admin_default:
            # HA replaces entry.options wholesale, so an omitted picker
            # field must carry the CURRENT allowlist forward: dropping
            # it would leave only the stale config-flow copy in entry
            # data, and a later database loss would resurrect admins
            # the owner has since removed.
            data[CONF_ADMIN_USER_IDS] = list(admin_default)
        return self.async_create_entry(title="NestQuest", data=data)

    def _current_values(self) -> dict[str, Any]:
        """Resolve current values from entry options, then entry data, then defaults."""
        options = self.options
        entry_data = getattr(self.config_entry, "data", None) or {}
        values: dict[str, Any] = {}
        for key, default in (
            (CONF_HORIZON_DAYS, DEFAULT_HORIZON_DAYS),
            (CONF_DAY_ROLLOVER_TIME, DEFAULT_DAY_ROLLOVER_TIME),
            (CONF_PANEL_IDLE_TIMEOUT, DEFAULT_PANEL_IDLE_TIMEOUT),
            (CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            (CONF_SNAPSHOT_STALENESS, DEFAULT_SNAPSHOT_STALENESS),
            (CONF_NOTIFY_TARGET, ""),
            (CONF_MORNING_SUMMARY_TIME, DEFAULT_MORNING_SUMMARY_TIME),
            (CONF_AFTERNOON_REMINDER_TIME, DEFAULT_AFTERNOON_REMINDER_TIME),
            (CONF_END_OF_DAY_REPORT_TIME, DEFAULT_END_OF_DAY_REPORT_TIME),
            (CONF_MORNING_SUMMARY_ENABLED, DEFAULT_AUTOMATION_ENABLED),
            (CONF_AFTERNOON_REMINDER_ENABLED, DEFAULT_AUTOMATION_ENABLED),
            (CONF_END_OF_DAY_REPORT_ENABLED, DEFAULT_AUTOMATION_ENABLED),
            (CONF_CELEBRATION_ENABLED, DEFAULT_AUTOMATION_ENABLED),
            (CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
            (CONF_PANEL_TOKEN, DEFAULT_PANEL_TOKEN),
        ):
            if key in options:
                values[key] = options[key]
            elif key in entry_data:
                values[key] = entry_data[key]
            else:
                values[key] = default
        return values