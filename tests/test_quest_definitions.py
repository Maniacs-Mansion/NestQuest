"""Tests for quest_definitions.py: the Feature 06 create business layer."""
from __future__ import annotations

import asyncio
import re

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_rules import (
    QuestDefinitionsDao,
    ScheduleRulesDao,
    schedule_rule_to_storage,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.quest_definitions import (
    CreatedQuestDefinition,
    create_quest_definition,
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


async def _prepare(path) -> tuple:
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    await apply_migrations(database)
    children = ChildrenDao(database)
    rules = ScheduleRulesDao(database)
    definitions = QuestDefinitionsDao(database)
    child = await children.create("Ada", NOW)
    return database, children, rules, definitions, child


def _with_db(tmp_path, name):
    """Run an async body against a prepared database, closing it after."""

    def _run_test(body):
        async def _main():
            database, children, rules, definitions, child = await _prepare(
                tmp_path / name
            )
            try:
                return await body(database, children, rules, definitions, child)
            finally:
                await database.close()

        return _run(_main())

    return _run_test


def _daily_rule() -> ScheduleRule:
    return ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-14")


# ---------------------------------------------------------------------------
# create_quest_definition: successful creates
# ---------------------------------------------------------------------------


def test_create_one_child_one_window(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        rule = _daily_rule()
        result = await create_quest_definition(
            database,
            "  Brush teeth  ",
            rule,
            [child.id],
            ["morning"],
            description="  Twice daily  ",
            icon="  mdi:tooth  ",
        )
        assert isinstance(result, CreatedQuestDefinition)
        definition = result.definition
        assert definition.title == "Brush teeth"
        assert definition.description == "Twice daily"
        assert definition.icon == "mdi:tooth"
        assert definition.is_active is True
        # D-008: the definition-level due_time column is never set here.
        assert definition.due_time is None
        # Timestamp is stamped UTC at second precision by the business layer.
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00",
            definition.created_at,
        )
        # The rule round-trips through the storage mapping.
        assert result.rule == rule
        assert definition.schedule_rule_id is not None
        rule_row = await rules.get(definition.schedule_rule_id)
        assert rule_row is not None
        assert rule_row.rule_type == "daily"
        # Assignees and windows are read back through the DAO.
        assert [c.id for c in result.assignees] == [child.id]
        assert [w.window for w in result.windows] == ["morning"]
        assert result.windows[0].due_time is None
        return result

    _with_db(tmp_path, "create-one.db")(_body)


def test_create_several_children_several_windows_with_due_times(
    tmp_path,
) -> None:
    async def _body(database, children, rules, definitions, child):
        bo = await children.create("Bo", NOW)
        cleo = await children.create("Cleo", NOW)
        rule = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={0, 2, 4},
            start_date="2026-09-14",
        )
        result = await create_quest_definition(
            database,
            "Chore",
            rule,
            [child.id, bo.id, cleo.id],
            [("morning", "09:00"), ("evening", "19:30")],
        )
        assert sorted(c.id for c in result.assignees) == sorted(
            [child.id, bo.id, cleo.id]
        )
        by_name = {w.window: w.due_time for w in result.windows}
        assert by_name == {"morning": "09:00", "evening": "19:30"}
        assert result.rule == rule
        stored = await definitions.get(result.definition.id)
        assert stored is not None
        assert stored.due_time is None
        return result

    _with_db(tmp_path, "create-many.db")(_body)


# ---------------------------------------------------------------------------
# create_quest_definition: argument rejections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", None])
def test_create_rejects_empty_title(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="title is required"):
            await create_quest_definition(
                database, bad, _daily_rule(), [child.id], ["morning"]
            )
        return None

    _with_db(tmp_path, "create-bad-title.db")(_body)


def test_create_rejects_non_string_title(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="title must be a string"):
            await create_quest_definition(
                database, 42, _daily_rule(), [child.id], ["morning"]
            )
        return None

    _with_db(tmp_path, "create-bad-title-type.db")(_body)


@pytest.mark.parametrize("bad", [None, "daily", 42, {"rule_type": "daily"}])
def test_create_rejects_non_schedule_rule(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="rule must be a ScheduleRule"):
            await create_quest_definition(
                database, "Brush teeth", bad, [child.id], ["morning"]
            )
        return None

    _with_db(tmp_path, "create-bad-rule.db")(_body)


@pytest.mark.parametrize("bad", [[]])
def test_create_rejects_empty_assignees(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="assignee_child_ids must not be empty"
        ):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), bad, ["morning"]
            )
        return None

    _with_db(tmp_path, "create-empty-assignees.db")(_body)


