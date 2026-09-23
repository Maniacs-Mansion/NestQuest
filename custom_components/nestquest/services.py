"""Domain-global NestQuest service schemas and handlers (Feature 09).

Registration is domain-scoped and happens once (see
:func:`async_register_services`); handlers resolve a live database at
call time through the injected ``find_runtime`` callable.  Permission
checks are Feature 09 later tasks — this module only validates payload
shape and forwards to the Feature 03/06/08 business layers (the
presence writes included, through :mod:`.presence_management` — the
ONE implementation the API admin plane shares).  Since Feature 18 the
integration is a client of the NestQuest API service, so
``complete_quest`` proxies to the API's panel complete route through
the entry's shared API client instead of writing any database.
``export_history_csv`` is registered with a schema but raises until
Feature 13.  ``regenerate`` is supplied by the caller so
the Feature 07 handler stays the one in ``__init__``.
"""
from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import children as children_layer
from . import completion as completion_layer
from . import presence_management as presence_management_layer
from . import quest_definitions as quest_definitions_layer
from .api_client import NestQuestApiError
from .const import (
    DOMAIN,
    DOMAIN_SERVICES,
    QUEST_WINDOWS,
    SERVICE_COMPLETE_QUEST,
    SERVICE_CREATE_PRESENCE_OVERRIDE,
    SERVICE_CREATE_QUEST_DEFINITION,
    SERVICE_DELETE_PRESENCE_OVERRIDE,
    SERVICE_EXPORT_HISTORY_CSV,
    SERVICE_MANAGE_CHILD,
    SERVICE_REGENERATE,
    SERVICE_SET_PRESENCE_PATTERN,
    SERVICE_SET_QUEST_DEFINITION_ACTIVE,
    SERVICE_UNCOMPLETE_QUEST,
    SERVICE_UPDATE_QUEST_DEFINITION,
)
from .events import fire_quest_uncompleted
from .permissions import permission_gate
from .recurrence import ScheduleRule
from .service_policy import SERVICE_POLICY

FindRuntime = Callable[[HomeAssistant], Any]
ServiceHandler = Callable[[Any], Awaitable[None]]

ACTOR_PANEL = "panel"
ACTOR_USER = "user"
MANAGE_CHILD_CREATE = "create"
MANAGE_CHILD_EDIT = "edit"
MANAGE_CHILD_SET_ACTIVE = "set_active"
MANAGE_CHILD_REORDER = "reorder"


