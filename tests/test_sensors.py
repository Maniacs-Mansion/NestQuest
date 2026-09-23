"""Tests for the per-child daily count and percentage sensors (Feature 10, task 2).

Since the DB removal the snapshot comes from the API service's panel
route, so these tests script the route's payload (the documented
Feature 16 shape ``test_coordinator.py`` also uses) through
:class:`conftest.StubSnapshotClient` instead of seeding a local
database: the coordinator rebuilds the same core dataclasses the
sensors read, and every assertion below is on entity state.
"""
from __future__ import annotations

import datetime

import pytest
from homeassistant.util import slugify

from conftest import StubSnapshotClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.const import DOMAIN
from custom_components.nestquest.sensor import (
    MAX_STATE_LENGTH,
    _slugify,
    _state_within_limit,
)


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _instance(instance_id: int, child_id: int, **overrides) -> dict:
    """One panel instance in the API route's payload shape."""
    payload = {
        "id": instance_id,
        "definition_id": 3,
        "child_id": child_id,
        "title": "Brush teeth",
        "icon": "🦷",
        "window": "morning",
        "due_time": "08:00",
        "state": "open",
        "overdue": False,
        "completed_at": None,
        "on_time": None,
    }
    payload.update(overrides)
    return payload


def _child(child_id: int, name: str, instances=(), **overrides) -> dict:
    """One child in the API route's payload shape, counts precomputed.

    The API precomputes the per-child rollups from the full day; the
    builder here derives them from the instance list so a payload can
    never drift from its own counts.
    """
    completed = sum(1 for i in instances if i["state"] == "completed")
    due = max(len(instances), 0)
    payload = {
        "child_id": child_id,
        "child_name": name,
        "present": True,
        "next_present": None,
        "due_today": due,
        "completed_today": completed,
        "remaining_today": due - completed,
        "completion_pct": 100 if due == 0 else round(completed / due * 100),
        "instances": list(instances),
    }
    payload.update(overrides)
    return payload


def _payload(children) -> dict:
    return {
        "today_iso": _today_iso(),
        "cycle_day": 0,
        "children": list(children),
    }


#: The seeded household: Ada and Bo share one daily quest, Cory has none.
ADA = 1
BO = 2
CORY = 3


def _seeded_payload() -> dict:
    return _payload(
        [
            _child(ADA, "Ada", [_instance(7, ADA)]),
            _child(BO, "Bo", [_instance(8, BO)]),
            _child(CORY, "Cory"),
        ]
    )


def _completed_payload() -> dict:
    """The same household after the API recorded Ada's completion."""
    return _payload(
        [
            _child(
                ADA,
                "Ada",
                [_instance(7, ADA, state="completed", completed_at=f"{_today_iso()}T07:55:00+00:00", on_time=True)],
            ),
            _child(BO, "Bo", [_instance(8, BO)]),
            _child(CORY, "Cory"),
        ]
    )


async def _setup_entry(hass, make_entry, *payloads):
    """Set up the integration with a scripted snapshot client.

    The client serves the payloads in order (repeating the last), so
    setup's first refresh and any later explicit refresh each get the
    scripted state — the same path production takes through the API.
    """
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    client = set_coordinator_client(entry, StubSnapshotClient(*payloads))
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator.api_client is client
    return entry, coordinator, client


def _snapshot_child(coordinator, child_id):
    """Return the child's current day snapshot from the coordinator."""
    for child in coordinator.data.children:
        if child.child_id == child_id:
            return child
    raise AssertionError(f"child {child_id} missing from the snapshot")


def _sensor(hass, child_id, kind):
    """Return the registered sensor entity for (child, kind)."""
    return hass.entities[f"{DOMAIN}_child_{child_id}_{kind}"]


