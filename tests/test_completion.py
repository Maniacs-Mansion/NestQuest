"""Tests for completion.py: the Feature 08 append-only business layer."""
from __future__ import annotations

import asyncio
import datetime
import inspect
import re

import pytest

from custom_components.nestquest.completion import (
    append_event,
    complete_instance,
    instance_state,
    list_missed_for_child,
    uncomplete_instance,
)
from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_instances import (
    EVENT_COMPLETED,
    EVENT_UNCOMPLETED,
    CompletionEventRecord,
    CompletionEventsDao,
    QuestInstancesDao,
)
from custom_components.nestquest.dao_rules import (
    QuestDefinitionsDao,
    ScheduleRulesDao,
)
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
    return datetime.date.today().isoformat()


def _now_stamp() -> str:
    return f"{_today_iso()}T08:00:00+00:00"


def _future_day(offset: int) -> str:
    return (
        datetime.date.today() + datetime.timedelta(days=offset)
    ).isoformat()


D1 = _future_day(1)


async def _prepare(path) -> tuple:
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    children = ChildrenDao(database)
    rules = ScheduleRulesDao(database)
    definitions = QuestDefinitionsDao(database)
    instances = QuestInstancesDao(database)
    child = await children.create("Ada", _now_stamp())
    rule = await rules.create("daily", D1)
    definition = await definitions.create(
        "Brush teeth", rule.id, _now_stamp(), assignee_child_ids=[child.id]
    )
    instance = await instances.upsert(
        definition.id, child.id, D1, _now_stamp(), window="morning"
    )
    return database, child, instance


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
# inverted actor shapes: field-naming ValueErrors, no write
# ---------------------------------------------------------------------------


def test_user_without_actor_user_id_rejected() -> None:
    async def _body():
        with pytest.raises(ValueError, match="actor_user_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="user",
                was_on_time=True,
            )
        with pytest.raises(ValueError, match="actor_user_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="user",
                actor_user_id=None,
                was_on_time=True,
            )
        with pytest.raises(ValueError, match="actor_user_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="user",
                actor_user_id="",
                was_on_time=True,
            )

    _run(_body())


def test_user_must_not_carry_actor_child_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="actor_child_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="user",
                actor_user_id="user-1",
                actor_child_id=1,
                was_on_time=True,
            )

    _run(_body())


def test_panel_must_not_carry_actor_user_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="actor_user_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="panel",
                actor_user_id="user-1",
                actor_child_id=1,
                was_on_time=True,
            )

    _run(_body())


def test_panel_requires_actor_child_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="actor_child_id"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="panel",
                was_on_time=True,
            )

    _run(_body())


def test_actor_source_service_rejected() -> None:
    async def _body():
        with pytest.raises(ValueError, match="actor_source"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="service",
                actor_user_id="user-1",
                was_on_time=True,
            )

    _run(_body())


def test_completed_requires_was_on_time() -> None:
    async def _body():
        with pytest.raises(ValueError, match="was_on_time"):
            await append_event(
                object(),
                1,
                1,
                EVENT_COMPLETED,
                actor_source="user",
                actor_user_id="user-1",
            )

    _run(_body())


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------


def test_user_append_round_trips(tmp_path) -> None:
    async def _body(database, child, instance):
        event = await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
        )
        assert isinstance(event, CompletionEventRecord)
        assert event.event_type == EVENT_COMPLETED
        assert event.actor_source == "user"
        assert event.actor_user_id == "user-1"
        assert event.actor_child_id is None
        assert event.was_on_time is True
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", event.occurred_at
        )
        return event

    _with_db(tmp_path, "user-append.db")(_body)


def test_panel_append_round_trips(tmp_path) -> None:
    async def _body(database, child, instance):
        event = await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="panel",
            actor_child_id=child.id,
            was_on_time=False,
        )
        assert event.actor_source == "panel"
        assert event.actor_user_id is None
        assert event.actor_child_id == child.id
        assert event.was_on_time is False
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", event.occurred_at
        )
        return event

    _with_db(tmp_path, "panel-append.db")(_body)


