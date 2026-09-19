"""Tests for the per-child daily count and percentage sensors (Feature 10, task 2)."""
from __future__ import annotations

import datetime

import pytest

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.children import create_child
from custom_components.nestquest.completion import complete_instance
from custom_components.nestquest.const import DOMAIN
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import create_quest_definition
from custom_components.nestquest.recurrence import ScheduleRule
from custom_components.nestquest.sensor import (
    MAX_STATE_LENGTH,
    _state_within_limit,
)

#: The seeding horizon: instances exist for today and a few days out,
#: enough for the day snapshot without slowing the walk down.
SEED_HORIZON_DAYS = 3

#: The documented per-child day sensor kinds (unique_id suffixes).
SENSOR_KINDS = (
    "quests_due_today",
    "quests_completed_today",
    "quests_remaining_today",
    "completion_pct_today",
)


def _today() -> datetime.date:
    return datetime.date.today()


async def _seed_children(database):
    """Three active children: Ada and Bo share one daily quest; Cory has none."""
    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")
    cory = await create_child(database, "Cory")
    today = _today()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today.isoformat()}
        ),
        [ada.id, bo.id],
        ["morning"],
    )
    end = (today + datetime.timedelta(days=SEED_HORIZON_DAYS)).isoformat()
    await materialize(database, today.isoformat(), end, today=today)
    return ada, bo, cory


async def _setup_seeded_entry(hass, make_entry):
    """Set up the integration, seed three children, refresh: sensors exist.

    Children are seeded AFTER setup (the entry's database only exists
    once setup opens it), so the sensors appear through the refresh
    listener — the same path production takes when a child is added.
    """
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    ada, bo, cory = await _seed_children(database)
    await coordinator.async_refresh()
    return entry, coordinator, (ada, bo, cory)


def _snapshot_child(coordinator, child_id):
    """Return the child's current day snapshot from the coordinator."""
    for child in coordinator.data.children:
        if child.child_id == child_id:
            return child
    raise AssertionError(f"child {child_id} missing from the snapshot")


def _sensor(hass, child_id, kind):
    """Return the registered sensor entity for (child, kind)."""
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


async def _complete_first_instance(database, coordinator, child) -> None:
    """Complete the child's first open instance through the business layer."""
    snapshot_child = _snapshot_child(coordinator, child.id)
    instance_id = snapshot_child.instances[0].instance_id
    await complete_instance(
        database,
        instance_id,
        actor_source="panel",
        actor_child_id=child.id,
    )


async def test_every_active_child_gets_five_sensors_with_documented_identity(
    hass, make_entry
) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    assert hass.config_entries.forwarded_platforms == ["sensor"]
    await _complete_first_instance(database, coordinator, ada)
    await coordinator.async_refresh()

    # Two quest children plus the zero-quest child: three children x
    # five sensors, no duplicates.
    assert len(hass.entities) == 15
    expected = {
        ada.id: ("Ada", 1, 1, 0, 100),
        bo.id: ("Bo", 1, 0, 1, 0),
        cory.id: ("Cory", 0, 0, 0, 100),
    }
    for child_id, (name, due, completed, remaining, pct) in expected.items():
        due_entity = _sensor(hass, child_id, "quests_due_today")
        completed_entity = _sensor(hass, child_id, "quests_completed_today")
        remaining_entity = _sensor(hass, child_id, "quests_remaining_today")
        pct_entity = _sensor(hass, child_id, "completion_pct_today")
        next_entity = _sensor(hass, child_id, "next_quest")
        assert due_entity.name == f"NestQuest {name} quests due today"
        assert completed_entity.name == (
            f"NestQuest {name} quests completed today"
        )
        assert remaining_entity.name == (
            f"NestQuest {name} quests remaining today"
        )
        assert pct_entity.name == f"NestQuest {name} completion pct today"
        assert due_entity.native_value == due
        assert completed_entity.native_value == completed
        assert remaining_entity.native_value == remaining
        assert pct_entity.native_value == pct
        for entity in (due_entity, completed_entity, remaining_entity):
            assert entity.state_class == "measurement"
            assert entity.native_unit_of_measurement is None
        assert pct_entity.state_class == "measurement"
        assert pct_entity.native_unit_of_measurement == "%"
        assert pct_entity.device_class == "percentage"
        device_info = due_entity.device_info
        assert device_info.name == f"NestQuest {name}"
        assert device_info.manufacturer == "NestQuest"
        assert device_info.identifiers == {(DOMAIN, f"child_{child_id}")}


