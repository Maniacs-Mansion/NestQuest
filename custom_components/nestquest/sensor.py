"""Per-child daily count and percentage sensors (Feature 10, task 2).

Naming contract (design/ENTITIES-AND-SERVICES.md §1): the design table
documents the entity_id shape ``sensor.nestquest_<child>_quests_due_today``.
Home Assistant derives entity_id from the entity NAME and exact
entity_id strings are not directly controllable, so names are spelled
to slug into the documented shape — ``NestQuest Ada quests due today``
slugs to ``sensor.nestquest_ada_quests_due_today`` — while the
registry identity (``unique_id``) IS exact: built from the child's
database id, never the display name, so a rename never orphans an
entity's history.  The design table is the visual contract; this
module spells names so HA's default slugging produces it.

Every sensor reads ONLY ``coordinator.data`` (one
:class:`~.coordinator.ChildDaySnapshot` per active child); no entity
queries the database, so one refresh updates the whole board
coherently.  The due-today sensor additionally carries the child's
day payload as attributes: ``instances`` is the panel shape of
ENTITIES-AND-SERVICES.md §1 (state ``open``/``completed``) OMITTING
missed instances, and ``admin_instances`` includes them (D-009).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    ChildDaySnapshot,
    NestQuestCoordinator,
    QuestInstanceView,
)

#: Home Assistant's state machine refuses states longer than 255
#: characters (its hard recorder/state limit).  These sensors' states
#: are numeric, but the guard is applied uniformly: a payload-bearing
#: sensor can never crash the state write, and later string-state
#: sensors reuse the same helper.
MAX_STATE_LENGTH = 255


def _state_within_limit(state: Any) -> Any:
    """Return ``state`` unchanged, refusing strings over HA's limit.

    Numeric states pass through untouched; a string state longer than
    :data:`MAX_STATE_LENGTH` fails fast with ValueError at the property
    read — before HA's state machine rejects the write.
    """
    if isinstance(state, str) and len(state) > MAX_STATE_LENGTH:
        raise ValueError(
            f"state exceeds Home Assistant's {MAX_STATE_LENGTH}-character "
            f"limit ({len(state)} characters)"
        )
    return state


def _instance_payload(
    instances: Iterable[QuestInstanceView], *, include_missed: bool
) -> list[dict[str, Any]]:
    """Shape instance dicts per ENTITIES-AND-SERVICES.md §1.

    ``state`` maps the coordinator's derived ``done`` to the panel's
    ``completed`` spelling; ``missed`` instances are omitted unless
    ``include_missed`` (the admin payload, D-009, keeps them with
    their ``missed`` state).
    """
    payload: list[dict[str, Any]] = []
    for view in instances:
        if view.state == "missed" and not include_missed:
            continue
        payload.append(
            {
                "id": view.instance_id,
                "definition_id": view.definition_id,
                "child_id": view.child_id,
                "title": view.title,
                "icon": view.icon,
                "window": view.window,
                "due_time": view.due_time,
                "state": (
                    "completed" if view.state == "done" else view.state
                ),
                "overdue": view.overdue,
                "completed_at": view.completed_at,
                "on_time": view.was_on_time,
            }
        )
    return payload


#: State reported by the next-quest sensor when the child owes nothing
#: else today.  A documented sentinel, never an empty string (an empty
#: state reads as "sensor went unavailable" in HA).
NEXT_QUEST_NONE_STATE = "none"


def _next_open_quest(
    child: ChildDaySnapshot,
) -> QuestInstanceView | None:
    """Return the child's earliest open quest from today's snapshot.

    The snapshot carries TODAY's instances, so "next" is the earliest
    open instance by (due_date, due_time), with ``due_time`` ordering
    ahead of ``None`` (a window with no due time comes first only
    within the same date — the materializer snapshots each window's
    due_time, so a missing one means the window is unscheduled).
    Missed and completed instances never qualify.
    """
    open_views = [
        view
        for view in child.instances
        if view.state == "open"
    ]
    if not open_views:
        return None
    return min(
        open_views,
        key=lambda view: (
            view.due_date,
            view.due_time if view.due_time is not None else "",
        ),
    )


class _NestQuestChildDaySensor(CoordinatorEntity, SensorEntity):
    """Base for the per-child day sensors.

    Registry identity is built from the child's database id and never
    changes; the DISPLAYED name and device label are derived from the
    child's CURRENT snapshot on every read, so a rename through
    ``manage_child`` propagates on the next refresh without orphaning
    the entity's history.  A child absent from the latest snapshot (a
    deactivation; removal is a later task's scope) yields ``None``
    states rather than stale counts.
    """

    #: Per-subclass label appended to the name (e.g. ``quests due
    #: today``), set as a class attribute so ``name`` composes from the
    #: current snapshot.
    _name_suffix: str = ""

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child.child_id
        self._fallback_name = child.child_name
        self._attr_unique_id = None  # set by the subclass

    @property
    def _child(self) -> ChildDaySnapshot | None:
        """Return the child's current day snapshot, or None."""
        data = self.coordinator.data
        if data is None:
            return None
        for child in data.children:
            if child.child_id == self._child_id:
                return child
        return None

    def _displayed_child_name(self) -> str:
        child = self._child
        return child.child_name if child is not None else self._fallback_name

    @property
    def name(self) -> str | None:
        return f"NestQuest {self._displayed_child_name()} {self._name_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"child_{self._child_id}")},
            name=f"NestQuest {self._displayed_child_name()}",
            manufacturer="NestQuest",
        )


