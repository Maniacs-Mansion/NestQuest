"""Tests for dao_instances.py: task_instances + append-only completion_events."""
from __future__ import annotations

import asyncio
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


NOW = "2026-09-14T12:00:00+00:00"


async def _prepare(path) -> tuple:
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    children = ChildrenDao(database)
    rules = ScheduleRulesDao(database)
    definitions = TaskDefinitionsDao(database)
    instances = TaskInstancesDao(database)
    events = CompletionEventsDao(database)
    child = await children.create("Ada", NOW)
    rule = await rules.create("daily", "2026-09-01")
    definition = await definitions.create("Brush teeth", child.id, rule.id, NOW)
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
            definition.id, child.id, "2026-09-15", NOW
        )
        assert isinstance(first, TaskInstanceRecord)
        second = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW
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
        a = await instances.upsert(definition.id, child.id, "2026-09-15", NOW)
        b = await instances.upsert(definition.id, child.id, "2026-09-16", NOW)
        assert a.id != b.id
        return (a, b)

    _with_db(tmp_path, "upsert-multi-date.db")(_body)


def test_upsert_refreshes_snapshot_columns_on_conflict(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        first = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW, due_time="08:00"
        )
        second = await instances.upsert(
            definition.id,
            child.id,
            "2026-09-15",
            "2026-09-14T13:00:00+00:00",
            due_time="08:30",
        )
        assert second.id == first.id
        assert second.due_time == "08:30"
        assert second.generated_at == "2026-09-14T13:00:00+00:00"
        return second

    _with_db(tmp_path, "upsert-refresh.db")(_body)


def test_upsert_rejects_wrong_child_for_definition(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await children.create("Bo", NOW)
        with pytest.raises(ValueError, match="assigned to"):
            await instances.upsert(definition.id, other.id, "2026-09-15", NOW)
        return None

    _with_db(tmp_path, "upsert-wrong-child.db")(_body)


def test_upsert_rejects_unknown_definition_and_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="definition 999"):
            await instances.upsert(999, child.id, "2026-09-15", NOW)
        # Unknown child: the definition-assignee check fires first and
        # is the one that matters (an instance must carry its
        # definition's assignee).  To reach the child-existence check
        # at all, the definition would have to claim child 999 — an
        # FK-impossible state — so the child check only guards direct
        # callers with a matching fake assignee; assert the guard
        # order instead of forcing the FK-impossible state.
        rule = await rules.create("daily", "2026-09-01")
        other_definition = await definitions.create(
            "X", child.id, rule.id, NOW
        )
        with pytest.raises(ValueError, match="not 999"):
            await instances.upsert(other_definition.id, 999, "2026-09-15", NOW)
        return None

    _with_db(tmp_path, "upsert-unknown.db")(_body)


def test_upsert_malformed_due_date_raises(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        for bad in ("not-a-date", "2026-9-15", ""):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await instances.upsert(definition.id, child.id, bad, NOW)
        return None

    _with_db(tmp_path, "upsert-bad-date.db")(_body)


# ---------------------------------------------------------------------------
# task_instances: get / list
# ---------------------------------------------------------------------------


def test_get_by_definition_and_date_round_trip(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        created = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW, due_time="17:30"
        )
        fetched = await instances.get(definition.id, "2026-09-15")
        assert fetched == created
        assert fetched.due_time == "17:30"
        assert await instances.get(definition.id, "2026-09-16") is None
        return fetched

    _with_db(tmp_path, "get-round-trip.db")(_body)


def test_get_by_id_round_trip(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        created = await instances.upsert(definition.id, child.id, "2026-09-15", NOW)
        fetched = await instances.get_by_id(created.id)
        assert fetched == created
        assert await instances.get_by_id(999) is None
        return fetched

    _with_db(tmp_path, "get-by-id.db")(_body)


def test_list_by_child_and_date_filters(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await children.create("Bo", NOW)
        rule = await rules.create("daily", "2026-09-01")
        other_definition = await definitions.create(
            "Make bed", other.id, rule.id, NOW
        )
        await instances.upsert(definition.id, child.id, "2026-09-15", NOW)
        await instances.upsert(definition.id, child.id, "2026-09-16", NOW)
        await instances.upsert(
            other_definition.id, other.id, "2026-09-15", NOW
        )
        mine = await instances.list_by_child_and_date(child.id, "2026-09-15")
        assert len(mine) == 1
        assert mine[0].child_id == child.id
        assert mine[0].due_date == "2026-09-15"
        return mine

    _with_db(tmp_path, "list-by-child-date.db")(_body)


def test_list_by_date_range_filters_and_orders(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        for day in ("2026-09-10", "2026-09-12", "2026-09-14", "2026-09-20"):
            await instances.upsert(definition.id, child.id, day, NOW)
        found = await instances.list_by_date_range(
            child.id, "2026-09-11", "2026-09-15"
        )
        assert [i.due_date for i in found] == ["2026-09-12", "2026-09-14"]
        edge = await instances.list_by_date_range(
            child.id, "2026-09-12", "2026-09-12"
        )
        assert [i.due_date for i in edge] == ["2026-09-12"]
        return found

    _with_db(tmp_path, "list-by-range.db")(_body)


def test_list_by_date_range_rejects_inverted_range(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="on or after"):
            await instances.list_by_date_range(
                child.id, "2026-09-15", "2026-09-10"
            )
        return None

    _with_db(tmp_path, "list-inverted.db")(_body)


# ---------------------------------------------------------------------------
# task_instances: delete_future_uncompleted
# ---------------------------------------------------------------------------


def test_delete_future_uncompleted_removes_only_eligible(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        await instances.upsert(definition.id, child.id, "2026-09-10", NOW)
        future_open = await instances.upsert(
            definition.id, child.id, "2026-09-20", NOW
        )
        await instances.upsert(definition.id, child.id, "2026-09-21", NOW)
        deleted = await instances.delete_future_uncompleted(
            definition.id, "2026-09-20"
        )
        assert deleted == 2
        assert await instances.get(definition.id, "2026-09-10") is not None
        assert await instances.get(definition.id, "2026-09-20") is None
        assert await instances.get(definition.id, "2026-09-21") is None
        return deleted

    _with_db(tmp_path, "delete-future.db")(_body)


def test_delete_future_uncompleted_spares_completed(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        completed = await instances.upsert(
            definition.id, child.id, "2026-09-20", NOW
        )
        open_one = await instances.upsert(
            definition.id, child.id, "2026-09-21", NOW
        )
        await events.append(
            completed.id, child.id, "completed", "user", NOW, True,
            actor_user_id="user-1",
        )
        deleted = await instances.delete_future_uncompleted(
            definition.id, "2026-09-20"
        )
        assert deleted == 1
        assert await instances.get_by_id(completed.id) is not None, (
            "an instance with a completion event must never be deleted"
        )
        assert await instances.get_by_id(open_one.id) is None
        return deleted

    _with_db(tmp_path, "delete-spares-completed.db")(_body)


def test_delete_future_uncompleted_spares_past(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        await instances.upsert(definition.id, child.id, "2026-09-10", NOW)
        await instances.upsert(definition.id, child.id, "2026-09-11", NOW)
        deleted = await instances.delete_future_uncompleted(
            definition.id, "2026-09-11"
        )
        assert deleted == 1
        assert await instances.get(definition.id, "2026-09-10") is not None
        return deleted

    _with_db(tmp_path, "delete-spares-past.db")(_body)


def test_delete_future_uncompleted_other_definitions_untouched(
    tmp_path,
) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        other = await definitions.create(
            "Make bed", child.id, (await rules.create("daily", "2026-09-01")).id,
            NOW,
        )
        await instances.upsert(definition.id, child.id, "2026-09-20", NOW)
        await instances.upsert(other.id, child.id, "2026-09-20", NOW)
        deleted = await instances.delete_future_uncompleted(
            definition.id, "2026-09-20"
        )
        assert deleted == 1
        assert await instances.get(other.id, "2026-09-20") is not None
        return deleted

    _with_db(tmp_path, "delete-scoped.db")(_body)


# ---------------------------------------------------------------------------
# completion_events: append
# ---------------------------------------------------------------------------


def test_append_completion_round_trips(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW
        )
        event = await events.append(
            instance.id, child.id, "completed", "user", NOW, True,
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
            definition.id, child.id, "2026-09-15", NOW
        )
        event = await events.append(
            instance.id, child.id, "completed", "panel", NOW, False,
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
            definition.id, child.id, "2026-09-15", NOW
        )
        reversal = await events.append(
            instance.id, child.id, "uncompleted", "user", NOW, None,
            actor_user_id="user-1",
        )
        assert reversal.event_type == "uncompleted"
        assert reversal.was_on_time is None
        carried = await events.append(
            instance.id, child.id, "uncompleted", "user", NOW, True,
            actor_user_id="user-1",
        )
        assert carried.was_on_time is True
        return (reversal, carried)

    _with_db(tmp_path, "append-uncompleted.db")(_body)


def test_append_validation_rejects_bad_shapes(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW
        )
        with pytest.raises(ValueError, match="event_type"):
            await events.append(
                instance.id, child.id, "missed", "user", NOW, True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="actor_source"):
            await events.append(
                instance.id, child.id, "completed", "kiosk", NOW, True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="requires actor_user_id"):
            await events.append(
                instance.id, child.id, "completed", "user", NOW, True,
                actor_user_id=None,
            )
        with pytest.raises(ValueError, match="must not carry"):
            await events.append(
                instance.id, child.id, "completed", "panel", NOW, True,
                actor_user_id="user-1",
            )
        with pytest.raises(ValueError, match="requires was_on_time"):
            await events.append(
                instance.id, child.id, "completed", "panel", NOW, None
            )
        return None

    _with_db(tmp_path, "append-validation.db")(_body)


def test_append_rejects_unknown_instance_or_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        with pytest.raises(ValueError, match="instance 999"):
            await events.append(
                999, child.id, "completed", "user", NOW, True,
                actor_user_id="user-1",
            )
        instance = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW
        )
        with pytest.raises(ValueError, match="belongs to child"):
            await events.append(
                instance.id, 999, "completed", "user", NOW, True,
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
            definition.id, child.id, "2026-09-15", NOW
        )
        await events.append(
            instance.id, child.id, "completed", "panel", NOW, True
        )
        await events.append(
            instance.id, child.id, "uncompleted", "user", NOW, True,
            actor_user_id="user-1",
        )
        await events.append(
            instance.id, child.id, "completed", "panel", NOW, False
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
            definition.id, child.id, "2026-09-15", NOW
        )
        return await events.get_latest_for_instance(instance.id)

    assert _with_db(tmp_path, "latest-none.db")(_body) is None


def test_get_latest_returns_uncompleted_when_reversed(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        instance = await instances.upsert(
            definition.id, child.id, "2026-09-15", NOW
        )
        await events.append(
            instance.id, child.id, "completed", "panel", NOW, True
        )
        await events.append(
            instance.id, child.id, "uncompleted", "user", NOW, True,
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
            definition.id, child.id, "2026-09-10", NOW
        )
        inside = await instances.upsert(
            definition.id, child.id, "2026-09-12", NOW
        )
        late = await instances.upsert(
            definition.id, child.id, "2026-09-20", NOW
        )
        await events.append(
            early.id, child.id, "completed", "panel", NOW, True
        )
        await events.append(
            inside.id, child.id, "completed", "panel", NOW, False
        )
        await events.append(
            inside.id, child.id, "uncompleted", "user", NOW, True,
            actor_user_id="user-1",
        )
        await events.append(
            late.id, child.id, "completed", "panel", NOW, True
        )
        found = await events.list_by_child_and_date_range(
            child.id, "2026-09-11", "2026-09-15"
        )
        assert [e.id for e in found] == [2, 3]  # inside's two events
        return found

    _with_db(tmp_path, "events-by-range.db")(_body)


def test_list_events_occurred_at_scope_variant(tmp_path) -> None:
    async def _body(database, children, rules, definitions, instances,
                    events, child, definition):
        late_due = await instances.upsert(
            definition.id, child.id, "2026-09-20", NOW
        )
        # Completed long after its due date: due-date scope misses it,
        # occurred-at scope catches it.
        await events.append(
            late_due.id, child.id, "completed", "panel", NOW, False
        )
        by_due = await events.list_by_child_and_date_range(
            child.id, "2026-09-01", "2026-09-15"
        )
        assert by_due == []
        by_occurrence = await events.list_by_child_and_date_range(
            child.id, "2026-09-14", "2026-09-14", due_date_scope=False
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
    """Package-wide guardrail: UPDATE/DELETE ... completion_events must
    not appear in ANY module or test — the append-only property is
    enforced here, not just in the DAO class docstring.
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
        r"(UPDATE|DELETE\s+FROM)\s+[`'\"]*(\[)?completion_events\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for root in (package, repo_root / "tests"):
        for py in sorted(root.rglob("*.py")):
            if mutation_pattern.search(py.read_text()):
                offenders.append(py.relative_to(repo_root).as_posix())
    assert offenders == [], (
        f"completion_events mutation SQL found in: {offenders}"
    )


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
                definition.id, child.id, "2026-09-15", NOW
            )
            tasks = [
                asyncio.ensure_future(
                    events.append(
                        instance.id, child.id, "completed", "user",
                        f"2026-09-15T08:0{index}:00+00:00", True,
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
        child = await children.create("Ada", NOW)
        rule = await rules.create("daily", "2026-09-01")
        definition = await definitions.create(
            "Brush teeth", child.id, rule.id, NOW
        )
        return (database, children, rules, definitions, instances,
                events, child, definition)

    history = _run(_main())
    assert history[-1].occurred_at == "2026-09-15T08:04:00+00:00"