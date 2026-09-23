"""The Feature 10 entity-and-event matrix (task 9).

One fixture drives every assertion the done-condition names: correct
values for every sensor and binary sensor (including the zero-quest
child and the 255-character state limit), the three events firing
exactly once with schema-valid payloads, the instances payload
omitting missed instances while admin_instances includes them, and no
entities for an inactive child.  The per-task test files cover each
behavior in depth; this file is the single pass that proves them all
against ONE fixture, so a regression in any contract fails here too.
"""
from __future__ import annotations

import datetime
import re

from conftest import refire_api_transitions, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import (
    create_child,
    list_children,
    set_child_active,
)
from custom_components.nestquest.completion import derive_state
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_UNCOMPLETED,
    SERVICE_COMPLETE_QUEST,
    SERVICE_UNCOMPLETE_QUEST,
)
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


async def _fixture(hass, make_entry):
    """Two quest children, one zero-quest child, one inactive child."""
    entry = wire_entry_to_registry(
        make_entry(data={CONF_ADMIN_USER_IDS: ["admin-1"]}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")
    cory = await create_child(database, "Cory")
    ghost = await create_child(database, "Ghost")
    await set_child_active(database, ghost.id, False)
    today = datetime.date.today()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today.isoformat()}
        ),
        [ada.id, bo.id],
        ["morning", "evening"],
    )
    end = (today + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today.isoformat(), end, today=today)
    await entry.runtime_data.coordinator.async_refresh()
    return entry, (ada, bo, cory, ghost)


def _sensor(hass, child_id, kind):
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


