"""Configuration for the NestQuest API service.

The API reads its single configuration knob — the SQLite database path —
from the ``NESTQUEST_DB_PATH`` environment variable.  Unlike a dev
convenience default, a missing or empty value is a configuration ERROR,
not a silent fallback to a predictable world-writable temp path: the API
owns the database (it is the writer of record per Feature 16's
contract), and silently dropping data into ``$TMPDIR/nestquest.db``
would lose it at reboot.  ``ApiConfig.from_env`` therefore RAISES when
the variable is unset or empty.  This mirrors the integration's
"explicit settings object" discipline (Feature 15's
``core.settings``): the API never reads HA config; callers pass the
resolved path into the database wiring.

Serving: the app is built with the factory ``api.app:create_app`` — run
it with ``uvicorn --factory api.app:create_app`` so the factory reads
the environment on each worker startup rather than at import time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

#: Environment variable holding the SQLite file path.  The API opens
#: this file on startup (creating it if absent) and applies migrations.
#: REQUIRED — unset or empty raises :class:`ConfigError` from
#: :meth:`ApiConfig.from_env`.
DB_PATH_ENV = "NESTQUEST_DB_PATH"


class ConfigError(RuntimeError):
    """Raised when required API configuration is missing or invalid."""


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

        Raises :class:`ConfigError` when ``NESTQUEST_DB_PATH`` is unset
        or empty/whitespace-only — there is no silent default, because a
        default in the temp directory would silently lose data at reboot.
        """
        source = env if env is not None else os.environ
        raw = source.get(DB_PATH_ENV, "").strip()
        if not raw:
            raise ConfigError(
                f"{DB_PATH_ENV} must be set to a writable SQLite file path "
                f"(it is unset or empty — the API will not fall back to a "
                f"temp directory and silently lose data)"
            )
        return cls(db_path=raw)


__all__ = ["ApiConfig", "ConfigError", "DB_PATH_ENV"]
