"""Test the pure panel snapshot builder (task 9047a97b).

The snapshot assembly that lived inline in the coordinator's
``_async_update_data`` was extracted into the Home-Assistant-free
:func:`custom_components.nestquest.core.snapshot.build_snapshot`, and
the panel payload shaper (:func:`instance_payload`) with it.  These
tests seed a household and assert the pure builder's output against
EXPLICIT literal expected values — not self-equality — so the AWAY
child's ``next_present``, a due-timed quest's ``overdue`` under a
pinned ``now``, the custody ``cycle_day`` (> 1), and the panel payload
dict shape (``done`` -> ``completed``, ``on_time`` passthrough, and
``missed`` omission) are all exercised as literals.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import create_child
from custom_components.nestquest.completion import complete_instance
from custom_components.nestquest.core.snapshot import (
    ChildDaySnapshot,
    NestQuestSnapshot,
    QuestInstanceView,
    build_snapshot,
    instance_payload,
)
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.dao_presence import (
    PresenceOverridesDao,
    PresenceSchedulesDao,
)
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import create_quest_definition
from custom_components.nestquest.recurrence import ScheduleRule


async def test_instance_payload_shape_and_missed_omission() -> None:
    """``instance_payload`` is the documented panel shape (§1).

    ``done`` maps to ``completed``; ``open`` passes through; ``on_time``
    is the builder's ``was_on_time`` verbatim; ``missed`` instances are
    omitted unless ``include_missed`` (the admin payload, D-009).
    """
    def view(state: str, *, overdue: bool = False, on_time: bool | None = None,
             completed_at: str | None = None, instance_id: int = 1) -> QuestInstanceView:
        return QuestInstanceView(
            instance_id=instance_id,
            definition_id=10,
            child_id=3,
            title="Fill bird feeder",
            icon="bird",
            window="afternoon",
            due_date="2026-09-21",
            due_time="17:00",
            state=state,
            overdue=overdue,
            completed_at=completed_at,
            was_on_time=on_time,
        )

    open_view = view("open", overdue=True)
    done_view = view("done", on_time=True, completed_at="2026-09-21T12:00:00+00:00")
    missed_view = view("missed", instance_id=2)

    panel = instance_payload([open_view, done_view, missed_view], include_missed=False)
    assert panel == [
        {
            "id": 1,
            "definition_id": 10,
            "child_id": 3,
            "title": "Fill bird feeder",
            "icon": "bird",
            "window": "afternoon",
            "due_time": "17:00",
            "state": "open",
            "overdue": True,
            "completed_at": None,
            "on_time": None,
        },
        {
            "id": 1,
            "definition_id": 10,
            "child_id": 3,
            "title": "Fill bird feeder",
            "icon": "bird",
            "window": "afternoon",
            "due_time": "17:00",
            "state": "completed",
            "overdue": False,
            "completed_at": "2026-09-21T12:00:00+00:00",
            "on_time": True,
        },
    ], "panel payload omits missed and spells done as completed"

    admin = instance_payload(
        [open_view, done_view, missed_view], include_missed=True
    )
    assert len(admin) == 3
    assert admin[2]["state"] == "missed", (
        "admin payload keeps missed instances with their missed state"
    )


async def test_build_snapshot_explicit_values(hass, make_entry) -> None:
    """The builder produces the documented shape as literals, pinned in time.

    Ada is AWAY today (a 2-week schedule whose absent week 0 covers today,
    plus a presence override marking her present on today+2) so
    ``present`` is False and ``next_present`` is the override date.  Her
    open quest due at 10:00 is OVERDUE under the pinned 12:00 ``now``.
    Bo's quest due at 17:00 is completed at 12:00 (on time) so its
    payload ``state`` is ``completed`` and ``on_time`` is True.  The first
    scheduled active child is Ada, whose 2-week cycle anchored one day
    before today puts ``cycle_day`` at 2.
    """
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    database = entry.runtime_data.database
    settings = entry.runtime_data.settings

    # Single clock read for the seed/snapshot anchor (no midnight skew).
    today = coordinator._local_now().date()
    time_zone = ZoneInfo(hass.config.time_zone)
    # Pin the build instant at 12:00 local: past Ada's 10:00 due time
    # (overdue) and before Bo's 17:00, and the completion moment for Bo.
    pinned_now = datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=time_zone
    )
    today_iso = today.isoformat()

    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")

    await create_quest_definition(
        database,
        "Pack bag",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today_iso}
        ),
        [ada.id],
        [("morning", "10:00")],
    )
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today_iso}
        ),
        [bo.id],
        [("morning", "17:00")],
    )
    end = (today + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today_iso, end, today=today)

    # Ada: 2-week cycle anchored yesterday. Week 0 (the empty segment)
    # covers today, so she is absent today; an override marks her present
    # on today+2, so next_present resolves to that date and cycle_day is
    # ((today - (today-1)) % 14) + 1 == 2.
    await PresenceSchedulesDao(database).upsert_by_child(
        ada.id,
        cycle_length_weeks=2,
        anchor_date=(today - datetime.timedelta(days=1)).isoformat(),
        pattern="|0,1,2,3,4,5,6",
    )
    returns_date = today + datetime.timedelta(days=2)
    await PresenceOverridesDao(database).create(
        ada.id,
        returns_date.isoformat(),
        returns_date.isoformat(),
        is_present=True,
        note="visit",
    )

    # Complete Bo's instance at the pinned 12:00 (17:00 due => on time).
    bo_instances = await QuestInstancesDao(database).list_by_child_and_date(
        bo.id, today_iso
    )
    await complete_instance(
        database,
        bo_instances[0].id,
        actor_source="panel",
        actor_child_id=bo.id,
        now=pinned_now,
        today=today,
    )

    built = await build_snapshot(database, settings, today, pinned_now)

    assert isinstance(built, NestQuestSnapshot)
    assert built.today_iso == today_iso
    assert built.cycle_day == 2, (
        "Ada's 2-week cycle anchored yesterday => day 2 today"
    )

    by_id = {child.child_id: child for child in built.children}
    assert list(by_id) == [ada.id, bo.id], (
        "active children appear in sort_order, id order"
    )
    ada_child = by_id[ada.id]
    bo_child = by_id[bo.id]

    # Ada: away today, returns on the override date, one open+overdue quest.
    assert isinstance(ada_child, ChildDaySnapshot)
    assert ada_child.present is False
    assert ada_child.next_present == returns_date.isoformat()
    assert ada_child.due_today == 1
    assert ada_child.completed_today == 0
    assert ada_child.remaining_today == 1
    assert ada_child.completion_pct == 0
    ada_view = ada_child.instances[0]
    assert isinstance(ada_view, QuestInstanceView)
    assert ada_view.state == "open"
    assert ada_view.due_time == "10:00"
    assert ada_view.overdue is True, "12:00 now is past the 10:00 due time"
    assert ada_view.completed_at is None
    assert ada_view.was_on_time is None

    # Bo: present, one completed instance, on time, not overdue.
    assert bo_child.present is True
    assert bo_child.next_present is None
    assert bo_child.due_today == 1
    assert bo_child.completed_today == 1
    assert bo_child.remaining_today == 0
    assert bo_child.completion_pct == 100
    bo_view = bo_child.instances[0]
    assert bo_view.state == "done"
    assert bo_view.due_time == "17:00"
    assert bo_view.overdue is False, "overdue is only computed for open state"
    assert bo_view.completed_at == f"{today_iso}T12:00:00+00:00"
    assert bo_view.was_on_time is True

    # Panel payload shape: Ada open+overdue stays open; Bo done -> completed.
    ada_payload = instance_payload(ada_child.instances, include_missed=False)
    assert ada_payload == [
        {
            "id": ada_view.instance_id,
            "definition_id": ada_view.definition_id,
            "child_id": ada.id,
            "title": "Pack bag",
            "icon": None,
            "window": "morning",
            "due_time": "10:00",
            "state": "open",
            "overdue": True,
            "completed_at": None,
            "on_time": None,
        }
    ]
    bo_payload = instance_payload(bo_child.instances, include_missed=False)
    assert bo_payload == [
        {
            "id": bo_view.instance_id,
            "definition_id": bo_view.definition_id,
            "child_id": bo.id,
            "title": "Brush teeth",
            "icon": None,
            "window": "morning",
            "due_time": "17:00",
            "state": "completed",
            "overdue": False,
            "completed_at": f"{today_iso}T12:00:00+00:00",
            "on_time": True,
        }
    ]

    # Missed omission is real: a missed view is dropped from the panel
    # payload and kept in the admin payload with its missed state.
    missed_view = QuestInstanceView(
        instance_id=999,
        definition_id=10,
        child_id=ada.id,
        title="Stale quest",
        icon=None,
        window="morning",
        due_date=(today - datetime.timedelta(days=1)).isoformat(),
        due_time="09:00",
        state="missed",
        overdue=False,
        completed_at=None,
        was_on_time=None,
    )
    assert instance_payload([missed_view], include_missed=False) == []
    assert (
        instance_payload([missed_view], include_missed=True)[0]["state"]
        == "missed"
    )
