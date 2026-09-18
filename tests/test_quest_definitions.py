"""Tests for quest_definitions.py: the Feature 06 create business layer."""
from __future__ import annotations

import asyncio
import datetime
import re

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.const import DEFAULT_HORIZON_DAYS
from custom_components.nestquest.dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
)
from custom_components.nestquest.dao_rules import (
    QuestDefinitionsDao,
    ScheduleRulesDao,
    schedule_rule_to_storage,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.quest_definitions import (
    CreatedQuestDefinition,
    assign_child,
    create_quest_definition,
    edit_quest_definition,
    list_active_definitions,
    list_definitions_firing_on,
    list_definitions_for_child,
    set_quest_definition_active,
    unassign_child,
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


def _today_iso() -> str:
    """Today's date in ISO form, computed at call time (never cached).

    ``QuestInstancesDao.upsert`` refuses past due dates, so seeded
    instances use a date that is always today-or-later at test time.
    """
    return datetime.date.today().isoformat()


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


# ---------------------------------------------------------------------------
# edit_quest_definition: successful edits
# ---------------------------------------------------------------------------


def test_edit_title_description_icon(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            ["morning"],
            description="Old description",
            icon="mdi:old",
        )
        result = await edit_quest_definition(
            database,
            created.definition.id,
            title="  Floss  ",
            description="  New description  ",
            icon="  mdi:new  ",
        )
        assert result.definition.title == "Floss"
        assert result.definition.description == "New description"
        assert result.definition.icon == "mdi:new"
        # Untouched fields survive the edit unchanged.
        assert result.definition.id == created.definition.id
        assert result.definition.schedule_rule_id == created.definition.schedule_rule_id
        assert result.definition.due_time is None
        assert result.definition.is_active is True
        assert result.definition.created_at == created.definition.created_at
        # Rule, assignees and windows are read back through the DAO.
        assert result.rule == _daily_rule()
        assert [c.id for c in result.assignees] == [child.id]
        assert [w.window for w in result.windows] == ["morning"]
        stored = await definitions.get(created.definition.id)
        assert stored is not None
        assert stored.title == "Floss"
        assert stored.description == "New description"
        assert stored.icon == "mdi:new"
        return None

    _with_db(tmp_path, "edit-metadata.db")(_body)


def test_edit_omitted_fields_left_unchanged(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            ["morning"],
            description="Keep me",
        )
        result = await edit_quest_definition(
            database, created.definition.id, title="Renamed"
        )
        assert result.definition.title == "Renamed"
        assert result.definition.description == "Keep me"
        assert result.definition.icon is None
        return None

    _with_db(tmp_path, "edit-omitted.db")(_body)


def test_edit_clears_optional_metadata(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            ["morning"],
            description="Old",
            icon="mdi:old",
        )
        result = await edit_quest_definition(
            database,
            created.definition.id,
            description=None,
            icon=None,
        )
        assert result.definition.description is None
        assert result.definition.icon is None
        return None

    _with_db(tmp_path, "edit-clear-metadata.db")(_body)


def test_edit_rule_updates_existing_row_in_place(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        rule_id = created.definition.schedule_rule_id
        assert rule_id == 1
        new_rule = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={1, 3},
            start_date="2026-09-14",
        )
        result = await edit_quest_definition(
            database, created.definition.id, rule=new_rule
        )
        assert result.rule == new_rule
        # The definition keeps the SAME rule row: no new or orphaned row.
        assert result.definition.schedule_rule_id == rule_id
        rule_row = await rules.get(rule_id)
        assert rule_row is not None
        assert rule_row.rule_type == "weekly"
        assert rule_row.weekday_set == "1,3"
        assert await rules.get(rule_id + 1) is None
        return None

    _with_db(tmp_path, "edit-rule-in-place.db")(_body)


def test_edit_rule_shape_change_clears_stale_columns(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={2},
            start_date="2026-09-14",
        )
        created = await create_quest_definition(
            database, "Chore", weekly, [child.id], ["morning"]
        )
        rule_id = created.definition.schedule_rule_id
        result = await edit_quest_definition(
            database, created.definition.id, rule=_daily_rule()
        )
        assert result.rule == _daily_rule()
        rule_row = await rules.get(rule_id)
        assert rule_row is not None
        # The old weekly shape's weekday_set must be cleared, not left stale.
        assert rule_row.rule_type == "daily"
        assert rule_row.weekday_set is None
        return None

    _with_db(tmp_path, "edit-rule-shape.db")(_body)


def test_edit_replaces_windows(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            [("morning", "07:00"), ("evening", "19:00")],
        )
        result = await edit_quest_definition(
            database,
            created.definition.id,
            windows=[("morning", "08:00"), ("afternoon", "12:00")],
        )
        by_name = {w.window: w.due_time for w in result.windows}
        # morning's due time changed, afternoon added, evening removed.
        assert by_name == {"morning": "08:00", "afternoon": "12:00"}
        persisted = {
            w.window: w.due_time
            for w in await definitions.list_windows(created.definition.id)
        }
        assert persisted == {"morning": "08:00", "afternoon": "12:00"}
        return None

    _with_db(tmp_path, "edit-replace-windows.db")(_body)


def test_edit_preserves_assignees(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        bo = await children.create("Bo", NOW)
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id, bo.id], ["morning"]
        )
        result = await edit_quest_definition(
            database,
            created.definition.id,
            title="Renamed",
            rule=ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={0},
                start_date="2026-09-14",
            ),
            windows=[("evening", "20:00")],
        )
        assert sorted(c.id for c in result.assignees) == sorted([child.id, bo.id])
        persisted = [
            c.id for c in await definitions.list_assignees(created.definition.id)
        ]
        assert sorted(persisted) == sorted([child.id, bo.id])
        return None

    _with_db(tmp_path, "edit-preserves-assignees.db")(_body)


