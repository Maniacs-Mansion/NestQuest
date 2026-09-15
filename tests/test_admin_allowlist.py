"""Tests for admin_allowlist.py: the Feature 03 allowlist business layer."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.admin_allowlist import (
    list_admin_ids,
    seed_setup_admin,
    set_admin_ids,
)
from custom_components.nestquest.dao_children import AdminUsersDao
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
# Setup wiring: async_setup_entry seeds automatically
# ---------------------------------------------------------------------------


async def _setup_entry(hass, entry, registry):
    from tests.test_lifecycle import _wire

    entry = _wire(entry, registry)
    await async_setup_entry(hass, entry)
    return entry


async def test_setup_seeds_allowlist_from_entry_context(
    hass, make_entry
) -> None:
    entry = await _setup_entry(
        hass,
        make_entry(context={"user_id": "ha-owner"}),
        hass.registry,
    )
    database = entry.runtime_data.database
    try:
        assert await list_admin_ids(database) == ["ha-owner"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_seeds_allowlist_from_stored_entry_data(
    hass, make_entry
) -> None:
    """A lost database re-seeded from the entry's stored admin copy."""
    from custom_components.nestquest.const import CONF_ADMIN_USER_IDS

    entry = await _setup_entry(
        hass,
        make_entry(data={CONF_ADMIN_USER_IDS: ["user-a", "user-b"]}),
        hass.registry,
    )
    database = entry.runtime_data.database
    try:
        assert await list_admin_ids(database) == ["user-a", "user-b"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_without_context_leaves_allowlist_empty(
    hass, make_entry
) -> None:
    """Fail closed: no context user and no stored copy means an empty
    allowlist — nobody is admin until the owner configures it."""
    entry = await _setup_entry(hass, make_entry(), hass.registry)
    database = entry.runtime_data.database
    try:
        assert await list_admin_ids(database) == []
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_does_not_reseed_narrowed_allowlist(
    hass, make_entry
) -> None:
    from custom_components.nestquest import async_unload_entry
    from custom_components.nestquest.const import CONF_ADMIN_USER_IDS

    entry = await _setup_entry(
        hass, make_entry(context={"user_id": "ha-owner"}), hass.registry
    )
    database = entry.runtime_data.database
    await set_admin_ids(database, ["user-parent"])
    await database.close()
    assert await async_unload_entry(hass, entry) is True

    # Reload with the SAME context: the narrowed list survives.
    entry_reloaded = await _setup_entry(
        hass, make_entry(context={"user_id": "ha-owner"}), hass.registry
    )
    database_b = entry_reloaded.runtime_data.database
    try:
        assert await list_admin_ids(database_b) == ["user-parent"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry_reloaded) is True


async def test_setup_seed_prefers_options_over_entry_data(
    hass, make_entry
) -> None:
    """Seed precedence on a fresh database: the options flow's saved
    list (the current one) beats the config flow's original copy."""
    from custom_components.nestquest.const import CONF_ADMIN_USER_IDS

    entry = await _setup_entry(
        hass,
        make_entry(
            options={CONF_ADMIN_USER_IDS: ["user-current"]},
            data={CONF_ADMIN_USER_IDS: ["ha-owner"]},
            context={"user_id": "ha-owner"},
        ),
        hass.registry,
    )
    database = entry.runtime_data.database
    try:
        assert await list_admin_ids(database) == ["user-current"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_owner_fallback_seeds_owner_accounts(
    hass, make_entry
) -> None:
    """Last-resort seed: with no persisted copy and no flow-context
    user, HA owner accounts are seeded so first setup is never
    ownerless (the real flow may lose the context; owners can already
    do everything in HA)."""
    from unittest.mock import AsyncMock

    hass.auth.async_get_users = AsyncMock(
        return_value=[
            SimpleNamespace(id="owner-1", is_owner=True),
            SimpleNamespace(id="member-1", is_owner=False),
            SimpleNamespace(id="owner-2", is_owner=True),
        ]
    )
    entry = await _setup_entry(hass, make_entry(), hass.registry)
    database = entry.runtime_data.database
    try:
        assert sorted(await list_admin_ids(database)) == ["owner-1", "owner-2"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_owner_fallback_not_used_when_context_present(
    hass, make_entry
) -> None:
    """The context user (flow caller) wins over the owner fallback:
    a non-owner parent configuring the integration becomes the admin."""
    from unittest.mock import AsyncMock

    hass.auth.async_get_users = AsyncMock(
        return_value=[SimpleNamespace(id="owner-1", is_owner=True)]
    )
    entry = await _setup_entry(
        hass,
        make_entry(context={"user_id": "parent-configured"}),
        hass.registry,
    )
    database = entry.runtime_data.database
    try:
        assert await list_admin_ids(database) == ["parent-configured"]
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


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
