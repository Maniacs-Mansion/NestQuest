"""Business layer for the admin allowlist (Feature 03).

Sits between the options flow / Feature 09 service gate and the typed
:class:`~.dao_children.AdminUsersDao`.  The allowlist stores Home
Assistant user IDs — never usernames or display names (feature
guardrail) — and an empty allowlist must fail closed: every function
here refuses to write an empty allowlist, so the owner can never be
accidentally locked out of admin operations by a bad save.

Shape policy: a user id is a non-empty trimmed string.  Duplicate ids
in one write are rejected up front — they would silently map to one
row and hide a caller bug.  Writes replace the allowlist atomically:
the diff (additions and removals) is computed and applied inside one
transaction under the connection-scoped lock shared with the DAOs, so
a concurrent reader never observes a half-applied sync.

Seed policy (:func:`seed_setup_admin`): the allowlist is seeded only
when it is EMPTY, so re-running setup never resurrects a deliberately
narrowed list.  The setup user (the HA user who completed the config
flow, via the entry context) is added automatically so the owner is
never locked out on first setup; a stored entry-data copy of the list
re-seeds a lost database.
"""
from __future__ import annotations

import datetime
import logging

from .dao_children import AdminUsersDao, _connection_lock
from .db import NestQuestDatabase

LOGGER = logging.getLogger(__name__)


def _now_stamp() -> str:
    """UTC second-precision stamp, matching the registry's policy."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _validate_user_id(value: object) -> str:
    """Return ``value`` trimmed; raise unless a non-empty string."""
    if not isinstance(value, str):
        raise ValueError(
            f"admin user id must be a string, got {value!r}"
        )
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("admin user id must not be empty")
    return trimmed


async def list_admin_ids(database: NestQuestDatabase) -> list[str]:
    """Return the allowlisted HA user IDs in storage order."""
    return [row.ha_user_id for row in await AdminUsersDao(database).list()]


async def set_admin_ids(
    database: NestQuestDatabase, user_ids: list[str]
) -> None:
    """Replace the allowlist with exactly ``user_ids`` (atomic sync).

    Refuses an empty list — an empty allowlist must fail closed, and
    the only way to reach one through this API would be removing the
    last admin, so that removal is refused here with a clear error.
    Refuses non-string, empty, or duplicate ids up front.  The diff
    against the current allowlist (additions and removals) applies
    inside one transaction under the connection lock.
    """
    if not isinstance(user_ids, list):
        raise ValueError("user_ids must be a list of HA user id strings")
    normalized: list[str] = []
    for value in user_ids:
        normalized.append(_validate_user_id(value))
    if len(set(normalized)) != len(normalized):
        raise ValueError("user_ids must not contain duplicates")
    if not normalized:
        raise ValueError(
            "refusing to empty the admin allowlist: at least one admin "
            "must remain (an empty allowlist fails closed)"
        )
    dao = AdminUsersDao(database)
    async with _connection_lock(database):
        async with database.transaction():
            current = {row.ha_user_id for row in await dao.list()}
            target = set(normalized)
            for user_id in sorted(current - target):
                await dao.remove(user_id)
            for user_id in normalized:
                await dao.add(user_id, _now_stamp())


async def seed_setup_admin(
    database: NestQuestDatabase,
    *,
    stored_admin_ids: list[str] | None = None,
    context_user_id: str | None = None,
    owner_ids: list[str] | None = None,
) -> list[str]:
    """Seed an empty allowlist so the owner is never locked out.

    Only acts when the allowlist is EMPTY.  Preference order: the
    stored persisted copy of the list (the options flow's current
    selection, then the config flow's original — disaster recovery for
    a lost database), then the HA user who completed the config flow
    (``context_user_id``), then — when no caller identity survived at
    all — every Home Assistant OWNER account (``owner_ids``), so a
    first setup whose flow context lost the user id still seeds a
    working admin.  Returns the allowlist after seeding.  Non-empty
    allowlists are returned untouched — re-running setup must never
    resurrect a deliberately narrowed list.
    """
    dao = AdminUsersDao(database)
    async with _connection_lock(database):
        current = [row.ha_user_id for row in await dao.list()]
        if current:
            return current
        candidates: list[str] = []
        if stored_admin_ids is not None:
            if not isinstance(stored_admin_ids, list):
                raise ValueError(
                    "stored_admin_ids must be a list of HA user id strings"
                )
            candidates = [_validate_user_id(value) for value in stored_admin_ids]
        elif context_user_id is not None:
            candidates = [_validate_user_id(context_user_id)]
        elif owner_ids:
            if not isinstance(owner_ids, list):
                raise ValueError(
                    "owner_ids must be a list of HA user id strings"
                )
            candidates = [_validate_user_id(value) for value in owner_ids]
        for user_id in candidates:
            await dao.add(user_id, _now_stamp())
        return [row.ha_user_id for row in await dao.list()]
