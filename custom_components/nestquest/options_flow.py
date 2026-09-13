"""Options flow for NestQuest post-setup settings."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DAY_ROLLOVER_TIME,
    CONF_HORIZON_DAYS,
    CONF_PANEL_IDLE_TIMEOUT,
    DEFAULT_DAY_ROLLOVER_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_PANEL_IDLE_TIMEOUT,
)

try:
    import voluptuous as vol
except ImportError:
    vol = None

MIN_HORIZON_DAYS = 1
MIN_PANEL_IDLE_TIMEOUT = 30
_TIME_PART_LENGTH = 2


def _parse_time(value: str) -> bool:
    """Return True when value is a valid 24-hour HH:MM string."""
    parts = value.split(":")
    if len(parts) != 2:
        return False
    hours, minutes = parts
    if len(hours) != _TIME_PART_LENGTH or len(minutes) != _TIME_PART_LENGTH:
        return False
    if not hours.isdigit() or not minutes.isdigit():
        return False
    return int(hours) <= 23 and int(minutes) <= 59


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


def _build_schema(current: dict[str, Any]) -> Any:
    """Build the form schema, pre-filled with the current values."""
    if vol is not None:
        return vol.Schema(
            {
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
        )
    return {
        CONF_HORIZON_DAYS: current[CONF_HORIZON_DAYS],
        CONF_DAY_ROLLOVER_TIME: current[CONF_DAY_ROLLOVER_TIME],
        CONF_PANEL_IDLE_TIMEOUT: current[CONF_PANEL_IDLE_TIMEOUT],
    }


class NestQuestOptionsFlow(config_entries.OptionsFlow):
    """Handle the options flow for NestQuest."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the NestQuest options."""
        if user_input is None:
            return self.async_show_form(
                step_id="init", data_schema=_build_schema(self._current_values())
            )

        errors = _async_validate(user_input)
        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=_build_schema(self._current_values()),
                errors=errors,
            )

        return self.async_create_entry(
            title="NestQuest",
            data={
                CONF_HORIZON_DAYS: user_input[CONF_HORIZON_DAYS],
                CONF_DAY_ROLLOVER_TIME: user_input[CONF_DAY_ROLLOVER_TIME],
                CONF_PANEL_IDLE_TIMEOUT: user_input[CONF_PANEL_IDLE_TIMEOUT],
            },
        )

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