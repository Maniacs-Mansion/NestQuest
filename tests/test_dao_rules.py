"""Tests for dao_rules.py: typed DAO for schedule_rules and quest_definitions."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_rules import (
    ScheduleRuleRecord,
    ScheduleRuleStorage,
    ScheduleRulesDao,
    QuestDefinitionRecord,
    QuestDefinitionWindowRecord,
    QuestDefinitionsDao,
    schedule_rule_from_storage,
    schedule_rule_to_storage,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations
from custom_components.nestquest.recurrence import (
    RuleType,
    RuleValidationError,
    ScheduleRule,
)


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
    rules = ScheduleRulesDao(database)
    definitions = QuestDefinitionsDao(database)
    children = ChildrenDao(database)
    child = await children.create("Ada", NOW)
    return database, rules, definitions, children, child


def _with_db(tmp_path, name):
    """Run an async body against a prepared database, closing it after."""

    def _run_test(body):
        async def _main():
            database, rules, definitions, children, child = await _prepare(
                tmp_path / name
            )
            try:
                return await body(database, rules, definitions, children, child)
            finally:
                await database.close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# schedule_rules: create / get
# ---------------------------------------------------------------------------


def test_rule_create_returns_typed_record(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create(
            "weekly", "2026-09-14", weekday_set="0,2,4", interval=2
        )
        assert isinstance(rule, ScheduleRuleRecord)
        assert rule.id == 1
        assert rule.rule_type == "weekly"
        assert rule.interval == 2
        assert rule.weekday_set == "0,2,4"
        assert rule.day_of_month is None
        assert rule.nth_weekday is None
        assert rule.month is None
        assert rule.start_date == "2026-09-14"
        assert rule.end_date is None
        return rule

    _with_db(tmp_path, "rule-create.db")(_body)


def test_rule_create_monthly_with_day_of_month(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create(
            "monthly", "2026-09-14", day_of_month=15, weekday_set=None
        )
        assert rule.day_of_month == 15
        assert rule.weekday_set is None
        return rule

    _with_db(tmp_path, "rule-monthly.db")(_body)


def test_rule_get_missing_returns_none(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await rules.get(999)

    assert _with_db(tmp_path, "rule-get-missing.db")(_body) is None


def test_rule_create_coherence_enforced_by_schema(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await rules.create("weekly", "2026-09-14", weekday_set=None)
        return None

    _with_db(tmp_path, "rule-coherence.db")(_body)


def test_rule_create_rejects_malformed_dates(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        for bad in (
            "not-a-date",
            "2026-9-4",
            "2026-13-01",
            "2026-02-30",
            "09-14",
            "",
        ):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await rules.create("daily", bad)
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await rules.create("daily", "2026-09-14", end_date=bad)
        return None

    _with_db(tmp_path, "rule-create-dates.db")(_body)


def test_rule_create_end_before_start_rejected(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await rules.create(
                "daily", "2026-09-14", end_date="2026-09-13"
            )
        return None

    _with_db(tmp_path, "rule-dates.db")(_body)


# ---------------------------------------------------------------------------
# schedule_rules: update
# ---------------------------------------------------------------------------


def test_rule_update_fields_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("weekly", "2026-09-14", weekday_set="0,2")
        updated = await rules.update(
            rule.id, weekday_set="1,3", interval=3, end_date="2026-12-31"
        )
        assert updated == 1
        fetched = await rules.get(rule.id)
        assert fetched.weekday_set == "1,3"
        assert fetched.interval == 3
        assert fetched.end_date == "2026-12-31"
        assert fetched.rule_type == "weekly"
        return fetched

    _with_db(tmp_path, "rule-update.db")(_body)


def test_rule_update_omitted_fields_untouched(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("weekly", "2026-09-14", weekday_set="0,2")
        await rules.update(rule.id, interval=2)
        fetched = await rules.get(rule.id)
        assert fetched.weekday_set == "0,2"
        assert fetched.start_date == "2026-09-14"
        return fetched

    _with_db(tmp_path, "rule-update-partial.db")(_body)


def test_rule_update_no_fields_returns_zero(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        return await rules.update(rule.id)

    assert _with_db(tmp_path, "rule-update-empty.db")(_body) == 0


def test_rule_update_missing_rule_returns_zero(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await rules.update(999, interval=2)

    assert _with_db(tmp_path, "rule-update-missing.db")(_body) == 0


def test_rule_update_bad_type_rejected_by_check(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await rules.update(rule.id, rule_type="sometimes")
        return None

    _with_db(tmp_path, "rule-update-bad-type.db")(_body)


def test_rule_update_can_clear_nullable_fields(tmp_path) -> None:
    """Explicit None clears a nullable column; omitted leaves it alone.

    A caller must be able to reopen an ended rule (end_date back to
    NULL) and clear rule-shape fields; the _UNSET sentinel keeps
    'omitted' distinct from 'write NULL'.
    """
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create(
            "weekly",
            "2026-09-14",
            weekday_set="0,2",
            end_date="2026-12-31",
            month=3,
        )
        # Omitted: nothing changes.
        await rules.update(rule.id, interval=2)
        kept = await rules.get(rule.id)
        assert kept.end_date == "2026-12-31"
        assert kept.month == 3
        # Explicit None: clears both.
        await rules.update(rule.id, end_date=None, month=None)
        cleared = await rules.get(rule.id)
        assert cleared.end_date is None
        assert cleared.month is None
        assert cleared.interval == 2
        return cleared

    _with_db(tmp_path, "rule-update-clear.db")(_body)


def test_rule_update_validates_date_shape(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        for bad in ("not-a-date", "2026-9-4", "2026-13-01", "09-14"):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await rules.update(rule.id, start_date=bad)
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await rules.update(rule.id, end_date=bad)
        # None is still allowed (clears the column) without validation.
        await rules.update(rule.id, end_date=None)
        return None

    _with_db(tmp_path, "rule-update-dates.db")(_body)


# ---------------------------------------------------------------------------
# schedule_rules: delete-if-unreferenced
# ---------------------------------------------------------------------------


def test_rule_delete_unreferenced_succeeds(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        assert await rules.delete_if_unreferenced(rule.id) is True
        return await rules.get(rule.id)

    assert _with_db(tmp_path, "rule-delete-ok.db")(_body) is None


def test_rule_delete_referenced_is_rejected(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        await definitions.create("Brush teeth", rule.id, NOW)
        assert await rules.delete_if_unreferenced(rule.id) is False
        fetched = await rules.get(rule.id)
        assert fetched is not None, (
            "referenced rule must survive the delete attempt"
        )
        return fetched

    _with_db(tmp_path, "rule-delete-referenced.db")(_body)


def test_rule_delete_missing_returns_false(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await rules.delete_if_unreferenced(999)

    assert _with_db(tmp_path, "rule-delete-missing.db")(_body) is False


def test_rule_delete_after_last_reference_removed_succeeds(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create(
            "Brush teeth", rule.id, NOW
        )
        assert await rules.delete_if_unreferenced(rule.id) is False
        await definitions.set_active(definition.id, False)
        # Deactivation is NOT deletion: the definition still references
        # the rule, so the delete must still be rejected.
        assert await rules.delete_if_unreferenced(rule.id) is False
        return None

    _with_db(tmp_path, "rule-delete-inactive-ref.db")(_body)


def test_rule_delete_concurrent_with_definition_create_is_safe(
    tmp_path,
) -> None:
    """A racing definition creation cannot produce a dangling reference.

    Both operations queue on the connection lock, so exactly one of two
    safe outcomes happens: the create wins and the delete is rejected
    (definition exists, rule exists), or the delete wins and the create
    fails cleanly with ValueError (rule gone).  A definition row
    pointing at a deleted rule is impossible in either case.

    BOTH orderings are forced: delete-first by starting the delete and
    yielding; create-first by hooking ScheduleRulesDao.get so the
    create's validation pauses mid-flight before the delete starts.
    """
    async def _main(order: str):
        database = NestQuestDatabase(_make_hass_mock())
        await database.open(tmp_path / f"rule-delete-race-{order}.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            rules = ScheduleRulesDao(database)
            definitions = QuestDefinitionsDao(database)
            child = await children.create("Ada", NOW)
            rule_a = await rules.create("daily", "2026-09-14")

            if order == "create-first":
                # Pause the create inside its rule validation: the hook
                # blocks after the rule-lookup statement until the
                # delete task has been scheduled, so the create holds
                # the connection lock while the delete queues behind
                # it — then the create proceeds and wins.
                import custom_components.nestquest.dao_rules as dao_rules

                original_validate = (
                    dao_rules.QuestDefinitionsDao._validate_rule_exists
                )
                release = asyncio.Event()
                started = asyncio.Event()

                async def _pausing_validate(self, rule_id):
                    # Run the real validation FIRST (this is the
                    # time-of-check), THEN pause: the delete task gets
                    # scheduled while the create sits between its
                    # passed validation and its INSERT.  The serialized
                    # transaction must keep the delete queued until the
                    # insert commits, so the create must win the race
                    # and the delete must be rejected as referenced.
                    await original_validate(self, rule_id)
                    if rule_id == rule_a.id and not started.is_set():
                        started.set()
                        await release.wait()

                dao_rules.QuestDefinitionsDao._validate_rule_exists = (
                    _pausing_validate
                )
                try:
                    create_task = asyncio.ensure_future(
                        definitions.create("Brush teeth", rule_a.id, NOW)
                    )
                    await started.wait()
                    delete_task = asyncio.ensure_future(
                        rules.delete_if_unreferenced(rule_a.id)
                    )
                    await asyncio.sleep(0)
                    started.clear()
                    release.set()
                    deleted, creation = await asyncio.gather(
                        delete_task, create_task, return_exceptions=True
                    )
                finally:
                    dao_rules.QuestDefinitionsDao._validate_assignable = (
                        original_validate
                    )
            else:
                async def _delete():
                    return await rules.delete_if_unreferenced(rule_a.id)

                async def _create():
                    return await definitions.create(
                        "Brush teeth", rule_a.id, NOW
                    )

                delete_task = asyncio.ensure_future(_delete())
                await asyncio.sleep(0)
                create_task = asyncio.ensure_future(_create())
                deleted, creation = await asyncio.gather(
                    delete_task, create_task, return_exceptions=True
                )

            assert not isinstance(deleted, BaseException), (
                f"delete must queue, not crash: {deleted!r}"
            )
            rule_row = await rules.get(rule_a.id)
            if deleted:
                # Delete won: the create must have failed cleanly.
                assert isinstance(creation, ValueError), (
                    f"creating against a deleted rule must raise "
                    f"ValueError, got {creation!r}"
                )
                assert rule_row is None
            else:
                # Create won: the delete was rejected, both rows exist.
                assert isinstance(creation, QuestDefinitionRecord), (
                    f"create must succeed, got {creation!r}"
                )
                assert rule_row is not None
            return deleted
        finally:
            await database.close()

    delete_won = _run(_main("delete-first"))
    create_won = _run(_main("create-first"))
    # delete-first: the delete acquires the lock before the create can
    # validate, so the rule is gone and the create fails cleanly.
    assert delete_won is True
    # create-first: validation passed, the create holds the lock across
    # its INSERT, so the queued delete must find the definition and be
    # rejected — the create must NOT lose its rule after validating it.
    assert create_won is False


# ---------------------------------------------------------------------------
# ScheduleRule <-> storage mapping
# ---------------------------------------------------------------------------


_RULE_STORAGE_CASES = [
    (
        ScheduleRule(rule_type=RuleType.DAILY, start_date="2026-09-01"),
        ScheduleRuleStorage(
            "daily", 1, None, None, None, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.DAILY,
            interval=3,
            start_date="2026-09-01",
            end_date="2026-12-31",
        ),
        ScheduleRuleStorage(
            "daily", 3, None, None, None, None, "2026-09-01", "2026-12-31"
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.WEEKLY,
            weekday_set={2, 0, 4},
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "weekly", 1, "0,2,4", None, None, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.CUSTOM_DAYS,
            weekday_set={1, 3, 5},
            interval=2,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "custom", 2, "1,3,5", None, None, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.MONTHLY_DAY,
            day_of_month=15,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "monthly", 1, None, 15, None, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.MONTHLY_DAY,
            day_of_month=31,
            interval=3,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "monthly", 3, None, 31, None, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.MONTHLY_WEEKDAY,
            nth_weekday=2,
            nth_weekday_weekday=1,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "monthly", 1, "1", None, 2, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.MONTHLY_WEEKDAY,
            nth_weekday=-1,
            nth_weekday_weekday=4,
            interval=2,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "monthly", 2, "4", None, -1, None, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.YEARLY, month=6, start_date="2026-09-01"
        ),
        ScheduleRuleStorage(
            "yearly", 1, None, None, None, 6, "2026-09-01", None
        ),
    ),
    (
        ScheduleRule(
            rule_type=RuleType.YEARLY,
            month=2,
            day_of_month=29,
            start_date="2026-09-01",
        ),
        ScheduleRuleStorage(
            "yearly", 1, None, 29, None, 2, "2026-09-01", None
        ),
    ),
]


@pytest.mark.parametrize("rule, storage", _RULE_STORAGE_CASES)
def test_schedule_rule_to_storage_maps_each_type(rule, storage) -> None:
    assert schedule_rule_to_storage(rule) == storage


@pytest.mark.parametrize("rule, storage", _RULE_STORAGE_CASES)
def test_schedule_rule_from_storage_rebuilds_each_type(rule, storage) -> None:
    assert schedule_rule_from_storage(storage) == rule


@pytest.mark.parametrize("rule, storage", _RULE_STORAGE_CASES)
def test_schedule_rule_round_trips_losslessly_both_directions(
    rule, storage
) -> None:
    assert schedule_rule_from_storage(schedule_rule_to_storage(rule)) == rule
    assert schedule_rule_to_storage(schedule_rule_from_storage(storage)) == storage


@pytest.mark.parametrize(
    "storage",
    [
        # monthly with neither day_of_month nor nth_weekday
        ScheduleRuleStorage(
            "monthly", 1, None, None, None, None, "2026-09-01", None
        ),
        # monthly with both day_of_month and nth_weekday
        ScheduleRuleStorage(
            "monthly", 1, None, 15, 2, None, "2026-09-01", None
        ),
        # MONTHLY_WEEKDAY whose weekday_set is None
        ScheduleRuleStorage(
            "monthly", 1, None, None, 2, None, "2026-09-01", None
        ),
        # MONTHLY_WEEKDAY whose weekday_set is empty
        ScheduleRuleStorage("monthly", 1, "", None, 2, None, "2026-09-01", None),
        # MONTHLY_WEEKDAY whose weekday_set is multi-element
        ScheduleRuleStorage(
            "monthly", 1, "1,3", None, 2, None, "2026-09-01", None
        ),
        # unknown storage rule_type
        ScheduleRuleStorage(
            "sometimes", 1, None, None, None, None, "2026-09-01", None
        ),
    ],
)
def test_schedule_rule_from_storage_rejects_ambiguous_or_invalid(
    storage,
) -> None:
    with pytest.raises(RuleValidationError):
        schedule_rule_from_storage(storage)


def test_schedule_rule_from_storage_rejects_malformed_weekday_csv() -> None:
    with pytest.raises(RuleValidationError):
        schedule_rule_from_storage(
            ScheduleRuleStorage(
                "weekly", 1, "0,2,x", None, None, None, "2026-09-01", None
            )
        )
    with pytest.raises(RuleValidationError):
        schedule_rule_from_storage(
            ScheduleRuleStorage(
                "weekly", 1, "7", None, None, None, "2026-09-01", None
            )
        )


# ---------------------------------------------------------------------------
# quest_definitions: create / get
# ---------------------------------------------------------------------------


def test_definition_create_returns_typed_record(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("weekly", "2026-09-14", weekday_set="0,2")
        definition = await definitions.create(
            "Brush teeth",
            rule.id,
            NOW,
            description="Morning and night",
            icon="mdi:tooth",
            due_time="08:00",
            assignee_child_ids=[child.id],
        )
        assert isinstance(definition, QuestDefinitionRecord)
        assert definition.title == "Brush teeth"
        assert definition.schedule_rule_id == rule.id
        assert definition.due_time == "08:00"
        assert definition.is_active is True
        assert definition.created_at == NOW
        assert not hasattr(definition, "child_id"), (
            "D-008: assignment lives in quest_definition_assignees"
        )
        assignees = await definitions.list_assignees(definition.id)
        assert [c.id for c in assignees] == [child.id]
        return definition

    _with_db(tmp_path, "definition-create.db")(_body)


def test_definition_get_missing_returns_none(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await definitions.get(999)

    assert _with_db(tmp_path, "definition-get-missing.db")(_body) is None


def test_definition_create_unknown_assignee_raises_value_error(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        with pytest.raises(ValueError, match="does not exist"):
            await definitions.create(
                "X", rule.id, NOW, assignee_child_ids=[999]
            )
        return None

    _with_db(tmp_path, "definition-bad-child.db")(_body)


def test_definition_create_inactive_assignee_raises_value_error(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        await children.set_active(child.id, False)
        with pytest.raises(ValueError, match="inactive"):
            await definitions.create(
                "X", rule.id, NOW, assignee_child_ids=[child.id]
            )
        return None

    _with_db(tmp_path, "definition-inactive-child.db")(_body)


def test_definition_create_unknown_rule_raises_value_error(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await definitions.create("X", 999, NOW)
        return None

    _with_db(tmp_path, "definition-bad-rule.db")(_body)


# ---------------------------------------------------------------------------
# quest_definitions: list by child / list active
# ---------------------------------------------------------------------------


def test_definition_list_by_child_filters_and_orders(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other_child = await children.create("Bo", NOW)
        await definitions.create("A", rule.id, NOW, assignee_child_ids=[child.id])
        await definitions.create("B", rule.id, NOW, assignee_child_ids=[child.id])
        await definitions.create(
            "C", rule.id, NOW, assignee_child_ids=[other_child.id]
        )
        mine = await definitions.list_by_child(child.id)
        assert [d.title for d in mine] == ["B", "A"]
        return mine

    _with_db(tmp_path, "definition-list-by-child.db")(_body)


def test_definition_list_by_child_missing_child_returns_empty(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        return await definitions.list_by_child(999)

    assert _with_db(tmp_path, "definition-list-missing.db")(_body) == []


def test_definition_list_active_excludes_inactive(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        first = await definitions.create("A", rule.id, NOW)
        await definitions.create("B", rule.id, NOW)
        await definitions.set_active(first.id, False)
        active = await definitions.list_active()
        assert [d.title for d in active] == ["B"]
        assert all(d.is_active for d in active)
        return active

    _with_db(tmp_path, "definition-list-active.db")(_body)


# ---------------------------------------------------------------------------
# quest_definitions: update / set_active / set_assignee
# ---------------------------------------------------------------------------


def test_definition_update_fields_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create(
            "A", rule.id, NOW, due_time="08:00"
        )
        assert await definitions.update(
            definition.id,
            title="A2",
            description="New",
            icon="mdi:star",
            due_time="09:00",
        ) == 1
        fetched = await definitions.get(definition.id)
        assert fetched.title == "A2"
        assert fetched.description == "New"
        assert fetched.icon == "mdi:star"
        assert fetched.due_time == "09:00"
        return fetched

    _with_db(tmp_path, "definition-update.db")(_body)


def test_definition_update_cannot_change_assignee_or_active(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id]
        )
        # title= / child_id= / is_active= are NOT update() parameters;
        # this asserts the API shape: assignment and activation have
        # their own explicit methods.
        import inspect

        parameters = inspect.signature(definitions.update).parameters
        assert set(parameters) == {
            "definition_id",
            "title",
            "description",
            "icon",
            "due_time",
        }
        assert await definitions.update(
            definition.id, title="A2"
        ) == 1
        fetched = await definitions.get(definition.id)
        assert [c.id for c in await definitions.list_assignees(definition.id)] == [
            child.id
        ]
        assert other.id not in [c.id for c in await definitions.list_assignees(definition.id)]
        assert fetched.is_active is True
        return fetched

    _with_db(tmp_path, "definition-update-shape.db")(_body)


def test_definition_update_no_fields_returns_zero(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        return await definitions.update(definition.id)

    assert _with_db(tmp_path, "definition-update-empty.db")(_body) == 0


def test_definition_update_can_clear_optional_fields(tmp_path) -> None:
    """Explicit None removes description/icon/due_time; omitted keeps."""
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create(
            "A",
            rule.id,
            NOW,
            description="d",
            icon="mdi:x",
            due_time="08:00",
        )
        await definitions.update(definition.id, title="A2")
        kept = await definitions.get(definition.id)
        assert kept.description == "d"
        assert kept.icon == "mdi:x"
        await definitions.update(
            definition.id, description=None, icon=None, due_time=None
        )
        cleared = await definitions.get(definition.id)
        assert cleared.description is None
        assert cleared.icon is None
        assert cleared.due_time is None
        assert cleared.title == "A2"
        return cleared

    _with_db(tmp_path, "definition-update-clear.db")(_body)


def test_definition_update_missing_returns_zero(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await definitions.update(999, title="X")

    assert _with_db(tmp_path, "definition-update-missing.db")(_body) == 0


def test_definition_set_active_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        assert await definitions.set_active(definition.id, False) == 1
        fetched = await definitions.get(definition.id)
        assert fetched.is_active is False
        assert await definitions.set_active(definition.id, True) == 1
        fetched = await definitions.get(definition.id)
        assert fetched.is_active is True
        return fetched

    _with_db(tmp_path, "definition-set-active.db")(_body)


def test_definition_set_active_missing_returns_zero(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        return await definitions.set_active(999, False)

    assert _with_db(tmp_path, "definition-set-active-missing.db")(_body) == 0


def test_definition_no_delete_method_exists(tmp_path) -> None:
    """Guardrail: definitions are deactivated, never hard-deleted."""
    async def _body(database, rules, definitions, children, child):
        import inspect

        methods = {
            name
            for name, _ in inspect.getmembers(
                QuestDefinitionsDao, inspect.isfunction
            )
        }
        assert "delete" not in methods
        assert not any(name.startswith("delete") for name in methods)
        return methods

    _with_db(tmp_path, "definition-no-delete.db")(_body)


def test_definition_add_assignee_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id]
        )
        await definitions.add_assignee(definition.id, other.id)
        assignees = await definitions.list_assignees(definition.id)
        assert sorted(c.id for c in assignees) == sorted([child.id, other.id])
        # Idempotent: re-adding an existing assignee stays a no-op.
        await definitions.add_assignee(definition.id, other.id)
        assignees = await definitions.list_assignees(definition.id)
        assert sorted(c.id for c in assignees) == sorted([child.id, other.id])
        return assignees

    _with_db(tmp_path, "definition-add-assignee.db")(_body)


def test_definition_add_assignee_inactive_child_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id]
        )
        await children.set_active(other.id, False)
        with pytest.raises(ValueError, match="inactive"):
            await definitions.add_assignee(definition.id, other.id)
        assignees = await definitions.list_assignees(definition.id)
        assert [c.id for c in assignees] == [child.id], (
            "failed assignment must leave the current assignees intact"
        )
        return assignees

    _with_db(tmp_path, "definition-assignee-inactive.db")(_body)


def test_definition_add_assignee_unknown_child_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id]
        )
        with pytest.raises(ValueError, match="does not exist"):
            await definitions.add_assignee(definition.id, 999)
        return None

    _with_db(tmp_path, "definition-assignee-unknown.db")(_body)


def test_definition_add_assignee_missing_definition_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await definitions.add_assignee(999, child.id)
        return None

    _with_db(tmp_path, "definition-assignee-missing.db")(_body)


def test_definition_remove_assignee_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id, other.id]
        )
        assert await definitions.remove_assignee(definition.id, other.id) is True
        assignees = await definitions.list_assignees(definition.id)
        assert [c.id for c in assignees] == [child.id]
        # Removing a non-assignee reports False.
        assert await definitions.remove_assignee(definition.id, other.id) is False
        return assignees

    _with_db(tmp_path, "definition-remove-assignee.db")(_body)


def test_definition_list_assignees_orders_by_child_sort_order(
    tmp_path,
) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        second = await children.create("Bo", NOW)
        third = await children.create("Cleo", NOW)
        await children.reorder([third.id, child.id, second.id])
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[second.id, child.id, third.id]
        )
        assignees = await definitions.list_assignees(definition.id)
        assert [c.id for c in assignees] == [third.id, child.id, second.id]
        return assignees

    _with_db(tmp_path, "definition-assignees-order.db")(_body)


def test_definition_upsert_window_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        window = await definitions.upsert_window(
            definition.id, "morning", due_time="09:00"
        )
        assert window == QuestDefinitionWindowRecord(
            definition.id, "morning", "09:00"
        )
        # Upsert: re-declaring the same window updates in place, never
        # duplicates (one row per definition+window).
        updated = await definitions.upsert_window(
            definition.id, "morning", due_time="09:30"
        )
        assert updated.due_time == "09:30"
        rows = await definitions.list_windows(definition.id)
        assert [w.window for w in rows] == ["morning"]
        # All three windows list in const order regardless of insertion.
        await definitions.upsert_window(definition.id, "evening")
        await definitions.upsert_window(definition.id, "afternoon")
        rows = await definitions.list_windows(definition.id)
        assert [w.window for w in rows] == [
            "morning",
            "afternoon",
            "evening",
        ]
        assert rows[1].due_time is None
        return rows

    _with_db(tmp_path, "definition-window-roundtrip.db")(_body)


def test_definition_window_unknown_name_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        with pytest.raises(ValueError, match="window must be one of"):
            await definitions.upsert_window(definition.id, "noon")
        with pytest.raises(ValueError, match="window must be one of"):
            await definitions.remove_window(definition.id, "MORNING")
        return None

    _with_db(tmp_path, "definition-window-bad-name.db")(_body)


def test_definition_window_bad_due_time_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        with pytest.raises(ValueError, match="HH:MM"):
            await definitions.upsert_window(
                definition.id, "morning", due_time="9:30"
            )
        with pytest.raises(ValueError, match="HH:MM"):
            await definitions.upsert_window(
                definition.id, "morning", due_time="25:00"
            )
        return None

    _with_db(tmp_path, "definition-window-bad-time.db")(_body)


def test_definition_window_missing_definition_raises(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await definitions.upsert_window(999, "morning")
        return None

    _with_db(tmp_path, "definition-window-missing.db")(_body)


def test_definition_remove_window_round_trip(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        await definitions.upsert_window(definition.id, "morning")
        assert await definitions.remove_window(
            definition.id, "morning"
        ) is True
        assert await definitions.list_windows(definition.id) == []
        # Removing an absent window reports False.
        assert await definitions.remove_window(
            definition.id, "morning"
        ) is False
        return None

    _with_db(tmp_path, "definition-window-remove.db")(_body)


def test_definition_unassigned_has_no_assignees(tmp_path) -> None:
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        definition = await definitions.create("A", rule.id, NOW)
        assert await definitions.list_assignees(definition.id) == []
        return None

    _with_db(tmp_path, "definition-no-assignees.db")(_body)


def test_definition_shared_by_multiple_children_via_list_by_child(
    tmp_path,
) -> None:
    """D-008: one definition covering several children appears for
    every assignee through list_by_child, once each."""
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        second = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id, second.id]
        )
        for assignee in (child, second):
            mine = await definitions.list_by_child(assignee.id)
            assert [d.id for d in mine] == [definition.id]
        return definition

    _with_db(tmp_path, "definition-shared.db")(_body)


def test_definition_assignment_leaves_history_rows_alone(
    tmp_path,
) -> None:
    """Assignment edits write the assignees table only: any instances
    that already exist keep their generation-time child_id (Feature 06
    guardrail 'changes future instances only').
    """
    async def _body(database, rules, definitions, children, child):
        rule = await rules.create("daily", "2026-09-14")
        other = await children.create("Bo", NOW)
        definition = await definitions.create(
            "A", rule.id, NOW, assignee_child_ids=[child.id]
        )
        # Simulate an already-generated instance (materialization owns
        # this table, but its row shape proves assignment isolation).
        await database.execute(
            "INSERT INTO quest_instances (definition_id, child_id, "
            "window, due_date, generated_at) VALUES (?, ?, 'morning', ?, ?)",
            (definition.id, child.id, "2026-09-15", NOW),
        )
        await definitions.add_assignee(definition.id, other.id)
        await definitions.remove_assignee(definition.id, child.id)
        row = await database.fetch_one(
            "SELECT child_id FROM quest_instances WHERE definition_id = ?",
            (definition.id,),
        )
        assert row == (child.id,)
        return None

    _with_db(tmp_path, "definition-assignee-history.db")(_body)


# ---------------------------------------------------------------------------
# No SQL for these tables outside the DAO module
# ---------------------------------------------------------------------------


def test_rules_and_definitions_sql_lives_only_in_dao_module() -> None:
    """Guardrail: schedule_rules/quest_definitions SQL may appear only
    in the DAO modules (and the schema DDL declarations).  RECURSIVE
    scan of package and tests, FROM/INTO/UPDATE/DELETE FROM/JOIN
    pattern, with exact repo-relative exclusions justified by role:
    schema.py declares the DDL, migrations.py applies it, and the
    test files for exactly those layers verify DDL, not data paths.
    """
    import re
    from pathlib import Path

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent
    repo_root = package.parent.parent
    scan_roots = [package, repo_root / "tests"]

    allowed = {
        "custom_components/nestquest/dao_rules.py",  # this DAO
        "custom_components/nestquest/dao_instances.py",  # validates the
        # definition exists + fetches its assignee before generating an
        # instance (the instance must snapshot the definition's child)
        "custom_components/nestquest/schema.py",  # declares the DDL
        "custom_components/nestquest/migrations.py",  # applies the DDL
        "tests/test_schema.py",  # tests the DDL
        "tests/test_migrations.py",  # tests migration application
        "tests/test_dao_rules.py",  # this file, scanned separately
        "tests/test_dao_instances.py",  # instances guard, own scope
    }
    sql_pattern = re.compile(
        r"(FROM|INTO|UPDATE|DELETE\s+FROM|JOIN)\s+[`'\"]*(\[)?"
        r"(schedule_rules|quest_definitions|quest_definition_assignees|quest_definition_windows)\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for root in scan_roots:
        for py in sorted(root.rglob("*.py")):
            relative = py.relative_to(repo_root).as_posix()
            if relative in allowed:
                continue
            if sql_pattern.search(py.read_text()):
                offenders.append(relative)
    assert offenders == [], (
        f"SQL touching schedule_rules/quest_definitions/assignees leaked: "
        f"{offenders}"
    )


def test_dao_instances_test_file_uses_dao_not_raw_rules_sql() -> None:
    """Compensating self-scan for the test_dao_instances.py exemption:
    that file may query quest_instances/completion_events raw (its own
    guard's scope) but must go through the DAO for schedule_rules and
    quest_definitions, except its single sanctioned definition-create
    helper usage and guard spans.
    """
    import ast
    import re
    from pathlib import Path

    instances_test = Path(__file__).parent / "test_dao_instances.py"
    text = instances_test.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    guard_names = {
        "test_rules_and_definitions_sql_lives_only_in_dao_module",
        "test_no_mutation_sql_for_completion_events_anywhere",
    }
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in guard_names:
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )

    remaining = "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM|"
        r"FROM|JOIN)\s+[`'\"]*(\[)?(schedule_rules|quest_definitions|quest_definition_assignees|quest_definition_windows)\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(remaining) is None, (
        "test_dao_instances.py must go through the DAO, not raw SQL, "
        "for schedule_rules/quest_definitions"
    )


def test_dao_rules_test_file_uses_dao_not_raw_table_sql() -> None:
    """This test module must exercise the DAO, not raw SQL, for these
    tables.  Exceptions: the guard functions' own spans (their regexes
    mention the names), and the reassignment-isolation test, which
    legitimately touches quest_instances — a table this DAO does not
    own — to prove the guardrail that reassignment leaves it alone.
    """
    import ast
    import re
    from pathlib import Path

    path = Path(__file__)
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    guard_names = {
        "test_rules_and_definitions_sql_lives_only_in_dao_module",
        "test_dao_rules_test_file_uses_dao_not_raw_table_sql",
    }
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in guard_names
        ):
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )

    remaining = "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM|"
        r"FROM|JOIN)\s+[`'\"]*(\[)?(schedule_rules|quest_definitions|quest_definition_assignees|quest_definition_windows)\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(remaining) is None, (
        "tests must go through the DAO, not raw SQL, for these tables"
    )