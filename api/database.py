"""Database wiring for the NestQuest API service.

The API owns the database (it is the writer of record per Feature 16's
contract).  This module owns one application-lifetime
:class:`core.db.NestQuestDatabase`: it opens the SQLite file at the
configured path on startup, applies migrations (creating the schema on
a fresh file), and closes the connection on shutdown.

The executor callable passed into ``NestQuestDatabase`` mirrors the
contract of ``hass.async_add_executor_job``: schedule a synchronous
callable on a worker and await its result.  HA's own version lives on
the event loop; the API is not HA, so it uses
:func:`asyncio.to_thread` for the same effect — sqlite3 calls run on a
worker thread and only plain data returns to the event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from api.nestquest_core import core_db, core_migrations

LOGGER = logging.getLogger(__name__)

#: The async SQLite wrapper.  Re-exported so route handlers and later
#: tasks reach it through the API package, not the bundled core.
NestQuestDatabase = core_db.NestQuestDatabase

#: The migration runner.  Re-exported for the same reason.
apply_migrations = core_migrations.apply_migrations


async def _executor(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous callable on a worker thread and await its result.

    Mirrors the contract of ``hass.async_add_executor_job`` so the
    bundled ``NestQuestDatabase`` (written against that contract) works
    unchanged in the API process: sqlite3 calls never block the event
    loop, and only plain Python data (row tuples,
    :class:`core.db.ExecutionResult`) crosses back.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


class DatabaseState:
    """Holds the live database wrapper and its resolved path.

    A small container so the lifespan and the route handlers share one
    authoritative reference; FastAPI's lifespan stores one of these on
    ``app.state.db`` and the health route reads it back.
    """

    __slots__ = ("database", "db_path")

    def __init__(self, database: NestQuestDatabase, db_path: str) -> None:
        self.database = database
        self.db_path = db_path

    async def open_and_migrate(self) -> None:
        """Open the connection and apply migrations to the latest version."""
        LOGGER.info("Opening NestQuest database at %s", self.db_path)
        await self.database.open(self.db_path)
        version = await apply_migrations(self.database)
        LOGGER.info("NestQuest schema at version %d", version)

    async def close(self) -> None:
        """Close the connection; safe to call even if open failed."""
        await self.database.close()


def make_database(db_path: str) -> DatabaseState:
    """Construct a :class:`DatabaseState` for the given path (not yet open)."""
    return DatabaseState(NestQuestDatabase(_executor), db_path)


__all__ = [
    "DatabaseState",
    "NestQuestDatabase",
    "apply_migrations",
    "make_database",
]
