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
    set_child_active,
)
from custom_components.nestquest.dao_children import ChildRecord
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
        assert any(
            "duplicates existing child" in r.getMessage()
            for r in caplog.records
        )
        caplog.clear()
        # Renaming a child to their own name (casing aside) is not a
        # duplicate: no warning.
        await edit_child(database, ada.id, display_name="ADA")
        assert not any(
            "duplicates existing child" in r.getMessage()
            for r in caplog.records
        )
        return None

    _with_db(tmp_path, "edit-rename-duplicate.db")(_body)


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
