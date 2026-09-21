"""The NestQuest FastAPI application.

This module builds the ASGI app for the NestQuest API service (Feature
16).  The skeleton here wires the bundled ``core`` (Feature 15) and
exposes the two endpoints every later task depends on:

- ``GET /health`` — returns ``200`` with a JSON status body once the
  app has imported core, opened the database, and applied migrations;
  a cheap ``SELECT 1`` confirms the connection is live without leaking
  the filesystem path on an unauthenticated route.
- ``GET /docs`` — FastAPI's auto-served OpenAPI document (Swagger UI);
  ``/openapi.json`` is the raw schema.  No extra wiring is needed;
  FastAPI serves both by default.

The database is opened and migrated in a FastAPI lifespan context so a
startup failure (e.g. an unwritable path) surfaces as a startup error
rather than the first request.  The connection is closed on shutdown.

This module exports ONLY the :func:`create_app` factory — there is no
module-level app instance, because building one at import time would
read ``NESTQUEST_DB_PATH`` at import (and fail-fast on a missing value)
before any worker is ready to report it.  Serve with::

    uvicorn --factory api.app:create_app

so the factory runs on each worker startup and reads the environment
then.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from api.config import ApiConfig
from api.database import DatabaseState, make_database


def _build_lifespan(db_path: str):
    """Return a lifespan that opens+migrates then closes one database.

    Captured as a closure so the app factory can hand the configured
    path in without threading it through FastAPI's lifespan signature.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = make_database(db_path)
        app.state.db = state
        try:
            await state.open_and_migrate()
            yield
        finally:
            await state.close()

    return lifespan


def create_app(config: ApiConfig | None = None) -> FastAPI:
    """Build the NestQuest API FastAPI app.

    ``config`` defaults to one built from the process environment, so
    ``uvicorn --factory api.app:create_app`` picks up
    ``NESTQUEST_DB_PATH`` (and fails fast on startup if it is missing).
    Tests pass an explicit config so each test gets a hermetic temp
    SQLite file.
    """
    cfg = config if config is not None else ApiConfig.from_env()

    app = FastAPI(
        title="NestQuest API",
        description=(
            "Standalone HTTP service that owns the NestQuest database and "
            "exposes it to the Home Assistant integration (panel plane) and "
            "the admin PWA (admin plane)."
        ),
        version="0.1.0",
        lifespan=_build_lifespan(cfg.db_path),
    )

    @app.get("/health", summary="Service health")
    async def health() -> dict[str, str]:
        """Return service health.

        Returns ``200`` with ``{"status": "ok"}`` once the lifespan has
        opened and migrated the database.  A cheap ``SELECT 1`` against
        the live connection confirms the database is reachable WITHOUT
        leaking the filesystem path on an unauthenticated route; if the
        connection is dead the query raises and the probe fails.
        """
        state: DatabaseState = app.state.db
        await state.database.fetch_one("SELECT 1")
        return {"status": "ok"}

    return app


__all__ = ["create_app"]