class NestQuestQuestsDueTodaySensor(_NestQuestChildDaySensor):
    """How many quests the child has due today, with the day payload."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _name_suffix = "quests due today"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = (
            f"{DOMAIN}_child_{child.child_id}_quests_due_today"
        )

    @property
    def native_value(self) -> int | None:
        child = self._child
        if child is None:
            return None
        return _state_within_limit(child.due_today)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        child = self._child
        if child is None:
            return None
        return {
            "instances": _instance_payload(
                child.instances, include_missed=False
            ),
            "admin_instances": _instance_payload(
                child.instances, include_missed=True
            ),
            "child_id": child.child_id,
            "child_name": child.child_name,
            "present": child.present,
        }


class NestQuestQuestsCompletedTodaySensor(_NestQuestChildDaySensor):
    """How many of the child's quests were completed today."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _name_suffix = "quests completed today"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = (
            f"{DOMAIN}_child_{child.child_id}_quests_completed_today"
        )

    @property
    def native_value(self) -> int | None:
        child = self._child
        if child is None:
            return None
        return _state_within_limit(child.completed_today)


class NestQuestQuestsRemainingTodaySensor(_NestQuestChildDaySensor):
    """How many of the child's quests are still owed today."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _name_suffix = "quests remaining today"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = (
            f"{DOMAIN}_child_{child.child_id}_quests_remaining_today"
        )

    @property
    def native_value(self) -> int | None:
        child = self._child
        if child is None:
            return None
        return _state_within_limit(child.remaining_today)


class NestQuestCompletionPctTodaySensor(_NestQuestChildDaySensor):
    """The child's completion percentage for today (100 on a zero-quest day)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _name_suffix = "completion pct today"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = (
            f"{DOMAIN}_child_{child.child_id}_completion_pct_today"
        )

    @property
    def native_value(self) -> int | None:
        child = self._child
        if child is None:
            return None
        return _state_within_limit(child.completion_pct)


