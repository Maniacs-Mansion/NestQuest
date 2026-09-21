"""Pure, Home-Assistant-free panel snapshot builder.

The household snapshot the NestQuest panel renders — active children in
sort order, each child's today-instances in the documented payload shape
(missed instances OMITTED from the entity-facing attribute payload, but
retained on the snapshot for the count rollups), per-child counts and
presence, and the custody cycle day — used to be assembled inline inside
:mod:`custom_components.nestquest.coordinator`'s
``_async_update_data``.  That assembly is HA-coupled only because its
host is a :class:`~homeassistant.helpers.update_coordinator.DataUpdateCoordinator`;
the assembly itself touches no HA surface.

This module holds the pure pieces — the snapshot dataclasses
(:class:`QuestInstanceView`, :class:`ChildDaySnapshot`,
:class:`NestQuestSnapshot`), the cycle-day helper (:func:`_cycle_day`),
the panel payload shaper (:func:`instance_payload`), and the async
:func:`build_snapshot` builder — so the HA coordinator and the API
service's panel snapshot route share ONE implementation of both the
snapshot assembly and the entity-facing attribute payload shape.
Nothing here imports :mod:`homeassistant`; the builder takes the
database, the settings object, the target date, and the HA-local
``now`` (a single clock read the caller already resolved) and returns
the snapshot, mirroring exactly what the coordinator used to do inline.

``settings`` is accepted because the API route hands in the entry's
:class:`~.settings.NestQuestSettings`; it is CURRENTLY UNUSED — the
assembly reads nothing from it — and is retained so the builder's
contract stays stable if a future panel feature derives scan caps or
rollup behaviour from configuration.  No speculative read is wired in.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .completion import derive_state
from .dao_children import ChildrenDao
from .dao_instances import CompletionEventsDao, QuestInstancesDao
from .dao_presence import PresenceOverridesDao, PresenceSchedulesDao
from .dao_rules import QuestDefinitionsDao
from .db import NestQuestDatabase
from .presence import (
    MAX_PREVIEW_SCAN_DAYS,
    PresenceEngine,
    PresenceOverride,
    PresenceSchedule,
)
from .settings import NestQuestSettings


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
    #: For a child away today: the ISO date of their next present day
    #: (the panel's away plate renders ``Returns <weekday>, <Mon D>``
    #: from it).  ``None`` when the child is present today or no
    #: present day exists within the presence engine's scan cap.
    next_present: str | None = None


@dataclass(frozen=True)
class NestQuestSnapshot:
    """The coordinator's whole-entity data payload."""

    today_iso: str
    children: tuple[ChildDaySnapshot, ...]
    cycle_day: int


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


def instance_payload(
    instances: Iterable[QuestInstanceView], *, include_missed: bool
) -> list[dict[str, Any]]:
    """Shape instance dicts per ENTITIES-AND-SERVICES.md §1.

    The panel payload ``state`` is the documented ``open`` | ``completed``
    spelling, so the builder's derived ``done`` maps to ``completed`` here;
    ``open`` passes through.  ``missed`` instances are OMITTED from the
    entity-facing attribute payload (decision 5) unless ``include_missed``
    is set — the admin payload (D-009) keeps them with their ``missed``
    state.  ``on_time`` passes the builder's ``was_on_time`` through
    verbatim (``True`` / ``False`` for a completed instance, ``None`` for
    an open one).  This is the SINGLE shared implementation both the HA
    sensor layer and the API panel route read; it touches no Home
    Assistant surface.
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


async def build_snapshot(
    database: NestQuestDatabase,
    settings: NestQuestSettings,
    today: datetime.date,
    now: datetime.datetime,
) -> NestQuestSnapshot:
    """Build the household panel snapshot for ``today`` at the ``now`` instant.

    Mirrors the assembly that lived in the coordinator's
    ``_async_update_data``: active children in sort order, each child's
    today-instances with derived state (open / done / missed via
    :func:`~.completion.derive_state`) and the overdue flag, per-child
    presence (resolved through :class:`~.presence.PresenceEngine`), the
    per-child rollup counts, and the custody cycle day of the first
    scheduled active child.  Missed instances are retained on the
    snapshot (the rollup counts and the panel's missed plate need them)
    but the entity-facing attribute payload omits them at the
    :func:`instance_payload` layer — this builder produces the shared
    shape both consumers read.

    ``now`` is the HA-local timezone-aware datetime the caller already
    resolved (a SINGLE clock read); the overdue check compares
    ``now.time()`` against the instance's ``due_time`` for today's open
    instances.  The builder performs NO internal clock read — it never
    calls :func:`datetime.datetime.now` — so the instant is pinned in
    tests and date and time can never disagree across two reads.
    ``today`` is the calendar date the caller resolved from the same
    clock (``now.date()``); it anchors the due-date and cycle-day
    arithmetic.  ``settings`` is accepted but currently unused (see the
    module docstring).
    """
    today_iso = today.isoformat()

    children = await ChildrenDao(database).list_active()

    schedules: dict[int, PresenceSchedule] = {}
    overrides: dict[int, list[PresenceOverride]] = {}
    for child in children:
        schedule = await PresenceSchedulesDao(database).get_by_child(
            child.id
        )
        if schedule is not None:
            schedules[child.id] = PresenceSchedule.decode(
                child.id, schedule.anchor_date, schedule.pattern
            )
        window_end = today + datetime.timedelta(
            days=MAX_PREVIEW_SCAN_DAYS
        )
        window_end_iso = window_end.isoformat()
        ranged = await PresenceOverridesDao(
            database
        ).list_by_child_and_range(child.id, today_iso, window_end_iso)
        if ranged:
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
                for record in ranged
            ]
    engine = PresenceEngine(schedules, overrides)

    instances_dao = QuestInstancesDao(database)
    events_dao = CompletionEventsDao(database)
    definitions_dao = QuestDefinitionsDao(database)

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
        child_present = engine.is_present(child.id, today)
        next_present: str | None = None
        if not child_present:
            try:
                next_present = engine.next_present_dates(
                    child.id, today, 1
                )[0].isoformat()
            except ValueError:
                next_present = None
        snapshots.append(
            ChildDaySnapshot(
                child_id=child.id,
                child_name=child.display_name,
                instances=tuple(views),
                present=child_present,
                due_today=due,
                completed_today=completed,
                remaining_today=remaining,
                completion_pct=(
                    round(completed * 100 / due) if due else 100
                ),
                next_present=next_present,
            )
        )

    return NestQuestSnapshot(
        today_iso=today_iso,
        children=tuple(snapshots),
        cycle_day=_cycle_day(schedules, children, today),
    )
