"""Tests for children.py: the Feature 03 child-profile business layer."""
from __future__ import annotations

import asyncio
import logging
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.nestquest.children import (
    create_child,
    edit_child,
    list_children,
    reorder_children,
    set_child_active,
)
from custom_components.nestquest.dao_children import ChildRecord, ChildrenDao
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _with_db(tmp_path, name):
    def _run_test(body):
        async def _main():
            database = NestQuestDatabase(_make_hass_mock())
            await database.open(tmp_path / name)
            try:
                await apply_migrations(database)
                return await body(database)
            finally:
                await database.close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# create_child: required, trimmed display name
# ---------------------------------------------------------------------------


def test_create_child_returns_typed_record(tmp_path) -> None:
    async def _body(database):
        child = await create_child(
            database,
            "  Declan  ",
            colour="#2E7D32",
            avatar_ref="avatars/declan.png",
            sort_order=2,
        )
        assert isinstance(child, ChildRecord)
        # The name is trimmed before storage.
        assert child.display_name == "Declan"
        assert child.colour == "#2E7D32"
        assert child.avatar_ref == "avatars/declan.png"
        assert child.sort_order == 2
        assert child.is_active is True
        # The business layer stamps created_at in strict UTC shape.
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", child.created_at
        )
        return child

    _with_db(tmp_path, "create-typed.db")(_body)


def test_create_child_defaults(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Chloe")
        assert child.display_name == "Chloe"
        assert child.colour is None
        assert child.avatar_ref is None
        assert child.sort_order == 0
        return child

    _with_db(tmp_path, "create-defaults.db")(_body)


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", None])
def test_create_child_missing_name_rejected(tmp_path, bad) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="display_name is required"):
            await create_child(database, bad)
        assert await list_children(database) == []
        return None

    _with_db(tmp_path, "create-empty-name.db")(_body)


@pytest.mark.parametrize("bad", [42, ["Ada"], 3.5])
def test_create_child_non_string_name_rejected(tmp_path, bad) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="must be a string"):
            await create_child(database, bad)
        return None

    _with_db(tmp_path, "create-bad-name-type.db")(_body)


def test_create_child_optional_text_fields_validated(tmp_path) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="colour must be a string"):
            await create_child(database, "Ada", colour=7)
        with pytest.raises(ValueError, match="avatar_ref must be a string"):
            await create_child(database, "Ada", avatar_ref=1.5)
        return None

    _with_db(tmp_path, "create-bad-optional.db")(_body)


@pytest.mark.parametrize("bad", ["2", 1.5, True, None])
def test_create_child_sort_order_must_be_int(tmp_path, bad) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="sort_order must be an integer"):
            await create_child(database, "Ada", sort_order=bad)
        return None

    _with_db(tmp_path, "create-bad-order.db")(_body)


# ---------------------------------------------------------------------------
# create_child: duplicate display name allowed but warned
# ---------------------------------------------------------------------------


def test_create_child_duplicate_name_allowed_and_warned(
    tmp_path, caplog
) -> None:
    async def _body(database):
        first = await create_child(database, "Ada")
        with caplog.at_level(
            logging.WARNING, logger="custom_components.nestquest.children"
        ):
            second = await create_child(database, "  ADA ")
        # Whitespace/case-normalised duplicate: allowed, both rows exist.
        assert first.display_name == "Ada"
        assert second.display_name == "ADA"
        names = [c.display_name for c in await list_children(database)]
        assert names == ["Ada", "ADA"]
        warnings = [
            r for r in caplog.records if "duplicates existing child" in r.getMessage()
        ]
        assert len(warnings) == 1, (
            "exactly one duplicate warning for the second create"
        )
        assert "Ada" in warnings[0].getMessage()
        return second

    _with_db(tmp_path, "create-duplicate.db")(_body)