# ---------------------------------------------------------------------------
# edit_quest_definition: argument rejections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_edit_rejects_empty_title(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="title is required"):
            await edit_quest_definition(
                database, created.definition.id, title=bad
            )
        return None

    _with_db(tmp_path, "edit-bad-title.db")(_body)


@pytest.mark.parametrize("bad", [None, "weekly", 42, {"rule_type": "daily"}])
def test_edit_rejects_non_schedule_rule(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="rule must be a ScheduleRule"):
            await edit_quest_definition(
                database, created.definition.id, rule=bad
            )
        return None

    _with_db(tmp_path, "edit-bad-rule.db")(_body)


@pytest.mark.parametrize("bad", [["noon"], [("MORNING", None)], [("", None)]])
def test_edit_rejects_invalid_window(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="window must be one of"):
            await edit_quest_definition(
                database, created.definition.id, windows=bad
            )
        return None

    _with_db(tmp_path, "edit-bad-window.db")(_body)


@pytest.mark.parametrize("bad", ["9:30", "25:00", "09:60", "0900"])
def test_edit_rejects_malformed_due_time(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="HH:MM"):
            await edit_quest_definition(
                database, created.definition.id, windows=[("morning", bad)]
            )
        return None

    _with_db(tmp_path, "edit-bad-due-time.db")(_body)


@pytest.mark.parametrize("bad", [[]])
def test_edit_rejects_empty_windows(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="windows must not be empty"):
            await edit_quest_definition(
                database, created.definition.id, windows=bad
            )
        return None

    _with_db(tmp_path, "edit-empty-windows.db")(_body)


@pytest.mark.parametrize("bad", [("morning",), "morning", {"morning"}])
def test_edit_rejects_non_list_windows(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="windows must be a list"):
            await edit_quest_definition(
                database, created.definition.id, windows=bad
            )
        return None

    _with_db(tmp_path, "edit-non-list-windows.db")(_body)


def test_edit_rejects_nonexistent_definition(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="does not exist"):
            await edit_quest_definition(database, 999, title="X")
        return None

    _with_db(tmp_path, "edit-missing-definition.db")(_body)


def test_edit_nonexistent_definition_names_field(tmp_path) -> None:
    """A missing definition's error names the ``definition_id`` field.

    The DAO raises a bare "quest definition <id> does not exist"; the
    business layer must re-raise it prefixed with the field the caller
    passed, matching assign/unassign/deactivate.
    """
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError,
            match="definition_id: quest definition 999 does not exist",
        ):
            await edit_quest_definition(database, 999, title="X")
        return None

    _with_db(tmp_path, "edit-missing-definition-field.db")(_body)


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_edit_rejects_non_int_definition_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id must be an integer"
        ):
            await edit_quest_definition(database, bad, title="X")
        return None

    _with_db(tmp_path, "edit-bad-definition-id.db")(_body)


# ---------------------------------------------------------------------------
# edit_quest_definition: consistent snapshot and rollback (CQ-01, CQ-02)
# ---------------------------------------------------------------------------


def test_concurrent_edit_omitted_rule_snapshot_consistent(tmp_path) -> None:
    """Two concurrent edits never return a mixed-time snapshot.

    One edit changes windows only (rule omitted); the other changes the
    rule only (windows omitted).  Because each edit reads its rule,
    assignees and windows back inside its own locked transaction, the
    windows-only edit reports the rule as it was AT THAT EDIT's
    transaction: the ORIGINAL rule when it ran first, the NEW rule when
    it ran second.  That yields a strict invariant — the windows-only
    result's rule is the original exactly when the rule-only result
    still saw the original windows — which a post-transaction rule read
    would violate.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={2},
            start_date="2026-09-14",
        )
        windows_result, rule_result = await asyncio.gather(
            edit_quest_definition(
                database,
                created.definition.id,
                windows=[("evening", "19:00")],
            ),
            edit_quest_definition(database, created.definition.id, rule=weekly),
        )
        # Each edit reports its own change...
        assert [w.window for w in windows_result.windows] == ["evening"]
        assert rule_result.rule == weekly
        # ...and the pair is self-consistent: the windows-only edit saw
        # the original rule iff the rule-only edit saw the original
        # windows (they ran in that order).
        assert (windows_result.rule == _daily_rule()) == (
            [w.window for w in rule_result.windows] == ["evening"]
        )
        return None

    _with_db(tmp_path, "edit-concurrent-snapshot.db")(_body)


def test_edit_post_write_failure_rolls_back_everything(tmp_path) -> None:
    """A post-write failure during an edit rolls every table back together.

    Deterministic trigger: call the DAO's edit directly with a window
    name outside const.QUEST_WINDOWS.  The DAO applies the metadata and
    rule writes and the window delete, THEN validates the window name
    and raises ValueError.  That failure lands after several writes
    inside the transaction, so the metadata, rule and window changes
    must all roll back — the baseline definition, rule and windows
    survive unchanged.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            [("morning", "07:00")],
        )
        rule_id = created.definition.schedule_rule_id
        weekly_storage = schedule_rule_to_storage(
            ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={2},
                start_date="2026-09-14",
            )
        )
        dao = QuestDefinitionsDao(database)
        with pytest.raises(ValueError, match="window must be one of"):
            await dao.edit_definition(
                created.definition.id,
                title="Changed",
                rule=weekly_storage,
                windows=[("noon", None)],
            )
        stored = await definitions.get(created.definition.id)
        assert stored is not None
        assert stored.title == "Brush teeth"
        rule_row = await rules.get(rule_id)
        assert rule_row is not None
        assert rule_row.rule_type == "daily"
        assert rule_row.weekday_set is None
        by_name = {
            w.window: w.due_time
            for w in await definitions.list_windows(created.definition.id)
        }
        assert by_name == {"morning": "07:00"}
        assert [
            c.id for c in await definitions.list_assignees(created.definition.id)
        ] == [child.id]
        return None

    _with_db(tmp_path, "edit-post-write-rollback.db")(_body)


