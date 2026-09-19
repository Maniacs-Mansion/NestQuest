"""The shared NestQuest DataUpdateCoordinator (Feature 10).

ONE refresh pass builds the whole entity snapshot: active children,
today's instances with their derived states (open / done / missed via
:func:`~.completion.derive_state`), each child's presence today, and
per-child rollup counts.  Every Feature 10 entity reads
``coordinator.data`` — no entity queries the database itself, so one
refresh updates the whole board coherently.

"Today" and "now" are HA-local (``hass.config.time_zone``), never the
host clock and never UTC, matching the materialization and completion
layers.

Presence is resolved through the SAME engine the materializer uses
(:class:`~.presence.PresenceEngine`): schedules and overrides are read
with the public DAO methods and the engine's anchor-date arithmetic
answers ``is this child at this house today`` (D-004 — never ISO week
parity).

``cycle_day`` reports where today falls in the custody cycle of the
first active child (display order) that HAS a schedule — 1-based day
``N`` of ``cycle_length_weeks * 7``, computed from that schedule's
anchor date.  ``0`` means no active child has a schedule at all, so
the admin header degrades to a harmless zero instead of guessing.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .completion import derive_state
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL,
)
from .dao_children import ChildrenDao
from .dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
)
from .dao_rules import QuestDefinitionsDao
from .dao_presence import PresenceOverridesDao, PresenceSchedulesDao
from .db import NestQuestDatabase
from .presence import (
    PresenceEngine,
    PresenceOverride,
    PresenceSchedule,
)


@dataclass(frozen=True)
class QuestInstanceView:
    """One instance plus everything the entities render from it."""

    instance_id: int
    definition_id: int
    child_id: int
    title: str
    icon: str | None
    window: str
    due_date: str
    due_time: str | None
    state: str  # open | done | missed
    overdue: bool
    completed_at: str | None
    was_on_time: bool | None


@dataclass(frozen=True)
class ChildDaySnapshot:
    """One active child's day: instances, presence, and rollup counts."""

    child_id: int
    child_name: str
    instances: tuple[QuestInstanceView, ...]
    present: bool
    due_today: int
    completed_today: int
    remaining_today: int
    completion_pct: int


@dataclass(frozen=True)
class NestQuestSnapshot:
    """The coordinator's whole-entity data payload."""

    today_iso: str
    children: tuple[ChildDaySnapshot, ...]
    cycle_day: int


class NestQuestCoordinator(DataUpdateCoordinator):
    """Shared refresh cycle for every NestQuest entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        database: NestQuestDatabase,
        update_interval_seconds: int | None = None,
    ) -> None:
        interval = update_interval_seconds
        if (
            not isinstance(interval, int)
            or isinstance(interval, bool)
            or interval < MIN_UPDATE_INTERVAL
        ):
            interval = DEFAULT_UPDATE_INTERVAL
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=interval),
        )
        self.entry_id = entry_id
        self.database = database

    def _local_now(self) -> datetime.datetime:
        time_zone = ZoneInfo(self.hass.config.time_zone)
        return datetime.datetime.now(time_zone)

    async def _async_update_data(self) -> NestQuestSnapshot:
        now = self._local_now()
        today = now.date()
        today_iso = today.isoformat()

        children = await ChildrenDao(self.database).list_active()

        schedules: dict[int, PresenceSchedule] = {}
        overrides: dict[int, list[PresenceOverride]] = {}
        for child in children:
            schedule = await PresenceSchedulesDao(self.database).get_by_child(
                child.id
            )
            if schedule is not None:
                schedules[child.id] = PresenceSchedule.decode(
                    child.id, schedule.anchor_date, schedule.pattern
                )
            todays = await PresenceOverridesDao(
                self.database
            ).list_by_child_and_range(child.id, today_iso, today_iso)
            if todays:
                # The engine validates MODEL objects, not DAO records;
                # each record converts losslessly (the schema guarantees
                # end >= start and a real is_present).
                overrides[child.id] = [
                    PresenceOverride(
                        record.child_id,
                        record.start_date,
                        record.end_date,
                        record.is_present,
                        record.note,
                    )
                    for record in todays
                ]
        engine = PresenceEngine(schedules, overrides)

        instances_dao = QuestInstancesDao(self.database)
        events_dao = CompletionEventsDao(self.database)
        definitions_dao = QuestDefinitionsDao(self.database)

        snapshots: list[ChildDaySnapshot] = []
        for child in children:
            instances = await instances_dao.list_by_date_range(
                child.id, today_iso, today_iso
            )
            views: list[QuestInstanceView] = []
            for instance in instances:
                latest = await events_dao.get_latest_for_instance(instance.id)
                definition = await definitions_dao.get(instance.definition_id)
                state = derive_state(instance, latest, today)
                overdue = False
                if state == "open" and instance.due_date == today_iso:
                    if instance.due_time is not None:
                        due_moment = datetime.datetime.strptime(
                            instance.due_time, "%H:%M"
                        ).time()
                        overdue = now.time() > due_moment
                views.append(
                    QuestInstanceView(
                        instance_id=instance.id,
                        definition_id=instance.definition_id,
                        child_id=instance.child_id,
                        title=definition.title if definition else "Quest",
                        icon=definition.icon if definition else None,
                        window=instance.window,
                        due_date=instance.due_date,
                        due_time=instance.due_time,
                        state=state,
                        overdue=overdue,
                        completed_at=(
                            latest.occurred_at
                            if latest is not None
                            and latest.event_type == "completed"
                            else None
                        ),
                        was_on_time=(
                            latest.was_on_time
                            if latest is not None
                            and latest.event_type == "completed"
                            else None
                        ),
                    )
                )
            due = len(views)
            completed = sum(1 for view in views if view.state == "done")
            remaining = due - completed
            snapshots.append(
                ChildDaySnapshot(
                    child_id=child.id,
                    child_name=child.display_name,
                    instances=tuple(views),
                    present=engine.is_present(child.id, today),
                    due_today=due,
                    completed_today=completed,
                    remaining_today=remaining,
                    completion_pct=(
                        round(completed * 100 / due) if due else 100
                    ),
                )
            )

        return NestQuestSnapshot(
            today_iso=today_iso,
            children=tuple(snapshots),
            cycle_day=_cycle_day(schedules, children, today),
        )


def _cycle_day(
    schedules: dict[int, PresenceSchedule], children, today: datetime.date
) -> int:
    """Return today's 1-based day in the first scheduled child's cycle.

    Anchor-date arithmetic ONLY (D-004): the day offset is computed from
    the schedule's own anchor, never ISO week numbers or parity, so a
    53-week year cannot silently invert the cycle.
    """
    for child in children:
        schedule = schedules.get(child.id)
        if schedule is None:
            continue
        days = (today - schedule.anchor_date).days
        cycle_length = schedule.cycle_length_weeks * 7
        return (days % cycle_length) + 1
    return 0
