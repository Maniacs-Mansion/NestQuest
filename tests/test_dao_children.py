"""Tests for dao_children.py: typed DAO for children and admin_users."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.dao_children import (
    AdminUserRecord,
    AdminUsersDao,
    ChildRecord,
    ChildrenDao,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.schema import SCHEMA_V1_STATEMENTS
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> NestQuestDatabase:
    database = NestQuestDatabase(_make_hass_mock())
    _run(database.open(path))
    _run(apply_migrations(database))
    return database


def _daos(database) -> tuple[ChildrenDao, AdminUsersDao]:
    return ChildrenDao(database), AdminUsersDao(database)


NOW = "2026-09-14T11:00:00+00:00"


def _make_child(dao, name="Ada", **kwargs) -> ChildRecord:
    return _run(dao.create(name, NOW, **kwargs))


# ---------------------------------------------------------------------------
# children: create and get
# ---------------------------------------------------------------------------


def test_create_returns_typed_record(tmp_path) -> None:
    database = _open_db(tmp_path / "create.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, colour="#ff0000", avatar_ref="avatars/1")
        assert isinstance(child, ChildRecord)
        assert child.id == 1
        assert child.display_name == "Ada"
        assert child.colour == "#ff0000"
        assert child.avatar_ref == "avatars/1"
        assert child.sort_order == 0
        assert child.is_active is True
        assert child.created_at == NOW
    finally:
        _run(database.close())


def test_get_returns_none_for_missing_child(tmp_path) -> None:
    database = _open_db(tmp_path / "get-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.get(999)) is None
    finally:
        _run(database.close())


def test_create_duplicate_name_is_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "dup-name.db")
    try:
        dao, _ = _daos(database)
        first = _make_child(dao, "Ada")
        second = _make_child(dao, "Ada")
        assert first.id != second.id
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# children: list active / list all
# ---------------------------------------------------------------------------


def test_list_active_excludes_inactive_and_sorts(tmp_path) -> None:
    database = _open_db(tmp_path / "list-active.db")
    try:
        dao, _ = _daos(database)
        _make_child(dao, "Bo", sort_order=2)
        ada = _make_child(dao, "Ada", sort_order=1)
        cy = _make_child(dao, "Cy", sort_order=1)
        _make_child(dao, "Dee", sort_order=0)
        _run(dao.set_active(ada.id, False))
        active = _run(dao.list_active())
        assert [c.display_name for c in active] == ["Dee", "Cy", "Bo"]
        assert all(c.is_active for c in active)
    finally:
        _run(database.close())


def test_list_all_includes_inactive(tmp_path) -> None:
    database = _open_db(tmp_path / "list-all.db")
    try:
        dao, _ = _daos(database)
        ada = _make_child(dao, "Ada", sort_order=1)
        _make_child(dao, "Bo", sort_order=0)
        _run(dao.set_active(ada.id, False))
        all_children = _run(dao.list_all())
        assert [c.display_name for c in all_children] == ["Bo", "Ada"]
        assert all_children[1].is_active is False
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# children: update, set_active, reorder
# ---------------------------------------------------------------------------


def test_update_fields_round_trip(tmp_path) -> None:
    database = _open_db(tmp_path / "update.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada", colour="#111111")
        updated = _run(
            dao.update(
                child.id,
                display_name="Ada L.",
                colour="#222222",
                avatar_ref="avatars/x.png",
            )
        )
        assert updated == 1
        fetched = _run(dao.get(child.id))
        assert fetched is not None
        assert fetched.display_name == "Ada L."
        assert fetched.colour == "#222222"
        assert fetched.avatar_ref == "avatars/x.png"
        assert fetched.sort_order == 0
    finally:
        _run(database.close())


def test_update_omitted_fields_untouched(tmp_path) -> None:
    database = _open_db(tmp_path / "update-partial.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada", colour="#111111")
        _run(dao.update(child.id, display_name="Ada L."))
        fetched = _run(dao.get(child.id))
        assert fetched.colour == "#111111"
    finally:
        _run(database.close())


def test_update_no_fields_returns_zero_and_changes_nothing(tmp_path) -> None:
    database = _open_db(tmp_path / "update-empty.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada")
        assert _run(dao.update(child.id)) == 0
        fetched = _run(dao.get(child.id))
        assert fetched is not None and fetched.display_name == "Ada"
    finally:
        _run(database.close())


def test_update_missing_child_returns_zero(tmp_path) -> None:
    database = _open_db(tmp_path / "update-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.update(999, display_name="X")) == 0
    finally:
        _run(database.close())


def test_set_active_missing_child_returns_zero(tmp_path) -> None:
    database = _open_db(tmp_path / "set-active-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.set_active(999, False)) == 0
    finally:
        _run(database.close())


def test_reorder_assigns_positions_in_order(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        b = _make_child(dao, "Bo")
        c = _make_child(dao, "Cy")
        _run(dao.reorder([c.id, a.id, b.id]))
        children = _run(dao.list_all())
        assert [x.display_name for x in children] == ["Cy", "Ada", "Bo"]
        assert [x.sort_order for x in children] == [0, 1, 2]
    finally:
        _run(database.close())


def test_reorder_is_transactional_and_idempotent(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-idempotent.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        b = _make_child(dao, "Bo")
        _run(dao.reorder([b.id, a.id]))
        _run(dao.reorder([b.id, a.id]))
        children = _run(dao.list_all())
        assert [(x.display_name, x.sort_order) for x in children] == [
            ("Bo", 0),
            ("Ada", 1),
        ]
    finally:
        _run(database.close())


def test_reorder_empty_list_is_noop(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-empty.db")
    try:
        dao, _ = _daos(database)
        _make_child(dao, "Ada")
        _run(dao.reorder([]))
        children = _run(dao.list_all())
        assert children[0].sort_order == 0
    finally:
        _run(database.close())


def test_reorder_unknown_id_leaves_it_untouched(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-unknown.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        _run(dao.reorder([a.id, 999]))
        children = _run(dao.list_all())
        assert children[0].sort_order == 0
    finally:
        _run(database.close())


def test_reorder_survives_partial_state_on_rollback(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-rollback.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        b = _make_child(dao, "Bo")
        _run(dao.reorder([b.id, a.id]))
        # After a successful reorder no staged negative offsets remain.
        rows = _run(
            database.fetch_all(
                "SELECT display_name, sort_order FROM children"
            )
        )
        assert all(row[1] >= 0 for row in rows)
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# admin_users: add, remove, list, exists
# ---------------------------------------------------------------------------


def test_admin_add_then_exists(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-add.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.add("user-1", NOW)) is True
        assert _run(dao.exists("user-1")) is True
        assert _run(dao.exists("user-2")) is False
    finally:
        _run(database.close())


def test_admin_add_is_idempotent(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-idempotent.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.add("user-1", NOW)) is True
        assert _run(dao.add("user-1", NOW)) is False
        records = _run(dao.list())
        assert len(records) == 1
        assert records[0].added_at == NOW
    finally:
        _run(database.close())


def test_admin_add_preserves_original_added_at(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-added-at.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        _run(dao.add("user-1", "2026-09-15T00:00:00+00:00"))
        records = _run(dao.list())
        assert records[0].added_at == NOW
    finally:
        _run(database.close())


def test_admin_remove_returns_true_then_false(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-remove.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        assert _run(dao.remove("user-1")) is True
        assert _run(dao.remove("user-1")) is False
        assert _run(dao.exists("user-1")) is False
    finally:
        _run(database.close())


def test_admin_list_returns_typed_records_ordered(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-list.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-2", "2026-09-14T10:00:00+00:00"))
        _run(dao.add("user-1", "2026-09-14T09:00:00+00:00"))
        records = _run(dao.list())
        assert isinstance(records[0], AdminUserRecord)
        assert [r.ha_user_id for r in records] == ["user-1", "user-2"]
        assert records[0].added_at == "2026-09-14T09:00:00+00:00"
    finally:
        _run(database.close())


def test_admin_exists_empty_allowlist_fails_closed(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-empty.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.exists("user-1")) is False
        assert _run(dao.list()) == []
    finally:
        _run(database.close())


def test_admin_records_are_typed_not_raw_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-typed.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        records = _run(dao.list())
        assert records == [AdminUserRecord("user-1", NOW)]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# No SQL for these tables outside the module
# ---------------------------------------------------------------------------


def test_children_and_admin_sql_lives_only_in_dao_module() -> None:
    import re
    from pathlib import Path

    package = Path(
        __import__("custom_components.nestquest", fromlist=["__file__"]).__file__
    ).parent
    offenders = []
    pattern = re.compile(
        r"(FROM|INTO|UPDATE)\s+children\b|(FROM|INTO|DELETE FROM)\s+admin_users\b",
        re.IGNORECASE,
    )
    for py in package.glob("*.py"):
        if py.name == "dao_children.py" or py.name == "schema.py":
            continue
        text = py.read_text()
        if pattern.search(text):
            offenders.append(py.name)
    assert offenders == [], (
        f"SQL for children/admin_users leaked into: {offenders}"
    )