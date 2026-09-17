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
from custom_components.nestquest.dao_rules import (
    QuestDefinitionsDao,
    schedule_rule_to_storage,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.materialize import (
    materialize,
    regenerate_for_child,
    regenerate_for_definition,
)
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
    edit_quest_definition,
)
from custom_components.nestquest.recurrence import (
    RuleType,
    ScheduleRule,
    occurs_on,
)


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
                     *, window, due_time=None, today=None):
        seen["n"] += 1
        if seen["n"] == 1:
            seen["first"] = (definition_id, child_id, window)
            entered.set()
            await release.wait()
        return await original_upsert(
            self, definition_id, child_id, due_date, generated_at,
            window=window, due_time=due_time, today=today,
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


def test_materialize_accepts_ha_local_today_behind_host(tmp_path) -> None:
    """The clamp and no-past guard compare against a caller-supplied HA-local today.

    A household time zone behind the host clock around midnight resolves a
    HA-local "today" one calendar day earlier than the host's
    ``date.today()``.  The walk clamps its start to that anchor: without
    a pinned HA-local date the effective start is the host's today (one
    day after ha_today), so the now-past day is skipped rather than
    rejected, and only the host-today-onward days materialize.
    """
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)
        ha_today = datetime.date.today() - datetime.timedelta(days=1)
        start_iso = ha_today.isoformat()
        end_iso = (ha_today + datetime.timedelta(days=14)).isoformat()
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )

        # Without a pinned HA-local today, the walk clamps its start to the
        # host's today (one day after ha_today); the past day is dropped and
        # the 14 host-today-onward days materialize.
        without_pin = await materialize(database, start_iso, end_iso)
        assert without_pin == 14

        # With today=ha_today, the full 15-day horizon materializes.
        count = await materialize(database, start_iso, end_iso, today=ha_today)
        assert count == 15
        return count

    _with_db(tmp_path, "materialize-ha-local-today.db")(_body)


def test_materialize_clamps_past_start_to_today(tmp_path) -> None:
    """A past start_date is clamped to today: no past-dated instance is created.

    A caller passing a start one month in the past never yields a
    past-dated instance: the walk clamps its effective start up to today
    and materializes only dates on/after today, leaving the past untouched
    rather than raising or corrupting state.
    """
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)

        today = datetime.date.today()
        start_iso = (today - datetime.timedelta(days=30)).isoformat()
        end_iso = (today + datetime.timedelta(days=14)).isoformat()

        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )

        count = await materialize(database, start_iso, end_iso, today=today)
        assert count == 15

        dao = QuestInstancesDao(database)
        records = await dao.list_by_date_range(child.id, start_iso, end_iso)
        assert len(records) == 15
        assert all(r.due_date >= today.isoformat() for r in records)

        # The past month is empty: no past-dated instance was ever created.
        past_records = await dao.list_by_date_range(
            child.id,
            start_iso,
            (today - datetime.timedelta(days=1)).isoformat(),
        )
        assert past_records == []
        return count

    _with_db(tmp_path, "materialize-past-start.db")(_body)


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


def test_regenerate_for_definition_rebuilds_horizon_and_preserves_completed(
    tmp_path,
) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)

        today = datetime.date.today()
        horizon_end = today + datetime.timedelta(days=14)
        start_iso = today.isoformat()

        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            [("morning", "09:00")],
        )
        definition_id = created.definition.id

        dao = QuestInstancesDao(database)
        await materialize(database, start_iso, horizon_end.isoformat())
        baseline = await dao.list_by_date_range(
            child.id, start_iso, horizon_end.isoformat()
        )
        assert len(baseline) == 15

        # Park a completion on tomorrow.  The rule rewrite below gives the
        # new weekly shape a weekday two days out, so tomorrow never fires
        # under it — only the completion's immutability keeps the row.
        completed_due = (today + datetime.timedelta(days=1)).isoformat()
        completed = next(r for r in baseline if r.due_date == completed_due)
        await CompletionEventsDao(database).append(
            completed.id,
            child.id,
            "completed",
            "user",
            f"{completed_due}T08:00:00+00:00",
            True,
            actor_user_id="user-1",
        )

        # Rewrite the rule through the DAO (not the business layer) so
        # this test drives ``regenerate_for_definition`` directly.
        new_weekday = (today + datetime.timedelta(days=2)).weekday()
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={new_weekday},
            start_date=start_iso,
        )
        await QuestDefinitionsDao(database).edit_definition(
            definition_id, rule=schedule_rule_to_storage(weekly)
        )

        await regenerate_for_definition(database, definition_id)

        records = await dao.list_by_date_range(
            child.id, start_iso, horizon_end.isoformat()
        )
        by_due = {r.due_date: r for r in records}

        # The completed row survived untouched (same physical id).
        assert by_due[completed_due].id == completed.id

        # Every other horizon day matches the new weekly rule exactly.
        for offset in range(15):
            day = today + datetime.timedelta(days=offset)
            iso = day.isoformat()
            if iso == completed_due:
                assert iso in by_due
            else:
                assert (iso in by_due) == occurs_on(weekly, day)
        return None

    _with_db(tmp_path, "regenerate.db")(_body)


