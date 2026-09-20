"""Per-child binary sensors (Feature 10, task 4).

Two binary sensors per active child, both reading only the coordinator
snapshot (the same ChildDaySnapshot the day sensors read):

- ``binary_sensor.nestquest_<child>_all_done`` — ON exactly when the
  child owes quests today (due today > 0) AND owes none of them any
  more (remaining today == 0).  A zero-quest day is OFF: the
  celebration automation must never fire on an empty day (the
  day-complete event carries the same rule, Feature 10 task 7).
- ``binary_sensor.nestquest_<child>_present_today`` — ON when the
  presence engine resolves the child present on the HA-local date
  (schedules and overrides, D-004 anchor-date arithmetic).

Naming and registry identity follow the day sensors' contract: names
slug to the documented entity_id shape; unique_ids are built from the
child's database id, never the display name, so a rename never
orphans an entity's history.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChildDaySnapshot, NestQuestCoordinator


class _NestQuestChildBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base for the per-child binary sensors.

    Registry identity is built from the child's database id and never
    changes; the displayed name and device label re-derive from the
    child's CURRENT snapshot on every read, so a rename propagates on
    the next refresh without orphaning history.  A child absent from
    the latest snapshot (a deactivation; removal is a later task's
    scope) yields ``None`` states rather than stale values.
    """

    _name_suffix: str = ""

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child.child_id
        self._fallback_name = child.child_name

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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        child = self._child
        if child is None:
            return None
        return {
            "child_id": child.child_id,
            "child_name": child.child_name,
        }


class NestQuestAllDoneSensor(_NestQuestChildBinarySensor):
    """ON when the child had quests today and owes none of them."""

    _name_suffix = "all done"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{DOMAIN}_child_{child.child_id}_all_done"

    @property
    def is_on(self) -> bool | None:
        child = self._child
        if child is None:
            return None
        # Zero-quest days are OFF, not ON: an empty day must never fire
        # the celebration automation.
        return child.due_today > 0 and child.remaining_today == 0


class NestQuestPresentTodaySensor(_NestQuestChildBinarySensor):
    """ON when the child is at this house today (presence engine)."""

    _name_suffix = "present today"

    def __init__(
        self,
        coordinator: NestQuestCoordinator,
        child: ChildDaySnapshot,
    ) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{DOMAIN}_child_{child.child_id}_present_today"

    @property
    def is_on(self) -> bool | None:
        child = self._child
        if child is None:
            return None
        return child.present

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Base attributes plus, for a child away today, the ISO date
        of their next present day (the panel's away plate renders
        ``Returns <weekday>, <Mon D>`` from it)."""
        base = super().extra_state_attributes
        if base is None:
            return None
        child = self._child
        return {**base, "next_present": child.next_present if child else None}


def _child_binary_sensors(
    coordinator: NestQuestCoordinator, child: ChildDaySnapshot
) -> tuple[_NestQuestChildBinarySensor, ...]:
    """Build the two documented binary sensors for one active child."""
    return (
        NestQuestAllDoneSensor(coordinator, child),
        NestQuestPresentTodaySensor(coordinator, child),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[..., None],
) -> None:
    """Create the two binary sensors per active child.

    Entities are created for the snapshot's children at platform
    setup; a coordinator listener adds sensors for children that first
    appear on a later refresh (the day sensors' same pattern, so a new
    child's whole entity set lands together).  Deactivated children
    are NOT removed here — removal is a later task's scope.
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
                for sensor in _child_binary_sensors(coordinator, child)
            ]
        )

    data = coordinator.data
    if data is not None:
        _add_new_children(data.children)

    def _handle_coordinator_update() -> None:
        data = coordinator.data
        if data is not None:
            _add_new_children(data.children)

    coordinator.async_add_listener(_handle_coordinator_update)