def test_uncompleted_allows_null_was_on_time(tmp_path) -> None:
    async def _body(database, child, instance):
        event = await append_event(
            database,
            instance.id,
            child.id,
            EVENT_UNCOMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=None,
        )
        assert event.event_type == EVENT_UNCOMPLETED
        assert event.was_on_time is None
        return event

    _with_db(tmp_path, "uncompleted-null.db")(_body)


def test_now_pins_occurred_at_utc(tmp_path) -> None:
    async def _body(database, child, instance):
        pinned = datetime.datetime(
            2026, 9, 18, 8, 0, 0, tzinfo=datetime.timezone.utc
        )
        event = await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
            now=pinned,
        )
        assert event.occurred_at == "2026-09-18T08:00:00+00:00"
        return event

    _with_db(tmp_path, "pinned-now.db")(_body)


# ---------------------------------------------------------------------------
# append-only: the module never exposes update/delete
# ---------------------------------------------------------------------------


def test_module_never_exposes_update_or_delete() -> None:
    import custom_components.nestquest.completion as completion

    public = {
        name
        for name, _ in inspect.getmembers(completion, inspect.isfunction)
        if not name.startswith("_")
    }
    forbidden = {
        name
        for name in public
        if name.startswith(
            (
                "update",
                "delete",
                "set",
                "clear",
                "remove",
                "modify",
                "edit",
                "upsert",
            )
        )
    }
    assert forbidden == set(), (
        f"completion.py exposed mutation methods: {forbidden}"
    )
    assert "append_event" in public
    assert "instance_state" in public
    assert "complete_instance" in public
    assert "uncomplete_instance" in public
    assert "list_missed_for_child" in public
    source = inspect.getsource(completion)
    assert "UPDATE" not in source
    assert "DELETE" not in source
    assert "INSERT" not in source


# ---------------------------------------------------------------------------
# instance_state: derived from the latest event
# ---------------------------------------------------------------------------


def test_instance_state_open_when_no_events(tmp_path) -> None:
    async def _body(database, child, instance):
        assert await instance_state(database, instance.id) == "open"

    _with_db(tmp_path, "state-none.db")(_body)


def test_instance_state_open_when_latest_uncompleted(tmp_path) -> None:
    async def _body(database, child, instance):
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_UNCOMPLETED,
            actor_source="user",
            actor_user_id="user-1",
        )
        assert await instance_state(database, instance.id) == "open"

    _with_db(tmp_path, "state-uncompleted.db")(_body)


def test_instance_state_unknown_instance_id_raises(tmp_path) -> None:
    async def _body(database, child, instance):
        with pytest.raises(ValueError, match="instance_id"):
            await instance_state(database, instance.id + 999)

    _with_db(tmp_path, "state-unknown.db")(_body)


def test_instance_state_rejects_non_integer_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="instance_id"):
            await instance_state(object(), "1")
        with pytest.raises(ValueError, match="instance_id"):
            await instance_state(object(), True)

    _run(_body())


def test_instance_state_three_events_returns_done_and_preserves_rows(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        base = datetime.datetime(
            2026, 9, 18, 8, 0, 0, tzinfo=datetime.timezone.utc
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
            now=base,
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_UNCOMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            now=base + datetime.timedelta(seconds=1),
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=False,
            now=base + datetime.timedelta(seconds=2),
        )
        events = CompletionEventsDao(database)
        before = await events.list_by_instance(instance.id)
        assert [e.event_type for e in before] == [
            EVENT_COMPLETED,
            EVENT_UNCOMPLETED,
            EVENT_COMPLETED,
        ]
        assert await instance_state(database, instance.id) == "done"
        after = await events.list_by_instance(instance.id)
        assert after == before
        assert len(after) == 3

    _with_db(tmp_path, "state-three.db")(_body)


# ---------------------------------------------------------------------------
# complete_instance: append completed, no-op if already done
# ---------------------------------------------------------------------------


def test_complete_instance_appends_and_returns_done(tmp_path) -> None:
    async def _body(database, child, instance):
        events = CompletionEventsDao(database)
        assert await events.list_by_instance(instance.id) == []
        state = await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
        )
        assert state == "done"
        assert await instance_state(database, instance.id) == "done"
        rows = await events.list_by_instance(instance.id)
        assert len(rows) == 1
        assert rows[0].event_type == EVENT_COMPLETED
        assert rows[0].actor_source == "user"
        assert rows[0].actor_user_id == "user-1"
        assert rows[0].was_on_time is True

    _with_db(tmp_path, "complete-open.db")(_body)


