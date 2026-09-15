"""Typed DAO layer for the children and admin_users tables.

All SQL for ``children`` and ``admin_users`` lives in this module per
the feature guardrail: callers get typed dataclasses back and never see
raw rows or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Error contract: violations surface as the underlying
:class:`sqlite3.IntegrityError` (duplicate, foreign-key, or CHECK
failure) from the execute call; the DAO adds no wrapping exception
type.  A get that matches nothing returns ``None``; a mutation that
matches nothing is reported by :class:`~.db.ExecutionResult.rowcount`,
which each method returns where the caller may need it (reorder, and
the admin remove/set paths).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .db import NestQuestDatabase


@dataclass(frozen=True)
class ChildRecord:
    """One row of ``children``."""

    id: int
    display_name: str
    colour: str | None
    avatar_ref: str | None
    sort_order: int
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class AdminUserRecord:
    """One row of ``admin_users``."""

    ha_user_id: str
    added_at: str


def _child_from_row(row: tuple) -> ChildRecord:
    """Build a :class:`ChildRecord` from a SELECT row."""
    return ChildRecord(
        id=row[0],
        display_name=row[1],
        colour=row[2],
        avatar_ref=row[3],
        sort_order=row[4],
        is_active=bool(row[5]),
        created_at=row[6],
    )


_CHILD_COLUMNS = (
    "id, display_name, colour, avatar_ref, sort_order, is_active, created_at"
)


#: One asyncio.Lock per (connection wrapper, running loop), shared by
#: every ChildrenDao instance over the same database: the wrapper
#: rejects a second concurrent transaction with RuntimeError, so ALL
#: transactional DAO operations on one connection must queue here, not
#: per-instance.  Keyed like the migration runner's lock; entries are
#: never evicted (a config entry holds one wrapper per process).
_CONNECTION_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def _connection_lock(database) -> asyncio.Lock:
    """Return the shared transaction-serializing lock for ``database``."""
    loop = asyncio.get_running_loop()
    key = (id(database), id(loop))
    lock = _CONNECTION_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _CONNECTION_LOCKS[key] = lock
    return lock


class ChildrenDao:
    """Typed async data access for the ``children`` table.

    Deletion is deliberately absent: children are deactivated, never
    deleted, because completion history references them (feature
    guardrail).
    """

    def __init__(self, database) -> None:
        self._database = database

    async def create(
        self,
        display_name: str,
        created_at: str,
        *,
        colour: str | None = None,
        avatar_ref: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> ChildRecord:
        """Insert one child and return the record as stored."""
        result = await self._database.execute(
            "INSERT INTO children (display_name, colour, avatar_ref, "
            "sort_order, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                display_name,
                colour,
                avatar_ref,
                sort_order,
                int(is_active),
                created_at,
            ),
        )
        child = await self.get(result.lastrowid)
        assert child is not None
        return child

    async def get(self, child_id: int) -> ChildRecord | None:
        """Return the child with ``child_id``, or None."""
        row = await self._database.fetch_one(
            f"SELECT {_CHILD_COLUMNS} FROM children WHERE id = ?",
            (child_id,),
        )
        return _child_from_row(row) if row is not None else None

    async def list_active(self) -> list[ChildRecord]:
        """Return active children ordered by sort_order, then id."""
        rows = await self._database.fetch_all(
            f"SELECT {_CHILD_COLUMNS} FROM children WHERE is_active = 1 "
            "ORDER BY sort_order, id"
        )
        return [_child_from_row(row) for row in rows]

    async def list_all(self) -> list[ChildRecord]:
        """Return all children ordered by sort_order, then id."""
        rows = await self._database.fetch_all(
            f"SELECT {_CHILD_COLUMNS} FROM children "
            "ORDER BY sort_order, id"
        )
        return [record for record in map(_child_from_row, rows)]

    async def update(
        self,
        child_id: int,
        *,
        display_name: str | None = None,
        colour: str | None = None,
        avatar_ref: str | None = None,
        sort_order: int | None = None,
    ) -> int:
        """Update the given fields; returns rows updated (0 if absent).

        Only non-None arguments are written, so a caller cannot
        accidentally blank a column by omitting it.
        """
        assignments: list[str] = []
        parameters: list[object] = []
        if display_name is not None:
            assignments.append("display_name = ?")
            parameters.append(display_name)
        if colour is not None:
            assignments.append("colour = ?")
            parameters.append(colour)
        if avatar_ref is not None:
            assignments.append("avatar_ref = ?")
            parameters.append(avatar_ref)
        if sort_order is not None:
            assignments.append("sort_order = ?")
            parameters.append(sort_order)
        if not assignments:
            return 0
        parameters.append(child_id)
        result = await self._database.execute(
            f"UPDATE children SET {', '.join(assignments)} WHERE id = ?",
            tuple(parameters),
        )
        return result.rowcount

    async def set_active(self, child_id: int, is_active: bool) -> int:
        """Set the child's active flag; returns rows updated (0 if absent)."""
        result = await self._database.execute(
            "UPDATE children SET is_active = ? WHERE id = ?",
            (int(is_active), child_id),
        )
        return result.rowcount

    async def reorder(self, ordered_ids: list[int]) -> None:
        """Persist a new sort order: ``ordered_ids[i]`` gets sort_order i.

        The list must be a COMPLETE permutation of the children table:
        every existing child id appears exactly once.  Partial lists
        (missing an existing child) and unknown ids (naming a child
        that does not exist) are rejected with ValueError BEFORE any
        write, leaving the current order untouched — a silent partial
        reorder would leave unlisted children with stale positions and
        hide a caller bug.  Duplicate ids are rejected up front: they
        cannot all hold distinct positions, and silently assigning the
        last occurrence's index would hide a caller bug.

        Runs inside one transaction; positions are staged at offset
        -len (all negative, so any permutation of the same ids never
        collides mid-reorder under the wrapper's single-connection
        serialization), then finalized 0..n-1.

        Concurrent reorder() calls on one connection are serialized by
        a connection-scoped asyncio lock (shared across every ChildrenDao
        over the same wrapper, however many instances): the wrapper's
        transaction() rejects a second concurrent transaction with
        RuntimeError, so racing callers would crash instead of
        queueing.  The lock makes the second call wait, then run
        against the first call's final state — which also keeps the
        completeness check honest: the re-read of the table happens
        inside the same lock and transaction as the writes.
        """
        if len(set(ordered_ids)) != len(ordered_ids):
            raise ValueError(
                "reorder() received duplicate child ids; every id must "
                "appear at most once"
            )
        async with _connection_lock(self._database):
            async with self._database.transaction():
                rows = await self._database.fetch_all(
                    f"SELECT id FROM children"
                )
                existing = {row[0] for row in rows}
                listed = set(ordered_ids)
                missing = sorted(existing - listed)
                unknown = sorted(listed - existing)
                if missing or unknown:
                    details = []
                    if missing:
                        details.append(
                            f"missing child ids {missing} (a partial "
                            "reorder would leave them with stale "
                            "positions)"
                        )
                    if unknown:
                        details.append(
                            f"unknown child ids {unknown}"
                        )
                    raise ValueError(
                        "reorder() must list every child exactly once; "
                        + "; ".join(details)
                    )
                offset = len(ordered_ids)
                await self._database.execute_many(
                    "UPDATE children SET sort_order = ? WHERE id = ?",
                    [
                        (-(offset + index), child_id)
                        for index, child_id in enumerate(ordered_ids)
                    ],
                )
                await self._database.execute_many(
                    "UPDATE children SET sort_order = ? WHERE id = ?",
                    [
                        (index, child_id)
                        for index, child_id in enumerate(ordered_ids)
                    ],
                )


