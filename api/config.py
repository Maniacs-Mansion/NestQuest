"""Configuration for the NestQuest API service.

The API reads its single configuration knob — the SQLite database path —
from the ``NESTQUEST_DB_PATH`` environment variable, with a documented
default inside the OS temp directory.  This mirrors the integration's
"explicit settings object" discipline (Feature 15's
``core.settings``): the API never reads HA config; callers pass the
resolved path into the database wiring.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Environment variable holding the SQLite file path.  The API opens
#: this file on startup (creating it if absent) and applies migrations.
DB_PATH_ENV = "NESTQUEST_DB_PATH"

#: The default database location when the env var is unset.  Lives in
#: the OS temp directory so a dev run without configuration does not
#: litter the repo, and so tests that forget to set the env var still
#: get a hermetic-ish path.  Production deployments ALWAYS set
#: ``NESTQUEST_DB_PATH`` to a persistent volume path.
_DEFAULT_DB_NAME = "nestquest.db"


def _default_db_path() -> str:
    return str(Path(tempfile.gettempdir()) / _DEFAULT_DB_NAME)


@dataclass(frozen=True)
class ApiConfig:
    """Resolved API configuration.

    Currently a single field — the SQLite path — but kept as a dataclass
    so later tasks (auth, SSE, settings persistence) can extend it
    without touching the call sites that read ``db_path``.
    """

    db_path: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ApiConfig":
        """Build configuration from the process environment.

        ``env`` defaults to ``os.environ``; tests pass an explicit dict
        so they are hermetic (no monkeypatch of the global environ).
        """
        source = env if env is not None else os.environ
        raw = source.get(DB_PATH_ENV, "").strip()
        return cls(db_path=raw if raw else _default_db_path())


def resolve_db_path(env: dict[str, str] | None = None) -> str:
    """Return the resolved SQLite path (env override or documented default)."""
    return ApiConfig.from_env(env).db_path


__all__ = ["ApiConfig", "DB_PATH_ENV", "resolve_db_path"]
