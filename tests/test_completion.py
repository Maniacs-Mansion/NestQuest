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
    assert "uncomplete_instance" not in public
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
