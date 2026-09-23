"""Options flow for NestQuest post-setup settings.

Since the DB removal (Feature 18) the integration is a thin client of
the NestQuest API service: the settings that only served the local
database (the generation horizon, the day rollover, the notification
defaults, the admin allowlist) are gone — the API service owns those in
its own settings store, and the automations take their behaviour from
blueprint inputs.  What remains is what the CLIENT itself consumes: the
panel-plane API connection (base URL + token), the shared coordinator's
refresh interval, the last-good staleness threshold, and the
panel-facing idle timeout.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_API_BASE_URL,
    CONF_PANEL_IDLE_TIMEOUT,
    CONF_PANEL_TOKEN,
    CONF_SNAPSHOT_STALENESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_BASE_URL,
    DEFAULT_PANEL_IDLE_TIMEOUT,
    DEFAULT_PANEL_TOKEN,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .api_client import is_valid_base_url

MIN_PANEL_IDLE_TIMEOUT = 30


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


def _build_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the form schema, pre-filled with the current values.

    The API connection (Feature 18) carries the base URL the API client
    talks to and the panel service token it presents as the Bearer
    credential.  Schema-validated submits always carry every field (the
    defaults pre-fill from the stored values); raw callers omitting one
    keep its stored value (see _async_validate).
    """
    return vol.Schema(
        {
            vol.Required(
                CONF_PANEL_IDLE_TIMEOUT,
                default=current[CONF_PANEL_IDLE_TIMEOUT],
            ): int,
            vol.Required(
                CONF_UPDATE_INTERVAL, default=current[CONF_UPDATE_INTERVAL]
            ): int,
            # The last-good staleness threshold (Feature 18): how long
            # the coordinator keeps serving the cached snapshot after
            # the API stops answering.
            vol.Required(
                CONF_SNAPSHOT_STALENESS,
                default=current[CONF_SNAPSHOT_STALENESS],
            ): int,
            # Panel-plane API connection (Feature 18): the base URL the
            # API client talks to and the panel service token it
            # presents as the Bearer credential.
            vol.Required(
                CONF_API_BASE_URL, default=current[CONF_API_BASE_URL]
            ): str,
            vol.Required(
                CONF_PANEL_TOKEN, default=current[CONF_PANEL_TOKEN]
            ): str,
        }
    )


class NestQuestOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle the options flow for NestQuest."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the NestQuest options."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(self._current_values()),
            )

        errors = _async_validate(user_input, self._current_values())
        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(self._current_values()),
                errors=errors,
            )

        # Every remaining key is stored the fall-back-to-current way, so
        # raw submits that predate a section keep that section's stored
        # values.
        current = self._current_values()
        data: dict[str, Any] = {}
        for key in (
            CONF_PANEL_IDLE_TIMEOUT,
            CONF_UPDATE_INTERVAL,
            CONF_SNAPSHOT_STALENESS,
            CONF_API_BASE_URL,
            CONF_PANEL_TOKEN,
        ):
            data[key] = user_input.get(key, current[key])
        return self.async_create_entry(title="NestQuest", data=data)

    def _current_values(self) -> dict[str, Any]:
        """Resolve current values from entry options, then entry data, then defaults."""
        options = self.options
        entry_data = getattr(self.config_entry, "data", None) or {}
        values: dict[str, Any] = {}
        for key, default in (
            (CONF_PANEL_IDLE_TIMEOUT, DEFAULT_PANEL_IDLE_TIMEOUT),
            (CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            (CONF_SNAPSHOT_STALENESS, DEFAULT_SNAPSHOT_STALENESS),
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