class AdminUsersDao:
    """Typed async access to the ``admin_users`` allowlist.

    The allowlist stores HA user IDs, never usernames (feature
    guardrail); an empty allowlist means no admin, enforced by callers
    resolving through :meth:`exists`.
    """

    def __init__(self, database) -> None:
        self._database = database

    async def add(self, ha_user_id: str, added_at: str) -> bool:
        """Add a user to the allowlist; True if inserted, False if present.

        Idempotent under concurrency: a single INSERT ... ON CONFLICT DO
        NOTHING decides and inserts in one statement (the wrapper
        serializes statements, not check-then-insert sequences, so a
        SELECT/INSERT pair would let two concurrent adds both see no
        row and the second one raise IntegrityError).  rowcount reports
        whether the insert actually happened.
        """
        result = await self._database.execute(
            "INSERT INTO admin_users (ha_user_id, added_at) VALUES (?, ?) "
            "ON CONFLICT (ha_user_id) DO NOTHING",
            (ha_user_id, added_at),
        )
        return result.rowcount > 0

    async def remove(self, ha_user_id: str) -> bool:
        """Remove a user from the allowlist; True if a row was removed."""
        result = await self._database.execute(
            "DELETE FROM admin_users WHERE ha_user_id = ?",
            (ha_user_id,),
        )
        return result.rowcount > 0

    async def list(self) -> list[AdminUserRecord]:
        """Return every allowlisted user, oldest first."""
        rows = await self._database.fetch_all(
            "SELECT ha_user_id, added_at FROM admin_users "
            "ORDER BY added_at, ha_user_id"
        )
        return [
            AdminUserRecord(ha_user_id=row[0], added_at=row[1])
            for row in rows
        ]

    async def exists(self, ha_user_id: str) -> bool:
        """Return True if ``ha_user_id`` is allowlisted."""
        row = await self._database.fetch_one(
            "SELECT 1 FROM admin_users WHERE ha_user_id = ?",
            (ha_user_id,),
        )
        return row is not None