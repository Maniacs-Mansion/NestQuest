"""Tests for NestQuest service declarations and domain-global handlers.

Since Feature 18 the integration is a client of the NestQuest API
service: the only HA service left is the panel completion path
(``nestquest.complete_quest``, a proxy to the API's panel complete
route).  Every admin service was removed — the admin surface is the
PWA and the API service's admin routes — so these tests pin the
shrunk surface: services.yaml declares nothing else, setup registers
nothing else, and no removed admin service name may come back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.const import (
    DOMAIN,
    DOMAIN_SERVICES,
    SERVICE_COMPLETE_QUEST,
)

SERVICES_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "nestquest"
    / "services.yaml"
)

#: The admin services removed in Feature 18.  None of these names may
#: be registered as an HA service again — the admin surface is the PWA
#: and the API service's admin routes.
REMOVED_ADMIN_SERVICES = (
    "uncomplete_quest",
    "create_quest_definition",
    "update_quest_definition",
    "set_quest_definition_active",
    "set_presence_pattern",
    "create_presence_override",
    "delete_presence_override",
    "export_history_csv",
    "manage_child",
    "regenerate",
)


def _wire(entry, registry):
    return wire_entry_to_registry(entry, registry)


def _service_section(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*$", text, re.MULTILINE)
    assert match is not None, f"services.yaml must declare {name!r}"
    section = text[match.end() :]
    next_service = re.search(r"^(?![#\s])\w+:\s*$", section, re.MULTILINE)
    if next_service is not None:
        section = section[: next_service.start()]
    return section


def test_services_yaml_exists() -> None:
    assert SERVICES_PATH.exists(), f"services.yaml missing at {SERVICES_PATH}"


def test_services_yaml_declares_every_canonical_service() -> None:
    text = SERVICES_PATH.read_text(encoding="utf-8")
    declared = re.findall(r"^(?![#\s])(\w+):\s*$", text, re.MULTILINE)
    assert declared == list(DOMAIN_SERVICES) or set(declared) == set(
        DOMAIN_SERVICES
    )
    for name in DOMAIN_SERVICES:
        section = _service_section(text, name)
        assert re.search(r"description:", section), (
            f"{name} must carry a description"
        )


def test_services_yaml_no_longer_declares_removed_admin_services() -> None:
    """The admin services are gone from the HA service surface."""
    text = SERVICES_PATH.read_text(encoding="utf-8")
    for name in REMOVED_ADMIN_SERVICES:
        assert not re.search(rf"^{name}:\s*$", text, re.MULTILINE), (
            f"removed admin service {name!r} must not be declared"
        )


def test_services_yaml_canonical_services_declare_fields() -> None:
    text = SERVICES_PATH.read_text(encoding="utf-8")
    for name in DOMAIN_SERVICES:
        section = _service_section(text, name)
        assert "fields:" in section, f"{name} must declare fields"


async def test_only_complete_quest_registered_after_setup(
    hass, make_entry
) -> None:
    """Setup registers exactly the panel completion service — and no
    removed admin service under any name."""
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    for service in DOMAIN_SERVICES:
        assert hass.services.has_service(DOMAIN, service), service
    for service in REMOVED_ADMIN_SERVICES:
        assert not hass.services.has_service(DOMAIN, service), service


async def test_unload_last_entry_removes_all_services(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    for service in DOMAIN_SERVICES:
        assert not hass.services.has_service(DOMAIN, service), service


async def test_unload_one_of_two_entries_keeps_services(
    hass, make_entry
) -> None:
    entry_a = _wire(make_entry(entry_id="entry_a"), hass.registry)
    entry_b = _wire(make_entry(entry_id="entry_b"), hass.registry)
    assert await async_setup_entry(hass, entry_a) is True
    assert await async_setup_entry(hass, entry_b) is True
    assert await async_unload_entry(hass, entry_a) is True
    for service in DOMAIN_SERVICES:
        assert hass.services.has_service(DOMAIN, service), service
    assert await async_unload_entry(hass, entry_b) is True
    for service in DOMAIN_SERVICES:
        assert not hass.services.has_service(DOMAIN, service), service


async def test_invalid_schema_data_surfaces_as_error(hass, make_entry) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    with pytest.raises((vol.Invalid, ValueError, HomeAssistantError)):
        await hass.services.call(DOMAIN, SERVICE_COMPLETE_QUEST, {})
    with pytest.raises((vol.Invalid, ValueError, HomeAssistantError)):
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {"instance_id": True, "actor": "panel", "actor_child_id": 1},
        )


async def test_scheduled_internals_never_call_the_service_layer(
    hass, make_entry
) -> None:
    """The daily rollover and startup backfill run the materialization
    as direct function calls; they never widen the service gate."""
    import custom_components.nestquest as nestquest

    assert not hasattr(nestquest, "_run_horizon_materialization_service")
    source = Path(nestquest.__file__).read_text(encoding="utf-8")
    assert "hass.services.call" not in source, (
        "scheduled internals must call the materialization directly, "
        "never through hass.services.call"
    )