"""The domain-global ``nestquest.complete_quest`` service (Feature 18).

Registration is domain-scoped and happens once (see
:func:`async_register_services`).  Since Feature 18 the integration is
a client of the NestQuest API service, so ``complete_quest`` proxies
to the API's panel complete route through the entry's shared API
client instead of writing any database.  The former HA admin services
(uncomplete, quest-definition and presence management, CSV export,
child management, regenerate) are removed: the admin surface is the
PWA and the API service's admin routes, so the only HA service left is
the panel completion path.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api_client import NestQuestApiError
from .const import (
    DOMAIN,
    DOMAIN_SERVICES,
    SERVICE_COMPLETE_QUEST,
)

FindRuntime = Callable[[HomeAssistant], Any]
ServiceHandler = Callable[[Any], Awaitable[None]]

ACTOR_PANEL = "panel"
ACTOR_USER = "user"


def _strict_int(value: object) -> int:
    """Reject bools and non-ints; voluptuous ``int`` would accept True."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid(f"expected int, got {value!r}")
    return value


SCHEMA_COMPLETE_QUEST = vol.Schema(
    {
        vol.Required("instance_id"): _strict_int,
        vol.Required("actor"): vol.In([ACTOR_PANEL, ACTOR_USER]),
        vol.Optional("actor_child_id"): _strict_int,
        vol.Optional("actor_user_id"): str,
    }
)


def _require_runtime(hass: HomeAssistant, find_runtime: FindRuntime):
    runtime = find_runtime(hass)
    if runtime is None:
        raise HomeAssistantError(
            "NestQuest is not loaded; cannot run this service"
        )
    return runtime


async def _refresh_entities(runtime: Any) -> None:
    """Force an immediate coordinator refresh after the service call.

    Only the SERVICE path calls this — the scheduled materialize and
    rollover internals are direct function calls and never widen this
    gate — so the entities reflect a completion the moment the service
    call returns instead of waiting for the poll interval.
    """
    coordinator = getattr(runtime, "coordinator", None)
    if coordinator is not None:
        await coordinator.async_refresh()


def _actor_kwargs(call: Any) -> dict[str, Any]:
    actor = call.data["actor"]
    if actor == ACTOR_PANEL:
        actor_child_id = call.data.get("actor_child_id")
        if actor_child_id is None:
            raise HomeAssistantError(
                "actor_child_id is required when actor is panel"
            )
        return {
            "actor_source": ACTOR_PANEL,
            "actor_child_id": actor_child_id,
            "actor_user_id": None,
        }
    context = getattr(call, "context", None)
    user_id = getattr(context, "user_id", None) if context is not None else None
    if not user_id:
        user_id = call.data.get("actor_user_id")
    return {
        "actor_source": ACTOR_USER,
        "actor_user_id": user_id,
        "actor_child_id": None,
    }


def _with_errors(handler: ServiceHandler) -> ServiceHandler:
    async def _wrapped(call: Any) -> None:
        try:
            await handler(call)
        except HomeAssistantError:
            raise
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    return _wrapped


def _complete_quest(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        instance_id = call.data["instance_id"]
        # The panel contract (decision 9): a tap completes as the
        # tapped child profile, the only actor shape the API's panel
        # route accepts.  The payload schema is unchanged — the panel
        # cards call it with instance_id, actor=panel, actor_child_id.
        actor = _actor_kwargs(call)
        if actor["actor_source"] != ACTOR_PANEL:
            raise HomeAssistantError(
                "nestquest.complete_quest completes through the API's "
                "panel route as the tapped child profile; actor must "
                "be 'panel' with actor_child_id"
            )
        # The entry's ONE shared API client (built at setup): the
        # coordinator's snapshot poll, the SSE subscription, and this
        # proxy all ride the same instance.  An entry with no panel
        # token runs the unconfigured stub, which has no completion
        # surface — fail fast with a clear, token-free message.
        complete_instance = getattr(
            getattr(runtime.coordinator, "api_client", None),
            "complete_instance",
            None,
        )
        if complete_instance is None:
            raise HomeAssistantError(
                "NestQuest API is not configured; cannot complete a "
                "quest"
            )
        try:
            await complete_instance(instance_id, actor["actor_child_id"])
        except NestQuestApiError as err:
            # The typed API failure surfaces as a service error the
            # caller sees — never swallowed, never retried here.  The
            # typed message names method, path, and status only; the
            # panel token never appears in it.
            raise HomeAssistantError(
                f"NestQuest quest completion failed: {err}"
            ) from err
        # NO local completion write and NO local event: the API service
        # emits the transition on its SSE stream and the integration's
        # subscription re-fires it on the bus — firing it here too
        # would double-fire.  The immediate refresh keeps the old
        # behaviour where the sensors reflect the completion the
        # moment the service call returns instead of waiting for the
        # poll interval.
        await _refresh_entities(runtime)

    return _with_errors(_handler)


def async_register_services(
    hass: HomeAssistant,
    *,
    find_runtime: FindRuntime,
) -> None:
    """Register the panel completion service once at domain scope.

    The one remaining HA service is the panel completion path; every
    admin operation moved to the API service's admin routes, so there
    is no permission gate to apply here.
    """
    if hass.services.has_service(DOMAIN, SERVICE_COMPLETE_QUEST):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        _complete_quest(hass, find_runtime),
        schema=SCHEMA_COMPLETE_QUEST,
    )


def async_deregister_services(hass: HomeAssistant) -> None:
    """Remove every canonical service when the last entry unloads."""
    for service in DOMAIN_SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)