# ---------------------------------------------------------------------------
# assign_child / unassign_child: the assignment business-layer paths
# ---------------------------------------------------------------------------


def test_assign_child_multi_assignee_success(tmp_path) -> None:
    """Assigning a second child leaves both as assignees (D-008)."""
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        bo = await children.create("Bo", NOW)
        assignees = await assign_child(database, created.definition.id, bo.id)
        assert sorted(c.id for c in assignees) == sorted([child.id, bo.id])
        return assignees

    _with_db(tmp_path, "assign-multi.db")(_body)


def test_assign_child_duplicate_is_noop(tmp_path) -> None:
    """Assigning an already-assigned child adds no duplicate row."""
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        assignees = await assign_child(
            database, created.definition.id, child.id
        )
        assert [c.id for c in assignees] == [child.id]
        again = await assign_child(
            database, created.definition.id, child.id
        )
        assert [c.id for c in again] == [child.id]
        return assignees

    _with_db(tmp_path, "assign-duplicate.db")(_body)


def test_assign_child_unknown_child_names_field(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(
            ValueError, match="child_id.*does not exist"
        ):
            await assign_child(database, created.definition.id, 999)
        return None

    _with_db(tmp_path, "assign-unknown-child.db")(_body)


def test_assign_child_inactive_child_names_field(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        bo = await children.create("Bo", NOW)
        await children.set_active(bo.id, False)
        with pytest.raises(ValueError, match="child_id.*inactive"):
            await assign_child(database, created.definition.id, bo.id)
        # The failed assignment leaves the roster unchanged.
        assert [c.id for c in await definitions.list_assignees(
            created.definition.id
        )] == [child.id]
        return None

    _with_db(tmp_path, "assign-inactive-child.db")(_body)


def test_assign_child_nonexistent_definition_names_field(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id.*does not exist"
        ):
            await assign_child(database, 999, child.id)
        return None

    _with_db(tmp_path, "assign-missing-definition.db")(_body)


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_assign_child_rejects_non_int_definition_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id must be an integer"
        ):
            await assign_child(database, bad, child.id)
        return None

    _with_db(tmp_path, "assign-bad-definition-id.db")(_body)


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_assign_child_rejects_non_int_child_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="child_id must be an integer"):
            await assign_child(database, created.definition.id, bad)
        return None

    _with_db(tmp_path, "assign-bad-child-id.db")(_body)


def test_unassign_child_success_returns_true(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        bo = await children.create("Bo", NOW)
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id, bo.id],
            ["morning"],
        )
        assert await unassign_child(
            database, created.definition.id, bo.id
        ) is True
        assert [c.id for c in await definitions.list_assignees(
            created.definition.id
        )] == [child.id]
        return None

    _with_db(tmp_path, "unassign-success.db")(_body)


def test_unassign_child_not_assigned_returns_false(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        assert await unassign_child(
            database, created.definition.id, 999
        ) is False
        return None

    _with_db(tmp_path, "unassign-not-assigned.db")(_body)


def test_unassign_child_nonexistent_definition_names_field(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id.*does not exist"
        ):
            await unassign_child(database, 999, child.id)
        return None

    _with_db(tmp_path, "unassign-missing-definition.db")(_body)


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_unassign_child_rejects_non_int_definition_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id must be an integer"
        ):
            await unassign_child(database, bad, child.id)
        return None

    _with_db(tmp_path, "unassign-bad-definition-id.db")(_body)


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_unassign_child_rejects_non_int_child_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="child_id must be an integer"):
            await unassign_child(database, created.definition.id, bad)
        return None

    _with_db(tmp_path, "unassign-bad-child-id.db")(_body)


