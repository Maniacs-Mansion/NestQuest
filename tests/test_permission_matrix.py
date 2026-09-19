"""Feature 09 permission test matrix across every registered service."""
from __future__ import annotations

import datetime

import pytest
from homeassistant.exceptions import Unauthorized

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    DEFAULT_HORIZON_DAYS,
    DOMAIN,
    DOMAIN_SERVICES,
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
from custom_components.nestquest.service_policy import (
    ADMIN_ONLY,
    OPEN,
    SERVICE_POLICY,
)

ADMIN_ID = "admin-1"
ADMIN_CTX = {"user_id": ADMIN_ID}
NON_ADMIN_ID = "non-admin"
NON_ADMIN_CTX = {"user_id": NON_ADMIN_ID}
KIOSK_ID = "kiosk-panel"
KIOSK_CTX = {"user_id": KIOSK_ID}


def test_every_registered_service_is_in_the_operation_registry() -> None:
    """The registry is total: a service outside it could never be gated."""
    missing = [
        service for service in DOMAIN_SERVICES if service not in SERVICE_POLICY
    ]
    extra = [
        service for service in SERVICE_POLICY if service not in DOMAIN_SERVICES
    ]
    assert not missing, f"registered but ungated: {missing}"
    assert not extra, f"gated but never registered: {extra}"
    assert set(SERVICE_POLICY.values()) == {OPEN, ADMIN_ONLY}


async def _setup(hass, make_entry, *, admin=True):
    data = {CONF_ADMIN_USER_IDS: [ADMIN_ID]} if admin else {}
    entry = wire_entry_to_registry(make_entry(data=data), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    return entry


async def _seed(hass, entry) -> dict:
    """Seed one child, one definition, and materialized instances."""
    from custom_components.nestquest.children import list_children
    from custom_components.nestquest.dao_instances import QuestInstancesDao

    database = entry.runtime_data.database
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
        context=ADMIN_CTX,
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_QUEST_DEFINITION,
        {
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [(await list_children(database))[0].id],
            "windows": ["morning"],
        },
        context=ADMIN_CTX,
    )
    await hass.services.call(DOMAIN, SERVICE_REGENERATE, context=ADMIN_CTX)
    child = (await list_children(database))[0]
    today = datetime.date.today().isoformat()
    end = (
        datetime.date.today() + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
    ).isoformat()
    instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today, end
    )
    assert instances
    from custom_components.nestquest.dao_presence import (
        PresenceOverridesDao,
    )

    return {
        "child_id": child.id,
        "instance_id": instances[0].id,
        "definition_id": instances[0].definition_id,
        "override": await PresenceOverridesDao(database).create(
            child.id, "2027-01-01", "2027-01-02", False
        ),
        "today": today,
        "database": database,
    }


def _admin_success_payload(service: str, ctx: dict) -> dict | None:
    """A schema-valid, end-to-end-successful payload per admin service."""
    if service == SERVICE_UNCOMPLETE_QUEST:
        return {"instance_id": ctx["instance_id"], "actor": "user"}
    if service == SERVICE_CREATE_QUEST_DEFINITION:
        return {
            "title": "Second quest",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [ctx["child_id"]],
            "windows": ["afternoon"],
        }
    if service == SERVICE_UPDATE_QUEST_DEFINITION:
        return {"definition_id": ctx["definition_id"], "title": "Brush teeth 2"}
    if service == SERVICE_SET_QUEST_DEFINITION_ACTIVE:
        return {"definition_id": ctx["definition_id"], "is_active": False}
    if service == SERVICE_SET_PRESENCE_PATTERN:
        return {
            "child_id": ctx["child_id"],
            "cycle_length_weeks": 1,
            "anchor_date": ctx["today"],
            "pattern": {0: [0, 1, 2, 3, 4, 5, 6]},
        }
    if service == SERVICE_CREATE_PRESENCE_OVERRIDE:
        return {
            "child_id": ctx["child_id"],
            "start_date": "2027-03-01",
            "end_date": "2027-03-02",
            "is_present": False,
        }
    if service == SERVICE_DELETE_PRESENCE_OVERRIDE:
        return {"override_id": ctx["override"].id}
    if service == SERVICE_EXPORT_HISTORY_CSV:
        return None  # raises HomeAssistantError (Feature 13) — not Unauthorized
    if service == SERVICE_MANAGE_CHILD:
        return {"action": "create", "display_name": "Bo"}
    if service == SERVICE_REGENERATE:
        return {}
    raise AssertionError(f"unexpected service {service}")


_ADMIN_ONLY = [
    service for service, policy in SERVICE_POLICY.items() if policy == ADMIN_ONLY
]


@pytest.mark.parametrize("service", _ADMIN_ONLY)
async def test_admin_succeeds_on_every_admin_only_service(
    hass, make_entry, service
) -> None:
    from homeassistant.exceptions import HomeAssistantError

    entry = await _setup(hass, make_entry)
    ctx = await _seed(hass, entry)
    if service == SERVICE_EXPORT_HISTORY_CSV:
        # The gate passes; the Feature 13 stub raises its "not
        # implemented" HomeAssistantError — NOT Unauthorized.
        with pytest.raises(HomeAssistantError, match="Feature 13"):
            await hass.services.call(
                DOMAIN, service, None, context=ADMIN_CTX
            )
        return
    await hass.services.call(
        DOMAIN, service, _admin_success_payload(service, ctx), context=ADMIN_CTX
    )


@pytest.mark.parametrize("service", _ADMIN_ONLY)
async def test_non_admin_refused_on_every_admin_only_service(
    hass, make_entry, service
) -> None:
    entry = await _setup(hass, make_entry)
    ctx = await _seed(hass, entry)
    if service != SERVICE_EXPORT_HISTORY_CSV:
        await hass.services.call(
            DOMAIN,
            service,
            _admin_success_payload(service, ctx),
            context=ADMIN_CTX,
        )
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN,
            service,
            _admin_success_payload(service, ctx),
            context=NON_ADMIN_CTX,
        )


async def test_non_admin_allowed_on_complete_quest(hass, make_entry) -> None:
    from custom_components.nestquest.completion import instance_state

    entry = await _setup(hass, make_entry)
    ctx = await _seed(hass, entry)
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": ctx["instance_id"],
            "actor": "panel",
            "actor_child_id": ctx["child_id"],
        },
        context=NON_ADMIN_CTX,
    )
    assert (
        await instance_state(ctx["database"], ctx["instance_id"]) == "done"
    )


async def test_kiosk_refused_on_uncomplete_and_regenerate(
    hass, make_entry
) -> None:
    entry = await _setup(hass, make_entry)
    ctx = await _seed(hass, entry)
    from custom_components.nestquest.admin_allowlist import list_admin_ids

    assert KIOSK_ID not in await list_admin_ids(ctx["database"])
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN,
            SERVICE_UNCOMPLETE_QUEST,
            {"instance_id": ctx["instance_id"], "actor": "user"},
            context=KIOSK_CTX,
        )
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN, SERVICE_REGENERATE, context=KIOSK_CTX
        )