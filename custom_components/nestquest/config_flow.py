"""Config flow for NestQuest."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class NestQuestConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NestQuest."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step of the config flow."""
        existing = any(
            entry.domain == DOMAIN
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )
        if existing:
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(title="NestQuest", data=user_input)