def _strict_int(value: object) -> int:
    """Reject bools and non-ints; voluptuous ``int`` would accept True."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid(f"expected int, got {value!r}")
    return value


def _strict_bool(value: object) -> bool:
    """Reject ints and other truthy values; require a real bool."""
    if type(value) is not bool:
        raise vol.Invalid(f"expected bool, got {value!r}")
    return value


def _weekday_list(value: object) -> list[int]:
    if type(value) is not list:
        raise vol.Invalid(f"expected a list of weekday ints, got {value!r}")
    return [_strict_int(item) for item in value]


def _presence_pattern(value: object) -> dict[int, list[int]]:
    if not isinstance(value, dict):
        raise vol.Invalid(f"pattern must be a mapping, got {value!r}")
    pattern: dict[int, list[int]] = {}
    for week, days in value.items():
        if isinstance(week, str):
            try:
                week_index = int(week)
            except ValueError as err:
                raise vol.Invalid(
                    f"pattern week index must be an integer, got {week!r}"
                ) from err
            if str(week_index) != week:
                raise vol.Invalid(
                    f"pattern week index must be an integer, got {week!r}"
                )
        else:
            week_index = _strict_int(week)
        pattern[week_index] = _weekday_list(days)
    return pattern


def _window_entry(value: object) -> str | tuple[str, str | None]:
    if isinstance(value, str):
        if value not in QUEST_WINDOWS:
            raise vol.Invalid(f"unknown window {value!r}")
        return value
    if isinstance(value, dict):
        parsed = vol.Schema(
            {
                vol.Required("window"): vol.In(QUEST_WINDOWS),
                vol.Optional("due_time"): str,
            }
        )(value)
        due_time = parsed.get("due_time")
        if due_time is None:
            return parsed["window"]
        return (parsed["window"], due_time)
    raise vol.Invalid(
        f"windows entry must be a window name or object, got {value!r}"
    )


def _windows(value: object) -> list[str | tuple[str, str | None]]:
    if type(value) is not list:
        raise vol.Invalid(f"windows must be a list, got {value!r}")
    if not value:
        raise vol.Invalid("windows must not be empty")
    return [_window_entry(entry) for entry in value]


def _int_list(value: object) -> list[int]:
    if type(value) is not list:
        raise vol.Invalid(f"expected a list of ints, got {value!r}")
    return [_strict_int(item) for item in value]


def _rule_dict(value: object) -> dict:
    if not isinstance(value, dict):
        raise vol.Invalid(f"rule must be a dict, got {value!r}")
    return value


SCHEMA_COMPLETE_QUEST = vol.Schema(
    {
        vol.Required("instance_id"): _strict_int,
        vol.Required("actor"): vol.In([ACTOR_PANEL, ACTOR_USER]),
        vol.Optional("actor_child_id"): _strict_int,
        vol.Optional("actor_user_id"): str,
    }
)

SCHEMA_UNCOMPLETE_QUEST = SCHEMA_COMPLETE_QUEST

SCHEMA_CREATE_QUEST_DEFINITION = vol.Schema(
    {
        vol.Required("title"): str,
        vol.Required("rule"): _rule_dict,
        vol.Required("assignee_child_ids"): vol.All(
            _int_list, vol.Length(min=1)
        ),
        vol.Required("windows"): _windows,
        vol.Optional("description"): str,
        vol.Optional("icon"): str,
    }
)

SCHEMA_UPDATE_QUEST_DEFINITION = vol.Schema(
    {
        vol.Required("definition_id"): _strict_int,
        vol.Optional("title"): str,
        vol.Optional("description"): vol.Any(str, None),
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("rule"): _rule_dict,
        vol.Optional("windows"): _windows,
    }
)

SCHEMA_SET_QUEST_DEFINITION_ACTIVE = vol.Schema(
    {
        vol.Required("definition_id"): _strict_int,
        vol.Required("is_active"): _strict_bool,
    }
)

SCHEMA_SET_PRESENCE_PATTERN = vol.Schema(
    {
        vol.Required("child_id"): _strict_int,
        vol.Required("cycle_length_weeks"): _strict_int,
        vol.Required("anchor_date"): str,
        vol.Required("pattern"): _presence_pattern,
    }
)

SCHEMA_CREATE_PRESENCE_OVERRIDE = vol.Schema(
    {
        vol.Required("child_id"): _strict_int,
        vol.Required("start_date"): str,
        vol.Required("end_date"): str,
        vol.Required("is_present"): _strict_bool,
        vol.Optional("note"): str,
    }
)

SCHEMA_DELETE_PRESENCE_OVERRIDE = vol.Schema(
    {
        vol.Required("override_id"): _strict_int,
    }
)

SCHEMA_EXPORT_HISTORY_CSV = vol.Schema({})

SCHEMA_MANAGE_CHILD = vol.Schema(
    {
        vol.Required("action"): vol.In(
            [
                MANAGE_CHILD_CREATE,
                MANAGE_CHILD_EDIT,
                MANAGE_CHILD_SET_ACTIVE,
                MANAGE_CHILD_REORDER,
            ]
        ),
        vol.Optional("child_id"): _strict_int,
        vol.Optional("display_name"): str,
        vol.Optional("colour"): str,
        vol.Optional("avatar_ref"): str,
        vol.Optional("sort_order"): _strict_int,
        vol.Optional("is_active"): _strict_bool,
        vol.Optional("ordered_ids"): _int_list,
    }
)


def _require_runtime(hass: HomeAssistant, find_runtime: FindRuntime):
    runtime = find_runtime(hass)
    if runtime is None:
        raise HomeAssistantError(
            "NestQuest has no live database; cannot run this service"
        )
    return runtime


async def _refresh_entities(runtime: Any) -> None:
    """Force an immediate coordinator refresh after a service mutation.

    Only the SERVICE paths call this — the scheduled materialize and
    rollover internals are direct function calls and never widen this
    gate — so entities reflect a completion the moment the service
    call returns instead of waiting for the poll interval.
    """
    coordinator = getattr(runtime, "coordinator", None)
    if coordinator is not None:
        await coordinator.async_refresh()


def _generation_kwargs(hass: HomeAssistant, runtime: Any) -> dict[str, Any]:
    time_zone = ZoneInfo(hass.config.time_zone)
    today = datetime.datetime.now(time_zone).date()
    return {"today": today, "horizon_days": runtime.settings.horizon_days}


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


def _uncomplete_quest(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        instance_id = call.data["instance_id"]
        result = await completion_layer.uncomplete_instance(
            runtime.database,
            instance_id,
            **_actor_kwargs(call),
        )
        if result.appended:
            await fire_quest_uncompleted(
                hass, runtime.database, instance_id
            )
            await _refresh_entities(runtime)

    return _with_errors(_handler)


def _create_quest_definition(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        database = _require_runtime(hass, find_runtime).database
        data = call.data
        await quest_definitions_layer.create_quest_definition(
            database,
            data["title"],
            ScheduleRule.from_dict(data["rule"]),
            data["assignee_child_ids"],
            data["windows"],
            description=data.get("description"),
            icon=data.get("icon"),
        )

    return _with_errors(_handler)


def _update_quest_definition(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        data = call.data
        kwargs: dict[str, Any] = _generation_kwargs(hass, runtime)
        if "title" in data:
            kwargs["title"] = data["title"]
        if "description" in data:
            kwargs["description"] = data["description"]
        if "icon" in data:
            kwargs["icon"] = data["icon"]
        if "rule" in data:
            kwargs["rule"] = ScheduleRule.from_dict(data["rule"])
        if "windows" in data:
            kwargs["windows"] = data["windows"]
        await quest_definitions_layer.edit_quest_definition(
            runtime.database, data["definition_id"], **kwargs
        )

    return _with_errors(_handler)


def _set_quest_definition_active(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        await quest_definitions_layer.set_quest_definition_active(
            runtime.database,
            call.data["definition_id"],
            call.data["is_active"],
            **_generation_kwargs(hass, runtime),
        )

    return _with_errors(_handler)


def _set_presence_pattern(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        data = call.data
        await presence_management_layer.set_presence_schedule(
            runtime.database,
            data["child_id"],
            data["cycle_length_weeks"],
            data["anchor_date"],
            data["pattern"],
            **_generation_kwargs(hass, runtime),
        )

    return _with_errors(_handler)


def _create_presence_override(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        data = call.data
        await presence_management_layer.create_presence_override(
            runtime.database,
            data["child_id"],
            data["start_date"],
            data["end_date"],
            data["is_present"],
            note=data.get("note"),
            **_generation_kwargs(hass, runtime),
        )

    return _with_errors(_handler)


def _delete_presence_override(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        runtime = _require_runtime(hass, find_runtime)
        await presence_management_layer.delete_presence_override(
            runtime.database,
            call.data["override_id"],
            **_generation_kwargs(hass, runtime),
        )

    return _with_errors(_handler)


async def _export_history_csv(_call: Any) -> None:
    raise HomeAssistantError(
        "CSV history export is not implemented until Feature 13"
    )


def _manage_child(
    hass: HomeAssistant, find_runtime: FindRuntime
) -> ServiceHandler:
    async def _handler(call: Any) -> None:
        database = _require_runtime(hass, find_runtime).database
        data = call.data
        action = data["action"]
        if action == MANAGE_CHILD_CREATE:
            display_name = data.get("display_name")
            if display_name is None:
                raise HomeAssistantError(
                    "display_name is required when action is create"
                )
            kwargs: dict[str, Any] = {}
            if "colour" in data:
                kwargs["colour"] = data["colour"]
            if "avatar_ref" in data:
                kwargs["avatar_ref"] = data["avatar_ref"]
            if "sort_order" in data:
                kwargs["sort_order"] = data["sort_order"]
            await children_layer.create_child(
                database, display_name, **kwargs
            )
            return
        if action == MANAGE_CHILD_EDIT:
            child_id = data.get("child_id")
            if child_id is None:
                raise HomeAssistantError(
                    "child_id is required when action is edit"
                )
            kwargs = {}
            if "display_name" in data:
                kwargs["display_name"] = data["display_name"]
            if "colour" in data:
                kwargs["colour"] = data["colour"]
            if "avatar_ref" in data:
                kwargs["avatar_ref"] = data["avatar_ref"]
            if "sort_order" in data:
                kwargs["sort_order"] = data["sort_order"]
            await children_layer.edit_child(database, child_id, **kwargs)
            return
        if action == MANAGE_CHILD_SET_ACTIVE:
            child_id = data.get("child_id")
            is_active = data.get("is_active")
            if child_id is None:
                raise HomeAssistantError(
                    "child_id is required when action is set_active"
                )
            if is_active is None:
                raise HomeAssistantError(
                    "is_active is required when action is set_active"
                )
            await children_layer.set_child_active(
                database, child_id, is_active
            )
            return
        ordered_ids = data.get("ordered_ids")
        if ordered_ids is None:
            raise HomeAssistantError(
                "ordered_ids is required when action is reorder"
            )
        await children_layer.reorder_children(database, ordered_ids)

    return _with_errors(_handler)


def async_register_services(
    hass: HomeAssistant,
    *,
    find_runtime: FindRuntime,
    regenerate_handler: ServiceHandler,
) -> None:
    """Register every canonical service once at domain scope.

    Every service — regenerate included — passes through the Feature
    09 permission gate before its handler runs; the gate reads
    :data:`~.service_policy.SERVICE_POLICY`, so no service can be
    registered exempt from the policy.
    """
    if hass.services.has_service(DOMAIN, SERVICE_REGENERATE):
        return
    gate = permission_gate
    specs: list[tuple[str, ServiceHandler, object]] = [
        (SERVICE_REGENERATE, regenerate_handler, None),
        (
            SERVICE_COMPLETE_QUEST,
            _complete_quest(hass, find_runtime),
            SCHEMA_COMPLETE_QUEST,
        ),
        (
            SERVICE_UNCOMPLETE_QUEST,
            _uncomplete_quest(hass, find_runtime),
            SCHEMA_UNCOMPLETE_QUEST,
        ),
        (
            SERVICE_CREATE_QUEST_DEFINITION,
            _create_quest_definition(hass, find_runtime),
            SCHEMA_CREATE_QUEST_DEFINITION,
        ),
        (
            SERVICE_UPDATE_QUEST_DEFINITION,
            _update_quest_definition(hass, find_runtime),
            SCHEMA_UPDATE_QUEST_DEFINITION,
        ),
        (
            SERVICE_SET_QUEST_DEFINITION_ACTIVE,
            _set_quest_definition_active(hass, find_runtime),
            SCHEMA_SET_QUEST_DEFINITION_ACTIVE,
        ),
        (
            SERVICE_SET_PRESENCE_PATTERN,
            _set_presence_pattern(hass, find_runtime),
            SCHEMA_SET_PRESENCE_PATTERN,
        ),
        (
            SERVICE_CREATE_PRESENCE_OVERRIDE,
            _create_presence_override(hass, find_runtime),
            SCHEMA_CREATE_PRESENCE_OVERRIDE,
        ),
        (
            SERVICE_DELETE_PRESENCE_OVERRIDE,
            _delete_presence_override(hass, find_runtime),
            SCHEMA_DELETE_PRESENCE_OVERRIDE,
        ),
        (
            SERVICE_EXPORT_HISTORY_CSV,
            _export_history_csv,
            SCHEMA_EXPORT_HISTORY_CSV,
        ),
        (
            SERVICE_MANAGE_CHILD,
            _manage_child(hass, find_runtime),
            SCHEMA_MANAGE_CHILD,
        ),
    ]

    def _database_of(_call: Any) -> Any:
        return _require_runtime(hass, find_runtime).database

    for service, handler, schema in specs:
        gated = gate(
            service, SERVICE_POLICY[service], _database_of
        )(handler)
        hass.services.async_register(DOMAIN, service, gated, schema=schema)


def async_deregister_services(hass: HomeAssistant) -> None:
    """Remove every canonical service when the last entry unloads."""
    for service in DOMAIN_SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