def test_edit_quest_definition_regenerates_future_instances(tmp_path) -> None:
    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)

        today = datetime.date.today()
        horizon_end = today + datetime.timedelta(days=14)
        start_iso = today.isoformat()

        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            ["morning"],
        )
        definition_id = created.definition.id

        dao = QuestInstancesDao(database)
        await materialize(database, start_iso, horizon_end.isoformat())

        # The business-layer edit wires regeneration: no explicit
        # ``regenerate_for_definition`` call is made here.
        new_weekday = (today + datetime.timedelta(days=2)).weekday()
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={new_weekday},
            start_date=start_iso,
        )
        await edit_quest_definition(database, definition_id, rule=weekly)

        records = await dao.list_by_date_range(
            child.id, start_iso, horizon_end.isoformat()
        )
        by_due = {r.due_date: r for r in records}
        for offset in range(15):
            day = today + datetime.timedelta(days=offset)
            assert (day.isoformat() in by_due) == occurs_on(weekly, day)
        return None

    _with_db(tmp_path, "edit-regenerates.db")(_body)


def test_regenerate_for_child_rebuilds_horizon_preserves_history(
    tmp_path,
) -> None:
    async def _body(database):
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )

        children = ChildrenDao(database)
        overrides = PresenceOverridesDao(database)
        child = await children.create("Ada", NOW)

        today = datetime.date.today()
        horizon_end = today + datetime.timedelta(days=14)
        start_iso = today.isoformat()

        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [child.id],
            [("morning", "09:00")],
        )

        dao = QuestInstancesDao(database)
        events = CompletionEventsDao(database)

        # Instances across the full horizon: 15 daily rows.
        await materialize(database, start_iso, horizon_end.isoformat())
        all_future = await dao.list_by_date_range(
            child.id, start_iso, horizon_end.isoformat()
        )
        assert len(all_future) == 15

        # A completed instance on tomorrow: immutable, must be spared.
        completed_due = (today + datetime.timedelta(days=1)).isoformat()
        completed = next(r for r in all_future if r.due_date == completed_due)
        await events.append(
            completed.id,
            child.id,
            "completed",
            "user",
            f"{completed_due}T08:00:00+00:00",
            True,
            actor_user_id="user-1",
        )

        # A past instance (yesterday): raw insert bypasses the walk's
        # no-past guard so the child-scoped delete has history to spare.
        past_due = (today - datetime.timedelta(days=1)).isoformat()
        await database.execute(
            "INSERT INTO quest_instances (definition_id, child_id, "
            "window, due_date, due_time, generated_at) "
            "VALUES (?, ?, 'morning', ?, '09:00', ?)",
            (created.definition.id, child.id, past_due, NOW),
        )

        # An ABSENT override covering three future dates that had
        # instances: days 2..4 after today.
        absent_start = (today + datetime.timedelta(days=2)).isoformat()
        absent_end = (today + datetime.timedelta(days=4)).isoformat()
        override = await overrides.create(
            child.id, absent_start, absent_end, False, note="away"
        )

        await regenerate_for_child(database, child.id)

        records = await dao.list_by_date_range(
            child.id, past_due, horizon_end.isoformat()
        )
        by_due = {r.due_date: r for r in records}

        # The now-absent days' instances are gone.
        for offset in range(2, 5):
            iso = (today + datetime.timedelta(days=offset)).isoformat()
            assert iso not in by_due

        # The completed instance survived untouched (same physical id).
        assert by_due[completed_due].id == completed.id

        # The past instance survived.
        assert past_due in by_due

        # Every non-absent future day still has its instance.
        for offset in range(15):
            iso = (today + datetime.timedelta(days=offset)).isoformat()
            if 2 <= offset <= 4:
                continue
            assert iso in by_due

        # Remove the override and regenerate again: the absent days return.
        await overrides.delete(override.id)
        await regenerate_for_child(database, child.id)

        records = await dao.list_by_date_range(
            child.id, past_due, horizon_end.isoformat()
        )
        by_due = {r.due_date: r for r in records}

        for offset in range(15):
            iso = (today + datetime.timedelta(days=offset)).isoformat()
            assert iso in by_due

        # The completed instance is still the same untouched row, and the
        # past instance is still there.
        assert by_due[completed_due].id == completed.id
        assert by_due[completed_due].due_time == "09:00"
        assert past_due in by_due
        return None

    _with_db(tmp_path, "regenerate-child.db")(_body)


