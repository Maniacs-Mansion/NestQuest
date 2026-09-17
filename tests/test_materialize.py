"""Tests for materialize.py: the Feature 07 materialization walk."""
from __future__ import annotations

import asyncio
import datetime

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
)
from custom_components.nestquest.dao_presence import PresenceSchedulesDao
from custom_components.nestquest.dao_rules import QuestDefinitionsDao
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
    edit_quest_definition,
)
from custom_components.nestquest.recurrence import RuleType, ScheduleRule


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


NOW = "2026-09-14T12:00:00+00:00"


async def _prepare(path):
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    return database


def _with_db(tmp_path, name):
    def _run_test(body):
        async def _main():
            database = await _prepare(tmp_path / name)
            try:
                return await body(database)
            finally:
                await database.close()

        return _run(_main())

    return _run_test


def _future_monday() -> datetime.date:
    """The Monday of next week (strictly future, all 28 days eligible)."""
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    return this_monday + datetime.timedelta(days=7)


def _build_expected(start, def1_id, def2_id, a_id, b_id, c_id) -> set:
    """Hand-derived expected (definition_id, child_id, window, due_date,
    due_time) tuples over the four-week window.

    Custody: A is present week 0 and 2 of the two-week cycle, absent
    1 and 3; B is the mirror; C has no schedule (present every day).
    """
    expected: set = set()
    start_dt = datetime.date.fromisoformat(start)
    for offset in range(28):
        day = start_dt + datetime.timedelta(days=offset)
        iso = day.isoformat()
        week = offset // 7
        monday = day.weekday() == 0

        # Def1: DAILY, assignees A + C, window morning due 09:00.
        if week % 2 == 0:
            expected.add((def1_id, a_id, "morning", iso, "09:00"))
        expected.add((def1_id, c_id, "morning", iso, "09:00"))

        # Def2: WEEKLY Monday, assignees B + C, morning 07:00 + evening 19:00.
        if monday:
            if week % 2 == 1:
                expected.add((def2_id, b_id, "morning", iso, "07:00"))
                expected.add((def2_id, b_id, "evening", iso, "19:00"))
            expected.add((def2_id, c_id, "morning", iso, "07:00"))
            expected.add((def2_id, c_id, "evening", iso, "19:00"))
    return expected


async def _collect_instances(database, child_ids, start, end) -> set:
    dao = QuestInstancesDao(database)
    collected = set()
    for child_id in child_ids:
        for record in await dao.list_by_date_range(child_id, start, end):
            collected.add(
                (
                    record.definition_id,
                    record.child_id,
                    record.window,
                    record.due_date,
                    record.due_time,
                )
            )
    return collected


def test_materialize_two_custody_one_always_present(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        schedules = PresenceSchedulesDao(database)

        a = await children.create("Ada", NOW)      # present weeks 0, 2
        b = await children.create("Bo", NOW)       # present weeks 1, 3
        c = await children.create("Cleo", NOW)     # no schedule: always present

        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=27)).isoformat()

        await schedules.upsert_by_child(
            a.id, 2, start_iso, "0,1,2,3,4,5,6|"
        )
        await schedules.upsert_by_child(
            b.id, 2, start_iso, "|0,1,2,3,4,5,6"
        )

        def1 = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, c.id],
            [("morning", "09:00")],
        )
        def2 = await create_quest_definition(
            database,
            "Weekly chore",
            ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={0},
                start_date=start_iso,
            ),
            [b.id, c.id],
            [("morning", "07:00"), ("evening", "19:00")],
        )

        expected = _build_expected(
            start_iso, def1.definition.id, def2.definition.id,
            a.id, b.id, c.id,
        )

        count = await materialize(database, start_iso, end_iso)
        assert count == len(expected)

        actual = await _collect_instances(
            database, (a.id, b.id, c.id), start_iso, end_iso
        )
        assert actual == expected
        return count

    _with_db(tmp_path, "materialize.db")(_body)


def test_materialize_shares_one_generated_at_per_run(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=6)).isoformat()
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )
        await materialize(database, start_iso, end_iso)
        dao = QuestInstancesDao(database)
        stamps = {
            record.generated_at
            for record in await dao.list_by_date_range(
                child.id, start_iso, end_iso
            )
        }
        assert len(stamps) == 1
        return stamps

    _with_db(tmp_path, "materialize-stamp.db")(_body)