async def test_every_active_child_gets_five_sensors_with_documented_identity(
    hass, make_entry
) -> None:
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload(), _completed_payload()
    )
    assert hass.config_entries.forwarded_platforms == [
        "sensor",
        "binary_sensor",
    ]
    await coordinator.async_refresh()

    # Three children x (five sensors + two binary sensors) + three
    # household sensors, no duplicates.
    assert len(hass.entities) == 24
    expected = {
        ADA: ("Ada", 1, 1, 0, 100),
        BO: ("Bo", 1, 0, 1, 0),
        CORY: ("Cory", 0, 0, 0, 100),
    }
    for child_id, (name, due, completed, remaining, pct) in expected.items():
        due_entity = _sensor(hass, child_id, "quests_due_today")
        completed_entity = _sensor(hass, child_id, "quests_completed_today")
        remaining_entity = _sensor(hass, child_id, "quests_remaining_today")
        pct_entity = _sensor(hass, child_id, "completion_pct_today")
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
        assert pct_entity.device_class is None
        device_info = due_entity.device_info
        assert device_info.name == f"NestQuest {name}"
        assert device_info.manufacturer == "NestQuest"
        assert device_info.identifiers == {(DOMAIN, f"child_{child_id}")}


async def test_zero_quest_child_is_a_perfect_day(hass, make_entry) -> None:
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )
    due_entity = _sensor(hass, CORY, "quests_due_today")
    pct_entity = _sensor(hass, CORY, "completion_pct_today")
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
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _completed_payload()
    )

    ada_due = _sensor(hass, ADA, "quests_due_today")
    attributes = ada_due.extra_state_attributes
    assert set(attributes) == {
        "instances",
        "admin_instances",
        "child_id",
        "child_name",
        "present",
    }
    assert attributes["child_id"] == ADA
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
    assert instance["child_id"] == ADA
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

    bo_due = _sensor(hass, BO, "quests_due_today")
    [bo_instance] = bo_due.extra_state_attributes["instances"]
    assert bo_instance["state"] == "open"
    assert bo_instance["completed_at"] is None
    assert bo_instance["on_time"] is None


async def test_due_today_payload_omits_missed_admin_equals_panel(
    hass, make_entry
) -> None:
    """D-009: the panel payload omits missed instances.

    Since Feature 18 the snapshot comes from the API panel route,
    which omits missed rows entirely (the admin surface for missed
    quests is the PWA, reading the API directly).  The integration
    renders exactly what the route sent: a snapshot can never carry a
    ``missed`` view, ``admin_instances`` equals ``instances``, and the
    precomputed counts arrive untouched — pinned here with an open
    instance whose derived state reads missed (a past ``due_time``
    with the counts already rolled up the way the route builds them).
    """
    payload = _payload(
        [
            _child(
                BO,
                "Bo",
                [
                    _instance(
                        8,
                        BO,
                        due_time="00:01",
                        overdue=True,
                    )
                ],
            )
        ]
    )
    entry, _coordinator, _client = await _setup_entry(hass, make_entry, payload)

    bo_due = _sensor(hass, BO, "quests_due_today")
    attributes = bo_due.extra_state_attributes
    assert attributes["instances"], "an open row renders in the panel payload"
    assert attributes["admin_instances"] == attributes["instances"], (
        "the API payload omits missed rows, so the admin payload "
        "carries none either (the PWA is the admin surface now)"
    )
    # The counts arrive precomputed from the route's own build, which
    # rolls the FULL day (any missed row included) into the numbers.
    assert _sensor(hass, BO, "quests_completed_today").native_value == 0
    assert _sensor(hass, BO, "quests_remaining_today").native_value == 1


@pytest.mark.parametrize("kind", (
    "quests_due_today",
    "quests_completed_today",
    "quests_remaining_today",
    "completion_pct_today",
))
async def test_no_sensor_state_exceeds_the_255_character_limit(
    hass, make_entry, kind
) -> None:
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )
    for child_id in (ADA, BO, CORY):
        entity = _sensor(hass, child_id, kind)
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
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload(), _completed_payload()
    )
    completed_entity = _sensor(hass, ADA, "quests_completed_today")
    remaining_entity = _sensor(hass, ADA, "quests_remaining_today")
    pct_entity = _sensor(hass, ADA, "completion_pct_today")
    due_entity = _sensor(hass, ADA, "quests_due_today")
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

    await coordinator.async_refresh()

    assert completed_entity.native_value == 1
    assert remaining_entity.native_value == 0
    assert pct_entity.native_value == 100
    assert writes == [due_entity.unique_id]