class NestQuestNextQuestSensor(_NestQuestChildDaySensor):
    """The child's next open quest today (title in the state).

    State is the quest TITLE, truncated to HA's 255-character state
    limit (attributes always carry the full title); when the child
    owes nothing else today the state is the documented sentinel
    ``none`` (NEXT_QUEST_NONE_STATE), never an empty string.
    """

    _attr_state_class = None  # a label, not a measurement
    _name_suffix = "next quest"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = (
            f"{DOMAIN}_child_{child.child_id}_next_quest"
        )

    @property
    def native_value(self) -> str | None:
        child = self._child
        if child is None:
            return None
        quest = _next_open_quest(child)
        if quest is None:
            return NEXT_QUEST_NONE_STATE
        return quest.title[:MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        child = self._child
        if child is None:
            return None
        quest = _next_open_quest(child)
        if quest is None:
            return {"child_id": child.child_id, "child_name": child.child_name}
        return {
            "instance_id": quest.instance_id,
            "definition_id": quest.definition_id,
            "child_id": quest.child_id,
            "child_name": child.child_name,
            "title": quest.title,
            "icon": quest.icon,
            "window": quest.window,
            "due_date": quest.due_date,
            "due_time": quest.due_time,
            "overdue": quest.overdue,
        }


def _child_day_sensors(
    coordinator: NestQuestCoordinator, child: ChildDaySnapshot
) -> tuple[_NestQuestChildDaySensor, ...]:
    """Build the per-child day sensors for one active child."""
    return (
        NestQuestQuestsDueTodaySensor(coordinator, child),
        NestQuestQuestsCompletedTodaySensor(coordinator, child),
        NestQuestQuestsRemainingTodaySensor(coordinator, child),
        NestQuestCompletionPctTodaySensor(coordinator, child),
        NestQuestNextQuestSensor(coordinator, child),
    )


class _NestQuestHouseholdSensor(CoordinatorEntity, SensorEntity):
    """Base for the household-level rollup sensors.

    Aggregates the ACTIVE children's snapshots only (the snapshot
    already excludes inactive children), matching the per-child
    sensors exactly — a household number is always the sum of the
    per-child numbers.  Grouped under one household device so the
    three household sensors render together.
    """

    _attr_name: str

    def __init__(self, coordinator: NestQuestCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "household")},
            name="NestQuest Household",
            manufacturer="NestQuest",
        )


class NestQuestHouseholdDueTodaySensor(_NestQuestHouseholdSensor):
    """Total quests due today across active children."""

    _attr_name = "NestQuest household quests due today"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id = f"{DOMAIN}_household_quests_due_today"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return _state_within_limit(
            sum(child.due_today for child in data.children)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        return {
            "children": {
                str(child.child_id): child.due_today
                for child in data.children
            }
        }


class NestQuestHouseholdCompletedTodaySensor(_NestQuestHouseholdSensor):
    """Total quests completed today across active children."""

    _attr_name = "NestQuest household quests completed today"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id = f"{DOMAIN}_household_quests_completed_today"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return _state_within_limit(
            sum(child.completed_today for child in data.children)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        return {
            "children": {
                str(child.child_id): child.completed_today
                for child in data.children
            }
        }


class NestQuestCycleDaySensor(_NestQuestHouseholdSensor):
    """Cycle day N of the custody cycle (0 when nobody is scheduled).

    Computed by the coordinator from the first active child with a
    presence schedule, anchor-date arithmetic only (D-004 — never ISO
    week parity), so a 53-week year cannot silently invert it.
    """

    _attr_name = "NestQuest cycle day"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id = f"{DOMAIN}_cycle_day"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return _state_within_limit(data.cycle_day)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        return {"cycle_day": data.cycle_day, "today": data.today_iso}


def _household_sensors(
    coordinator: NestQuestCoordinator,
) -> tuple[_NestQuestHouseholdSensor, ...]:
    """Build the three household-level sensors (one set per entry)."""
    return (
        NestQuestHouseholdDueTodaySensor(coordinator),
        NestQuestHouseholdCompletedTodaySensor(coordinator),
        NestQuestCycleDaySensor(coordinator),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[..., None],
) -> None:
    """Create the five day sensors per active child.

    Entities are created for the snapshot's children at platform
    setup; a coordinator listener adds sensors for children that
    first appear on a later refresh.  Deactivated children are NOT
    removed here — their sensors hold ``None`` states until the
    entity-removal task lands.
    """
    coordinator = entry.runtime_data.coordinator
    known_child_ids: set[int] = set()

    def _add_new_children(children: Iterable[ChildDaySnapshot]) -> None:
        new_children = [
            child
            for child in children
            if child.child_id not in known_child_ids
        ]
        if not new_children:
            return
        known_child_ids.update(child.child_id for child in new_children)
        async_add_entities(
            [
                sensor
                for child in new_children
                for sensor in _child_day_sensors(coordinator, child)
            ]
        )

    data = coordinator.data
    if data is not None:
        _add_new_children(data.children)
        # The household rollups are child-independent: created exactly
        # once at platform setup, they aggregate whatever the snapshot
        # carries (empty included — an empty household is a valid 0).
        async_add_entities(_household_sensors(coordinator))

    def _handle_coordinator_update() -> None:
        data = coordinator.data
        if data is not None:
            _add_new_children(data.children)

    coordinator.async_add_listener(_handle_coordinator_update)
