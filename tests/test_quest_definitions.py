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