async def test_zero_quest_child_is_a_perfect_day(hass, make_entry) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    due_entity = _sensor(hass, cory.id, "quests_due_today")
    pct_entity = _sensor(hass, cory.id, "completion_pct_today")
    assert due_entity.native_value == 0
    assert pct_entity.native_value == 100, (
        "zero quests is a perfect day, not a division error"
    )
    attributes = due_entity.extra_state_attributes
    assert attributes["instances"] == []
    assert attributes["admin_instances"] == []


async def test_due_today_attributes_carry_the_panel_payload(
    hass, make_entry
) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    await _complete_first_instance(database, coordinator, ada)
    await coordinator.async_refresh()

    ada_due = _sensor(hass, ada.id, "quests_due_today")
    attributes = ada_due.extra_state_attributes
    assert set(attributes) == {
        "instances",
        "admin_instances",
        "child_id",
        "child_name",
        "present",
    }
    assert attributes["child_id"] == ada.id
    assert attributes["child_name"] == "Ada"
    assert attributes["present"] is True
    [instance] = attributes["instances"]
    assert set(instance) == {
        "id",
        "definition_id",
        "child_id",
        "title",
        "icon",
        "window",
        "due_time",
        "state",
        "overdue",
        "completed_at",
        "on_time",
    }
    assert instance["child_id"] == ada.id
    assert instance["title"] == "Brush teeth"
    assert instance["window"] == "morning"
    assert instance["state"] == "completed", (
        "the derived 'done' maps to the panel's 'completed' spelling"
    )
    assert instance["completed_at"] is not None
    assert instance["on_time"] is not None
    assert instance["overdue"] is False
    assert attributes["admin_instances"] == attributes["instances"], (
        "with nothing missed, admin and panel payloads are identical"
    )

    bo_due = _sensor(hass, bo.id, "quests_due_today")
    [bo_instance] = bo_due.extra_state_attributes["instances"]
    assert bo_instance["state"] == "open"
    assert bo_instance["completed_at"] is None
    assert bo_instance["on_time"] is None


async def test_due_today_payload_omits_missed_for_panel_includes_for_admin(
    hass, make_entry, monkeypatch
) -> None:
    """D-009: the panel payload omits missed instances, the admin one keeps them.

    A missed instance is derived (``due_date`` before the snapshot's
    "today"), never stored.  The coordinator's day listing is keyed on
    ``_local_now``'s date, so pinning the clock forward would move the
    listing window off today's rows entirely; the pinned FUTURE clock
    is therefore applied at the ``derive_state`` boundary instead —
    today's open instances then read as missed through the same
    derivation rule, without back-dating instance rows past the DAO's
    no-past guard or touching append-only completion events.
    """
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    import custom_components.nestquest.coordinator as coordinator_module

    tomorrow = _today() + datetime.timedelta(days=1)
    real_derive_state = coordinator_module.derive_state

    def _derive_against_pinned_future(instance, latest, today):
        return real_derive_state(instance, latest, tomorrow)

    monkeypatch.setattr(
        coordinator_module, "derive_state", _derive_against_pinned_future
    )
    await coordinator.async_refresh()

    bo_due = _sensor(hass, bo.id, "quests_due_today")
    attributes = bo_due.extra_state_attributes
    assert attributes["instances"] == [], (
        "missed instances are omitted from the panel payload"
    )
    [missed] = attributes["admin_instances"]
    assert missed["state"] == "missed"
    assert missed["completed_at"] is None
    # Counts still roll the missed instance up as not-completed.
    assert _sensor(hass, bo.id, "quests_completed_today").native_value == 0
    assert _sensor(hass, bo.id, "quests_remaining_today").native_value == 1


@pytest.mark.parametrize("kind", SENSOR_KINDS)
async def test_no_sensor_state_exceeds_the_255_character_limit(
    hass, make_entry, kind
) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    for child in (ada, bo, cory):
        entity = _sensor(hass, child.id, kind)
        state = entity.native_value
        assert len(str(state)) <= MAX_STATE_LENGTH


def test_state_within_limit_refuses_overlong_strings() -> None:
    """The truncation guard: numerics pass, overlong strings fail fast."""
    assert _state_within_limit(3) == 3
    assert _state_within_limit("ok") == "ok"
    with pytest.raises(ValueError, match="255"):
        _state_within_limit("x" * (MAX_STATE_LENGTH + 1))


