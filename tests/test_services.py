"""Tests for NestQuest service declarations and domain-global handlers."""
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
    SERVICE_CREATE_PRESENCE_OVERRIDE,
    SERVICE_CREATE_QUEST_DEFINITION,
    SERVICE_DELETE_PRESENCE_OVERRIDE,
    SERVICE_EXPORT_HISTORY_CSV,
    SERVICE_MANAGE_CHILD,
    SERVICE_REGENERATE,
    SERVICE_SET_PRESENCE_PATTERN,
    SERVICE_SET_QUEST_DEFINITION_ACTIVE,
    SERVICE_UNCOMPLETE_QUEST,
)

SERVICES_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "nestquest"
    / "services.yaml"
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


def test_services_yaml_declares_regenerate() -> None:
    text = SERVICES_PATH.read_text(encoding="utf-8")
    assert re.search(r"^regenerate:\s*$", text, re.MULTILINE), (
        "services.yaml must declare the 'regenerate' service"
    )


def test_services_yaml_regenerate_has_description_and_no_fields() -> None:
    """The regenerate service is documented with a clear description and no
    required fields (there is no ``fields`` block under it)."""
    text = SERVICES_PATH.read_text(encoding="utf-8")
    section = _service_section(text, "regenerate")
    assert re.search(r"description:", section), (
        "regenerate must carry a description"
    )
    assert "fields:" not in section, (
        "regenerate declares no required fields"
    )


def test_services_yaml_other_services_declare_fields() -> None:
    text = SERVICES_PATH.read_text(encoding="utf-8")
    for name in DOMAIN_SERVICES:
        if name in (SERVICE_REGENERATE, SERVICE_EXPORT_HISTORY_CSV):
            continue
        section = _service_section(text, name)
        assert "fields:" in section, f"{name} must declare fields"


async def test_all_canonical_services_registered_after_setup(
    hass, make_entry
) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    for service in DOMAIN_SERVICES:
        assert hass.services.has_service(DOMAIN, service), service


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


async def test_manage_child_create_persists_child(hass, make_entry) -> None:
    from custom_components.nestquest.children import list_children

    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
    )
    children = await list_children(entry.runtime_data.database)
    assert [child.display_name for child in children] == ["Ada"]


async def test_create_and_set_quest_definition_active(
    hass, make_entry
) -> None:
    from custom_components.nestquest.children import list_children
    from custom_components.nestquest.quest_definitions import (
        list_active_definitions,
    )
    from custom_components.nestquest.dao_rules import QuestDefinitionsDao

    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
    )
    child = (await list_children(entry.runtime_data.database))[0]
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_QUEST_DEFINITION,
        {
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child.id],
            "windows": ["morning"],
        },
    )
    active = await list_active_definitions(entry.runtime_data.database)
    assert len(active) == 1
    definition_id = active[0].definition.id
    await hass.services.call(
        DOMAIN,
        SERVICE_SET_QUEST_DEFINITION_ACTIVE,
        {"definition_id": definition_id, "is_active": False},
    )
    assert await list_active_definitions(entry.runtime_data.database) == []
    stored = await QuestDefinitionsDao(entry.runtime_data.database).get(
        definition_id
    )
    assert stored is not None
    assert stored.is_active is False


