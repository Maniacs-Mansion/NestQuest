"""Async SQLite connection wrapper for the NestQuest integration."""
from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant


class NestQuestDatabase:
    """Async wrapper around a single SQLite connection.

    Every sqlite3 call is delegated to the Home Assistant executor through
    ``hass.async_add_executor_job`` so the event loop is never blocked.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the wrapper around a Home Assistant instance."""
        self._hass = hass
        self._conn: sqlite3.Connection | None = None
        self._cursor: sqlite3.Cursor | None = None

    @property
    def connected(self) -> bool:
        """Return True while the underlying connection is open."""
        return self._conn is not None

    @property
    def rowcount(self) -> int:
        """Row count of the most recent statement, or -1 when unset."""
        return self._cursor.rowcount if self._cursor is not None else -1

    @property
    def lastrowid(self) -> int | None:
        """Row id of the most recent insert, or None when unset."""
        return self._cursor.lastrowid if self._cursor is not None else None

    async def open(self, path: Path | str) -> NestQuestDatabase:
        """Open the SQLite file with WAL journal mode and foreign keys on."""
        if self._conn is not None:
            return self

        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(
                path, check_same_thread=False, isolation_level=None
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn

        self._conn = await self._hass.async_add_executor_job(_open)
        return self

    async def execute(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> sqlite3.Cursor:
        """Run one statement in the executor and return its cursor."""
        conn = self._require_conn()

        def _execute() -> sqlite3.Cursor:
            return conn.execute(sql, parameters)

        self._cursor = await self._hass.async_add_executor_job(_execute)
        return self._cursor

    async def execute_many(
        self, sql: str, parameters: Sequence[Sequence[Any]]
    ) -> sqlite3.Cursor:
        """Run executemany in the executor and return its cursor."""
        conn = self._require_conn()

        def _execute_many() -> sqlite3.Cursor:
            return conn.executemany(sql, parameters)

        self._cursor = await self._hass.async_add_executor_job(_execute_many)
        return self._cursor

    async def fetch_one(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> tuple | None:
        """Run a query in the executor and return its first row, or None."""
        cursor = await self.execute(sql, parameters)

        def _fetch_one() -> tuple | None:
            return cursor.fetchone()

        return await self._hass.async_add_executor_job(_fetch_one)

    async def fetch_all(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> list[tuple]:
        """Run a query in the executor and return all of its rows."""
        cursor = await self.execute(sql, parameters)

        def _fetch_all() -> list[tuple]:
            return cursor.fetchall()

        return await self._hass.async_add_executor_job(_fetch_all)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Run a block inside BEGIN/COMMIT, rolling back on any exception."""
        conn = self._require_conn()

        def _begin() -> None:
            conn.execute("BEGIN")

        await self._hass.async_add_executor_job(_begin)
        try:
            yield
        except BaseException:

            def _rollback() -> None:
                conn.execute("ROLLBACK")

            await self._hass.async_add_executor_job(_rollback)
            raise

        def _commit() -> None:
            conn.execute("COMMIT")

        await self._hass.async_add_executor_job(_commit)

    async def close(self) -> None:
        """Close the connection in the executor; safe to call repeatedly."""
        conn, self._conn, self._cursor = self._conn, None, None
        if conn is None:
            return

        def _close() -> None:
            conn.close()

        await self._hass.async_add_executor_job(_close)

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(
                "The NestQuest database connection is closed; call open() first"
            )
        return self._conn