def test_regenerate_for_child_uses_single_anchor_across_midnight(
    tmp_path, monkeypatch
) -> None:
    """A call queued across midnight must not delete-then-fail-to-rebuild.

    ``regenerate_for_child`` reads "today" once as a cutoff hint, but the
    delete clamps that cutoff to the execution-day under its own lock and
    RETURNS the effective cutoff; the re-materialization window is then
    anchored to the same returned day.  This test fakes a midnight rollover
    between the two reads: the caller's hint is day0 while the delete
    executes on day1.  The rebuild must start on day1 (so the walk's
    no-past guard never fires) and the now-past day0 instance must survive.
    """
    day0 = datetime.date.today() + datetime.timedelta(days=30)
    day1 = day0 + datetime.timedelta(days=1)

    clock = {"rolled": False, "reads": 0}

    def _fake_today() -> datetime.date:
        if not clock["rolled"]:
            return day0
        clock["reads"] += 1
        return day0 if clock["reads"] == 1 else day1

    import custom_components.nestquest.dao_instances as dao_instances_module

    monkeypatch.setattr(dao_instances_module, "_today", _fake_today)

    async def _body(database):
        children = ChildrenDao(database)
        child = await children.create("Ada", NOW)

        day0_iso = day0.isoformat()
        horizon_end = day0 + datetime.timedelta(days=14)

        created = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=day0_iso),
            [child.id],
            [("morning", "09:00")],
        )
        dao = QuestInstancesDao(database)

        # Seed the horizon while the clock reads day0.
        await materialize(database, day0_iso, horizon_end.isoformat())

        # Roll the clock forward: every read after the caller's single
        # cutoff hint now returns day1 (the delete's execution-day).
        clock["rolled"] = True
        clock["reads"] = 0

        rebuilt = await regenerate_for_child(database, child.id)

        # No raise occurred; the rebuilt window is anchored on the delete's
        # execution-day (day1), so day1..day1+14 all exist.
        assert rebuilt == 15
        day1_iso = day1.isoformat()
        day1_horizon_end = day1 + datetime.timedelta(days=14)
        assert len(await dao.list_by_date_range(
            child.id, day1_iso, day1_horizon_end.isoformat()
        )) == 15

        # day0 was the caller's "today" but rolled over to the past by the
        # time the delete ran; it must survive (never delete the past).
        assert await dao.get(
            created.definition.id, child.id, day0_iso, "morning"
        ) is not None
        return rebuilt

    _with_db(tmp_path, "regenerate-child-midnight.db")(_body)