async def test_sensors_update_on_refresh_after_a_completion(
    hass, make_entry
) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    completed_entity = _sensor(hass, ada.id, "quests_completed_today")
    remaining_entity = _sensor(hass, ada.id, "quests_remaining_today")
    pct_entity = _sensor(hass, ada.id, "completion_pct_today")
    due_entity = _sensor(hass, ada.id, "quests_due_today")
    assert completed_entity.native_value == 0
    assert remaining_entity.native_value == 1
    assert pct_entity.native_value == 0

    # Coordinator listener wiring: each refresh writes the entity's
    # state (the registration the cards' state_changed handlers ride).
    writes = []
    real_write = due_entity.async_write_ha_state

    def _record_write():
        writes.append(due_entity.unique_id)
        real_write()

    due_entity.async_write_ha_state = _record_write

    await _complete_first_instance(database, coordinator, ada)
    await coordinator.async_refresh()

    assert completed_entity.native_value == 1
    assert remaining_entity.native_value == 0
    assert pct_entity.native_value == 100
    assert writes == [due_entity.unique_id]


async def test_repeated_refreshes_do_not_duplicate_entities(
    hass, make_entry
) -> None:
    entry, coordinator, (ada, bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert len(hass.entities) == 15


async def test_setup_with_no_children_registers_no_entities(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert hass.entities == {}


async def test_unload_unloads_platforms(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    assert hass.config_entries.unloaded_platforms == ["sensor"]


async def test_rename_propagates_to_name_and_device_label(
    hass, make_entry
) -> None:
    """A manage_child rename shows on the next refresh: the name and
    device label re-derive from the snapshot while the unique_id (and
    therefore history) is untouched."""
    from custom_components.nestquest.children import edit_child

    entry, coordinator, (ada, _bo, _cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    due_sensor = _sensor(hass, ada.id, "quests_due_today")
    original_unique_id = due_sensor.unique_id
    assert due_sensor.name.startswith("NestQuest Ada ")

    await edit_child(database, ada.id, display_name="Mirren")
    await coordinator.async_refresh()

    assert due_sensor.name.startswith("NestQuest Mirren ")
    assert due_sensor.device_info.name == "NestQuest Mirren"
    assert due_sensor.unique_id == original_unique_id


async def test_failed_platform_unload_returns_false_and_retains_runtime(
    hass, make_entry
) -> None:
    """When HA reports platforms still loaded, the unload must NOT
    close the database the live entities read: it returns False and
    keeps the runtime record for a retry."""
    entry, _coordinator, _children = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database

    async def _refuse_unload(entry_arg, platforms):
        return False

    hass.config_entries.async_unload_platforms = _refuse_unload
    assert await async_unload_entry(hass, entry) is False
    assert hass.data[DOMAIN][entry.entry_id] is entry.runtime_data
    assert database.connected is True

async def test_next_quest_sensor_reports_earliest_open_quest(
    hass, make_entry
) -> None:
    """The next-quest sensor carries the earliest open quest's title in
    state with the full shape in attributes."""
    entry, coordinator, (ada, _bo, _cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    next_entity = _sensor(hass, ada.id, "next_quest")
    assert next_entity.name == f"NestQuest Ada next quest"
    assert next_entity.native_value == "Brush teeth"
    attributes = next_entity.extra_state_attributes
    assert attributes["title"] == "Brush teeth"
    assert attributes["window"] == "morning"
    assert attributes["instance_id"] == _snapshot_child(
        coordinator, ada.id
    ).instances[0].instance_id
    assert attributes["child_id"] == ada.id


async def test_next_quest_sensor_reports_none_sentinel_when_day_clear(
    hass, make_entry
) -> None:
    """A child with every quest done (and a zero-quest child) reports
    the documented sentinel, never an empty string."""
    entry, coordinator, (ada, _bo, cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    await _complete_first_instance(database, coordinator, ada)
    await coordinator.async_refresh()
    assert _sensor(hass, ada.id, "next_quest").native_value == "none"
    assert _sensor(hass, cory.id, "next_quest").native_value == "none"


async def test_next_quest_state_truncates_over_the_limit(
    hass, make_entry
) -> None:
    """A quest title longer than the state limit is truncated; the
    attribute keeps the full title."""
    entry, coordinator, (ada, _bo, _cory) = await _setup_seeded_entry(
        hass, make_entry
    )
    database = entry.runtime_data.database
    from custom_components.nestquest.quest_definitions import (
        edit_quest_definition,
    )

    snapshot_child = _snapshot_child(coordinator, ada.id)
    await edit_quest_definition(
        database,
        snapshot_child.instances[0].definition_id,
        title="A very long quest title. " * 30,
    )
    await coordinator.async_refresh()
    next_entity = _sensor(hass, ada.id, "next_quest")
    full_title = _snapshot_child(coordinator, ada.id).instances[0].title
    assert len(full_title) > 255
    state = next_entity.native_value
    assert len(state) <= 255
    assert next_entity.extra_state_attributes["title"] == full_title
