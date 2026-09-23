"""Config flow for NestQuest."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class NestQuestConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NestQuest."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> Any:
        """Create the options flow handler for NestQuest."""
        from .options_flow import NestQuestOptionsFlow

        return NestQuestOptionsFlow(config_entry=config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step of the config flow.

        The integration needs no configuration to start (the API
        connection is set in the options flow), so the user input is
        stored as-is.  The former admin-allowlist copy is gone: with
        the database removed the allowlist lives in the API service's
        own store, not on the entry.
        """
        await self.async_set_unique_id(DOMAIN, raise_on_progress=False)
        if self._async_in_progress() or self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(title="NestQuest", data=dict(user_input))