def test_complete_instance_already_done_is_noop(tmp_path) -> None:
    async def _body(database, child, instance):
        first = await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
        )
        events = CompletionEventsDao(database)
        before = await events.list_by_instance(instance.id)
        assert first == "done"
        assert len(before) == 1
        second = await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-2",
        )
        after = await events.list_by_instance(instance.id)
        assert second == "done"
        assert after == before
        assert after[0].actor_user_id == "user-1"

    _with_db(tmp_path, "complete-noop.db")(_body)


def test_complete_instance_unknown_instance_id_raises(tmp_path) -> None:
    async def _body(database, child, instance):
        with pytest.raises(ValueError, match="instance_id"):
            await complete_instance(
                database,
                instance.id + 999,
                actor_source="user",
                actor_user_id="user-1",
            )

    _with_db(tmp_path, "complete-unknown.db")(_body)


def test_complete_instance_rejects_non_integer_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="instance_id"):
            await complete_instance(
                object(),
                "1",
                actor_source="user",
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="instance_id"):
            await complete_instance(
                object(),
                True,
                actor_source="user",
                actor_user_id="user-1",
            )

    _run(_body())


def test_complete_instance_after_uncompleted_appends(tmp_path) -> None:
    async def _body(database, child, instance):
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_UNCOMPLETED,
            actor_source="user",
            actor_user_id="user-1",
        )
        events = CompletionEventsDao(database)
        before = await events.list_by_instance(instance.id)
        assert await instance_state(database, instance.id) == "open"
        state = await complete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
        )
        assert state == "done"
        after = await events.list_by_instance(instance.id)
        assert len(after) == len(before) + 1
        assert after[-1].event_type == EVENT_COMPLETED
        assert after[-1].actor_source == "panel"
        assert after[-1].was_on_time is True

    _with_db(tmp_path, "complete-reopen.db")(_body)


def test_complete_instance_now_pins_occurred_at(tmp_path) -> None:
    async def _body(database, child, instance):
        pinned = datetime.datetime(
            2026, 9, 18, 8, 0, 0, tzinfo=datetime.timezone.utc
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=pinned,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].occurred_at == "2026-09-18T08:00:00+00:00"

    _with_db(tmp_path, "complete-pinned.db")(_body)


def _gated_hass(armed: dict, gate_open: asyncio.Event, a_started: asyncio.Event):
    """A hass mock whose executor gates the FIRST ``_execute`` job after
    arming — the INSERT of whichever ``complete_instance`` starts first
    — proving that caller holds the connection lock and the second
    caller must queue behind it."""
    from unittest.mock import MagicMock

    hass = MagicMock()

    async def _gated_executor(fn, *args):
        if armed["active"]:
            if getattr(fn, "__name__", "") == "_execute" and not armed["gated"]:
                armed["gated"] = True
                a_started.set()
                await gate_open.wait()
        return fn(*args)

    hass.async_add_executor_job = _gated_executor
    return hass