def test_materialize_is_idempotent(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=6)).isoformat()
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )
        dao = QuestInstancesDao(database)
        first = await materialize(database, start_iso, end_iso)
        assert first == 7
        first_ids = sorted(
            r.id
            for r in await dao.list_by_date_range(child.id, start_iso, end_iso)
        )
        assert len(first_ids) == 7
        assert len(set(first_ids)) == 7

        # Re-running over the same range refreshes the SAME physical rows:
        # the ON CONFLICT path updates the snapshot columns in place and
        # never delete + reinserts, so every primary-key id is stable.
        for _ in range(2):
            count = await materialize(database, start_iso, end_iso)
            assert count == 7
            run_ids = sorted(
                r.id
                for r in await dao.list_by_date_range(
                    child.id, start_iso, end_iso
                )
            )
            assert run_ids == first_ids

        # And the widened key never duplicated: exactly one physical row
        # per (definition_id, child_id, due_date, window).
        records = await dao.list_by_date_range(child.id, start_iso, end_iso)
        keys = [
            (r.definition_id, r.child_id, r.due_date, r.window)
            for r in records
        ]
        assert len(keys) == 7
        assert len(set(keys)) == 7
        return first

    _with_db(tmp_path, "materialize-idempotent.db")(_body)


def test_materialize_skips_completed_instance_on_re_run(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            [("morning", "09:00")],
        )

        await materialize(database, start_iso, end_iso)
        dao = QuestInstancesDao(database)
        records = await dao.list_by_date_range(child.id, start_iso, end_iso)
        assert len(records) == 3
        completed = records[0]

        await CompletionEventsDao(database).append(
            completed.id,
            child.id,
            "completed",
            "user",
            f"{start_iso}T08:00:00+00:00",
            True,
            actor_user_id="user-1",
        )

        # Change the definition so the tuple would otherwise regenerate:
        # the morning window's due time moves from 09:00 to 10:15.
        await edit_quest_definition(
            database,
            created.definition.id,
            windows=[("morning", "10:15")],
        )

        # Re-running must skip the completed instance (no exception) and
        # leave it untouched, while the open days regenerate to 10:15.
        count = await materialize(database, start_iso, end_iso)
        assert count == 2

        refreshed = await dao.list_by_date_range(child.id, start_iso, end_iso)
        by_due_date = {r.due_date: r for r in refreshed}
        survived = by_due_date[completed.due_date]
        assert survived.id == completed.id
        assert survived.due_time == "09:00"
        assert survived.generated_at == completed.generated_at

        others = [r for r in refreshed if r.id != completed.id]
        assert len(others) == 2
        assert {r.due_time for r in others} == {"10:15"}
        return count

    _with_db(tmp_path, "materialize-skip-completed.db")(_body)


async def _materialize_with_change(
    database, start_iso, end_iso, change
) -> int:
    """Run materialize, pause before its first atomic write, apply
    ``change``, then release.  Returns the materialize count.

    The gate parks the walk AFTER the single input snapshot is read but
    BEFORE the first :meth:`QuestInstancesDao.upsert_if_valid` call
    acquires the connection lock, so ``change`` commits against the live
    state and the write's own in-transaction precondition check then
    skips the tuples it invalidated (or, for a presence-only change,
    proceeds with the snapped presence).  This deterministically
    exercises the snapshot-to-insert gap that a config edit can
    interleave into.
    """
    original_upsert = QuestInstancesDao.upsert_if_valid
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = {"n": 0}

    async def _gated(self, definition_id, child_id, due_date, generated_at,
                     *, window, due_time=None):
        seen["n"] += 1
        if seen["n"] == 1:
            seen["first"] = (definition_id, child_id, window)
            entered.set()
            await release.wait()
        return await original_upsert(
            self, definition_id, child_id, due_date, generated_at,
            window=window, due_time=due_time,
        )

    QuestInstancesDao.upsert_if_valid = _gated
    try:
        task = asyncio.ensure_future(
            materialize(database, start_iso, end_iso)
        )
        await entered.wait()
        await change()
        release.set()
        return await task
    finally:
        QuestInstancesDao.upsert_if_valid = original_upsert


def test_materialize_skips_removed_assignee_mid_walk(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        a = await children.create("Ada", NOW)
        c = await children.create("Cleo", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, c.id],
            ["morning"],
        )

        async def _remove_assignee():
            await QuestDefinitionsDao(database).remove_assignee(
                created.definition.id, a.id
            )

        count = await _materialize_with_change(
            database, start_iso, end_iso, _remove_assignee
        )
        assert count == 3  # Cleo's three days survive
        assert await QuestInstancesDao(database).list_by_date_range(
            a.id, start_iso, end_iso
        ) == []
        assert len(await QuestInstancesDao(database).list_by_date_range(
            c.id, start_iso, end_iso
        )) == 3
        return count

    _with_db(tmp_path, "materialize-removed-assignee.db")(_body)


def test_materialize_skips_deactivated_definition_mid_walk(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        a = await children.create("Ada", NOW)
        c = await children.create("Cleo", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, c.id],
            ["morning"],
        )

        async def _deactivate():
            await QuestDefinitionsDao(database).set_active(
                created.definition.id, False
            )

        count = await _materialize_with_change(
            database, start_iso, end_iso, _deactivate
        )
        assert count == 0
        assert await QuestInstancesDao(database).list_by_date_range(
            a.id, start_iso, end_iso
        ) == []
        assert await QuestInstancesDao(database).list_by_date_range(
            c.id, start_iso, end_iso
        ) == []
        return count

    _with_db(tmp_path, "materialize-deactivated-definition.db")(_body)


