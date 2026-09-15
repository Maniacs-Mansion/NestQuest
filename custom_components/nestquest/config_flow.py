"""Config flow for NestQuest."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ADMIN_USER_IDS, DOMAIN


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

        The HA user completing the flow is persisted into the entry
        data as the initial admin allowlist copy: real HA does not
        guarantee the flow context survives to setup, and entry data is
        the persisted record first setup seeds from — the owner is
        never locked out.
        """
        await self.async_set_unique_id(DOMAIN, raise_on_progress=False)
        if self._async_in_progress() or self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user")

        data = dict(user_input)
        flow_user_id = (
            self.context.get("user_id")
            if isinstance(self.context, dict)
            else None
        )
        if flow_user_id:
            data[CONF_ADMIN_USER_IDS] = [flow_user_id]
        return self.async_create_entry(title="NestQuest", data=data)