async def test_repeated_refreshes_do_not_duplicate_entities(
    hass, make_entry
) -> None:
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert len(hass.entities) == 24


async def test_setup_with_no_children_registers_only_household(
    hass, make_entry
) -> None:
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _payload([])
    )
    # No children means no per-child entities; the three household
    # rollups still exist (an empty household is a valid 0).
    assert set(hass.entities) == {
        "nestquest_household_quests_due_today",
        "nestquest_household_quests_completed_today",
        "nestquest_cycle_day",
    }
    assert hass.entities["nestquest_household_quests_due_today"].native_value == 0


async def test_unload_unloads_platforms(hass, make_entry) -> None:
    entry, _coordinator, _client = await _setup_entry(hass, make_entry)
    assert await async_unload_entry(hass, entry) is True
    assert hass.config_entries.unloaded_platforms == [
        "sensor",
        "binary_sensor",
    ]


async def test_rename_propagates_to_name_and_device_label(
    hass, make_entry
) -> None:
    """A rename in the API's snapshot shows on the next refresh: the
    name and device label re-derive from the snapshot while the
    unique_id (and therefore history) is untouched."""
    renamed = _payload(
        [
            _child(ADA, "Mirren", [_instance(7, ADA)]),
            _child(BO, "Bo", [_instance(8, BO)]),
            _child(CORY, "Cory"),
        ]
    )
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload(), renamed
    )
    due_sensor = _sensor(hass, ADA, "quests_due_today")
    original_unique_id = due_sensor.unique_id
    assert due_sensor.name.startswith("NestQuest Ada ")

    await coordinator.async_refresh()

    assert due_sensor.name.startswith("NestQuest Mirren ")
    assert due_sensor.device_info.name == "NestQuest Mirren"
    assert due_sensor.unique_id == original_unique_id


async def test_failed_platform_unload_returns_false_and_retains_runtime(
    hass, make_entry
) -> None:
    """When HA reports platforms still loaded, the unload must NOT
    tear down the coordinator the live entities read: it returns False
    and keeps the runtime record for a retry."""
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )

    async def _refuse_unload(entry_arg, platforms):
        return False

    hass.config_entries.async_unload_platforms = _refuse_unload
    assert await async_unload_entry(hass, entry) is False
    assert hass.data[DOMAIN][entry.entry_id] is entry.runtime_data
    assert entry.runtime_data.coordinator is coordinator


async def test_next_quest_sensor_reports_earliest_open_quest(
    hass, make_entry
) -> None:
    """The next-quest sensor carries the earliest open quest's title in
    state with the full shape in attributes."""
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )
    next_entity = _sensor(hass, ADA, "next_quest")
    assert next_entity.name == f"NestQuest Ada next quest"
    assert next_entity.native_value == "Brush teeth"
    attributes = next_entity.extra_state_attributes
    assert attributes["title"] == "Brush teeth"
    assert attributes["window"] == "morning"
    assert attributes["instance_id"] == _snapshot_child(
        coordinator, ADA
    ).instances[0].instance_id
    assert attributes["child_id"] == ADA


async def test_next_quest_sensor_reports_none_sentinel_when_day_clear(
    hass, make_entry
) -> None:
    """A child with every quest done (and a zero-quest child) reports
    the documented sentinel, never an empty string."""
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _completed_payload()
    )
    assert _sensor(hass, ADA, "next_quest").native_value == "none"
    assert _sensor(hass, CORY, "next_quest").native_value == "none"


async def test_next_quest_state_truncates_over_the_limit(
    hass, make_entry
) -> None:
    """A quest title longer than the state limit is truncated; the
    attribute keeps the full title."""
    long_title = "A very long quest title. " * 30
    payload = _payload(
        [_child(ADA, "Ada", [_instance(7, ADA, title=long_title)])]
    )
    entry, _coordinator, _client = await _setup_entry(hass, make_entry, payload)
    next_entity = _sensor(hass, ADA, "next_quest")
    full_title = _snapshot_child(
        entry.runtime_data.coordinator, ADA
    ).instances[0].title
    assert len(full_title) > 255
    state = next_entity.native_value
    assert len(state) <= 255
    assert next_entity.extra_state_attributes["title"] == full_title