def test_complete_instance_concurrent_second_call_is_noop(tmp_path) -> None:
    """Two racing completes cannot both append.

    Deterministic gate: task A is paused at its INSERT (it holds the
    connection lock); task B is then started and must queue.  A
    finishes, B sees done and appends nothing.
    """
    async def _main():
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()
        hass = _gated_hass(armed, gate_open, a_started)
        database = NestQuestDatabase(hass)
        await database.open(tmp_path / "complete-race.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            rules = ScheduleRulesDao(database)
            definitions = QuestDefinitionsDao(database)
            instances = QuestInstancesDao(database)
            child = await children.create("Ada", _now_stamp())
            rule = await rules.create("daily", D1)
            definition = await definitions.create(
                "Brush teeth",
                rule.id,
                _now_stamp(),
                assignee_child_ids=[child.id],
            )
            instance = await instances.upsert(
                definition.id,
                child.id,
                D1,
                _now_stamp(),
                window="morning",
            )

            armed["active"] = True
            task_a = asyncio.ensure_future(
                complete_instance(
                    database,
                    instance.id,
                    actor_source="user",
                    actor_user_id="user-1",
                )
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                complete_instance(
                    database,
                    instance.id,
                    actor_source="user",
                    actor_user_id="user-2",
                )
            )
            await asyncio.sleep(0)
            gate_open.set()
            state_a, state_b = await asyncio.gather(task_a, task_b)
            assert state_a == "done"
            assert state_b == "done"
            rows = await CompletionEventsDao(database).list_by_instance(
                instance.id
            )
            assert len(rows) == 1
            assert rows[0].actor_user_id == "user-1"
        finally:
            await database.close()

    _run(_main())


_HA_TZ = datetime.timezone(datetime.timedelta(hours=-8))


def _ha_local(day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(
        day.year, day.month, day.day, hour, minute, 0,
        tzinfo=_HA_TZ,
    )


def test_complete_instance_on_due_date_before_due_time_is_on_time(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(due_date, 11, 0),
            today=due_date,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is True

    _with_db(tmp_path, "ontime-before-due-time.db")(_body)


def test_complete_instance_on_due_date_after_due_time_is_late(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(due_date, 12, 1),
            today=due_date,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is False

    _with_db(tmp_path, "late-after-due-time.db")(_body)


def test_complete_instance_microsecond_after_due_time_is_late(tmp_path) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        now = datetime.datetime(
            due_date.year, due_date.month, due_date.day, 12, 0, 0, 500,
            tzinfo=_HA_TZ,
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=now,
            today=due_date,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is False

    _with_db(tmp_path, "late-microsecond-after-due-time.db")(_body)


def test_complete_instance_no_due_time_on_due_date_is_on_time(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        assert instance.due_time is None
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(due_date, 23, 59),
            today=due_date,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is True

    _with_db(tmp_path, "ontime-no-due-time.db")(_body)


def test_complete_instance_no_due_time_after_due_date_is_late(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        later = due_date + datetime.timedelta(days=1)
        assert instance.due_time is None
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(later, 8, 0),
            today=later,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is False

    _with_db(tmp_path, "late-after-due-date.db")(_body)


def test_complete_instance_ha_local_wall_clock_not_utc(tmp_path) -> None:
    """HA-local 11:00 with due_time 12:00 is on time even when UTC is 19:00.

    The helper's zone is UTC-8, so 11:00 local is 19:00 UTC.  Converting
    to UTC before comparing would mark this late.
    """
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        now = _ha_local(due_date, 11, 0)
        assert now.astimezone(datetime.timezone.utc).hour == 19
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=now,
            today=due_date,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[0].was_on_time is True

    _with_db(tmp_path, "ontime-ha-local-not-utc.db")(_body)


def test_complete_instance_due_time_requires_now_on_due_date(tmp_path) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        with pytest.raises(ValueError, match="now is required to compare due_time"):
            await complete_instance(
                database,
                instance.id,
                actor_source="user",
                actor_user_id="user-1",
                today=due_date,
            )

    _with_db(tmp_path, "due-time-requires-now.db")(_body)


# ---------------------------------------------------------------------------
# uncomplete_instance: append uncompleted, no-op if already open
# ---------------------------------------------------------------------------


def test_uncomplete_instance_appends_and_leaves_original_untouched(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        completed_at = datetime.datetime(
            2026, 9, 18, 8, 0, 0, tzinfo=datetime.timezone.utc
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=completed_at,
        )
        events = CompletionEventsDao(database)
        before = await events.list_by_instance(instance.id)
        assert len(before) == 1
        original = before[0]
        assert original.event_type == EVENT_COMPLETED
        assert original.occurred_at == "2026-09-18T08:00:00+00:00"
        assert original.actor_source == "user"
        assert original.actor_user_id == "user-1"
        assert original.actor_child_id is None
        uncompleted_at = completed_at + datetime.timedelta(seconds=1)
        state = await uncomplete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
            now=uncompleted_at,
        )
        assert state == "open"
        assert await instance_state(database, instance.id) == "open"
        after = await events.list_by_instance(instance.id)
        assert len(after) == 2
        assert after[0].id == original.id
        assert after[0].event_type == EVENT_COMPLETED
        assert after[0].occurred_at == original.occurred_at
        assert after[0].actor_source == original.actor_source
        assert after[0].actor_user_id == original.actor_user_id
        assert after[0].actor_child_id == original.actor_child_id
        assert after[1].event_type == EVENT_UNCOMPLETED
        assert after[1].actor_source == "panel"
        assert after[1].actor_child_id == child.id
        assert after[1].was_on_time is None

    _with_db(tmp_path, "uncomplete-append.db")(_body)


def test_uncomplete_instance_already_open_is_noop(tmp_path) -> None:
    async def _body(database, child, instance):
        events = CompletionEventsDao(database)
        assert await events.list_by_instance(instance.id) == []
        first = await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
        )
        after_first = await events.list_by_instance(instance.id)
        assert first == "open"
        assert after_first == []
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
        )
        await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
        )
        before = await events.list_by_instance(instance.id)
        assert len(before) == 2
        second = await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-2",
        )
        after = await events.list_by_instance(instance.id)
        assert second == "open"
        assert after == before
        assert after[0].actor_user_id == "user-1"
        assert after[1].actor_user_id == "user-1"

    _with_db(tmp_path, "uncomplete-noop.db")(_body)


def test_uncomplete_instance_unknown_instance_id_raises(tmp_path) -> None:
    async def _body(database, child, instance):
        with pytest.raises(ValueError, match="instance_id"):
            await uncomplete_instance(
                database,
                instance.id + 999,
                actor_source="user",
                actor_user_id="user-1",
            )

    _with_db(tmp_path, "uncomplete-unknown.db")(_body)


def test_uncomplete_instance_rejects_non_integer_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="instance_id"):
            await uncomplete_instance(
                object(),
                "1",
                actor_source="user",
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="instance_id"):
            await uncomplete_instance(
                object(),
                True,
                actor_source="user",
                actor_user_id="user-1",
            )

    _run(_body())


def test_uncomplete_instance_now_pins_occurred_at(tmp_path) -> None:
    async def _body(database, child, instance):
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=datetime.datetime(
                2026, 9, 18, 8, 0, 0, tzinfo=datetime.timezone.utc
            ),
        )
        pinned = datetime.datetime(
            2026, 9, 18, 8, 0, 1, tzinfo=datetime.timezone.utc
        )
        await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=pinned,
        )
        rows = await CompletionEventsDao(database).list_by_instance(
            instance.id
        )
        assert rows[1].occurred_at == "2026-09-18T08:00:01+00:00"

    _with_db(tmp_path, "uncomplete-pinned.db")(_body)


