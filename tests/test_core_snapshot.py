"""Test the pure panel snapshot builder (task 9047a97b).

The snapshot assembly that lived inline in the coordinator's
``_async_update_data`` was extracted into the Home-Assistant-free
:func:`custom_components.nestquest.core.snapshot.build_snapshot`.  This
test seeds a household (active + inactive children, a daily quest
definition, today's instances, one completed instance, and a presence
schedule) and asserts the pure builder's output is byte-for-byte equal
to the coordinator's snapshot for the SAME database and date — the
shared-implementation invariant the API panel snapshot route depends on.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import (
    create_child,
    list_children,
    set_child_active,
)
from custom_components.nestquest.completion import complete_instance
from custom_components.nestquest.core.snapshot import (
    ChildDaySnapshot,
    NestQuestSnapshot,
    QuestInstanceView,
    build_snapshot,
)
from custom_components.nestquest.dao_presence import PresenceSchedulesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import create_quest_definition
from custom_components.nestquest.recurrence import ScheduleRule

SEED_HORIZON_DAYS = 3


def _today() -> datetime.date:
    return datetime.date.today()


async def _seed_household(database):
    """Three active children + one inactive; a daily quest for two of them.

    Ada and Bo share a daily morning quest; Cory is active but has no
    quest (exercises the empty-instance / 100%-completion path); Ghost
    is inactive and must be absent from the snapshot.  Ada's first
    instance is completed so the ``done`` state and rollup counts are
    exercised, not just the ``open`` default.
    """
    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")
    cory = await create_child(database, "Cory")
    ghost = await create_child(database, "Ghost")
    await set_child_active(database, ghost.id, False)

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

    # A 1-week presence schedule for Ada, present every day, anchored
    # today: exercises cycle_day (== 1) and the present=True path.  Bo
    # and Cory have no schedule, so the engine treats them as present
    # every day (the documented default).
    await PresenceSchedulesDao(database).upsert_by_child(
        ada.id,
        cycle_length_weeks=1,
        anchor_date=today.isoformat(),
        pattern="0,1,2,3,4,5,6",
    )
    return ada, bo, cory, ghost


async def test_build_snapshot_matches_coordinator_snapshot(
    hass, make_entry
) -> None:
    """The pure builder and the coordinator produce identical snapshots."""
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    settings = entry.runtime_data.settings
    ada, bo, cory, ghost = await _seed_household(database)

    # Complete Ada's first open instance through the business layer so
    # the ``done`` state, completed_at/was_on_time, and the rollup
    # counts are exercised alongside the ``open`` default for Bo.
    active_children = await list_children(database, active_only=True)
    ada_id = next(child.id for child in active_children if child.display_name == "Ada")
    bo_id = next(child.id for child in active_children if child.display_name == "Bo")
    await coordinator.async_refresh()
    ada_snapshot = next(
        child for child in coordinator.data.children if child.child_id == ada_id
    )
    await complete_instance(
        database,
        ada_snapshot.instances[0].instance_id,
        actor_source="panel",
        actor_child_id=ada_id,
    )

    # Drive the coordinator's refresh (the path production takes) and
    # the pure builder with the SAME date and timezone the coordinator
    # resolves, so the comparison is exact — no host-clock skew, no
    # timezone drift.  Instances here carry no due_time, so the overdue
    # flag is False regardless of the instant each pass reads ``now``.
    await coordinator.async_refresh()
    coordinator_snapshot = coordinator.data
    today = coordinator._local_now().date()
    time_zone = ZoneInfo(hass.config.time_zone)
    built = await build_snapshot(database, settings, today, time_zone)

    assert isinstance(built, NestQuestSnapshot)
    assert built == coordinator_snapshot, (
        "build_snapshot and the coordinator must produce identical "
        "snapshots for the same database, date, and timezone"
    )

    # Shape and documented invariants, not just equality: children in
    # sort order, inactive child omitted, missed instances omitted from
    # the panel payload (none are missed in this seed, so the instances
    # tuple carries only open/done views), per-child counts, presence,
    # and cycle day.
    active_ordered = await list_children(database, active_only=True)
    active_ids_ordered = [child.id for child in active_ordered]
    child_ids = [child.child_id for child in built.children]
    assert ghost.id not in child_ids, "inactive child must be absent"
    assert child_ids == active_ids_ordered, (
        "children must appear in the DAO's sort_order, id order"
    )
    assert built.today_iso == today.isoformat()
    assert built.cycle_day == 1, "Ada's 1-week schedule anchored today => day 1"

    by_id = {child.child_id: child for child in built.children}
    ada_child = by_id[ada_id]
    bo_child = by_id[bo_id]
    cory_child = by_id[cory.id]
    for child in built.children:
        assert isinstance(child, ChildDaySnapshot)
        for view in child.instances:
            assert isinstance(view, QuestInstanceView)
            assert view.state in ("open", "done", "missed")
            # Missed instances are omitted from the panel payload shape;
            # in this seed none are missed (today's open instances have
            # not crossed their due time and there is no due_time set).
            assert view.state != "missed", (
                "no instance should be missed for today's seed"
            )

    assert ada_child.present is True
    assert bo_child.present is True
    assert cory_child.present is True
    assert cory_child.instances == ()
    assert cory_child.due_today == 0
    assert cory_child.completion_pct == 100

    assert ada_child.due_today == 1
    assert ada_child.completed_today == 1
    assert ada_child.remaining_today == 0
    assert ada_child.completion_pct == 100
    assert ada_child.instances[0].state == "done"
    assert ada_child.instances[0].completed_at is not None
    assert ada_child.instances[0].was_on_time is not None

    assert bo_child.due_today == 1
    assert bo_child.completed_today == 0
    assert bo_child.remaining_today == 1
    assert bo_child.completion_pct == 0
    assert bo_child.instances[0].state == "open"
    assert bo_child.instances[0].completed_at is None
    assert bo_child.instances[0].was_on_time is None