def test_regenerate_for_child_is_child_scoped(tmp_path) -> None:
    """Regenerating one child must never touch another child's rows."""
    async def _body(database):
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )

        children = ChildrenDao(database)
        overrides = PresenceOverridesDao(database)
        a = await children.create("Ada", NOW)
        b = await children.create("Bo", NOW)

        today = datetime.date.today()
        horizon_end = today + datetime.timedelta(days=14)
        start_iso = today.isoformat()

        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, b.id],
            [("morning", "09:00")],
        )

        dao = QuestInstancesDao(database)
        await materialize(database, start_iso, horizon_end.isoformat())

        # Baseline for child b, keyed by due_date, so we can prove its rows
        # are byte-for-byte unchanged afterward.
        baseline_b = {
            r.due_date: (r.id, r.due_time, r.generated_at)
            for r in await dao.list_by_date_range(
                b.id, start_iso, horizon_end.isoformat()
            )
        }
        assert len(baseline_b) == 15

        # An ABSENT override for child a only, covering days 2..4.
        absent_start = (today + datetime.timedelta(days=2)).isoformat()
        absent_end = (today + datetime.timedelta(days=4)).isoformat()
        await overrides.create(
            a.id, absent_start, absent_end, False, note="away"
        )

        await regenerate_for_child(database, a.id)

        # Child a's now-absent days vanished.
        a_by_due = {
            r.due_date: r
            for r in await dao.list_by_date_range(
                a.id, start_iso, horizon_end.isoformat()
            )
        }
        for offset in range(2, 5):
            iso = (today + datetime.timedelta(days=offset)).isoformat()
            assert iso not in a_by_due

        # Child b is untouched: same physical rows, same snapshot columns.
        b_records = await dao.list_by_date_range(
            b.id, start_iso, horizon_end.isoformat()
        )
        assert len(b_records) == 15
        for r in b_records:
            assert (r.id, r.due_time, r.generated_at) == baseline_b[r.due_date]
        return None

    _with_db(tmp_path, "regenerate-child-scoped.db")(_body)


#: Fixed end-to-end anchor: 2026-06-01 is a Monday AND the 1st of its month,
#: so the two-week custody cycle is week-aligned and the yearly rule's
#: "1st of the anchor month" is GUARANTEED to fire inside the 28-day window
#: (pin ``today=anchor`` throughout so the walk never clamps this fixed
#: calendar date up to the host clock).
_E2E_ANCHOR = "2026-06-01"