def test_materialize_skips_removed_window_mid_walk(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        a = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id],
            [("morning", "09:00")],
        )

        async def _remove_window():
            await QuestDefinitionsDao(database).remove_window(
                created.definition.id, "morning"
            )

        count = await _materialize_with_change(
            database, start_iso, end_iso, _remove_window
        )
        assert count == 0
        assert await QuestInstancesDao(database).list_by_date_range(
            a.id, start_iso, end_iso
        ) == []
        return count

    _with_db(tmp_path, "materialize-removed-window.db")(_body)


def test_materialize_skips_deactivated_child_mid_walk(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        a = await children.create("Ada", NOW)
        c = await children.create("Cleo", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, c.id],
            ["morning"],
        )

        async def _deactivate_child():
            await ChildrenDao(database).set_active(a.id, False)

        count = await _materialize_with_change(
            database, start_iso, end_iso, _deactivate_child
        )
        assert count == 3  # Cleo's three days survive
        assert await QuestInstancesDao(database).list_by_date_range(
            a.id, start_iso, end_iso
        ) == []
        assert len(await QuestInstancesDao(database).list_by_date_range(
            c.id, start_iso, end_iso
        )) == 3
        return count

    _with_db(tmp_path, "materialize-deactivated-child.db")(_body)


def test_materialize_uses_single_presence_snapshot_mid_walk(tmp_path) -> None:
    async def _body(database):
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )

        children = ChildrenDao(database)
        overrides = PresenceOverridesDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )

        async def _add_blocking_override():
            await overrides.create(
                child.id, start_iso, end_iso, False, note="away"
            )

        # Presence is read once, inside the input snapshot; a blocking
        # override landing AFTER that read must not make the walk panic
        # or half-apply it.  The walk stays fully governed by the
        # snapshot it read: Ada was present every day there, so all
        # three days still materialize, deterministically.
        count = await _materialize_with_change(
            database, start_iso, end_iso, _add_blocking_override
        )
        assert count == 3
        assert len(await QuestInstancesDao(database).list_by_date_range(
            child.id, start_iso, end_iso
        )) == 3
        return count

    _with_db(tmp_path, "materialize-presence-snapshot.db")(_body)


def test_materialize_stores_snapshot_due_time_not_live(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=2)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            [("morning", "09:00")],
        )

        async def _edit_due_time():
            await QuestDefinitionsDao(database).upsert_window(
                created.definition.id, "morning", due_time="10:15"
            )

        # The window's due_time is edited to 10:15 between the input
        # snapshot and the insert.  The walk must store the SNAPSHOT's
        # 09:00, not the live 10:15 — the batch is governed entirely by
        # the coherent snapshot it read.
        count = await _materialize_with_change(
            database, start_iso, end_iso, _edit_due_time
        )
        assert count == 3
        records = await QuestInstancesDao(database).list_by_date_range(
            child.id, start_iso, end_iso
        )
        assert len(records) == 3
        assert {r.due_time for r in records} == {"09:00"}
        return records

    _with_db(tmp_path, "materialize-snapshot-due-time.db")(_body)


def test_materialize_honours_overrides(tmp_path) -> None:
    async def _body(database):
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )

        children = ChildrenDao(database)
        overrides = PresenceOverridesDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=6)).isoformat()
        # No schedule means the child is present every day; a blocking
        # override covering the whole week must still suppress every day.
        await overrides.create(
            child.id, start_iso, end_iso, False, note="away all week"
        )
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )
        count = await materialize(database, start_iso, end_iso)
        assert count == 0
        return count

    _with_db(tmp_path, "materialize-override.db")(_body)


def test_materialize_rejects_malformed_or_inverted_bounds(tmp_path) -> None:
    async def _body(database):
        start = (_future_monday()).isoformat()
        end = (datetime.date.fromisoformat(start)
               + datetime.timedelta(days=1)).isoformat()
        for bad in ("not-a-date", "2026-9-7", ""):
            with pytest.raises(ValueError, match="start_date"):
                await materialize(database, bad, end)
            with pytest.raises(ValueError, match="end_date"):
                await materialize(database, start, bad)
        with pytest.raises(ValueError, match="end_date must be on or after"):
            await materialize(database, end, start)
        return None

    _with_db(tmp_path, "materialize-bounds.db")(_body)


def test_materialize_skips_inactive_definitions(tmp_path) -> None:
    async def _body(database):
        from custom_components.nestquest.quest_definitions import (
            set_quest_definition_active,
        )

        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        start = _future_monday()
        start_iso = start.isoformat()
        end_iso = (start + datetime.timedelta(days=6)).isoformat()
        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )
        await set_quest_definition_active(database, created.definition.id, False)
        count = await materialize(database, start_iso, end_iso)
        assert count == 0
        return count

    _with_db(tmp_path, "materialize-inactive.db")(_body)