def test_assign_and_unassign_leave_instances_and_history_alone(
    tmp_path,
) -> None:
    """Assign/unassign write the assignees table only.

    An already-generated instance keeps its generation-time child_id, and
    no completion event appears — the assignment paths touch neither
    ``quest_instances`` nor ``completion_events``.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        bo = await children.create("Bo", NOW)
        await database.execute(
            "INSERT INTO quest_instances (definition_id, child_id, "
            "window, due_date, generated_at) VALUES (?, ?, 'morning', ?, ?)",
            (created.definition.id, child.id, "2026-09-15", NOW),
        )
        await assign_child(database, created.definition.id, bo.id)
        await unassign_child(database, created.definition.id, child.id)
        row = await database.fetch_one(
            "SELECT child_id FROM quest_instances WHERE definition_id = ?",
            (created.definition.id,),
        )
        assert row == (child.id,)
        events = await database.fetch_one(
            "SELECT COUNT(*) FROM completion_events"
        )
        assert events == (0,)
        return None

    _with_db(tmp_path, "assign-unassign-history.db")(_body)


def test_concurrent_assign_unassign_returns_consistent_roster(
    tmp_path,
) -> None:
    """A concurrent unassign cannot strip the just-assigned child from
    the roster that ``assign_child`` returns.

    ``assign_child`` returns the roster read inside the same locked
    transaction as the INSERT, so the child it assigned is always present
    in its result — even when an unassign of that same child races.  The
    pause hook holds ``list_assignees`` mid-flight so the unassign is
    deterministically queued against the assignment's lock.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        bo = await children.create("Bo", NOW)

        import custom_components.nestquest.dao_rules as dao_rules

        original_list = dao_rules.QuestDefinitionsDao.list_assignees
        started = asyncio.Event()
        release = asyncio.Event()

        async def _pausing_list(self, definition_id):
            if not started.is_set():
                started.set()
                await release.wait()
            return await original_list(self, definition_id)

        dao_rules.QuestDefinitionsDao.list_assignees = _pausing_list
        try:
            assign_task = asyncio.ensure_future(
                assign_child(database, created.definition.id, bo.id)
            )
            await started.wait()
            unassign_task = asyncio.ensure_future(
                unassign_child(database, created.definition.id, bo.id)
            )
            await asyncio.sleep(0)
            release.set()
            assignees, removed = await asyncio.gather(
                assign_task, unassign_task
            )
        finally:
            dao_rules.QuestDefinitionsDao.list_assignees = original_list

        assert bo.id in [c.id for c in assignees], (
            "assign_child must return a roster containing the child it "
            "just assigned, even under a concurrent unassign"
        )
        assert removed is True
        return assignees

    _with_db(tmp_path, "assign-unassign-concurrent.db")(_body)


# ---------------------------------------------------------------------------
# set_quest_definition_active: deactivate / reactivate
# ---------------------------------------------------------------------------


def test_set_quest_definition_active_round_trip(tmp_path) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        definition_id = created.definition.id

        deactivated = await set_quest_definition_active(
            database, definition_id, False
        )
        assert isinstance(deactivated, CreatedQuestDefinition)
        assert deactivated.definition.id == definition_id
        assert deactivated.definition.is_active is False
        # The decoded rule, assignees and windows form a consistent
        # snapshot of the (unchanged) definition.
        assert deactivated.rule == _daily_rule()
        assert [c.id for c in deactivated.assignees] == [child.id]
        assert [w.window for w in deactivated.windows] == ["morning"]
        assert await definitions.list_active() == []

        reactivated = await set_quest_definition_active(
            database, definition_id, True
        )
        assert reactivated.definition.is_active is True
        assert [d.id for d in await definitions.list_active()] == [
            definition_id
        ]
        return reactivated

    _with_db(tmp_path, "set-active-round-trip.db")(_body)