async def test_household_rollups_sum_the_active_children(
    hass, make_entry
) -> None:
    """Household due/completed equal the sum of the per-child sensors;
    the cycle-day sensor carries the coordinator's answer (precomputed
    by the API, which resolves the schedule engine server-side)."""
    payload = _payload(
        [
            _child(
                ADA,
                "Ada",
                [_instance(7, ADA, state="completed", completed_at=f"{_today_iso()}T07:55:00+00:00", on_time=True)],
            ),
            _child(BO, "Bo", [_instance(8, BO)]),
            _child(CORY, "Cory"),
        ]
    )
    payload["cycle_day"] = 4
    entry, coordinator, _client = await _setup_entry(hass, make_entry, payload)

    household_due = hass.entities["nestquest_household_quests_due_today"]
    household_completed = hass.entities[
        "nestquest_household_quests_completed_today"
    ]
    cycle_day_entity = hass.entities["nestquest_cycle_day"]
    per_child_due = [
        _sensor(hass, child_id, "quests_due_today").native_value
        for child_id in (ADA, BO, CORY)
    ]
    per_child_completed = [
        _sensor(hass, child_id, "quests_completed_today").native_value
        for child_id in (ADA, BO, CORY)
    ]
    assert household_due.native_value == sum(per_child_due)
    assert household_completed.native_value == sum(per_child_completed)
    assert household_due.name == "NestQuest household quests due today"
    assert household_completed.name == (
        "NestQuest household quests completed today"
    )
    assert cycle_day_entity.name == "NestQuest cycle day"
    assert cycle_day_entity.native_value == 4
    assert cycle_day_entity.extra_state_attributes["today"] == _today_iso()


async def test_household_due_sensor_publishes_the_ordered_child_roster(
    hass, make_entry
) -> None:
    """Feature 20: the rollup carries the ordered child roster beside
    the unchanged per-child ``children`` counts, so the panel cards can
    discover the board without a configured child_order.  The order is
    the coordinator snapshot's (the API's sort_order, then id)."""
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload()
    )
    attributes = hass.entities[
        "nestquest_household_quests_due_today"
    ].extra_state_attributes
    assert attributes["child_roster"] == [
        {"child_id": ADA, "name": "Ada", "slug": "ada"},
        {"child_id": BO, "name": "Bo", "slug": "bo"},
        {"child_id": CORY, "name": "Cory", "slug": "cory"},
    ]
    # The pre-existing per-child counts attribute is untouched.
    assert attributes["children"] == {
        str(ADA): 1,
        str(BO): 1,
        str(CORY): 0,
    }


async def test_household_roster_tracks_the_snapshot_on_refresh(
    hass, make_entry
) -> None:
    """The roster re-derives from every snapshot: a reorder and a
    rename in the API payload show up (with the re-derived slug) on the
    next refresh, like the sensor names already do."""
    reordered = _payload(
        [
            _child(CORY, "Cory"),
            _child(ADA, "Ada", [_instance(7, ADA)]),
            _child(BO, "Mirren", [_instance(8, BO)]),
        ]
    )
    entry, coordinator, _client = await _setup_entry(
        hass, make_entry, _seeded_payload(), reordered
    )
    roster_entity = hass.entities["nestquest_household_quests_due_today"]
    assert [entry["slug"] for entry in roster_entity.extra_state_attributes["child_roster"]] == [
        "ada",
        "bo",
        "cory",
    ]

    await coordinator.async_refresh()

    assert roster_entity.extra_state_attributes["child_roster"] == [
        {"child_id": CORY, "name": "Cory", "slug": "cory"},
        {"child_id": ADA, "name": "Ada", "slug": "ada"},
        {"child_id": BO, "name": "Mirren", "slug": "mirren"},
    ]