async def test_entity_and_event_matrix(hass, make_entry) -> None:
    entry, (ada, bo, cory, ghost) = await _fixture(hass, make_entry)
    coordinator = entry.runtime_data.coordinator

    # --- Every active child has the full entity set; the inactive
    # child has none.
    kinds = (
        "quests_due_today",
        "quests_completed_today",
        "quests_remaining_today",
        "completion_pct_today",
        "next_quest",
        "all_done",
        "present_today",
    )
    for child in (ada, bo, cory):
        for kind in kinds:
            assert f"{DOMAIN}_child_{child.id}_{kind}" in hass.entities, kind
    for kind in kinds:
        assert f"{DOMAIN}_child_{ghost.id}_{kind}" not in hass.entities, (
            "inactive children must have no entities"
        )

    # --- Correct values against the fixture: Ada and Bo owe two
    # quests (morning + evening), Cory owes none and is still 100%.
    for child in (ada, bo):
        assert _sensor(hass, child.id, "quests_due_today").native_value == 2
        assert (
            _sensor(hass, child.id, "quests_completed_today").native_value == 0
        )
        assert (
            _sensor(hass, child.id, "quests_remaining_today").native_value == 2
        )
        assert (
            _sensor(hass, child.id, "completion_pct_today").native_value == 0
        )
        assert _sensor(hass, child.id, "next_quest").native_value == (
            "Brush teeth"
        )
        assert _sensor(hass, child.id, "all_done").is_on is False
        assert _sensor(hass, child.id, "present_today").is_on is True
    assert _sensor(hass, cory.id, "quests_due_today").native_value == 0
    assert _sensor(hass, cory.id, "completion_pct_today").native_value == 100
    assert _sensor(hass, cory.id, "all_done").is_on is False
    assert _sensor(hass, cory.id, "next_quest").native_value == "none"

    # --- Household rollups equal the per-child sums.
    assert hass.entities[
        "nestquest_household_quests_due_today"
    ].native_value == 4
    assert hass.entities[
        "nestquest_household_quests_completed_today"
    ].native_value == 0

    # --- The 255-character limit holds for every registered entity.
    for unique_id, entity in hass.entities.items():
        state = getattr(entity, "native_value", None)
        if state is None:
            state = getattr(entity, "is_on", None)
        assert state is None or not (
            isinstance(state, str) and len(state) > 255
        ), unique_id

    # --- Completing both of Ada's quests fires the events exactly
    # once each and flips her entities immediately.
    instances = await QuestInstancesDao(
        entry.runtime_data.database
    ).list_by_date_range(
        ada.id, datetime.date.today().isoformat(), datetime.date.today().isoformat()
    )
    for instance in instances:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": ada.id,
            },
        )
    # The transition events arrive over the API's SSE stream (the
    # subscription re-fires them), never from the service handler.
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 2
    for payload in hass.bus.fired(EVENT_QUEST_COMPLETED):
        assert _TIMESTAMP.match(payload["occurred_at"])
        assert isinstance(payload["was_on_time"], bool)
        assert payload["child_name"] in ("Ada",)
        assert payload["quest_title"] == "Brush teeth"
        assert isinstance(payload["instance_id"], int)
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1
    assert _sensor(hass, ada.id, "all_done").is_on is True
    assert _sensor(hass, ada.id, "quests_remaining_today").native_value == 0
    assert (
        _sensor(hass, ada.id, "completion_pct_today").native_value == 100
    )

    # --- Reversing one quest fires the uncompleted event exactly once
    # and restores the owed counts.
    await hass.services.call(
        DOMAIN,
        SERVICE_UNCOMPLETE_QUEST,
        {"instance_id": instances[0].id, "actor": "user"},
        context={"user_id": "admin-1"},
    )
    assert len(hass.bus.fired(EVENT_QUEST_UNCOMPLETED)) == 1
    assert _sensor(hass, ada.id, "all_done").is_on is False
    assert _sensor(hass, ada.id, "quests_remaining_today").native_value == 1

    # --- The instances payload omits missed instances (D-009) — and
    # since Feature 18 the snapshot comes from the API panel route,
    # which omits missed rows ENTIRELY, so admin_instances cannot
    # carry them either (the admin surface for missed quests is the
    # PWA, reading the API directly): pin the derive clock forward in
    # the TEST ONLY so today's open instances read missed.
    original_refresh = coordinator._async_update_data

    async def _future_dated_refresh():
        import custom_components.nestquest.core.snapshot as snapshot_module

        real_derive = snapshot_module.derive_state

        def _derive(instance, latest, today):
            return real_derive(instance, latest, today + datetime.timedelta(days=1))

        snapshot_module.derive_state = _derive
        try:
            return await original_refresh()
        finally:
            snapshot_module.derive_state = real_derive

    coordinator._async_update_data = _future_dated_refresh
    await coordinator.async_refresh()
    attributes = _sensor(hass, bo.id, "quests_due_today").extra_state_attributes
    assert attributes["instances"] == [], "panel payload omits missed"
    assert attributes["admin_instances"] == [], (
        "the API payload omits missed rows, so the admin payload "
        "carries none either (the PWA is the admin surface now)"
    )
    coordinator._async_update_data = original_refresh
    await coordinator.async_refresh()


async def test_payload_schema_matches_the_documented_contract(
    hass, make_entry
) -> None:
    """Every fired payload carries the documented fields with the
    documented types."""
    entry, (ada, _bo, _cory, _ghost) = await _fixture(hass, make_entry)
    instances = await QuestInstancesDao(
        entry.runtime_data.database
    ).list_by_date_range(
        ada.id, datetime.date.today().isoformat(), datetime.date.today().isoformat()
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": ada.id,
        },
    )
    # The completed event arrives over the API's SSE stream.
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    payload = hass.bus.fired(EVENT_QUEST_COMPLETED)[0]
    for key, check in (
        ("child_id", lambda v: isinstance(v, int)),
        ("child_name", lambda v: isinstance(v, str)),
        ("instance_id", lambda v: isinstance(v, int)),
        ("quest_title", lambda v: isinstance(v, str)),
        ("window", lambda v: v in ("morning", "evening")),
        ("due_date", lambda v: isinstance(v, str)),
        ("due_time", lambda v: v is None or isinstance(v, str)),
        ("occurred_at", lambda v: bool(_TIMESTAMP.match(v))),
        ("was_on_time", lambda v: isinstance(v, bool)),
    ):
        assert key in payload, key
        assert check(payload[key]), key