#: Hand-checked oracle over 2026-06-01 .. 2026-06-28 (69 entries).  Each row
#: is one independent (definition, child, window, due_date, due_time); the
#: definition/child slugs are substituted with runtime ids, but the dates are
#: literal, reviewed by hand — no recurrence/presence math is re-run here.
#: Custody (2-week cycle anchored on the Monday): A present weeks 0 and 2,
#: B present weeks 1 and 3, C present every day.
_E2E_EXPECTED = [
    # daily  [A, C]  morning 09:00, every day.  A present weeks 0, 2.
    ("daily", "A", "morning", "2026-06-01", "09:00"),
    ("daily", "A", "morning", "2026-06-02", "09:00"),
    ("daily", "A", "morning", "2026-06-03", "09:00"),
    ("daily", "A", "morning", "2026-06-04", "09:00"),
    ("daily", "A", "morning", "2026-06-05", "09:00"),
    ("daily", "A", "morning", "2026-06-06", "09:00"),
    ("daily", "A", "morning", "2026-06-07", "09:00"),
    ("daily", "A", "morning", "2026-06-15", "09:00"),
    ("daily", "A", "morning", "2026-06-16", "09:00"),
    ("daily", "A", "morning", "2026-06-17", "09:00"),
    ("daily", "A", "morning", "2026-06-18", "09:00"),
    ("daily", "A", "morning", "2026-06-19", "09:00"),
    ("daily", "A", "morning", "2026-06-20", "09:00"),
    ("daily", "A", "morning", "2026-06-21", "09:00"),
    # daily  C is present every day: all 28 days.
    ("daily", "C", "morning", "2026-06-01", "09:00"),
    ("daily", "C", "morning", "2026-06-02", "09:00"),
    ("daily", "C", "morning", "2026-06-03", "09:00"),
    ("daily", "C", "morning", "2026-06-04", "09:00"),
    ("daily", "C", "morning", "2026-06-05", "09:00"),
    ("daily", "C", "morning", "2026-06-06", "09:00"),
    ("daily", "C", "morning", "2026-06-07", "09:00"),
    ("daily", "C", "morning", "2026-06-08", "09:00"),
    ("daily", "C", "morning", "2026-06-09", "09:00"),
    ("daily", "C", "morning", "2026-06-10", "09:00"),
    ("daily", "C", "morning", "2026-06-11", "09:00"),
    ("daily", "C", "morning", "2026-06-12", "09:00"),
    ("daily", "C", "morning", "2026-06-13", "09:00"),
    ("daily", "C", "morning", "2026-06-14", "09:00"),
    ("daily", "C", "morning", "2026-06-15", "09:00"),
    ("daily", "C", "morning", "2026-06-16", "09:00"),
    ("daily", "C", "morning", "2026-06-17", "09:00"),
    ("daily", "C", "morning", "2026-06-18", "09:00"),
    ("daily", "C", "morning", "2026-06-19", "09:00"),
    ("daily", "C", "morning", "2026-06-20", "09:00"),
    ("daily", "C", "morning", "2026-06-21", "09:00"),
    ("daily", "C", "morning", "2026-06-22", "09:00"),
    ("daily", "C", "morning", "2026-06-23", "09:00"),
    ("daily", "C", "morning", "2026-06-24", "09:00"),
    ("daily", "C", "morning", "2026-06-25", "09:00"),
    ("daily", "C", "morning", "2026-06-26", "09:00"),
    ("daily", "C", "morning", "2026-06-27", "09:00"),
    ("daily", "C", "morning", "2026-06-28", "09:00"),
    # weekly  [B, C]  Mondays, morning 07:00 + evening 19:00.
    # B present weeks 1, 3 -> Mondays 06-08 and 06-22.
    ("weekly", "B", "morning", "2026-06-08", "07:00"),
    ("weekly", "B", "evening", "2026-06-08", "19:00"),
    ("weekly", "B", "morning", "2026-06-22", "07:00"),
    ("weekly", "B", "evening", "2026-06-22", "19:00"),
    # C present every Monday: 06-01, 06-08, 06-15, 06-22.
    ("weekly", "C", "morning", "2026-06-01", "07:00"),
    ("weekly", "C", "evening", "2026-06-01", "19:00"),
    ("weekly", "C", "morning", "2026-06-08", "07:00"),
    ("weekly", "C", "evening", "2026-06-08", "19:00"),
    ("weekly", "C", "morning", "2026-06-15", "07:00"),
    ("weekly", "C", "evening", "2026-06-15", "19:00"),
    ("weekly", "C", "morning", "2026-06-22", "07:00"),
    ("weekly", "C", "evening", "2026-06-22", "19:00"),
    # month_day  [C]  the 15th, morning 08:00.  2026-06-15 is the 15th.
    ("month_day", "C", "morning", "2026-06-15", "08:00"),
    # month_wd  [C]  2nd Wednesday, morning 07:30.  June 2026's 2nd
    # Wednesday is 06-10 (the 1st is 06-03).
    ("month_wd", "C", "morning", "2026-06-10", "07:30"),
    # yearly  [C]  1st of June, afternoon 12:00.  Fires on 06-01.
    ("yearly", "C", "afternoon", "2026-06-01", "12:00"),
    # custom  [A, C]  Saturdays + Sundays, evening 20:00.
    # A present weeks 0, 2 -> 06-06, 06-07, 06-20, 06-21.
    ("custom", "A", "evening", "2026-06-06", "20:00"),
    ("custom", "A", "evening", "2026-06-07", "20:00"),
    ("custom", "A", "evening", "2026-06-20", "20:00"),
    ("custom", "A", "evening", "2026-06-21", "20:00"),
    # C present every weekend day.
    ("custom", "C", "evening", "2026-06-06", "20:00"),
    ("custom", "C", "evening", "2026-06-07", "20:00"),
    ("custom", "C", "evening", "2026-06-13", "20:00"),
    ("custom", "C", "evening", "2026-06-14", "20:00"),
    ("custom", "C", "evening", "2026-06-20", "20:00"),
    ("custom", "C", "evening", "2026-06-21", "20:00"),
    ("custom", "C", "evening", "2026-06-27", "20:00"),
    ("custom", "C", "evening", "2026-06-28", "20:00"),
]

# The tuples that must disappear when Cleo (C) is overridden to ABSENT for
# 2026-06-04 .. 2026-06-06 (a mid-window stretch): her two daily chores and
# the Saturday-evening custom chore on 06-06.
_E2E_REMOVED = [
    ("daily", "C", "morning", "2026-06-04", "09:00"),
    ("daily", "C", "morning", "2026-06-05", "09:00"),
    ("daily", "C", "morning", "2026-06-06", "09:00"),
    ("custom", "C", "evening", "2026-06-06", "20:00"),
]


