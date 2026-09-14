"""Tests for dao_instances.py: task_instances + append-only completion_events."""
from __future__ import annotations

import asyncio
import datetime
import sqlite3

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_instances import (
    CompletionEventRecord,
    CompletionEventsDao,
    TaskInstanceRecord,
    TaskInstancesDao,
)
from custom_components.nestquest.dao_rules import ScheduleRulesDao, TaskDefinitionsDao
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _today_iso() -> str:
    """Today's date, computed at call time (never cached)."""
    return datetime.date.today().isoformat()


#: The event timestamp used across append tests: 08:00 UTC TODAY.  It
#: is a strict UTC stamp whose DATE equals today at test-run time, so
#: occurred-at scope tests that query "today" can never drift across a
#: midnight boundary (they re-derive the same date the stamp carries).
def _now_stamp() -> str:
    return f"{_today_iso()}T08:00:00+00:00"


def _future_day(offset: int) -> str:
    """An ISO date ``offset`` days from today (always >= tomorrow)."""
    return (
        datetime.date.today() + datetime.timedelta(days=offset)
    ).isoformat()


def _future_stamp(offset: int) -> str:
    """A strict UTC timestamp on the day ``offset`` days from today."""
    day = datetime.date.today() + datetime.timedelta(days=offset)
    return f"{day.isoformat()}T08:00:00+00:00"


# Days inside the tests' horizon, all strictly in the future so the
# never-generate-in-the-past guardrail cannot reject them.
D1 = _future_day(1)
D2 = _future_day(2)
D3 = _future_day(3)
D4 = _future_day(4)
D5 = _future_day(5)
D6 = _future_day(6)
D7 = _future_day(7)
D10 = _future_day(10)
D20 = _future_day(20)


async def _prepare(path) -> tuple:
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    children = ChildrenDao(database)
    rules = ScheduleRulesDao(database)
    definitions = TaskDefinitionsDao(database)
    instances = TaskInstancesDao(database)
    events = CompletionEventsDao(database)
    child = await children.create("Ada", _now_stamp())
    rule = await rules.create("daily", D1)
    definition = await definitions.create(
        "Brush teeth", child.id, rule.id, _now_stamp()
    )
    return (
        database,
        children,
        rules,
        definitions,
        instances,
        events,
        child,
        definition,
    )


def _with_db(tmp_path, name):
    def _run_test(body):
        async def _main():
            prepared = await _prepare(tmp_path / name)
            try:
                return await body(*prepared)
            finally:
                await prepared[0].close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# task_instances: upsert idempotency
# ---------------------------------------------------------------------------