def test_create_child_distinct_name_logs_no_warning(
    tmp_path, caplog
) -> None:
    async def _body(database):
        await create_child(database, "Ada")
        caplog.clear()
        await create_child(database, "Jordyn")
        warnings = [
            r for r in caplog.records if "duplicates existing child" in r.getMessage()
        ]
        assert warnings == []
        return None

    _with_db(tmp_path, "create-no-duplicate.db")(_body)


# ---------------------------------------------------------------------------
# edit_child: returns the updated record
# ---------------------------------------------------------------------------


def test_edit_child_updates_fields_and_returns_record(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Ada", colour="#111111")
        edited = await edit_child(
            database,
            child.id,
            display_name="  Ada L. ",
            colour="#222222",
            avatar_ref="avatars/ada.png",
            sort_order=3,
        )
        assert isinstance(edited, ChildRecord)
        assert edited.id == child.id
        assert edited.display_name == "Ada L."
        assert edited.colour == "#222222"
        assert edited.avatar_ref == "avatars/ada.png"
        assert edited.sort_order == 3
        # The stored row reflects every edit.
        stored = await list_children(database)
        assert len(stored) == 1
        assert stored[0] == edited
        return edited

    _with_db(tmp_path, "edit-round-trip.db")(_body)


def test_edit_child_omitted_fields_unchanged(tmp_path) -> None:
    async def _body(database):
        child = await create_child(
            database, "Ada", colour="#111111", sort_order=5
        )
        edited = await edit_child(database, child.id, sort_order=9)
        # Only sort_order moved; colour and name untouched.
        assert edited.sort_order == 9
        assert edited.colour == "#111111"
        assert edited.display_name == "Ada"
        return edited

    _with_db(tmp_path, "edit-partial.db")(_body)


def test_edit_child_no_fields_returns_current_record(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Ada", colour="#111111")
        edited = await edit_child(database, child.id)
        assert edited == child
        return edited

    _with_db(tmp_path, "edit-noop.db")(_body)


def test_edit_child_missing_raises(tmp_path) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="does not exist"):
            await edit_child(database, 999, display_name="X")
        return None

    _with_db(tmp_path, "edit-missing.db")(_body)


def test_edit_child_name_validation(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Ada")
        for bad in ("", "   ", None, 42):
            with pytest.raises(ValueError, match="display_name"):
                await edit_child(database, child.id, display_name=bad)
        # The failed edits left the record untouched.
        assert (await list_children(database))[0].display_name == "Ada"
        return None

    _with_db(tmp_path, "edit-name-validation.db")(_body)


def test_edit_child_sort_order_must_be_int(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Ada")
        with pytest.raises(ValueError, match="sort_order must be an integer"):
            await edit_child(database, child.id, sort_order="3")
        return None

    _with_db(tmp_path, "edit-bad-order.db")(_body)


def test_edit_child_explicit_none_clear_rejected(tmp_path) -> None:
    """Clearing is refused loudly, not silently ignored: the DAO cannot
    express NULL writes, so an explicit None must never masquerade as a
    no-op."""
    async def _body(database):
        child = await create_child(database, "Ada", colour="#111111")
        with pytest.raises(ValueError, match="clearing colour"):
            await edit_child(database, child.id, colour=None)
        with pytest.raises(ValueError, match="clearing avatar_ref"):
            await edit_child(database, child.id, avatar_ref=None)
        # The refused clears left the colour intact.
        assert (await list_children(database))[0].colour == "#111111"
        return None

    _with_db(tmp_path, "edit-clear-unsupported.db")(_body)


def test_edit_child_rename_to_duplicate_warns_but_different_name_not(
    tmp_path, caplog
) -> None:
    async def _body(database):
        ada = await create_child(database, "Ada")
        bo = await create_child(database, "Bo")
        caplog.clear()
        # Renaming Bo onto Ada's name warns (different child's name).
        edited = await edit_child(database, bo.id, display_name="ada")
        assert edited.display_name == "ada"
        warnings = [
            r for r in caplog.records if "duplicates existing child" in r.getMessage()
        ]
        assert len(warnings) == 1
        assert "Ada" in warnings[0].getMessage()
        return edited

    _with_db(tmp_path, "edit-rename-duplicate.db")(_body)


def test_edit_child_rename_to_own_name_casing_alone_warns_not(
    tmp_path, caplog
) -> None:
    """Renaming a child to their own name (casing aside) is not a
    duplicate when NO OTHER child carries the normalised name."""
    async def _body(database):
        ada = await create_child(database, "Ada")
        caplog.clear()
        edited = await edit_child(database, ada.id, display_name="ADA")
        assert edited.display_name == "ADA"
        assert not any(
            "duplicates existing child" in r.getMessage()
            for r in caplog.records
        )
        return edited

    _with_db(tmp_path, "edit-rename-self.db")(_body)


def test_create_child_concurrent_same_name_still_warns(tmp_path) -> None:
    """Racing creates of the same normalised name cannot slip through
    unlogged: the scan and INSERT are serialized on the connection
    lock, so the second create sees the first's committed row and
    warns.  Deterministic gate on task A's INSERT while task B queues
    behind the lock.  Without the lock, B's scan would run before A's
    INSERT commits and no warning would fire."""
    async def _main():
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()
        hass = _gated_hass(armed, gate_open, a_started)
        database = NestQuestDatabase(hass)
        await database.open(tmp_path / "create-race.db")
        try:
            await apply_migrations(database)
            logger = logging.getLogger(
                "custom_components.nestquest.children"
            )
            seen: list[logging.LogRecord] = []

            class _Capture(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    seen.append(record)

            handler = _Capture()
            logger.addHandler(handler)
            try:
                armed["active"] = True
                task_a = asyncio.ensure_future(
                    create_child(database, "Ada")
                )
                await a_started.wait()
                armed["active"] = False
                task_b = asyncio.ensure_future(
                    create_child(database, " ada ")
                )
                await asyncio.sleep(0)
                gate_open.set()
                first, second = await asyncio.gather(task_a, task_b)
            finally:
                logger.removeHandler(handler)

            # Both creates land; the duplicate is allowed.
            assert first.display_name == "Ada"
            assert second.display_name == "ada"
            names = [c.display_name for c in await list_children(database)]
            assert names == ["Ada", "ada"]
            # Exactly one warning: B's scan saw A's committed row.
            warnings = [
                r for r in seen if "duplicates existing child" in r.getMessage()
            ]
            assert len(warnings) == 1, (
                "the queued duplicate create must warn exactly once"
            )
            assert "Ada" in warnings[0].getMessage()
        finally:
            await database.close()

    _run(_main())


def test_edit_child_case_only_edit_colliding_with_other_child_warns(
    tmp_path, caplog
) -> None:
    """A case-only edit must not hide a real duplicate: with two Ada
    profiles already present, editing either one's name to another
    casing still warns (the scan excludes only the edited child)."""
    async def _body(database):
        first = await create_child(database, "Ada")
        await create_child(database, "ada")
        caplog.clear()
        edited = await edit_child(database, first.id, display_name="ADA")
        assert edited.display_name == "ADA"
        warnings = [
            r for r in caplog.records if "duplicates existing child" in r.getMessage()
        ]
        assert len(warnings) == 1
        # Editing the name to a value that STAYS duplicated (no change,
        # other child still carries it) warns too: the scan is on the
        # resulting state, not on whether the word moved.
        caplog.clear()
        await edit_child(database, first.id, display_name=" ada ")
        warnings = [
            r for r in caplog.records if "duplicates existing child" in r.getMessage()
        ]
        assert len(warnings) == 1
        return None

    _with_db(tmp_path, "edit-case-only-duplicate.db")(_body)


# ---------------------------------------------------------------------------
# set_child_active / list_children
# ---------------------------------------------------------------------------


def test_set_child_active_round_trip(tmp_path) -> None:
    async def _body(database):
        child = await create_child(database, "Ada")
        deactivated = await set_child_active(database, child.id, False)
        assert deactivated.is_active is False
        assert [c.id for c in await list_children(database)] == [child.id]
        assert await list_children(database, active_only=True) == []
        reactivated = await set_child_active(database, child.id, True)
        assert reactivated.is_active is True
        assert len(await list_children(database, active_only=True)) == 1
        return reactivated

    _with_db(tmp_path, "set-active.db")(_body)


def test_set_child_active_missing_raises(tmp_path) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="does not exist"):
            await set_child_active(database, 999, False)
        return None

    _with_db(tmp_path, "set-active-missing.db")(_body)


# ---------------------------------------------------------------------------
# reorder_children: complete permutation or nothing changes
# ---------------------------------------------------------------------------


def test_reorder_children_persists_display_order(tmp_path) -> None:
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        second = await create_child(database, "Bo", sort_order=1)
        third = await create_child(database, "Cleo", sort_order=2)
        await reorder_children(database, [third.id, first.id, second.id])
        # The active list returns children in the new sort order.
        listed = await list_children(database, active_only=True)
        assert [c.id for c in listed] == [third.id, first.id, second.id]
        assert [c.sort_order for c in listed] == [0, 1, 2]
        return listed

    _with_db(tmp_path, "reorder-round-trip.db")(_body)


def test_reorder_children_partial_list_rejected_order_unchanged(
    tmp_path,
) -> None:
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        second = await create_child(database, "Bo", sort_order=1)
        third = await create_child(database, "Cleo", sort_order=2)
        with pytest.raises(ValueError, match="missing child ids"):
            await reorder_children(database, [third.id, first.id])
        listed = await list_children(database)
        # Nothing changed: rejection happens before any write.
        assert [c.id for c in listed] == [first.id, second.id, third.id]
        assert [c.sort_order for c in listed] == [0, 1, 2]
        return listed

    _with_db(tmp_path, "reorder-partial.db")(_body)


def test_reorder_children_unknown_id_rejected_order_unchanged(
    tmp_path,
) -> None:
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        second = await create_child(database, "Bo", sort_order=1)
        with pytest.raises(ValueError, match="unknown child ids"):
            await reorder_children(database, [second.id, first.id, 999])
        listed = await list_children(database)
        assert [c.id for c in listed] == [first.id, second.id]
        assert [c.sort_order for c in listed] == [0, 1]
        return listed

    _with_db(tmp_path, "reorder-unknown.db")(_body)


def test_reorder_children_empty_list_rejected_when_children_exist(
    tmp_path,
) -> None:
    """An empty list is the maximally partial reorder: rejected while
    any child exists (against an empty table it is a complete
    permutation and stays a harmless no-op)."""
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        with pytest.raises(ValueError, match="missing child ids"):
            await reorder_children(database, [])
        assert [c.sort_order for c in await list_children(database)] == [0]
        return None

    _with_db(tmp_path, "reorder-empty.db")(_body)


def test_reorder_children_duplicate_and_non_int_rejected(tmp_path) -> None:
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        second = await create_child(database, "Bo", sort_order=1)
        with pytest.raises(ValueError, match="duplicate child ids"):
            await reorder_children(database, [first.id, first.id, second.id])
        with pytest.raises(ValueError, match="only integer child ids"):
            await reorder_children(database, [first.id, second.id, True])
        with pytest.raises(ValueError, match="only integer child ids"):
            await reorder_children(database, [first.id, second.id, "3"])
        listed = await list_children(database)
        assert [c.sort_order for c in listed] == [0, 1]
        return listed

    _with_db(tmp_path, "reorder-bad-inputs.db")(_body)


def test_reorder_children_inactive_children_included(tmp_path) -> None:
    """Inactive children keep their display position: the permutation
    covers the whole table, not just the active list."""
    async def _body(database):
        first = await create_child(database, "Ada", sort_order=0)
        second = await create_child(database, "Bo", sort_order=1)
        await set_child_active(database, second.id, False)
        # Both ids are required even though one is inactive.
        await reorder_children(database, [second.id, first.id])
        listed = await list_children(database)
        assert [c.id for c in listed] == [second.id, first.id]
        assert [c.sort_order for c in listed] == [0, 1]
        # The active list skips the inactive child but keeps position.
        assert [c.id for c in await list_children(database, active_only=True)] == [
            first.id
        ]
        return listed

    _with_db(tmp_path, "reorder-inactive.db")(_body)


@pytest.mark.parametrize("bad", ["1", "0", 1, 0, 1.0, None, "true"])
def test_set_child_active_rejects_non_bool(tmp_path, bad) -> None:
    """The DAO's int() would silently coerce "1"/0/1.0 into a state the
    caller never asked for; the business layer refuses non-bools."""
    async def _body(database):
        child = await create_child(database, "Ada")
        with pytest.raises(ValueError, match="is_active must be a real bool"):
            await set_child_active(database, child.id, bad)
        # The refused transition left the child untouched.
        assert (await list_children(database))[0].is_active is True
        return None

    _with_db(tmp_path, "set-active-non-bool.db")(_body)


# ---------------------------------------------------------------------------
# Concurrency: edit/set_active are atomic under the connection lock
# ---------------------------------------------------------------------------


def _gated_hass(armed: dict, gate_open: asyncio.Event, a_started: asyncio.Event):
    """A hass mock whose executor gates the FIRST `_execute` job after
    arming — the mutate statement of whichever business call starts
    first — proving the caller holds the connection lock at that
    moment and the second caller must queue behind it."""
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


def test_edit_child_concurrent_opposite_edits_return_own_values(
    tmp_path,
) -> None:
    """Two racing edits cannot cross-contaminate each other's readback.

    Deterministic gate: task A is paused at its UPDATE (it provably
    holds the connection lock), task B is then created and must queue;
    A's readback runs before B's edit, so A returns A's value and B
    returns B's.  Without the lock, A's readback would see B's write.
    """
    async def _main():
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()
        hass = _gated_hass(armed, gate_open, a_started)
        database = NestQuestDatabase(hass)
        await database.open(tmp_path / "edit-race.db")
        try:
            await apply_migrations(database)
            child = await create_child(
                database, "Ada", colour="#111111", sort_order=0
            )

            armed["active"] = True
            task_a = asyncio.ensure_future(
                edit_child(database, child.id, colour="#AAAAAA", sort_order=1)
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                edit_child(
                    database, child.id, colour="#BBBBBB", sort_order=2
                )
            )
            await asyncio.sleep(0)
            gate_open.set()
            record_a, record_b = await asyncio.gather(task_a, task_b)

            # Each caller gets back exactly what it wrote.
            assert record_a.colour == "#AAAAAA"
            assert record_a.sort_order == 1
            assert record_b.colour == "#BBBBBB"
            assert record_b.sort_order == 2
            # B landed last: the stored row is B's (read via the DAO —
            # the children leak guard forbids raw probes here).
            stored = await ChildrenDao(database).get(child.id)
            assert stored is not None
            assert (stored.colour, stored.sort_order) == ("#BBBBBB", 2)
        finally:
            await database.close()

    _run(_main())


def test_set_child_active_concurrent_opposite_transitions_return_own(
    tmp_path,
) -> None:
    """Racing activate/deactivate calls each report their own request.

    Same deterministic gate on task A's UPDATE; task B queues behind
    the connection lock and lands the opposite transition after A.
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
            child = await create_child(database, "Ada")

            armed["active"] = True
            task_a = asyncio.ensure_future(
                set_child_active(database, child.id, False)
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                set_child_active(database, child.id, True)
            )
            await asyncio.sleep(0)
            gate_open.set()
            record_a, record_b = await asyncio.gather(task_a, task_b)

            assert record_a.is_active is False
            assert record_b.is_active is True
            stored = await ChildrenDao(database).get(child.id)
            assert stored is not None
            assert stored.is_active is True
        finally:
            await database.close()

    _run(_main())


def test_list_children_orders_by_sort_order_then_id(tmp_path) -> None:
    async def _body(database):
        second = await create_child(database, "Bo", sort_order=1)
        first = await create_child(database, "Ada", sort_order=0)
        third = await create_child(database, "Cleo", sort_order=1)
        listed = await list_children(database)
        # sort_order 0 first, then the two sort_order-1 rows by id.
        assert [c.id for c in listed] == [first.id, second.id, third.id]
        return listed

    _with_db(tmp_path, "list-order.db")(_body)


# ---------------------------------------------------------------------------
# Deactivation keeps every referencing row intact (Feature 03)
# ---------------------------------------------------------------------------


def test_deactivating_child_preserves_definitions_instances_events(
    tmp_path,
) -> None:
    async def _body(database):
        from datetime import date, timedelta

        from custom_components.nestquest.dao_children import ChildrenDao
        from custom_components.nestquest.dao_instances import (
            CompletionEventsDao,
            QuestInstancesDao,
        )
        from custom_components.nestquest.dao_rules import (
            QuestDefinitionsDao,
            ScheduleRulesDao,
        )

        children = ChildrenDao(database)
        rules = ScheduleRulesDao(database)
        definitions = QuestDefinitionsDao(database)
        instances = QuestInstancesDao(database)
        events = CompletionEventsDao(database)

        child = await create_child(database, "Ada")
        rule = await rules.create("daily", "2026-01-01")
        definition = await definitions.create(
            "Brush teeth",
            rule.id,
            "2026-09-15T12:00:00+00:00",
            assignee_child_ids=[child.id],
        )
        due = (date.today() + timedelta(days=1)).isoformat()
        stamp = f"{due}T08:00:00+00:00"
        instance = await instances.upsert(
            definition.id, child.id, due, stamp, window="morning"
        )
        event = await events.append(
            instance.id,
            child.id,
            "completed",
            "panel",
            f"{due}T09:00:00+00:00",
            True,
            actor_child_id=child.id,
        )

        # Deactivate: the referencing rows must not move.
        deactivated = await set_child_active(database, child.id, False)
        assert deactivated.is_active is False
        assert await children.get(child.id) == deactivated
        assert (await definitions.get(definition.id)) == definition
        assert (await instances.get_by_id(instance.id)) == instance
        assert await events.list_by_instance(instance.id) == [event]
        # Excluded from the active list, still present in the full list.
        assert await list_children(database, active_only=True) == []
        assert [c.id for c in await list_children(database)] == [child.id]

        # Reactivate: fully restored.
        reactivated = await set_child_active(database, child.id, True)
        assert reactivated.is_active is True
        assert [c.id for c in await list_children(database, active_only=True)] == [
            child.id
        ]
        assert (await instances.get_by_id(instance.id)) == instance
        return reactivated

    _with_db(tmp_path, "deactivate-data-intact.db")(_body)


def test_no_code_path_deletes_a_child_row() -> None:
    """Structural guardrail: children are deactivated, never deleted.

    The DAO exposes no delete method at all, and no module in the
    package (nor any test outside the sanctioned DDL/migration layers,
    which create the tables) carries a statement that removes child
    rows — the leak guard in test_dao_children enforces the file
    allowlist, this asserts the no-delete property itself across every
    file that may legitimately name the table.
    """
    import re
    from pathlib import Path

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent

    delete_pattern = re.compile(
        r"DELETE\s+(FROM\s+)?((main|temp)\s*\.\s*)?[`'\"]*(\[)?children\b",
        re.IGNORECASE,
    )
    for py in sorted(package.rglob("*.py")):
        assert delete_pattern.search(py.read_text()) is None, (
            f"a code path in {py.name} deletes child rows"
        )

    import inspect

    from custom_components.nestquest.dao_children import ChildrenDao

    methods = {
        name
        for name, _ in inspect.getmembers(ChildrenDao, inspect.isfunction)
    }
    assert not any(
        name.startswith("delete") or name == "remove" for name in methods
    ), f"ChildrenDao exposed a delete-shaped method: {methods}"