@pytest.mark.parametrize("bad", ["1", "0", 1, 0, 1.0, None, "true"])
def test_set_quest_definition_active_rejects_non_bool(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(
            ValueError, match="is_active must be a real bool"
        ):
            await set_quest_definition_active(
                database, created.definition.id, bad
            )
        # The refused transition left the definition active.
        stored = await definitions.get(created.definition.id)
        assert stored is not None
        assert stored.is_active is True
        return None

    _with_db(tmp_path, "set-active-non-bool.db")(_body)


@pytest.mark.parametrize("bad", [True, False, 1.5, "1", None])
def test_set_quest_definition_active_rejects_non_int_definition_id(
    tmp_path, bad
) -> None:
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(
            ValueError, match="definition_id must be an integer"
        ):
            await set_quest_definition_active(database, bad, False)
        stored = await definitions.get(created.definition.id)
        assert stored is not None
        assert stored.is_active is True
        return None

    _with_db(tmp_path, "set-active-non-int-id.db")(_body)


def test_set_quest_definition_active_nonexistent_definition_names_field(
    tmp_path,
) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(
            ValueError, match="definition_id.*does not exist"
        ):
            await set_quest_definition_active(database, 999, False)
        return None

    _with_db(tmp_path, "set-active-missing-definition.db")(_body)


def test_set_quest_definition_active_preserves_completed_and_history(
    tmp_path,
) -> None:
    """Deactivation stops future generation; reactivation resumes it.

    The Feature 07 wiring makes both transitions regenerate the
    definition's rolling horizon: future OPEN instances are removed on
    deactivation and re-materialized on reactivation.  A pre-existing
    COMPLETED instance and its completion events always survive both
    transitions unchanged (regeneration never touches completed rows or
    the past), and the append-only completion-events table is never
    rewritten.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        definition_id = created.definition.id
        rule_id = created.definition.schedule_rule_id

        # Seed a real instance and a real completion event against the
        # definition BEFORE deactivation, so the test can detect a
        # delete or mutation of pre-existing data (not just an empty
        # table staying empty).
        instances = QuestInstancesDao(database)
        events = CompletionEventsDao(database)
        instance = await instances.upsert(
            definition_id, child.id, _today_iso(), NOW, window="morning"
        )
        event = await events.append(
            instance.id,
            child.id,
            "completed",
            "user",
            NOW,
            True,
            actor_user_id="admin-1",
        )

        event_count = await database.fetch_one(
            "SELECT COUNT(*) FROM completion_events"
        )

        await set_quest_definition_active(database, definition_id, False)

        # The definition row survives (deactivated, not deleted).
        stored = await definitions.get(definition_id)
        assert stored is not None
        assert stored.is_active is False
        # Its rule, assignee and window rows all survive too.
        assert await rules.get(rule_id) is not None
        assert [c.id for c in await definitions.list_assignees(
            definition_id
        )] == [child.id]
        assert [w.window for w in await definitions.list_windows(
            definition_id
        )] == ["morning"]
        # The pre-existing instance and completion event survive with
        # unchanged ids and contents, and no new event rows appeared.
        assert await instances.get_by_id(instance.id) == instance
        assert await events.list_by_instance(instance.id) == [event]
        assert await database.fetch_one(
            "SELECT COUNT(*) FROM completion_events"
        ) == event_count

        await set_quest_definition_active(database, definition_id, True)
        assert (await definitions.get(definition_id)).is_active is True
        # Reactivation regenerates future OPEN instances, but the
        # completed instance and its history survive the sweep unchanged.
        assert await instances.get_by_id(instance.id) == instance
        assert await events.list_by_instance(instance.id) == [event]
        assert await database.fetch_one(
            "SELECT COUNT(*) FROM completion_events"
        ) == event_count
        return None

    _with_db(tmp_path, "set-active-preserves-completed.db")(_body)


def _gated_hass(
    armed: dict, gate_open: asyncio.Event, a_started: asyncio.Event
):
    """A hass mock whose executor gates the FIRST ``_execute`` job after
    arming — the UPDATE of whichever ``set_quest_definition_active``
    call starts first — proving the caller holds the connection lock at
    that moment and the second caller must queue behind it."""
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


def test_set_quest_definition_active_concurrent_opposite_transitions_return_own(
    tmp_path,
) -> None:
    """Racing deactivate/reactivate calls each report their own request.

    Deterministic gate on task A's UPDATE: task B queues behind the
    connection lock and lands the opposite transition after A.  Without
    the lock, A's readback could see B's write and report B's value.
    """
    async def _main():
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()
        hass = _gated_hass(armed, gate_open, a_started)
        database = NestQuestDatabase(hass)
        await database.open(tmp_path / "active-race.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            child = await children.create("Ada", NOW)
            created = await create_quest_definition(
                database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
            )

            armed["active"] = True
            task_a = asyncio.ensure_future(
                set_quest_definition_active(
                    database, created.definition.id, False
                )
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                set_quest_definition_active(
                    database, created.definition.id, True
                )
            )
            await asyncio.sleep(0)
            gate_open.set()
            record_a, record_b = await asyncio.gather(task_a, task_b)

            # Each caller gets back exactly the state it requested.
            assert record_a.definition.is_active is False
            assert record_b.definition.is_active is True
            # Both snapshots stay coherent: the decoded rule and the
            # assignees are those of the definition they were read from.
            assert record_a.rule == _daily_rule()
            assert record_b.rule == _daily_rule()
            assert [c.id for c in record_a.assignees] == [child.id]
            assert [c.id for c in record_b.assignees] == [child.id]
            # B landed last: the stored row is B's (read via the DAO —
            # the four-table leak guard forbids raw probes here).
            stored = await QuestDefinitionsDao(database).get(
                created.definition.id
            )
            assert stored is not None
            assert stored.is_active is True
        finally:
            await database.close()

    _run(_main())


# ---------------------------------------------------------------------------
# list query helpers: list_active_definitions / list_definitions_for_child /
# list_definitions_firing_on
# ---------------------------------------------------------------------------


def test_list_active_definitions_returns_only_active_in_id_order(tmp_path) -> None:
    """Only active definitions come back, in rising id order, each rich.

    Two definitions are created (ids 1 and 2), then definition 1 is
    deactivated.  ``list_active_definitions`` must return only definition
    2, and every bundle must carry the decoded rule, assignees and
    windows of its own definition.
    """
    async def _body(database, children, rules, definitions, child):
        bo = await children.create("Bo", NOW)
        first = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={0, 2},
            start_date="2026-09-14",
        )
        second = await create_quest_definition(
            database,
            "Tidy room",
            weekly,
            [child.id, bo.id],
            [("morning", "08:00"), ("evening", "19:00")],
        )
        assert [d.id for d in await definitions.list_active()] == [
            first.definition.id,
            second.definition.id,
        ]

        await set_quest_definition_active(database, first.definition.id, False)

        result = await list_active_definitions(database)
        assert [bundle.definition.id for bundle in result] == [second.definition.id]
        assert isinstance(result[0], CreatedQuestDefinition)
        assert result[0].rule == weekly
        assert sorted(c.id for c in result[0].assignees) == sorted(
            [child.id, bo.id]
        )
        by_name = {w.window: w.due_time for w in result[0].windows}
        assert by_name == {"morning": "08:00", "evening": "19:00"}
        return result

    _with_db(tmp_path, "list-active.db")(_body)


def test_list_definitions_for_child_returns_only_that_child(tmp_path) -> None:
    """Only the given child's definitions come back, deterministically.

    Definitions are created assigned to Ada (child), Bo, or both; the
    helper must return exactly the definitions assigned to Ada, excluding
    a Bo-only definition.  Inactive definitions are still assigned, so
    they too come back (the helper filters by child, not by activity).
    """
    async def _body(database, children, rules, definitions, child):
        bo = await children.create("Bo", NOW)
        ada_only = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        both = await create_quest_definition(
            database,
            "Tidy room",
            ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={1},
                start_date="2026-09-14",
            ),
            [child.id, bo.id],
            ["evening"],
        )
        bo_only = await create_quest_definition(
            database, "Walk dog", _daily_rule(), [bo.id], ["afternoon"]
        )

        # The helper returns the given child's definitions in ascending
        # id order, consistent with list_active_definitions.
        result = await list_definitions_for_child(database, child.id)
        assert [bundle.definition.id for bundle in result] == [
            ada_only.definition.id,
            both.definition.id,
        ]
        assert result[0].rule == _daily_rule()
        assert [c.id for c in result[0].assignees] == [child.id]
        assert [w.window for w in result[0].windows] == ["morning"]

        bo_result = await list_definitions_for_child(database, bo.id)
        assert [bundle.definition.id for bundle in bo_result] == [
            both.definition.id,
            bo_only.definition.id,
        ]
        return result

    _with_db(tmp_path, "list-for-child.db")(_body)


@pytest.mark.parametrize("bad", [True, False, 1.5, "1", None])
def test_list_definitions_for_child_rejects_non_int_child_id(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        with pytest.raises(ValueError, match="child_id must be an integer"):
            await list_definitions_for_child(database, bad)
        return None

    _with_db(tmp_path, "list-for-child-bad-id.db")(_body)


def test_list_definitions_firing_on_mixed_rules(tmp_path) -> None:
    """A mixed daily + weekly + monthly set fires on the right dates.

    Daily fires every day from its start; weekly fires on its weekdays;
    monthly fires on its day-of-month.  Deactivated definitions never
    fire, and the returned bundles carry the decoded rule.
    """
    async def _body(database, children, rules, definitions, child):
        daily = await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-14"),
            [child.id],
            ["morning"],
        )
        weekly = await create_quest_definition(
            database,
            "Weekly chore",
            ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={0, 2},  # Monday, Wednesday
                start_date="2026-09-14",
            ),
            [child.id],
            ["evening"],
        )
        monthly = await create_quest_definition(
            database,
            "Monthly chore",
            ScheduleRule(
                rule_type=RuleType.MONTHLY_DAY,
                day_of_month=15,
                start_date="2026-09-14",
            ),
            [child.id],
            ["afternoon"],
        )

        # 2026-09-14 is a Monday (weekday 0): daily + weekly fire;
        # monthly (the 15th) does not.
        hits = await list_definitions_firing_on(database, "2026-09-14")
        assert [b.definition.id for b in hits] == [
            daily.definition.id,
            weekly.definition.id,
        ]
        # 2026-09-15 is a Tuesday (weekday 1, day 15): daily + monthly.
        hits = await list_definitions_firing_on(database, "2026-09-15")
        assert [b.definition.id for b in hits] == [
            daily.definition.id,
            monthly.definition.id,
        ]
        # 2026-09-16 is a Wednesday (weekday 2, day 16): daily + weekly.
        hits = await list_definitions_firing_on(database, "2026-09-16")
        assert [b.definition.id for b in hits] == [
            daily.definition.id,
            weekly.definition.id,
        ]

        # Deactivating a definition removes it from every future result.
        await set_quest_definition_active(database, weekly.definition.id, False)
        hits = await list_definitions_firing_on(database, "2026-09-14")
        assert [b.definition.id for b in hits] == [daily.definition.id]
        # The returned bundle carries the decoded rule, not the raw row.
        assert hits[0].rule == ScheduleRule(
            rule_type=RuleType.DAILY, start_date="2026-09-14"
        )
        return hits

    _with_db(tmp_path, "list-firing-on.db")(_body)


@pytest.mark.parametrize(
    "bad",
    ["2026-9-4", "2026-13-01", "2026-02-30", "not-a-date", None, 20260914],
)
def test_list_definitions_firing_on_rejects_malformed_date(tmp_path, bad) -> None:
    async def _body(database, children, rules, definitions, child):
        await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        with pytest.raises(ValueError, match="date must be"):
            await list_definitions_firing_on(database, bad)
        return None

    _with_db(tmp_path, "list-firing-on-bad-date.db")(_body)


def test_list_query_snapshot_coherent_under_racing_edit(tmp_path) -> None:
    """A racing edit cannot mix states into a query helper's snapshot.

    The query helper pauses mid-snapshot (inside its locked transaction)
    while an edit that changes BOTH the rule and the windows is queued
    behind the connection lock.  Because the helper reads definitions,
    rules and windows in one locked transaction, its returned bundle is
    either the whole old state or the whole new state — never the old
    rule paired with the new windows (the exact interleaving the unlocked
    reads used to allow).  The pause hook holds
    ``list_windows`` mid-flight so the edit is deterministically queued
    against the helper's lock.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={2},
            start_date="2026-09-14",
        )

        import custom_components.nestquest.dao_rules as dao_rules

        original_list = dao_rules.QuestDefinitionsDao.list_windows
        started = asyncio.Event()
        release = asyncio.Event()

        async def _pausing_list(self, definition_id):
            if not started.is_set():
                started.set()
                await release.wait()
            return await original_list(self, definition_id)

        dao_rules.QuestDefinitionsDao.list_windows = _pausing_list
        try:
            read_task = asyncio.ensure_future(
                list_definitions_firing_on(database, "2026-09-16")
            )
            await started.wait()
            edit_task = asyncio.ensure_future(
                edit_quest_definition(
                    database,
                    created.definition.id,
                    rule=weekly,
                    windows=["evening"],
                )
            )
            await asyncio.sleep(0)
            release.set()
            result, edited = await asyncio.gather(read_task, edit_task)
        finally:
            dao_rules.QuestDefinitionsDao.list_windows = original_list

        # The helper finished before the queued edit, so its snapshot is
        # the whole OLD state: the daily rule with its morning window.
        assert [b.definition.id for b in result] == [created.definition.id]
        assert result[0].rule == _daily_rule()
        assert [w.window for w in result[0].windows] == ["morning"]
        # The edit then reported the whole NEW state, not a mix either.
        assert edited.rule == weekly
        assert [w.window for w in edited.windows] == ["evening"]
        return result

    _with_db(tmp_path, "list-snapshot-concurrent.db")(_body)