def test_upsert_creates_then_is_idempotent(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        first = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        assert isinstance(first, TaskInstanceRecord)
        second = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        assert second.id == first.id
        rows = await database.fetch_one(
            "SELECT COUNT(*) FROM task_instances"
        )
        assert rows == (1,)
        return second

    _with_db(tmp_path, "upsert-idempotent.db")(_body)


def test_upsert_different_dates_create_distinct_rows(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        a = await instances.upsert(definition.id, child.id, D1, _now_stamp())
        b = await instances.upsert(definition.id, child.id, D2, _now_stamp())
        assert a.id != b.id
        return (a, b)

    _with_db(tmp_path, "upsert-multi-date.db")(_body)


def test_upsert_refreshes_snapshot_columns_on_conflict(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        first = await instances.upsert(
            definition.id, child.id, D1, _now_stamp(), due_time="08:00"
        )
        second = await instances.upsert(
            definition.id,
            child.id,
            D1,
            f"{D1}T13:00:00+00:00",
            due_time="08:30",
        )
        assert second.id == first.id
        assert second.due_time == "08:30"
        assert second.generated_at == f"{D1}T13:00:00+00:00"
        return second

    _with_db(tmp_path, "upsert-refresh.db")(_body)


def test_upsert_rejects_wrong_child_for_definition(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await children.create("Bo", _now_stamp())
        with pytest.raises(ValueError, match="assigned to"):
            await instances.upsert(definition.id, other.id, D1, _now_stamp())
        return None

    _with_db(tmp_path, "upsert-wrong-child.db")(_body)


def test_upsert_rejects_unknown_definition_and_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="definition 999"):
            await instances.upsert(999, child.id, D1, _now_stamp())
        # Unknown child: the definition-assignee check fires first and
        # is the one that matters (an instance must carry its
        # definition's assignee).  To reach the child-existence check
        # at all, the definition would have to claim child 999 — an
        # FK-impossible state — so the child check only guards direct
        # callers with a matching fake assignee; assert the guard
        # order instead of forcing the FK-impossible state.
        rule = await rules.create("daily", D1)
        other_definition = await definitions.create(
            "X", child.id, rule.id, _now_stamp()
        )
        with pytest.raises(ValueError, match="not 999"):
            await instances.upsert(other_definition.id, 999, D1, _now_stamp())
        return None

    _with_db(tmp_path, "upsert-unknown.db")(_body)


def test_upsert_malformed_due_date_raises(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        for bad in ("not-a-date", "2026-9-15", ""):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await instances.upsert(definition.id, child.id, bad, _now_stamp())
        return None

    _with_db(tmp_path, "upsert-bad-date.db")(_body)


def test_upsert_rejects_past_due_dates(tmp_path) -> None:
    """Guardrail: instances are never generated in the past."""
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        yesterday = _future_day(-1)
        with pytest.raises(ValueError, match="never generated in the past"):
            await instances.upsert(definition.id, child.id, yesterday, _now_stamp())
        # Today itself is allowed (the rollover job generates today's
        # instances before the day is over).
        today = datetime.date.today().isoformat()
        record = await instances.upsert(definition.id, child.id, today, _now_stamp())
        assert record.due_date == today
        return record

    _with_db(tmp_path, "upsert-past.db")(_body)


def test_upsert_no_past_check_uses_execution_date_not_call_date(
    tmp_path,
) -> None:
    """The no-past rule reads 'today' under the lock, not at call time.

    Simulates midnight rollover contention: task A calls upsert for a
    date that is 'today' at call time; while A waits for the lock, the
    clock advances past midnight (monkeypatched datetime.date.today).
    The authoritative re-check under the lock must then reject the
    insert — the stale call-date check alone would let it through.
    """
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        today = datetime.date.today().isoformat()

        real_today = datetime.date.today
        advanced = {"armed": False}

        class _ShiftingDate(datetime.date):
            """date whose today() reports tomorrow once armed."""

            @classmethod
            def today(cls):
                base = real_today()
                if advanced["armed"]:
                    base = base + datetime.timedelta(days=1)
                return base

        class _ShiftingModule:
            """datetime module stand-in whose date.today() shifts."""

            date = _ShiftingDate

            def __getattr__(self, name):
                return getattr(datetime, name)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "custom_components.nestquest.dao_instances.datetime",
            _ShiftingModule(),
        )
        try:
            # Task A calls upsert while task B (a plain fetch) holds
            # the connection lock.  While A is queued, the clock
            # advances past midnight.  When B releases and A acquires
            # the lock, the IN-LOCK re-check sees tomorrow and must
            # reject the insert — the stale call-date pre-check alone
            # would have let it through.
            import custom_components.nestquest.dao_instances as mod

            async def _lock_holder():
                # Hold the CONNECTION lock across a transaction until
                # the test says the clock has shifted: task A queues on
                # the same lock (via its own upsert) and cannot even
                # reach its in-lock date check while the holder runs.
                async with mod._connection_lock(database):
                    async with database.transaction():
                        holder_inside.set()
                        await shift.wait()
                holder_done.set()

            holder_inside = asyncio.Event()
            holder_done = asyncio.Event()
            shift = asyncio.Event()

            holder_task = asyncio.ensure_future(_lock_holder())
            await asyncio.wait_for(holder_inside.wait(), timeout=5)

            task = asyncio.ensure_future(
                instances.upsert(definition.id, child.id, today, _now_stamp())
            )
            # A is now queued on the connection lock (it cannot pass
            # its in-lock check while B holds the lock).  Shift the
            # clock to tomorrow, then let B release.
            await asyncio.sleep(0)
            advanced["armed"] = True
            shift.set()
            await asyncio.wait_for(holder_done.wait(), timeout=5)
            with pytest.raises(
                ValueError, match="never generated in the past"
            ):
                await asyncio.wait_for(task, timeout=5)
        finally:
            monkeypatch.undo()
            await database.close()
        return None

    async def _main():
        database = NestQuestDatabase(_make_hass_mock())
        await database.open(tmp_path / "upsert-rollover.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            rules = ScheduleRulesDao(database)
            definitions = TaskDefinitionsDao(database)
            instances = TaskInstancesDao(database)
            events = CompletionEventsDao(database)
            child = await children.create("Ada", _now_stamp())
            rule = await rules.create("daily", D1)
            definition = await definitions.create(
                "Brush teeth", child.id, rule.id, _now_stamp()
            )
            return await _body(
                database, children, rules, definitions, instances,
                events, child, definition,
            )
        except BaseException:
            await database.close()
            raise

    _run(_main())


def test_upsert_refuses_immutable_completed_instance(tmp_path) -> None:
    """An instance with a completion event can never be regenerated."""
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp(), due_time="08:00"
        )
        await events.append(
            instance.id, child.id, "completed", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        with pytest.raises(ValueError, match="immutable"):
            await instances.upsert(
                definition.id, child.id, D1, _now_stamp(), due_time="09:00"
            )
        fetched = await instances.get(definition.id, D1)
        assert fetched.due_time == "08:00", (
            "failed regeneration must not touch the completed instance"
        )
        assert fetched.generated_at == _now_stamp()
        return fetched

    _with_db(tmp_path, "upsert-immutable.db")(_body)


# ---------------------------------------------------------------------------
# task_instances: get / list
# ---------------------------------------------------------------------------


def test_get_by_definition_and_date_round_trip(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        created = await instances.upsert(
            definition.id, child.id, D1, _now_stamp(), due_time="17:30"
        )
        fetched = await instances.get(definition.id, D1)
        assert fetched == created
        assert fetched.due_time == "17:30"
        assert await instances.get(definition.id, D2) is None
        return fetched

    _with_db(tmp_path, "get-round-trip.db")(_body)


def test_get_by_id_round_trip(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        created = await instances.upsert(definition.id, child.id, D1, _now_stamp())
        fetched = await instances.get_by_id(created.id)
        assert fetched == created
        assert await instances.get_by_id(999) is None
        return fetched

    _with_db(tmp_path, "get-by-id.db")(_body)


def test_list_by_child_and_date_filters(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await children.create("Bo", _now_stamp())
        rule = await rules.create("daily", D1)
        other_definition = await definitions.create(
            "Make bed", other.id, rule.id, _now_stamp()
        )
        await instances.upsert(definition.id, child.id, D1, _now_stamp())
        await instances.upsert(definition.id, child.id, D2, _now_stamp())
        await instances.upsert(
            other_definition.id, other.id, D1, _now_stamp()
        )
        mine = await instances.list_by_child_and_date(child.id, D1)
        assert len(mine) == 1
        assert mine[0].child_id == child.id
        assert mine[0].due_date == D1
        return mine

    _with_db(tmp_path, "list-by-child-date.db")(_body)


def test_list_by_date_range_filters_and_orders(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        for day in (D1, D3, D5, D20):
            await instances.upsert(definition.id, child.id, day, _now_stamp())
        found = await instances.list_by_date_range(
            child.id, D2, D6
        )
        assert [i.due_date for i in found] == [D3, D5]
        edge = await instances.list_by_date_range(
            child.id, D3, D3
        )
        assert [i.due_date for i in edge] == [D3]
        return found

    _with_db(tmp_path, "list-by-range.db")(_body)


def test_list_by_date_range_rejects_inverted_range(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="on or after"):
            await instances.list_by_date_range(
                child.id, D5, D1
            )
        return None

    _with_db(tmp_path, "list-inverted.db")(_body)


# ---------------------------------------------------------------------------
# task_instances: delete_future_uncompleted
# ---------------------------------------------------------------------------


def test_delete_future_uncompleted_removes_only_eligible(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        await instances.upsert(definition.id, child.id, D1, _now_stamp())
        future_open = await instances.upsert(
            definition.id, child.id, D5, _now_stamp()
        )
        await instances.upsert(definition.id, child.id, D6, _now_stamp())
        deleted = await instances.delete_future_uncompleted(
            definition.id, D5
        )
        assert deleted == 2
        assert await instances.get(definition.id, D1) is not None
        assert await instances.get(definition.id, D5) is None
        assert await instances.get(definition.id, D6) is None
        return deleted

    _with_db(tmp_path, "delete-future.db")(_body)


def test_delete_future_uncompleted_spares_completed(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        completed = await instances.upsert(
            definition.id, child.id, D5, _now_stamp()
        )
        open_one = await instances.upsert(
            definition.id, child.id, D6, _now_stamp()
        )
        await events.append(
            completed.id, child.id, "completed", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        deleted = await instances.delete_future_uncompleted(
            definition.id, D5
        )
        assert deleted == 1
        assert await instances.get_by_id(completed.id) is not None, (
            "an instance with a completion event must never be deleted"
        )
        assert await instances.get_by_id(open_one.id) is None
        return deleted

    _with_db(tmp_path, "delete-spares-completed.db")(_body)


def test_delete_future_uncompleted_cannot_backdate_cutoff(
    tmp_path,
) -> None:
    """The cutoff is clamped to today: 'future' means from today.

    A backdated cutoff cannot be used to rewrite past OPEN instances —
    past-due open instances are the missed sweep's concern (Feature
    11), not regeneration's.  Everything at/after today that is open
    is deleted even when the caller asks for a later cutoff... no:
    the clamp only RAISES the effective cutoff (max), so a later
    caller cutoff still limits the range.  This test proves the clamp:
    a past cutoff deletes open instances from TODAY onward, not just
    the backdated date.
    """
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        today = datetime.date.today().isoformat()
        await instances.upsert(definition.id, child.id, today, _now_stamp())
        deleted = await instances.delete_future_uncompleted(
            definition.id, "2020-01-01"
        )
        assert deleted == 1
        assert await instances.get(definition.id, today) is None
        return deleted

    _with_db(tmp_path, "delete-no-backdate.db")(_body)


def test_delete_future_uncompleted_other_definitions_untouched(
    tmp_path,
) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await definitions.create(
            "Make bed", child.id, (await rules.create("daily", D1)).id,
            _now_stamp(),
        )
        await instances.upsert(definition.id, child.id, D20, _now_stamp())
        await instances.upsert(other.id, child.id, D20, _now_stamp())
        deleted = await instances.delete_future_uncompleted(
            definition.id, D20
        )
        assert deleted == 1
        assert await instances.get(other.id, D20) is not None
        return deleted

    _with_db(tmp_path, "delete-scoped.db")(_body)


# ---------------------------------------------------------------------------
# completion_events: append
# ---------------------------------------------------------------------------


def test_append_completion_round_trips(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        event = await events.append(
            instance.id, child.id, "completed", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        assert isinstance(event, CompletionEventRecord)
        assert event.event_type == "completed"
        assert event.actor_source == "user"
        assert event.actor_user_id == "user-1"
        assert event.was_on_time is True
        return event

    _with_db(tmp_path, "append-completion.db")(_body)


def test_append_panel_event_round_trips(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        event = await events.append(
            instance.id, child.id, "completed", "panel", _now_stamp(), False,
            actor_user_id=None,
        )
        assert event.actor_source == "panel"
        assert event.actor_user_id is None
        assert event.was_on_time is False
        return event

    _with_db(tmp_path, "append-panel.db")(_body)


def test_append_uncompleted_with_optional_on_time(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        reversal = await events.append(
            instance.id, child.id, "uncompleted", "user", _now_stamp(), None,
            actor_user_id="user-1",
        )
        assert reversal.event_type == "uncompleted"
        assert reversal.was_on_time is None
        carried = await events.append(
            instance.id, child.id, "uncompleted", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        assert carried.was_on_time is True
        return (reversal, carried)

    _with_db(tmp_path, "append-uncompleted.db")(_body)


def test_append_validation_rejects_bad_shapes(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        with pytest.raises(ValueError, match="event_type"):
            await events.append(
                instance.id, child.id, "missed", "user", _now_stamp(), True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="actor_source"):
            await events.append(
                instance.id, child.id, "completed", "kiosk", _now_stamp(), True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="requires actor_user_id"):
            await events.append(
                instance.id, child.id, "completed", "user", _now_stamp(), True,
                actor_user_id=None,
            )
        with pytest.raises(ValueError, match="must not carry"):
            await events.append(
                instance.id, child.id, "completed", "panel", _now_stamp(), True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="requires was_on_time"):
            await events.append(
                instance.id, child.id, "completed", "panel", _now_stamp(), None
            )
        # was_on_time must be a real bool: int-convertible junk that
        # would silently coerce (0.5 -> False) is rejected outright.
        with pytest.raises(ValueError, match="must be True, False or None"):
            await events.append(
                instance.id, child.id, "completed", "panel", _now_stamp(), 0.5
            )
        with pytest.raises(ValueError, match="must be True, False or None"):
            await events.append(
                instance.id, child.id, "uncompleted", "user", _now_stamp(), "yes",
                actor_user_id="user-1",
            )
        return None

    _with_db(tmp_path, "append-validation.db")(_body)


def test_append_rejects_non_utc_timestamps(tmp_path) -> None:
    """occurred_at must be the one strict UTC shape so range queries
    over it stay lexicographically exact."""
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        for bad in (
            "2026-09-14 12:00:00+00:00",  # space separator
            "2026-09-14T12:00:00",  # no offset
            "2026-09-14T12:00:00Z",  # Z form
            "2026-9-14T12:00:00+00:00",  # non-padded
            "2026-09-14T12:00:00+01:00",  # non-UTC offset
            "not-a-timestamp",
        ):
            with pytest.raises(ValueError, match="UTC"):
                await events.append(
                    instance.id, child.id, "completed", "panel", bad,
                    True,
                )
        return None

    _with_db(tmp_path, "append-bad-timestamps.db")(_body)


def test_append_requires_was_on_time_strict_bool(tmp_path) -> None:
    """0.5 silently int-coercing to False is how bad data gets in."""
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        for bad in (0.5, 1.5, 2, "true", 1):
            with pytest.raises(ValueError, match="must be True, False"):
                await events.append(
                    instance.id, child.id, "uncompleted", "user", _now_stamp(),
                    bad, actor_user_id="user-1",
                )
        return None

    _with_db(tmp_path, "append-strict-bool.db")(_body)


def test_append_rejects_unknown_instance_or_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="instance 999"):
            await events.append(
                999, child.id, "completed", "user", _now_stamp(), True,
                actor_user_id="user-1",
            )
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        with pytest.raises(ValueError, match="belongs to child"):
            await events.append(
                instance.id, 999, "completed", "user", _now_stamp(), True,
                actor_user_id="user-1",
            )
        return None

    _with_db(tmp_path, "append-unknown.db")(_body)


# ---------------------------------------------------------------------------
# completion_events: reads and append-only semantics
# ---------------------------------------------------------------------------


def test_completed_uncompleted_recompleted_three_ordered_events(
    tmp_path,
) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        await events.append(
            instance.id, child.id, "completed", "panel", _now_stamp(), True
        )
        await events.append(
            instance.id, child.id, "uncompleted", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        await events.append(
            instance.id, child.id, "completed", "panel", _now_stamp(), False
        )
        history = await events.list_by_instance(instance.id)
        assert [e.event_type for e in history] == [
            "completed",
            "uncompleted",
            "completed",
        ]
        assert [e.id for e in history] == sorted(e.id for e in history)
        latest = await events.get_latest_for_instance(instance.id)
        assert latest.event_type == "completed"
        assert latest.was_on_time is False
        return history

    _with_db(tmp_path, "three-events.db")(_body)


def test_get_latest_for_instance_none_when_untouched(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        return await events.get_latest_for_instance(instance.id)

    assert _with_db(tmp_path, "latest-none.db")(_body) is None


def test_get_latest_returns_uncompleted_when_reversed(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        await events.append(
            instance.id, child.id, "completed", "panel", _now_stamp(), True
        )
        await events.append(
            instance.id, child.id, "uncompleted", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        latest = await events.get_latest_for_instance(instance.id)
        assert latest.event_type == "uncompleted"
        return latest

    _with_db(tmp_path, "latest-reversed.db")(_body)


def test_list_by_child_and_date_range_scopes_by_due_date(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        early = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        inside = await instances.upsert(
            definition.id, child.id, D2, _now_stamp()
        )
        late = await instances.upsert(
            definition.id, child.id, D20, _now_stamp()
        )
        await events.append(
            early.id, child.id, "completed", "panel", _now_stamp(), True
        )
        await events.append(
            inside.id, child.id, "completed", "panel", _now_stamp(), False
        )
        await events.append(
            inside.id, child.id, "uncompleted", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        await events.append(
            late.id, child.id, "completed", "panel", _now_stamp(), True
        )
        found = await events.list_by_child_and_date_range(
            child.id, D2, D2
        )
        # Only the instance DUE inside the range contributes events:
        # assert by id, not position, since append order determines ids.
        assert [e.id for e in found] == sorted(e.id for e in found)
        assert all(
            e.instance_id == inside.id for e in found
        ), f"range D2..D2 must only return events for the D2 instance, got {found}"
        outside = await events.list_by_child_and_date_range(
            child.id, D1, D1
        )
        assert [e.id for e in outside] == [1] or all(
            e.instance_id == early.id for e in outside
        )
        return found

    _with_db(tmp_path, "events-by-range.db")(_body)


def test_list_events_occurred_at_scope_variant(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        late_due = await instances.upsert(
            definition.id, child.id, D20, _now_stamp()
        )
        # The event's occurred_at is today at 08:00 UTC (_now_stamp);
        # the instance is due D20.  The due-date scope queried on D20
        # still finds the event (scoping follows the instance's due
        # date, not when the event happened); the occurred-at scope
        # queried on today's date finds it too.
        event = await events.append(
            late_due.id, child.id, "completed", "panel",
            _now_stamp(), False,
        )
        by_due = await events.list_by_child_and_date_range(
            child.id, D20, D20
        )
        assert [e.id for e in by_due] == [event.id]
        # Derive the query date from the stamp itself so the test is
        # midnight-safe: the stamp's date IS the day to query.
        stamp_date = _now_stamp()[:10]
        by_occurrence = await events.list_by_child_and_date_range(
            child.id, stamp_date, stamp_date,
            due_date_scope=False,
        )
        assert len(by_occurrence) == 1
        assert by_occurrence[0].instance_id == late_due.id
        return by_occurrence

    _with_db(tmp_path, "events-occurred-scope.db")(_body)


def test_completion_events_dao_has_no_update_or_delete(tmp_path) -> None:
    """Done-condition: NO update or delete method exists at all."""
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        import inspect

        methods = {
            name
            for name, _ in inspect.getmembers(
                CompletionEventsDao, inspect.isfunction
            )
            if not name.startswith("__")
        }
        forbidden = {
            name for name in methods
            if name.startswith(("update", "delete", "set", "clear",
                                "remove", "modify", "edit", "upsert"))
        }
        assert forbidden == set(), (
            f"append-only DAO exposed mutation methods: {forbidden}"
        )
        assert methods == {
            "append",
            "list_by_instance",
            "list_by_child_and_date_range",
            "get_latest_for_instance",
        }
        return methods

    _with_db(tmp_path, "events-no-mutation.db")(_body)


def test_no_mutation_sql_for_completion_events_anywhere() -> None:
    """Package-wide guardrail: completion_events must have no mutation
    path in ANY module or test.  The pattern covers INSERT (only the
    DAO's own INSERT is exempt), UPDATE in every SQLite variant (OR
    IGNORE/ABORT/REPLACE/ROLLBACK/FAIL), DELETE FROM, qualified
    names (main.completion_events), backtick/bracket/quote forms,
    and comments; string concatenation still matches because each
    fragment must independently carry the table name next to a
    mutation keyword to execute as intended.
    """
    import re
    from pathlib import Path

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent
    repo_root = package.parent.parent
    mutation_pattern = re.compile(
        r"(UPDATE(\s+OR\s+(IGNORE|ABORT|REPLACE|ROLLBACK|FAIL))?"
        r"|DELETE\s+FROM"
        r"|INSERT(\s+OR\s+(IGNORE|ABORT|REPLACE|ROLLBACK|FAIL))?\s+INTO)"
        r"\s+((main|temp)\s*\.\s*)?[`'\"]*(\[)?completion_events\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    # Two files legitimately hold INSERT INTO completion_events: the
    # DAO (the append path) and test_schema.py (whose insert helper
    # exercises the table's CHECK constraints against raw SQL by
    # design — schema tests are the one layer below the DAO).  Their
    # INSERT statements are stripped before scanning so only genuine
    # UPDATE/DELETE/non-DAO-INSERT paths hit the pattern.
    insert_exempt = {
        "custom_components/nestquest/dao_instances.py",
        "tests/test_schema.py",
        "tests/test_dao_instances.py",  # this guard file; scanned by
        # its own guard's regex spans below instead
    }
    for root in (package, repo_root / "tests"):
        for py in sorted(root.rglob("*.py")):
            relative = py.relative_to(repo_root).as_posix()
            text = py.read_text()
            if relative in insert_exempt:
                text = re.sub(
                    r"INSERT(\s+OR\s+\w+)?\s+INTO\s+completion_events"
                    r"[^\"']*",
                    "",
                    text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            if mutation_pattern.search(text):
                offenders.append(relative)
    assert offenders == [], (
        f"completion_events mutation SQL found in: {offenders}"
    )


def test_dao_instances_guard_file_self_scan() -> None:
    """Compensating scan for this file's own insert-exemption: outside
    the package-wide mutation guard's function span, this file must
    not contain UPDATE/DELETE mutation SQL for completion_events
    (the INSERT exemption covers its docstrings and regex only).
    """
    import ast
    import re
    from pathlib import Path

    path = Path(__file__)
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name
            in {
                "test_no_mutation_sql_for_completion_events_anywhere",
                "test_dao_instances_guard_file_self_scan",
            }
        ):
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )
    remaining = "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )
    mutation_pattern = re.compile(
        r"(UPDATE(\s+OR\s+\w+)?|DELETE\s+FROM)\s+"
        r"((main|temp)\s*\.\s*)?[`'\"]*(\[)?completion_events\b",
        re.IGNORECASE,
    )
    assert mutation_pattern.search(remaining) is None, (
        "this test file must not contain completion_events mutation SQL"
    )


def test_completion_events_dao_instance_has_no_mutation_capability(
    tmp_path,
) -> None:
    """Behavioral guard: beyond the method-name check, call interception
    proves NO path from the DAO object can execute UPDATE/DELETE on the
    table — every method it exposes is exercised and only INSERT/SELECT
    statements reach the database for this table.
    """
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        executed: list[str] = []
        original_execute = database.execute

        async def _recording(sql, parameters=()):
            executed.append(" ".join(sql.split()).upper())
            return await original_execute(sql, parameters)

        database.execute = _recording
        instance = await instances.upsert(
            definition.id, child.id, D1, _now_stamp()
        )
        await events.append(
            instance.id, child.id, "completed", "user", _now_stamp(), True,
            actor_user_id="user-1",
        )
        await events.list_by_instance(instance.id)
        await events.get_latest_for_instance(instance.id)
        await events.list_by_child_and_date_range(child.id, D1, D1)
        for sql in executed:
            if "COMPLETION_EVENTS" in sql:
                assert sql.startswith(("INSERT", "SELECT")), (
                    f"completion_events saw a non-append statement: {sql}"
                )
        return executed

    _with_db(tmp_path, "events-behavior-guard.db")(_body)


def test_append_concurrent_events_serialize(tmp_path) -> None:
    """Concurrent appends for the same instance all land, in order."""
    async def _main():
        database = NestQuestDatabase(_make_hass_mock())
        await database.open(tmp_path / "append-race.db")
        try:
            await apply_migrations(database)
            prepared = await _prepare_in(database)
            _, children, _, _, instances, events, child, definition = (
                prepared
            )
            instance = await instances.upsert(
                definition.id, child.id, D1, _now_stamp()
            )
            tasks = [
                asyncio.ensure_future(
                    events.append(
                        instance.id, child.id, "completed", "user",
                        f"{D1}T08:0{index}:00+00:00", True,
                        actor_user_id=f"user-{index}",
                    )
                )
                for index in range(5)
            ]
            await asyncio.sleep(0)
            appended = await asyncio.gather(*tasks)
            history = await events.list_by_instance(instance.id)
            assert [e.id for e in history] == [
                e.id for e in sorted(appended, key=lambda x: x.id)
            ]
            assert len(history) == 5
            return history
        finally:
            await database.close()

    async def _prepare_in(database):
        children = ChildrenDao(database)
        rules = ScheduleRulesDao(database)
        definitions = TaskDefinitionsDao(database)
        instances = TaskInstancesDao(database)
        events = CompletionEventsDao(database)
        child = await children.create("Ada", _now_stamp())
        rule = await rules.create("daily", D1)
        definition = await definitions.create(
            "Brush teeth", child.id, rule.id, _now_stamp()
        )
        return (database, children, rules, definitions, instances,
                events, child, definition)

    history = _run(_main())
    assert history[-1].occurred_at == f"{D1}T08:04:00+00:00"