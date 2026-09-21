"""The NestQuest FastAPI application.

This module builds the ASGI app for the NestQuest API service (Feature
16).  The skeleton here wires the bundled ``core`` (Feature 15) and
exposes the two endpoints every later task depends on:

- ``GET /health`` — returns ``200`` with a JSON status body carrying
  ``status: "ok"`` and the resolved database path, proving the app
  imported core, opened the database, and applied migrations.
- ``GET /docs`` — FastAPI's auto-served OpenAPI document (Swagger UI);
  ``/openapi.json`` is the raw schema.  No extra wiring is needed;
  FastAPI serves both by default.

The database is opened and migrated in a FastAPI lifespan context so a
startup failure (e.g. an unwritable path) surfaces as a startup error
rather than the first request.  The connection is closed on shutdown.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from api.config import ApiConfig
from api.database import DatabaseState, make_database

LOGGER = logging.getLogger(__name__)


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
    ``uvicorn api.app:app`` picks up ``NESTQUEST_DB_PATH``.  Tests pass an
    explicit config (or set the env var) so each test gets a hermetic
    temp SQLite file.
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
        """Return service health and the resolved database path.

        The body carries ``status: "ok"`` and the ``db_path`` the app
        opened against — so a probe can confirm the app wired core and
        reached the configured SQLite file.  Returns 200 once the
        lifespan has opened and migrated the database.
        """
        state: DatabaseState = app.state.db
        return {"status": "ok", "db_path": state.db_path}

    return app


#: The module-level app instance, for ``uvicorn api.app:app``.
app: FastAPI = create_app()


__all__ = ["app", "create_app"]