def _resolve_e2e(raw, def_ids, child_ids) -> set:
    """Substitute the oracle's definition/child slugs with runtime ids."""
    return {
        (def_ids[slug], child_ids[child], window, due_date, due_time)
        for slug, child, window, due_date, due_time in raw
    }


async def _collect_keyed(database, child_ids, start, end) -> dict:
    """Return {(definition_id, child_id, window, due_date): (id, due_time)}.

    The stable parts of an instance — its widened key, its physical id and
    its due_time snapshot — with the refreshable ``generated_at`` stamp
    deliberately excluded.  Comparing two of these captures the real
    re-run contract: no rows added/removed, ids stable (upsert refreshes
    in place, never delete + reinsert), and due_time untouched.
    """
    dao = QuestInstancesDao(database)
    keyed = {}
    for child_id in child_ids:
        for record in await dao.list_by_date_range(child_id, start, end):
            key = (
                record.definition_id,
                record.child_id,
                record.window,
                record.due_date,
            )
            keyed[key] = (record.id, record.due_time)
    return keyed


async def _collect_records(database, child_ids, start, end) -> set:
    """Return the full 7-field instance records over the children/range.

    Includes the ``generated_at`` stamp, so this is only used for children
    that should NEVER be written (Ada/Bo during Cleo's override): their
    records are truly byte-for-byte untouched, unlike the idempotency
    re-run where the stamp legitimately refreshes.
    """
    dao = QuestInstancesDao(database)
    records = set()
    for child_id in child_ids:
        for record in await dao.list_by_date_range(child_id, start, end):
            records.add(
                (
                    record.id,
                    record.definition_id,
                    record.child_id,
                    record.window,
                    record.due_date,
                    record.due_time,
                    record.generated_at,
                )
            )
    return records


