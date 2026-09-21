"""Typed DAO for the integration-owned ``nestquest_meta_state`` table.

Generic persistent key/value bookkeeping that belongs to the
integration itself rather than any domain table — currently the
Feature 11 missed-sweep watermark.  Values are plain strings; callers
interpret them.  All SQL for this table lives here per the feature
guardrails, and every method runs through
:class:`~.db.NestQuestDatabase` so nothing blocks the event loop.
"""
from __future__ import annotations

from .dao_children import _connection_lock
from .db import NestQuestDatabase

_TABLE = "nestquest_meta_state"


class MetaStateDao:
    """Typed async access to the ``nestquest_meta_state`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def get(self, key: str) -> str | None:
        """Return the stored value for ``key``, or None when absent."""
        row = await self._database.fetch_one(
            f"SELECT value FROM {_TABLE} WHERE key = ?", (key,)
        )
        return row[0] if row is not None else None

    async def set(self, key: str, value: str) -> None:
        """Upsert one key/value row atomically.

        The write runs inside one transaction under the shared
        connection lock, so a racing reader either sees the old value
        or the fully-written new one, never a half-applied state.
        """
        async with _connection_lock(self._database):
            async with self._database.transaction():
                await self._database.execute(
                    f"INSERT INTO {_TABLE} (key, value) VALUES (?, ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )