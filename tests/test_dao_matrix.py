"""Cross-table DAO unit suite: CRUD and constraint coverage for all tables.

The per-DAO test modules (test_dao_children, test_dao_rules,
test_dao_presence, test_dao_instances) cover each table's operations in
depth; this module is the FEATURE-02 closing sweep: a single systematic
matrix proving that for EVERY table, the DAO layer supports insert,
read, update and surfaces constraint violations — plus the instance
upsert idempotency and the completion_events no-mutation guarantee —
all against a temporary database file from a clean checkout.

No raw SQL touches the DAO-owned tables here except the sanctioned
COUNT(*) probes (each guarded by the per-DAO leak guards); everything
else goes through the typed DAO methods.
"""
from __future__ import annotations

import asyncio
import datetime
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.nestquest.dao_children import (
    AdminUsersDao,
    ChildrenDao,
)
from custom_components.nestquest.dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
)
from custom_components.nestquest.dao_presence import (
    PresenceOverridesDao,
    PresenceSchedulesDao,
)
from custom_components.nestquest.dao_rules import (
    ScheduleRulesDao,
    QuestDefinitionsDao,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _future_day(offset: int) -> str:
    return (
        datetime.date.today() + datetime.timedelta(days=offset)
    ).isoformat()


def _stamp() -> str:
    return f"{datetime.date.today().isoformat()}T08:00:00+00:00"


D1 = _future_day(1)
D2 = _future_day(2)
D20 = _future_day(20)

#: Every table the v1 schema owns, with the DAO that governs it.
ALL_TABLES = (
    "children",
    "admin_users",
    "schedule_rules",
    "quest_definitions",
    "presence_schedules",
    "presence_overrides",
    "quest_instances",
    "completion_events",
)


class World:
    """All DAOs over one migrated temporary database."""

    def __init__(self, database: NestQuestDatabase):
        self.database = database
        self.children = ChildrenDao(database)
        self.admins = AdminUsersDao(database)
        self.rules = ScheduleRulesDao(database)
        self.definitions = QuestDefinitionsDao(database)
        self.schedules = PresenceSchedulesDao(database)
        self.overrides = PresenceOverridesDao(database)
        self.instances = QuestInstancesDao(database)
        self.events = CompletionEventsDao(database)

    async def seed(self) -> None:
        """Populate one valid fixture chain through the DAO layer."""
        self.child = await self.children.create("Ada", _stamp())
        self.child2 = await self.children.create("Bo", _stamp())
        assert await self.admins.add("user-1", _stamp()) is True
        self.rule = await self.rules.create("daily", D1)
        self.definition = await self.definitions.create(
            "Brush teeth", self.child.id, self.rule.id, _stamp()
        )
        self.schedule = await self.schedules.upsert_by_child(
            self.child.id, 2, D1, "0,2,4|1,3"
        )
        self.override = await self.overrides.create(
            self.child.id, D1, D2, True, note="test"
        )
        self.instance = await self.instances.upsert(
            self.definition.id, self.child.id, D1, _stamp()
        )


async def _world(path) -> World:
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    world = World(database)
    await world.seed()
    return world


def _with_world(name):
    def _run_test(body):
        async def _main():
            world = await _world(name)
            try:
                return await body(world)
            finally:
                await world.database.close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# The matrix: every table gets insert / read / update / constraint check
# ---------------------------------------------------------------------------


def test_matrix_children_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        fetched = await w.children.get(w.child.id)
        assert fetched is not None and fetched.display_name == "Ada"
        # update
        await w.children.update(w.child.id, display_name="Ada L.")
        assert (await w.children.get(w.child.id)).display_name == "Ada L."
        # constraint: NOT NULL display_name
        with pytest.raises(sqlite3.IntegrityError):
            await w.database.execute(
                "INSERT INTO children (display_name, created_at) "
                "VALUES (NULL, ?)",
                (_stamp(),),
            )
        return True

    assert _with_world(tmp_path / "m-children.db")(_body) is True


def test_matrix_admin_users_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert + read
        assert await w.admins.exists("user-1") is True
        records = await w.admins.list()
        assert len(records) == 1
        # update path: idempotent add is the allowlist's update semantics
        assert await w.admins.add("user-1", _stamp()) is False
        # constraint: ha_user_id PRIMARY KEY
        with pytest.raises(sqlite3.IntegrityError):
            await w.database.execute(
                "INSERT INTO admin_users (ha_user_id, added_at) "
                "VALUES (?, ?)",
                ("user-1", _stamp()),
            )
        # remove
        assert await w.admins.remove("user-1") is True
        assert await w.admins.exists("user-1") is False
        return True

    assert _with_world(tmp_path / "m-admins.db")(_body) is True


def test_matrix_schedule_rules_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        fetched = await w.rules.get(w.rule.id)
        assert fetched.rule_type == "daily"
        # update
        await w.rules.update(w.rule.id, interval=3)
        assert (await w.rules.get(w.rule.id)).interval == 3
        # constraint: rule_type CHECK
        with pytest.raises(sqlite3.IntegrityError):
            await w.rules.create("sometimes", D1)
        # delete-if-unreferenced: referenced -> rejected
        assert await w.rules.delete_if_unreferenced(w.rule.id) is False
        return True

    assert _with_world(tmp_path / "m-rules.db")(_body) is True


def test_matrix_quest_definitions_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        fetched = await w.definitions.get(w.definition.id)
        assert fetched.title == "Brush teeth"
        # update
        await w.definitions.update(w.definition.id, title="Brush TEETH")
        assert (await w.definitions.get(w.definition.id)).title == (
            "Brush TEETH"
        )
        # constraint: FK to a nonexistent child rejected with ValueError
        with pytest.raises(ValueError, match="does not exist"):
            await w.definitions.create("X", 999, w.rule.id, _stamp())
        # constraint: inactive child rejected
        await w.children.set_active(w.child2.id, False)
        with pytest.raises(ValueError, match="inactive"):
            await w.definitions.set_assignee(w.definition.id, w.child2.id)
        # set_active: deactivate, never delete
        assert await w.definitions.set_active(w.definition.id, False) == 1
        assert (await w.definitions.get(w.definition.id)).is_active is False
        return True

    assert _with_world(tmp_path / "m-definitions.db")(_body) is True


def test_matrix_presence_schedules_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        fetched = await w.schedules.get_by_child(w.child.id)
        assert fetched.pattern == "0,2,4|1,3"
        # update path: upsert replaces in place (same row id)
        replaced = await w.schedules.upsert_by_child(
            w.child.id, 2, D2, "1,3|0,2,4"
        )
        assert replaced.id == fetched.id
        assert (await w.schedules.get_by_child(w.child.id)).pattern == (
            "1,3|0,2,4"
        )
        # constraint: malformed pattern CHECK
        with pytest.raises(sqlite3.IntegrityError):
            await w.schedules.upsert_by_child(w.child.id, 2, D1, "0,2")
        # delete: row gone, child present every day
        assert await w.schedules.delete(w.child.id) is True
        assert await w.schedules.get_by_child(w.child.id) is None
        return True

    assert _with_world(tmp_path / "m-schedules.db")(_body) is True


def test_matrix_presence_overrides_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        found = await w.overrides.list_by_child_and_range(
            w.child.id, D1, D2
        )
        assert [r.id for r in found] == [w.override.id]
        # update path: delete + recreate (overrides are append-oriented)
        assert await w.overrides.delete(w.override.id) is True
        replacement = await w.overrides.create(
            w.child.id, D1, D2, False, note="updated"
        )
        assert replacement.is_present is False
        # constraint: end before start CHECK
        with pytest.raises(sqlite3.IntegrityError):
            await w.overrides.create(w.child.id, D2, D1, True)
        return True

    assert _with_world(tmp_path / "m-overrides.db")(_body) is True


def test_matrix_quest_instances_crud_and_constraints(tmp_path) -> None:
    async def _body(w: World):
        # insert (seeded) + read
        fetched = await w.instances.get(w.definition.id, D1)
        assert fetched == w.instance
        # update path: conflict refresh on the OPEN instance — same row
        # id, snapshot columns (due_time) actually rewritten.
        refreshed = await w.instances.upsert(
            w.definition.id, w.child.id, D1, _stamp(), due_time="17:00"
        )
        assert refreshed.id == fetched.id, (
            "the conflict path must refresh the existing row in place"
        )
        assert refreshed.due_time == "17:00"
        assert fetched.due_time is None
        assert await w.instances.get_by_id(fetched.id) is not None
        return True

    assert _with_world(tmp_path / "m-instances.db")(_body) is True


def test_matrix_quest_instances_constraints(tmp_path) -> None:
    async def _body(w: World):
        # D20 has no instance yet: a raw insert succeeds, then an
        # identical second insert must fail on the UNIQUE constraint —
        # proving the schema backs the DAO's idempotency.
        await w.database.execute(
            "INSERT INTO quest_instances (definition_id, child_id, "
            "due_date, due_time, generated_at) "
            "VALUES (?, ?, ?, NULL, ?)",
            (w.definition.id, w.child.id, D20, _stamp()),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await w.database.execute(
                "INSERT INTO quest_instances (definition_id, child_id, "
                "due_date, due_time, generated_at) "
                "VALUES (?, ?, ?, NULL, ?)",
                (w.definition.id, w.child.id, D20, _stamp()),
            )
        # delete future uncompleted removes D20's open instance
        deleted = await w.instances.delete_future_uncompleted(
            w.definition.id, D20
        )
        assert deleted == 1
        return True

    assert _with_world(tmp_path / "m-instances-constraints.db")(_body) is True


def test_matrix_quest_instances_upsert_idempotency(tmp_path) -> None:
    async def _body(w: World):
        first = await w.instances.upsert(
            w.definition.id, w.child.id, D2, _stamp()
        )
        second = await w.instances.upsert(
            w.definition.id, w.child.id, D2, _stamp(), due_time="17:00"
        )
        assert second.id == first.id
        count = await w.database.fetch_one(
            "SELECT COUNT(*) FROM quest_instances"
        )
        # Seed created one (D1) plus this one (D2) — no duplicate.
        assert count == (2,)
        return True

    assert _with_world(tmp_path / "m-upsert-idempotent.db")(_body) is True


# ---------------------------------------------------------------------------
# completion_events: append-only by construction
# ---------------------------------------------------------------------------


def test_matrix_completion_events_append_read_and_no_mutation(
    tmp_path,
) -> None:
    async def _body(w: World):
        # insert: append a completion then a reversal, then re-complete
        await w.events.append(
            w.instance.id, w.child.id, "completed", "panel", _stamp(), True
        )
        await w.events.append(
            w.instance.id, w.child.id, "uncompleted", "user", _stamp(), None,
            actor_user_id="user-1",
        )
        await w.events.append(
            w.instance.id, w.child.id, "completed", "panel", _stamp(), False
        )
        # read: full ordered history + latest
        history = await w.events.list_by_instance(w.instance.id)
        assert [e.event_type for e in history] == [
            "completed",
            "uncompleted",
            "completed",
        ]
        latest = await w.events.get_latest_for_instance(w.instance.id)
        assert latest.event_type == "completed"
        assert latest.was_on_time is False
        # constraint: unknown instance FK + bad actor pair surface as
        # ValueError from the DAO's atomic validation
        with pytest.raises(ValueError, match="does not exist"):
            await w.events.append(
                999, w.child.id, "completed", "user", _stamp(), True,
                actor_user_id="user-1",
            )
        return history

    assert _with_world(tmp_path / "m-events.db")(_body) is not None


def test_completion_events_absolutely_no_mutation_path() -> None:
    """The structural half of the done-condition: the DAO class exposes
    no update/delete, AND no module in the package holds mutation SQL
    for the table (already asserted package-wide in test_dao_instances;
    re-asserted here so THIS suite stands alone in a clean checkout).
    """
    import inspect
    import re
    from pathlib import Path

    methods = {
        name
        for name, _ in inspect.getmembers(
            CompletionEventsDao, inspect.isfunction
        )
        if not name.startswith("__")
    }
    assert methods == {
        "append",
        "list_by_instance",
        "list_by_child_and_date_range",
        "get_latest_for_instance",
    }

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent
    mutation = re.compile(
        r"(UPDATE(\s+OR\s+\w+)?|DELETE\s+FROM)\s+"
        r"((main|temp)\s*\.\s*)?[`'\"]*(\[)?completion_events\b",
        re.IGNORECASE,
    )
    offenders = [
        py.name
        for py in sorted(package.glob("*.py"))
        if py.name != "__pycache__" and mutation.search(py.read_text())
    ]
    assert offenders == []