def test_materialize_end_to_end_six_rule_types(tmp_path, monkeypatch) -> None:
    import custom_components.nestquest.materialize as materialize_module

    # Give each materialize run a DISTINCT batch stamp: production upserts
    # rewrite generated_at on every re-run, so a shared pinned stamp would
    # merely hide that rewrite.  The idempotency assertion below therefore
    # ignores generated_at and checks the stable columns only.
    stamps = {"n": 0}

    def _distinct_stamp() -> str:
        stamps["n"] += 1
        return f"2026-06-01T00:00:{stamps['n']:02d}+00:00"

    monkeypatch.setattr(materialize_module, "_now_stamp", _distinct_stamp)

    async def _body(database):
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )
        from custom_components.nestquest.presence import PresenceSchedule

        children = ChildrenDao(database)
        schedules = PresenceSchedulesDao(database)
        overrides = PresenceOverridesDao(database)

        a = await children.create("Ada", NOW)      # present weeks 0, 2
        b = await children.create("Bo", NOW)       # present weeks 1, 3
        c = await children.create("Cleo", NOW)     # no schedule: always present

        anchor = datetime.date.fromisoformat(_E2E_ANCHOR)
        start_iso = anchor.isoformat()
        end_iso = (anchor + datetime.timedelta(days=27)).isoformat()

        # Two-week custody with OPPOSITE weeks, encoded through the
        # PresenceSchedule model on the fixed Monday anchor.
        all_week = frozenset(range(7))
        a_schedule = PresenceSchedule(a.id, 2, anchor, {0: all_week, 1: frozenset()})
        b_schedule = PresenceSchedule(b.id, 2, anchor, {0: frozenset(), 1: all_week})
        await schedules.upsert_by_child(a.id, 2, start_iso, a_schedule.encode())
        await schedules.upsert_by_child(b.id, 2, start_iso, b_schedule.encode())

        def_ids = {}
        def_ids["daily"] = (await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=start_iso),
            [a.id, c.id],
            [("morning", "09:00")],
        )).definition.id
        def_ids["weekly"] = (await create_quest_definition(
            database,
            "Weekly Monday chore",
            ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={0},
                start_date=start_iso,
            ),
            [b.id, c.id],
            [("morning", "07:00"), ("evening", "19:00")],
        )).definition.id
        def_ids["month_day"] = (await create_quest_definition(
            database,
            "Monthly 15th chore",
            ScheduleRule(
                rule_type=RuleType.MONTHLY_DAY,
                day_of_month=15,
                start_date=start_iso,
            ),
            [c.id],
            [("morning", "08:00")],
        )).definition.id
        def_ids["month_wd"] = (await create_quest_definition(
            database,
            "Monthly 2nd-Wednesday chore",
            ScheduleRule(
                rule_type=RuleType.MONTHLY_WEEKDAY,
                nth_weekday=2,
                nth_weekday_weekday=2,
                start_date=start_iso,
            ),
            [c.id],
            [("morning", "07:30")],
        )).definition.id
        def_ids["yearly"] = (await create_quest_definition(
            database,
            "Yearly first-of-June chore",
            ScheduleRule(
                rule_type=RuleType.YEARLY,
                month=anchor.month,
                day_of_month=1,
                start_date=start_iso,
            ),
            [c.id],
            [("afternoon", "12:00")],
        )).definition.id
        def_ids["custom"] = (await create_quest_definition(
            database,
            "Weekend chore",
            ScheduleRule(
                rule_type=RuleType.CUSTOM_DAYS,
                weekday_set={5, 6},
                start_date=start_iso,
            ),
            [a.id, c.id],
            [("evening", "20:00")],
        )).definition.id

        child_ids = {"A": a.id, "B": b.id, "C": c.id}
        expected = _resolve_e2e(_E2E_EXPECTED, def_ids, child_ids)
        removed = _resolve_e2e(_E2E_REMOVED, def_ids, child_ids)
        all_children = (a.id, b.id, c.id)

        # First run: every (definition, child, window, date) tuple, exactly.
        first = await materialize(database, start_iso, end_iso, today=anchor)
        assert first == len(expected)
        assert await _collect_instances(
            database, all_children, start_iso, end_iso
        ) == expected

        # Re-run contract: the upsert refreshes each existing row IN PLACE,
        # so the widened key set, the physical ids and each due_time are all
        # stable (only generated_at may refresh to the new run's stamp).
        first_keyed = await _collect_keyed(
            database, all_children, start_iso, end_iso
        )
        second = await materialize(database, start_iso, end_iso, today=anchor)
        assert second == len(expected)
        assert await _collect_keyed(
            database, all_children, start_iso, end_iso
        ) == first_keyed

        # Capture Ada and Bo's complete records BEFORE the override, so we
        # can prove they are untouched afterward.
        a_before = await _collect_records(database, (a.id,), start_iso, end_iso)
        b_before = await _collect_records(database, (b.id,), start_iso, end_iso)

        # Cleo is ABSENT 2026-06-04 .. 2026-06-06 (mid-window).
        await overrides.create(
            c.id, "2026-06-04", "2026-06-06", False, note="away"
        )

        # regenerate_for_child deletes + rebuilds CLEO ONLY (Ada and Bo are
        # never touched).  It rebuilds a 14-day rolling horizon though, so
        # the child-scoped materialize below restores the remainder of the
        # 28-day window without ever writing another child.
        await regenerate_for_child(database, c.id, today=anchor)
        await materialize(
            database, start_iso, end_iso, child_ids=[c.id], today=anchor
        )

        # Ada and Bo are byte-for-byte untouched: id, snapshot columns and
        # generated_at alike.
        assert await _collect_records(
            database, (a.id,), start_iso, end_iso
        ) == a_before
        assert await _collect_records(
            database, (b.id,), start_iso, end_iso
        ) == b_before

        # Exactly Cleo's override-covered tuples vanish; every other tuple
        # survives.
        remaining = await _collect_instances(
            database, all_children, start_iso, end_iso
        )
        assert remaining == expected - removed
        assert remaining.isdisjoint(removed)
        return first

    _with_db(tmp_path, "materialize-e2e.db")(_body)


def test_regenerate_for_child_rejects_non_int_child_id(tmp_path) -> None:
    async def _body(database):
        for bad in (True, False, 1.0, "1"):
            with pytest.raises(ValueError, match="child_id must be an integer"):
                await regenerate_for_child(database, bad)
        return None

    _with_db(tmp_path, "regenerate-child-badid.db")(_body)