def test_list_definitions_for_child_snapshot_coherent_under_racing_unassign(
    tmp_path,
) -> None:
    """A racing unassign cannot strip the child from the child-scoped
    snapshot that ``list_definitions_for_child`` returns.

    The helper pauses mid-snapshot (inside its locked transaction) while
    an unassign of the very child it is listing is queued behind the
    connection lock.  Because the definition set and its assignees are
    read in one locked transaction, the returned bundle still shows the
    child assigned — the coherent pre-unassign snapshot — rather than the
    mixed state (definition returned "for child" but with the child
    already gone from its roster) that the unlocked reads used to allow.
    The pause hook holds ``list_assignees`` mid-flight so the unassign is
    deterministically queued against the helper's lock.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )

        import custom_components.nestquest.dao_rules as dao_rules

        original_list = dao_rules.QuestDefinitionsDao.list_assignees
        started = asyncio.Event()
        release = asyncio.Event()

        async def _pausing_list(self, definition_id):
            if not started.is_set():
                started.set()
                await release.wait()
            return await original_list(self, definition_id)

        dao_rules.QuestDefinitionsDao.list_assignees = _pausing_list
        try:
            read_task = asyncio.ensure_future(
                list_definitions_for_child(database, child.id)
            )
            await started.wait()
            unassign_task = asyncio.ensure_future(
                unassign_child(database, created.definition.id, child.id)
            )
            for _ in range(5):
                await asyncio.sleep(0)
            release.set()
            result, removed = await asyncio.gather(read_task, unassign_task)
        finally:
            dao_rules.QuestDefinitionsDao.list_assignees = original_list

        # The helper finished before the queued unassign, so its snapshot
        # is the whole OLD state: the child still assigned to the
        # definition it returned for that child.
        assert [b.definition.id for b in result] == [created.definition.id]
        assert [c.id for c in result[0].assignees] == [child.id]
        assert removed is True
        return result

    _with_db(tmp_path, "list-for-child-snapshot-concurrent.db")(_body)


def test_list_active_definitions_snapshot_coherent_under_racing_edit(
    tmp_path,
) -> None:
    """A racing edit cannot mix states into ``list_active_definitions``.

    The helper pauses mid-snapshot (inside its locked transaction) while
    an edit that changes BOTH the rule and the windows is queued behind
    the connection lock.  Because definitions, rules and windows are read
    in one locked transaction, the returned bundle is the whole old state
    — the daily rule with its morning window — never the old rule paired
    with the new windows.  The pause hook holds ``list_windows``
    mid-flight so the edit is deterministically queued against the
    helper's lock.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database, "Brush teeth", _daily_rule(), [child.id], ["morning"]
        )
        weekly = ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={2},
            start_date="2026-09-14",
        )

        import custom_components.nestquest.dao_rules as dao_rules

        original_list = dao_rules.QuestDefinitionsDao.list_windows
        started = asyncio.Event()
        release = asyncio.Event()

        async def _pausing_list(self, definition_id):
            if not started.is_set():
                started.set()
                await release.wait()
            return await original_list(self, definition_id)

        dao_rules.QuestDefinitionsDao.list_windows = _pausing_list
        try:
            read_task = asyncio.ensure_future(list_active_definitions(database))
            await started.wait()
            edit_task = asyncio.ensure_future(
                edit_quest_definition(
                    database,
                    created.definition.id,
                    rule=weekly,
                    windows=["evening"],
                )
            )
            await asyncio.sleep(0)
            release.set()
            result, edited = await asyncio.gather(read_task, edit_task)
        finally:
            dao_rules.QuestDefinitionsDao.list_windows = original_list

        # The helper finished before the queued edit, so its snapshot is
        # the whole OLD state: the daily rule with its morning window.
        assert [b.definition.id for b in result] == [created.definition.id]
        assert result[0].rule == _daily_rule()
        assert [w.window for w in result[0].windows] == ["morning"]
        # The edit then reported the whole NEW state, not a mix either.
        assert edited.rule == weekly
        assert [w.window for w in edited.windows] == ["evening"]
        return result

    _with_db(tmp_path, "list-active-snapshot-concurrent.db")(_body)