@pytest.mark.parametrize("bad", [(1,), (1, 2), "1", {1}])
def test_create_rejects_non_list_assignees(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="assignee_child_ids must be a list"
        ):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), bad, ["morning"]
            )
        return None

    _with_db(tmp_path, "create-non-list-assignees.db")(_body)


@pytest.mark.parametrize("bad", [True, False, 1.5, "1", None])
def test_create_rejects_non_int_assignee(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="assignee_child_ids must contain integer"
        ):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [bad], ["morning"]
            )
        return None

    _with_db(tmp_path, "create-bad-assignee.db")(_body)


def test_create_rejects_duplicate_assignees(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="assignee_child_ids must not contain duplicate"
        ):
            await create_quest_definition(
                database,
                "Brush teeth",
                _daily_rule(),
                [child.id, child.id],
                ["morning"],
            )
        return None

    _with_db(tmp_path, "create-duplicate-assignees.db")(_body)


def test_create_rejects_inactive_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        inactive = await children.create("Bo", NOW)
        await children.set_active(inactive.id, False)
        with pytest.raises(
            ValueError, match="assignee_child_ids.*inactive"
        ):
            await create_quest_definition(
                database,
                "Brush teeth",
                _daily_rule(),
                [inactive.id],
                ["morning"],
            )
        return None

    _with_db(tmp_path, "create-inactive-child.db")(_body)


def test_create_rejects_unknown_child(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="assignee_child_ids.*does not exist"
        ):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [999], ["morning"]
            )
        return None

    _with_db(tmp_path, "create-unknown-child.db")(_body)


@pytest.mark.parametrize("bad", [[]])
def test_create_rejects_empty_windows(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="windows must not be empty"):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [child.id], bad
            )
        return None

    _with_db(tmp_path, "create-empty-windows.db")(_body)


@pytest.mark.parametrize(
    "bad", [("morning",), ("morning", "afternoon"), "morning", {"morning"}]
)
def test_create_rejects_non_list_windows(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="windows must be a list"):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [child.id], bad
            )
        return None

    _with_db(tmp_path, "create-non-list-windows.db")(_body)


@pytest.mark.parametrize("bad", [["noon"], [("MORNING", None)], [("", None)]])
def test_create_rejects_invalid_window(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="window must be one of"):
            await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [child.id], bad
            )
        return None

    _with_db(tmp_path, "create-bad-window.db")(_body)


def test_create_rejects_duplicate_windows(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="windows must not contain duplicate"
        ):
            await create_quest_definition(
                database,
                "Brush teeth",
                _daily_rule(),
                [child.id],
                ["morning", "morning"],
            )
        with pytest.raises(
            ValueError, match="windows must not contain duplicate"
        ):
            await create_quest_definition(
                database,
                "Brush teeth",
                _daily_rule(),
                [child.id],
                [("morning", "09:00"), ("morning", "10:00")],
            )
        return None

    _with_db(tmp_path, "create-duplicate-windows.db")(_body)


@pytest.mark.parametrize("bad", ["9:30", "25:00", "09:60", "0900"])
def test_create_rejects_malformed_due_time(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="HH:MM"):
            await create_quest_definition(
                database,
                "Brush teeth",
                _daily_rule(),
                [child.id],
                [("morning", bad)],
            )
        return None

    _with_db(tmp_path, "create-bad-due-time.db")(_body)