def test_uncomplete_instance_concurrent_second_call_is_noop(tmp_path) -> None:
    """Two racing uncompletes cannot both append.

    Deterministic gate: task A is paused at its INSERT (it holds the
    connection lock); task B is then started and must queue.  A
    finishes, B sees open and appends nothing.
    """
    async def _main():
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()
        hass = _gated_hass(armed, gate_open, a_started)
        database = NestQuestDatabase(hass)
        await database.open(tmp_path / "uncomplete-race.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            rules = ScheduleRulesDao(database)
            definitions = QuestDefinitionsDao(database)
            instances = QuestInstancesDao(database)
            child = await children.create("Ada", _now_stamp())
            rule = await rules.create("daily", D1)
            definition = await definitions.create(
                "Brush teeth",
                rule.id,
                _now_stamp(),
                assignee_child_ids=[child.id],
            )
            instance = await instances.upsert(
                definition.id,
                child.id,
                D1,
                _now_stamp(),
                window="morning",
            )
            await complete_instance(
                database,
                instance.id,
                actor_source="user",
                actor_user_id="user-1",
            )

            armed["active"] = True
            task_a = asyncio.ensure_future(
                uncomplete_instance(
                    database,
                    instance.id,
                    actor_source="user",
                    actor_user_id="user-1",
                )
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                uncomplete_instance(
                    database,
                    instance.id,
                    actor_source="user",
                    actor_user_id="user-2",
                )
            )
            await asyncio.sleep(0)
            gate_open.set()
            state_a, state_b = await asyncio.gather(task_a, task_b)
            assert state_a == "open"
            assert state_b == "open"
            rows = await CompletionEventsDao(database).list_by_instance(
                instance.id
            )
            assert len(rows) == 2
            assert rows[0].event_type == EVENT_COMPLETED
            assert rows[1].event_type == EVENT_UNCOMPLETED
            assert rows[1].actor_user_id == "user-1"
        finally:
            await database.close()

    _run(_main())


# ---------------------------------------------------------------------------
# missed: derived for past-due open instances, never stored
# ---------------------------------------------------------------------------


def test_append_event_rejects_missed_event_type() -> None:
    async def _body():
        with pytest.raises(ValueError, match="event_type"):
            await append_event(
                object(),
                1,
                1,
                "missed",
                actor_source="user",
                actor_user_id="user-1",
                was_on_time=True,
            )

    _run(_body())


def test_instance_state_missed_when_past_due_and_open(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        later = due + datetime.timedelta(days=1)
        assert await instance_state(database, instance.id, today=later) == "missed"
        rows = await CompletionEventsDao(database).list_by_instance(instance.id)
        assert rows == []

    _with_db(tmp_path, "state-missed-open.db")(_body)


def test_instance_state_open_when_due_today(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        assert await instance_state(database, instance.id, today=due) == "open"

    _with_db(tmp_path, "state-open-due-today.db")(_body)


def test_instance_state_done_when_past_due_and_completed(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            today=due,
        )
        later = due + datetime.timedelta(days=1)
        assert await instance_state(database, instance.id, today=later) == "done"

    _with_db(tmp_path, "state-done-past-due.db")(_body)


def test_instance_state_missed_after_uncompleted_when_past_due(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_COMPLETED,
            actor_source="user",
            actor_user_id="user-1",
            was_on_time=True,
        )
        await append_event(
            database,
            instance.id,
            child.id,
            EVENT_UNCOMPLETED,
            actor_source="user",
            actor_user_id="user-1",
        )
        later = due + datetime.timedelta(days=1)
        assert await instance_state(database, instance.id, today=later) == "missed"

    _with_db(tmp_path, "state-missed-uncompleted.db")(_body)


def test_instance_state_missed_uses_host_today_when_unthreaded(tmp_path) -> None:
    async def _body(database, child, instance):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        past = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            yesterday.isoformat(),
            _now_stamp(),
            window="afternoon",
            today=yesterday,
        )
        assert await instance_state(database, past.id) == "missed"
        rows = await CompletionEventsDao(database).list_by_instance(past.id)
        assert rows == []
        assert all(row.event_type != "missed" for row in rows)

    _with_db(tmp_path, "state-missed-host-today.db")(_body)


def test_uncomplete_past_due_done_returns_missed_not_done(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            today=due,
        )
        later = due + datetime.timedelta(days=1)
        assert await instance_state(database, instance.id, today=later) == "done"
        state = await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            today=later,
        )
        assert state == "missed"
        assert await instance_state(database, instance.id, today=later) == "missed"
        rows = await CompletionEventsDao(database).list_by_instance(instance.id)
        assert [row.event_type for row in rows] == [
            EVENT_COMPLETED,
            EVENT_UNCOMPLETED,
        ]
        assert all(row.event_type != "missed" for row in rows)

    _with_db(tmp_path, "uncomplete-past-due-missed.db")(_body)


def test_uncomplete_past_due_already_open_is_noop_missed(tmp_path) -> None:
    async def _body(database, child, instance):
        later = datetime.date.fromisoformat(instance.due_date) + datetime.timedelta(
            days=1
        )
        events = CompletionEventsDao(database)
        assert await events.list_by_instance(instance.id) == []
        state = await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            today=later,
        )
        assert state == "missed"
        assert await events.list_by_instance(instance.id) == []

    _with_db(tmp_path, "uncomplete-past-due-noop.db")(_body)