async def test_complete_and_uncomplete_quest_call_business_layer(
    hass, make_entry
) -> None:
    import datetime

    from custom_components.nestquest.children import list_children
    from custom_components.nestquest.completion import instance_state
    from custom_components.nestquest.const import DEFAULT_HORIZON_DAYS
    from custom_components.nestquest.dao_instances import QuestInstancesDao

    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
    )
    child = (await list_children(entry.runtime_data.database))[0]
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_QUEST_DEFINITION,
        {
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child.id],
            "windows": ["morning"],
        },
    )
    await hass.services.call(DOMAIN, SERVICE_REGENERATE)
    today = datetime.date.today().isoformat()
    end = (
        datetime.date.today() + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
    ).isoformat()
    records = await QuestInstancesDao(
        entry.runtime_data.database
    ).list_by_date_range(child.id, today, end)
    assert records
    instance_id = records[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instance_id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    assert (
        await instance_state(entry.runtime_data.database, instance_id)
        == "done"
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_UNCOMPLETE_QUEST,
        {
            "instance_id": instance_id,
            "actor": "user",
            "actor_user_id": "parent-1",
        },
    )
    assert (
        await instance_state(entry.runtime_data.database, instance_id)
        == "open"
    )


async def test_set_presence_pattern_regenerates_child_instances(
    hass, make_entry
) -> None:
    import datetime

    from custom_components.nestquest.children import list_children
    from custom_components.nestquest.const import DEFAULT_HORIZON_DAYS
    from custom_components.nestquest.dao_instances import QuestInstancesDao

    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
    )
    child = (await list_children(entry.runtime_data.database))[0]
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_QUEST_DEFINITION,
        {
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child.id],
            "windows": ["morning"],
        },
    )
    await hass.services.call(DOMAIN, SERVICE_REGENERATE)
    today = datetime.date.today().isoformat()
    end = (
        datetime.date.today() + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
    ).isoformat()
    dao = QuestInstancesDao(entry.runtime_data.database)
    assert await dao.list_by_date_range(child.id, today, end)
    await hass.services.call(
        DOMAIN,
        SERVICE_SET_PRESENCE_PATTERN,
        {
            "child_id": child.id,
            "cycle_length_weeks": 1,
            "anchor_date": today,
            "pattern": {0: []},
        },
    )
    assert await dao.list_by_date_range(child.id, today, end) == []


async def test_presence_override_create_and_delete_regenerate(
    hass, make_entry
) -> None:
    import datetime

    from custom_components.nestquest.children import list_children
    from custom_components.nestquest.const import DEFAULT_HORIZON_DAYS
    from custom_components.nestquest.dao_instances import QuestInstancesDao
    from custom_components.nestquest.dao_presence import PresenceOverridesDao

    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
    )
    child = (await list_children(entry.runtime_data.database))[0]
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_QUEST_DEFINITION,
        {
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child.id],
            "windows": ["morning"],
        },
    )
    await hass.services.call(DOMAIN, SERVICE_REGENERATE)
    today = datetime.date.today()
    end = today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
    dao = QuestInstancesDao(entry.runtime_data.database)
    before = await dao.list_by_date_range(
        child.id, today.isoformat(), end.isoformat()
    )
    assert before
    await hass.services.call(
        DOMAIN,
        SERVICE_CREATE_PRESENCE_OVERRIDE,
        {
            "child_id": child.id,
            "start_date": today.isoformat(),
            "end_date": end.isoformat(),
            "is_present": False,
        },
    )
    assert (
        await dao.list_by_date_range(
            child.id, today.isoformat(), end.isoformat()
        )
        == []
    )
    override = (
        await PresenceOverridesDao(
            entry.runtime_data.database
        ).list_by_child_and_range(
            child.id, today.isoformat(), end.isoformat()
        )
    )[0]
    await hass.services.call(
        DOMAIN,
        SERVICE_DELETE_PRESENCE_OVERRIDE,
        {"override_id": override.id},
    )
    after = await dao.list_by_date_range(
        child.id, today.isoformat(), end.isoformat()
    )
    assert len(after) == len(before)


async def test_export_history_csv_raises_home_assistant_error(
    hass, make_entry
) -> None:
    entry = _wire(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    with pytest.raises(HomeAssistantError, match="Feature 13"):
        await hass.services.call(DOMAIN, SERVICE_EXPORT_HISTORY_CSV)


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
    with pytest.raises((vol.Invalid, ValueError, HomeAssistantError)):
        await hass.services.call(
            DOMAIN,
            SERVICE_MANAGE_CHILD,
            {"action": "create"},
        )