# ---------------------------------------------------------------------------
# full-lifecycle integration: one definition through every operation
# ---------------------------------------------------------------------------


def test_full_lifecycle_preserves_completed_and_history(tmp_path) -> None:
    """End-to-end lifecycle preserves completed rows and append-only history.

    Each stage (create -> edit rule/windows -> assign a second child ->
    unassign the original child -> deactivate -> reactivate) now
    regenerates the definition's future OPEN instances (Feature 07
    wiring), but a pre-existing COMPLETED instance and its completion
    events survive every stage unchanged — the completed row keeps its
    id and snapshot columns, the completion-events table stays append-only.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Brush teeth",
            _daily_rule(),
            [child.id],
            [("morning", "07:00")],
        )
        definition_id = created.definition.id

        instances = QuestInstancesDao(database)
        events = CompletionEventsDao(database)
        instance = await instances.upsert(
            definition_id, child.id, _today_iso(), NOW, window="morning"
        )
        event = await events.append(
            instance.id,
            child.id,
            "completed",
            "user",
            NOW,
            True,
            actor_user_id="admin-1",
        )
        event_count = await database.fetch_one(
            "SELECT COUNT(*) FROM completion_events"
        )

        async def _assert_history_preserved():
            assert await instances.get_by_id(instance.id) == instance
            assert await events.list_by_instance(instance.id) == [event]
            assert await database.fetch_one(
                "SELECT COUNT(*) FROM completion_events"
            ) == event_count

        await _assert_history_preserved()

        # Edit rule and windows together; the definition's rule row is
        # rewritten in place and its window set replaced.
        edited = await edit_quest_definition(
            database,
            definition_id,
            rule=ScheduleRule(
                rule_type=RuleType.WEEKLY,
                weekday_set={1, 3},
                start_date="2026-09-14",
            ),
            windows=[("morning", "08:00"), ("evening", "19:30")],
        )
        assert edited.rule == ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={1, 3},
            start_date="2026-09-14",
        )
        by_name = {w.window: w.due_time for w in edited.windows}
        assert by_name == {"morning": "08:00", "evening": "19:30"}
        await _assert_history_preserved()

        # Assign a second child: multi-assignee, both present.
        bo = await children.create("Bo", NOW)
        roster = await assign_child(database, definition_id, bo.id)
        assert sorted(c.id for c in roster) == sorted([child.id, bo.id])
        await _assert_history_preserved()

        # Unassign the original child: only the link drops.
        assert await unassign_child(database, definition_id, child.id) is True
        assert [
            c.id for c in await definitions.list_assignees(definition_id)
        ] == [bo.id]
        await _assert_history_preserved()

        # Deactivate, then reactivate: the definition survives both.
        deactivated = await set_quest_definition_active(
            database, definition_id, False
        )
        assert deactivated.definition.is_active is False
        await _assert_history_preserved()
        reactivated = await set_quest_definition_active(
            database, definition_id, True
        )
        assert reactivated.definition.is_active is True
        await _assert_history_preserved()

        return reactivated

    _with_db(tmp_path, "full-lifecycle.db")(_body)


@pytest.mark.parametrize(
    "mode",
    ["edit", "assign", "unassign", "set_active"],
)
def test_wrappers_forward_horizon_days(tmp_path, mode) -> None:
    """The four change wrappers forward a non-default horizon_days.

    Each wrapper threads ``horizon_days`` into the regeneration it triggers;
    passing 5 here must bound the regenerated window to today..today+5 —
    proving the forwarding argument is actually honored, not dropped.
    """
    async def _body(database, children, rules, definitions, child):
        created = await create_quest_definition(
            database,
            "Chore",
            ScheduleRule(rule_type=RuleType.DAILY, start_date=_today_iso()),
            [child.id],
            ["morning"],
        )
        definition_id = created.definition.id
        instances = QuestInstancesDao(database)

        if mode == "edit":
            await edit_quest_definition(
                database,
                definition_id,
                windows=[("morning", "10:30")],
                horizon_days=5,
            )
            tracked = child
        elif mode == "assign":
            bo = await children.create("Bo", NOW)
            await assign_child(database, definition_id, bo.id, horizon_days=5)
            tracked = bo
        elif mode == "unassign":
            # The remaining assignee (``child``) must be regenerated over
            # the 5-day window after ``bo`` is removed.
            bo = await children.create("Bo", NOW)
            await assign_child(database, definition_id, bo.id)
            await unassign_child(
                database, definition_id, bo.id, horizon_days=5
            )
            tracked = child
        else:  # set_active
            await set_quest_definition_active(
                database, definition_id, True, horizon_days=5
            )
            tracked = child

        today = datetime.date.today()
        end = (today + datetime.timedelta(days=5)).isoformat()
        records = await instances.list_by_date_range(
            tracked.id, today.isoformat(), end
        )
        assert len(records) == 6

        beyond = (today + datetime.timedelta(days=6)).isoformat()
        beyond_end = (
            today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)
        ).isoformat()
        assert await instances.list_by_date_range(
            tracked.id, beyond, beyond_end
        ) == []
        return None

    _with_db(tmp_path, f"wrapper-horizon-{mode}.db")(_body)