def test_complete_instance_of_missed_returns_done(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        later = due + datetime.timedelta(days=1)
        assert await instance_state(database, instance.id, today=later) == "missed"
        state = await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(later, 8, 0),
            today=later,
        )
        assert state == "done"
        assert await instance_state(database, instance.id, today=later) == "done"
        rows = await CompletionEventsDao(database).list_by_instance(instance.id)
        assert len(rows) == 1
        assert rows[0].event_type == EVENT_COMPLETED
        assert rows[0].was_on_time is False

    _with_db(tmp_path, "complete-missed.db")(_body)


def test_list_missed_for_child_over_date_range(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        later_due = due + datetime.timedelta(days=1)
        other = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            later_due.isoformat(),
            _now_stamp(),
            window="morning",
        )
        await complete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            today=due,
        )
        today = later_due + datetime.timedelta(days=1)
        found = await list_missed_for_child(
            database,
            child.id,
            instance.due_date,
            later_due.isoformat(),
            today=today,
        )
        assert [row.id for row in found] == [other.id]
        events = CompletionEventsDao(database)
        assert await events.list_by_instance(other.id) == []
        done_rows = await events.list_by_instance(instance.id)
        assert [row.event_type for row in done_rows] == [EVENT_COMPLETED]
        assert all(row.event_type != "missed" for row in done_rows)

    _with_db(tmp_path, "list-missed-range.db")(_body)


