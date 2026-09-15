"""Options flow for NestQuest post-setup settings."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ADMIN_USER_IDS,
    CONF_DAY_ROLLOVER_TIME,
    CONF_HORIZON_DAYS,
    CONF_PANEL_IDLE_TIMEOUT,
    DEFAULT_DAY_ROLLOVER_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_PANEL_IDLE_TIMEOUT,
    DOMAIN,
)
from .admin_allowlist import list_admin_ids, set_admin_ids

MIN_HORIZON_DAYS = 1
MIN_PANEL_IDLE_TIMEOUT = 30

_TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def _parse_time(value: str) -> bool:
    """Return True when value is a valid 24-hour HH:MM string."""
    return _TIME_PATTERN.fullmatch(value) is not None


def _multi_select(choices: dict[str, str]):
    """A voluptuous validator for a multi-select of ``choices``.

    The mock-only test harness cannot import HA's config-validation
    helpers (they pull in real HA), so this mirrors the shape of
    ``homeassistant.helpers.config_validation.multi_select``: accepts a
    list of keys from ``choices``, returns the list unchanged, rejects
    anything else (None becomes the empty selection).
    """

    def _validate(value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise vol.Invalid("expected a list of selections")
        for item in value:
            if item not in choices:
                raise vol.Invalid(f"{item!r} is not a valid choice")
        return list(value)

    return _validate


def _async_validate(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate user input and return field-level errors instead of raising."""
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

    return errors


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
    re-saves exactly who is already allowed.
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
    }
    if admin_choices is not None:
        fields[
            vol.Optional(
                CONF_ADMIN_USER_IDS, default=list(admin_default or [])
            )
        ] = _multi_select(admin_choices)
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

        errors = _async_validate(user_input)
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
        }
        if admin_ids_present:
            data[CONF_ADMIN_USER_IDS] = admin_ids
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
        ):
            if key in options:
                values[key] = options[key]
            elif key in entry_data:
                values[key] = entry_data[key]
            else:
                values[key] = default
        return values