async def test_duplicate_display_names_get_registry_suffix_slugs(
    hass, make_entry
) -> None:
    """Two children may share a nickname (the children layer allows
    it); the roster's slugs then mirror the registry's collision
    suffixing (_2, _3, ...) in snapshot order, so both plates resolve."""
    payload = _payload(
        [
            _child(ADA, "Ada", [_instance(7, ADA)]),
            _child(BO, "Ada"),
        ]
    )
    entry, _coordinator, _client = await _setup_entry(hass, make_entry, payload)
    assert hass.entities[
        "nestquest_household_quests_due_today"
    ].extra_state_attributes["child_roster"] == [
        {"child_id": ADA, "name": "Ada", "slug": "ada"},
        {"child_id": BO, "name": "Ada", "slug": "ada_2"},
    ]


async def test_empty_household_publishes_an_empty_roster(
    hass, make_entry
) -> None:
    """An empty household is a valid 0: the roster is an empty list,
    and the card's discovery of it renders the not-set-up notice."""
    entry, _coordinator, _client = await _setup_entry(
        hass, make_entry, _payload([])
    )
    attributes = hass.entities[
        "nestquest_household_quests_due_today"
    ].extra_state_attributes
    assert attributes["child_roster"] == []
    assert attributes["children"] == {}


def test_slugify_mirrors_home_assistant_entity_id_derivation() -> None:
    """The roster slugs match homeassistant.util.slugify — the real
    slugifier HA derives entity ids from, composed with the entity-id
    length cap the entity registry applies to ``sensor.`` ids."""
    assert _slugify("Ada") == "ada"
    assert _slugify("Mary Jane") == "mary_jane"
    assert _slugify("Mary-Jane") == "mary_jane"
    assert _slugify("O'Brien") == "o_brien"
    assert _slugify("Émilie") == "emilie"
    assert _slugify("Åsa") == "asa"
    assert _slugify("  Bo  ") == "bo"
    # HA's wrapper answers "unknown" when a name slugs to nothing.
    assert _slugify("   ") == "unknown"
    assert _slugify("?!?") == "unknown"
    # The registry caps the entity_id at 64 characters, so the slugged
    # object id alone is capped at 64 - len("sensor.").
    assert _slugify("a" * 80) == "a" * (64 - len("sensor."))


def test_slugify_transliterates_non_latin_names_like_home_assistant() -> None:
    """HA's slugifier transliterates every script through unidecode,
    so a non-Latin child name slugs to its romanization — never to the
    ``unknown`` sentinel — and the roster publishes the same slug HA's
    entity-id derivation produces for that name."""
    assert _slugify("Дана") == "dana"
    assert _slugify("京子") == "jing_zi"
    assert _slugify("Zoë") == "zoe"


async def test_non_latin_child_names_resolve_auto_discovery(
    hass, make_entry
) -> None:
    """A non-Latin child name slugs through the real slugifier, so the
    roster slug IS the object id of the per-child sensor's entity_id
    and the cards' auto-discovery resolves that child.

    HA derives the per-child entity id from the entity NAME ("NestQuest
    京子 quests due today") with the same slugifier the roster uses, so
    the two must agree exactly; the reviewed mirror dropped non-Latin
    characters (slugging "京子" to "unknown"), so the cards built
    "sensor.nestquest_unknown_…" ids that no entity had."""
    payload = _payload(
        [
            _child(ADA, "Дана", [_instance(7, ADA)]),
            _child(BO, "京子", [_instance(8, BO)]),
        ]
    )
    entry, _coordinator, _client = await _setup_entry(hass, make_entry, payload)
    roster = hass.entities[
        "nestquest_household_quests_due_today"
    ].extra_state_attributes["child_roster"]
    assert roster == [
        {"child_id": ADA, "name": "Дана", "slug": "dana"},
        {"child_id": BO, "name": "京子", "slug": "jing_zi"},
    ]
    for roster_entry in roster:
        due_entity = _sensor(hass, roster_entry["child_id"], "quests_due_today")
        assert due_entity.name == (
            f"NestQuest {roster_entry['name']} quests due today"
        )
        # The entity id HA's registry derives for this entity (from the
        # same slugifier) embeds exactly the slug the roster publishes:
        # the card builds sensor.nestquest_<slug>_quests_due_today.
        assert slugify(due_entity.name) == (
            f"nestquest_{roster_entry['slug']}_quests_due_today"
        )