def test_list_missed_for_child_empty_when_due_today(tmp_path) -> None:
    async def _body(database, child, instance):
        due = datetime.date.fromisoformat(instance.due_date)
        found = await list_missed_for_child(
            database,
            child.id,
            instance.due_date,
            instance.due_date,
            today=due,
        )
        assert found == []

    _with_db(tmp_path, "list-missed-due-today.db")(_body)


def test_list_missed_for_child_rejects_non_integer_id() -> None:
    async def _body():
        with pytest.raises(ValueError, match="child_id"):
            await list_missed_for_child(object(), "1", D1, D1)
        with pytest.raises(ValueError, match="child_id"):
            await list_missed_for_child(object(), True, D1, D1)

    _run(_body())


# ---------------------------------------------------------------------------
# lifecycle: complete → uncomplete → complete
# ---------------------------------------------------------------------------


def test_complete_uncomplete_complete_three_events_final_done(
    tmp_path,
) -> None:
    async def _body(database, child, instance):
        due_date = datetime.date.fromisoformat(instance.due_date)
        later = due_date + datetime.timedelta(days=1)
        instance = await QuestInstancesDao(database).upsert(
            instance.definition_id,
            child.id,
            instance.due_date,
            _now_stamp(),
            window=instance.window,
            due_time="12:00",
        )
        events = CompletionEventsDao(database)

        first = await complete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
            now=_ha_local(due_date, 11, 0),
            today=due_date,
        )
        assert first == "done"
        before_uncomplete = await events.list_by_instance(instance.id)
        assert len(before_uncomplete) == 1
        original = before_uncomplete[0]
        assert original.event_type == EVENT_COMPLETED
        assert original.was_on_time is True
        assert original.actor_source == "panel"
        assert original.actor_user_id is None
        assert original.actor_child_id == child.id
        assert await instance_state(database, instance.id, today=later) == "done"

        reversed_state = await uncomplete_instance(
            database,
            instance.id,
            actor_source="user",
            actor_user_id="user-1",
            now=_ha_local(later, 8, 0),
            today=later,
        )
        assert reversed_state == "missed"
        assert await instance_state(database, instance.id, today=later) == "missed"

        second = await complete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
            now=_ha_local(later, 9, 0),
            today=later,
        )
        assert second == "done"
        assert await instance_state(database, instance.id, today=later) == "done"

        after = await events.list_by_instance(instance.id)
        assert [row.event_type for row in after] == [
            EVENT_COMPLETED,
            EVENT_UNCOMPLETED,
            EVENT_COMPLETED,
        ]
        assert after[0].id == original.id
        assert after[0].occurred_at == original.occurred_at
        assert after[0].actor_source == original.actor_source
        assert after[0].actor_user_id == original.actor_user_id
        assert after[0].actor_child_id == original.actor_child_id
        assert after[0].was_on_time is True
        assert after[1].actor_source == "user"
        assert after[1].actor_user_id == "user-1"
        assert after[1].actor_child_id is None
        assert after[1].was_on_time is None
        assert after[2].actor_source == "panel"
        assert after[2].actor_user_id is None
        assert after[2].actor_child_id == child.id
        assert after[2].was_on_time is False
        assert all(row.event_type != "missed" for row in after)

    _with_db(tmp_path, "lifecycle-three.db")(_body)
