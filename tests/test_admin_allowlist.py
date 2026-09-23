"""Tests for the Feature 03 admin allowlist business layer (core.admin_allowlist)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.nestquest.core.admin_allowlist import (
    list_admin_ids,
    seed_setup_admin,
    set_admin_ids,
)
from custom_components.nestquest.core.db import NestQuestDatabase
from custom_components.nestquest.core.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _with_db(tmp_path, name):
    def _run_test(body):
        async def _main():
            database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
            await database.open(tmp_path / name)
            try:
                await apply_migrations(database)
                return await body(database)
            finally:
                await database.close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# set_admin_ids: read/write with the fail-closed guarantee
# ---------------------------------------------------------------------------


def test_set_admin_ids_round_trip(tmp_path) -> None:
    async def _body(database):
        await set_admin_ids(database, ["user-owner", "user-parent"])
        # Membership is the contract; AdminUsersDao.list orders by id.
        assert sorted(await list_admin_ids(database)) == [
            "user-owner",
            "user-parent",
        ]
        # Replace: the removed id is gone, the new one present.
        await set_admin_ids(database, ["user-parent", "user-grandma"])
        assert sorted(await list_admin_ids(database)) == [
            "user-grandma",
            "user-parent",
        ]
        return await list_admin_ids(database)

    _with_db(tmp_path, "set-round-trip.db")(_body)


def test_set_admin_ids_rejects_empty_allowlist(tmp_path) -> None:
    """Removing the last admin (or saving an empty selection) is
    refused with a clear error: an empty allowlist fails closed, so
    the owner must never be able to reach one through this API."""
    async def _body(database):
        await set_admin_ids(database, ["user-owner"])
        with pytest.raises(ValueError, match="at least one admin"):
            await set_admin_ids(database, [])
        # The refused write left the allowlist intact.
        assert await list_admin_ids(database) == ["user-owner"]
        return None

    _with_db(tmp_path, "set-empty-refused.db")(_body)


@pytest.mark.parametrize(
    "bad", [None, "notalist", [42], [None], [""], ["  "], 5]
)
def test_set_admin_ids_rejects_malformed_input(tmp_path, bad) -> None:
    async def _body(database):
        with pytest.raises(ValueError):
            await set_admin_ids(database, bad)
        assert await list_admin_ids(database) == []
        return None

    _with_db(tmp_path, "set-malformed.db")(_body)


def test_set_admin_ids_rejects_duplicates(tmp_path) -> None:
    async def _body(database):
        with pytest.raises(ValueError, match="duplicates"):
            await set_admin_ids(database, ["user-a", "user-a"])
        assert await list_admin_ids(database) == []
        return None

    _with_db(tmp_path, "set-duplicates.db")(_body)


def test_set_admin_ids_trims_and_replaces_atomically(tmp_path) -> None:
    async def _body(database):
        await set_admin_ids(database, ["  user-a  "])
        assert await list_admin_ids(database) == ["user-a"]
        # Sync that both adds and removes in one write.
        await set_admin_ids(database, ["user-b", "user-c"])
        assert await list_admin_ids(database) == ["user-b", "user-c"]
        return None

    _with_db(tmp_path, "set-trim.db")(_body)


# ---------------------------------------------------------------------------
# seed_setup_admin: the owner is never locked out on first setup
# ---------------------------------------------------------------------------


def test_seed_adds_context_user_on_first_setup(tmp_path) -> None:
    async def _body(database):
        seeded = await seed_setup_admin(
            database, stored_admin_ids=None, context_user_id="owner-1"
        )
        assert seeded == ["owner-1"]
        assert await list_admin_ids(database) == ["owner-1"]
        return seeded

    _with_db(tmp_path, "seed-context.db")(_body)


def test_seed_prefers_stored_entry_ids_over_context(tmp_path) -> None:
    async def _body(database):
        seeded = await seed_setup_admin(
            database,
            stored_admin_ids=["user-a", "user-b"],
            context_user_id="owner-1",
        )
        assert seeded == ["user-a", "user-b"]
        return seeded

    _with_db(tmp_path, "seed-stored.db")(_body)


def test_seed_leaves_nonempty_allowlist_untouched(tmp_path) -> None:
    """Re-running setup must never resurrect a deliberately narrowed
    list: only an EMPTY allowlist is seeded."""
    async def _body(database):
        await set_admin_ids(database, ["user-kept"])
        seeded = await seed_setup_admin(
            database,
            stored_admin_ids=["user-a", "user-b"],
            context_user_id="owner-1",
        )
        assert seeded == ["user-kept"]
        assert await list_admin_ids(database) == ["user-kept"]
        return seeded

    _with_db(tmp_path, "seed-narrowed.db")(_body)


def test_seed_with_nothing_available_leaves_empty(tmp_path) -> None:
    async def _body(database):
        seeded = await seed_setup_admin(
            database, stored_admin_ids=None, context_user_id=None
        )
        assert seeded == []
        return seeded

    _with_db(tmp_path, "seed-nothing.db")(_body)


def test_seed_rejects_malformed_candidates(tmp_path) -> None:
    async def _body(database):
        with pytest.raises(ValueError):
            await seed_setup_admin(
                database, stored_admin_ids=[42], context_user_id=None
            )
        with pytest.raises(ValueError):
            await seed_setup_admin(
                database, stored_admin_ids=None, context_user_id="  "
            )
        assert await list_admin_ids(database) == []
        return None

    _with_db(tmp_path, "seed-malformed.db")(_body)


# ---------------------------------------------------------------------------
def test_seed_owner_ids_argument(tmp_path) -> None:
    async def _body(database):
        # Malformed owner lists are rejected like any other candidate —
        # while the allowlist is still empty, so the seed proceeds far
        # enough to validate.
        with pytest.raises(ValueError):
            await seed_setup_admin(
                database,
                stored_admin_ids=None,
                context_user_id=None,
                owner_ids=[7],
            )
        assert await list_admin_ids(database) == []
        seeded = await seed_setup_admin(
            database,
            stored_admin_ids=None,
            context_user_id=None,
            owner_ids=["owner-1"],
        )
        assert seeded == ["owner-1"]
        return seeded

    _with_db(tmp_path, "seed-owner-arg.db")(_body)


# is_admin: the fail-closed resolver (Feature 09's verdict function)
# ---------------------------------------------------------------------------


def test_is_admin_verdict_matrix(tmp_path) -> None:
    async def _body(database):
        from custom_components.nestquest.core.admin_allowlist import is_admin

        await set_admin_ids(database, ["user-owner"])
        assert await is_admin(database, "user-owner") is True
        assert await is_admin(database, "user-other") is False
        # Unknown, malformed, and absent identities all fail closed.
        assert await is_admin(database, "") is False
        assert await is_admin(database, "  user-owner  ") is False, (
            "ids are stored trimmed; an untrimmed lookup is a different "
            "id and must not match"
        )
        assert await is_admin(database, None) is False
        assert await is_admin(database, 42) is False
        assert await is_admin(database, ["user-owner"]) is False
        assert await is_admin(database, True) is False
        return None

    _with_db(tmp_path, "resolver-matrix.db")(_body)


def test_is_admin_empty_allowlist_fails_closed(tmp_path) -> None:
    """An empty allowlist returns False for EVERYONE, not True."""
    async def _body(database):
        from custom_components.nestquest.core.admin_allowlist import is_admin

        for candidate in ("user-owner", "", None, 1):
            assert await is_admin(database, candidate) is False
        return None

    _with_db(tmp_path, "resolver-empty.db")(_body)


def test_is_admin_false_after_last_admin_removal_attempt(tmp_path) -> None:
    """The refusal keeps the verdict sound: a refused removal leaves
    the admin in place, so is_admin still resolves True."""
    async def _body(database):
        from custom_components.nestquest.core.admin_allowlist import is_admin

        await set_admin_ids(database, ["user-owner"])
        with pytest.raises(ValueError, match="at least one admin"):
            await set_admin_ids(database, [])
        assert await is_admin(database, "user-owner") is True
        return None

    _with_db(tmp_path, "resolver-refusal.db")(_body)
