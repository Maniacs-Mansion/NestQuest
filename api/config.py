"""Configuration for the NestQuest API service.

The API reads its configuration knobs from environment variables:

- ``NESTQUEST_DB_PATH`` — the SQLite database file.  The API opens this
  file on startup (creating it if absent) and applies migrations.
- ``NESTQUEST_PANEL_TOKEN`` — the static panel-plane service token
  (D-012): the credential ``/api/v1/panel/*`` routes require via
  :func:`api.dependencies.require_panel_token`.  It is stored outside
  the repo and handed to the service through the environment.

Unlike a dev convenience default, a missing or empty value is a
configuration ERROR, not a silent fallback: a default database path
would silently drop data at reboot, and a default (or empty) service
token would either authenticate everyone or lock the panel plane out
for good.  ``ApiConfig.from_env`` therefore RAISES when either variable
is unset or empty.  This mirrors the integration's "explicit settings
object" discipline (Feature 15's ``core.settings``): the API never
reads HA config; callers pass the resolved values into the wiring.

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

#: Environment variable holding the static panel-plane service token
#: (D-012), checked by :func:`api.dependencies.require_panel_token`.
#: REQUIRED — unset or empty raises :class:`ConfigError` from
#: :meth:`ApiConfig.from_env`; there is no silent default, because an
#: empty configured token would either authenticate every caller or
#: lock the panel plane out permanently.
PANEL_TOKEN_ENV = "NESTQUEST_PANEL_TOKEN"


class ConfigError(RuntimeError):
    """Raised when required API configuration is missing or invalid."""


@dataclass(frozen=True)
class ApiConfig:
    """Resolved API configuration.

    Both fields are required (no defaults): ``from_env`` rejects an
    unset or empty value for either, and a caller building the dataclass
    directly must pass an explicit token — the token check itself fails
    closed on an empty configured token, but expecting a caller to
    discover that at request time is a wiring mistake, so the field is
    mandatory.  Kept as a dataclass so later tasks (admin plane, SSE,
    settings persistence) can extend it without touching the call sites
    that read ``db_path``.
    """

    db_path: str
    panel_token: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ApiConfig":
        """Build configuration from the process environment.

        ``env`` defaults to ``os.environ``; tests pass an explicit dict
        so they are hermetic (no monkeypatch of the global environ).

        Raises :class:`ConfigError` when ``NESTQUEST_DB_PATH`` is unset
        or empty/whitespace-only — there is no silent default, because a
        default in the temp directory would silently lose data at reboot
        — and likewise when ``NESTQUEST_PANEL_TOKEN`` is unset or empty
        (a default token is never invented: the panel plane is closed
        until a real one is configured).
        """
        source = env if env is not None else os.environ
        raw_db_path = source.get(DB_PATH_ENV, "").strip()
        if not raw_db_path:
            raise ConfigError(
                f"{DB_PATH_ENV} must be set to a writable SQLite file path "
                f"(it is unset or empty — the API will not fall back to a "
                f"temp directory and silently lose data)"
            )
        raw_panel_token = source.get(PANEL_TOKEN_ENV, "").strip()
        if not raw_panel_token:
            raise ConfigError(
                f"{PANEL_TOKEN_ENV} must be set to the panel service token "
                f"(it is unset or empty — the API will not start without "
                f"one, and no default token is invented)"
            )
        return cls(db_path=raw_db_path, panel_token=raw_panel_token)


__all__ = ["ApiConfig", "ConfigError", "DB_PATH_ENV", "PANEL_TOKEN_ENV"]