# ---------------------------------------------------------------------------
# create_quest_definition: a rejected create persists nothing
# ---------------------------------------------------------------------------


async def _assert_only_baseline_rows(
    rules, definitions, child, baseline_definition
) -> None:
    """Assert the baseline rule/definition/assignee/window rows survive
    unchanged and no second row of any of them appeared.

    A rejected create must leave each table's row count exactly as it
    was: still one rule, one definition, one assignee, one window —
    checked through the DAO (id 2 must be absent everywhere, id 1
    intact), since the leak guard forbids raw SQL in this test file.
    """
    assert await rules.get(1) is not None
    assert await rules.get(2) is None
    assert await definitions.get(1) == baseline_definition
    assert await definitions.get(2) is None
    assert [c.id for c in await definitions.list_assignees(1)] == [child.id]
    assert await definitions.list_assignees(2) == []
    assert [w.window for w in await definitions.list_windows(1)] == [
        "morning"
    ]
    assert await definitions.list_windows(2) == []


def test_rejected_create_writes_nothing(tmp_path) -> None:
    """A rejected create leaves every quest row count unchanged.

    Two rejection paths are forced: an in-transaction rejection (an
    inactive assignee fails validation inside the transaction and must
    roll the rule/definition back together) and a pre-write rejection
    (an invalid window is caught in the business layer before any write).
    Both must leave the baseline single-rule/single-definition state
    untouched, with no second row in any of the four tables.
    """
    async def _body(database, children, rules, definitions, child):
        baseline_rule = await rules.create("daily", "2026-09-14")
        baseline_definition = await definitions.create(
            "Baseline", baseline_rule.id, NOW, assignee_child_ids=[child.id]
        )
        await definitions.upsert_window(baseline_definition.id, "morning")
        inactive = await children.create("Bo", NOW)
        await children.set_active(inactive.id, False)
        rule = _daily_rule()

        # In-transaction rejection: the inactive child fails validation
        # inside the transaction, rolling the rule and definition back.
        with pytest.raises(ValueError, match="inactive"):
            await create_quest_definition(
                database, "Brush teeth", rule, [inactive.id], ["morning"]
            )
        await _assert_only_baseline_rows(
            rules, definitions, child, baseline_definition
        )

        # Pre-write rejection: an invalid window is caught up front, so
        # no transaction ever opens.
        with pytest.raises(ValueError, match="window must be one of"):
            await create_quest_definition(
                database, "Brush teeth", rule, [child.id], [("noon", None)]
            )
        await _assert_only_baseline_rows(
            rules, definitions, child, baseline_definition
        )
        return None

    _with_db(tmp_path, "create-rejected-nothing.db")(_body)


def test_post_write_failure_rolls_back_everything(tmp_path) -> None:
    """A failure after some writes rolls all four tables back together.

    Deterministic post-write trigger: the DAO method inserts the rule,
    the definition and the assignee rows, THEN validates the window name
    and raises ValueError for a window outside const.QUEST_WINDOWS.
    That failure lands after three writes inside the transaction, so the
    rule, definition and assignee rows must all roll back — no partial
    rows survive in any of the four tables.
    """
    async def _body(database, children, rules, definitions, child):
        storage = schedule_rule_to_storage(_daily_rule())
        dao = QuestDefinitionsDao(database)
        with pytest.raises(ValueError, match="window must be one of"):
            await dao.create_with_rule_and_windows(
                "Brush teeth",
                storage,
                NOW,
                [child.id],
                [("noon", None)],
            )
        # All four tables are empty: the earlier rule, definition and
        # assignee writes were rolled back, and no window row was added.
        assert await rules.get(1) is None
        assert await definitions.get(1) is None
        assert await definitions.list_active() == []
        assert await definitions.list_assignees(1) == []
        assert await definitions.list_windows(1) == []
        return None

    _with_db(tmp_path, "post-write-rollback.db")(_body)
