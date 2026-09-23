"""Configuration for the NestQuest API service.

The API reads its configuration knobs from environment variables:

- ``NESTQUEST_DB_PATH`` — the SQLite database file.  The API opens this
  file on startup (creating it if absent) and applies migrations.
- ``NESTQUEST_PANEL_TOKEN`` — the static panel-plane service token
  (D-012): the credential ``/api/v1/panel/*`` routes require via
  :func:`api.dependencies.require_panel_token`.  It is stored outside
  the repo and handed to the service through the environment.
- ``NESTQUEST_OIDC_ISSUER`` — the Authentik OIDC issuer URL whose
  ``iss`` claim admin tokens must carry (D-012 admin plane).
- ``NESTQUEST_OIDC_AUDIENCE`` — the OIDC client id the admin tokens
  must carry as their ``aud`` claim (the API service's client id).
- ``NESTQUEST_OIDC_JWKS_URL`` — the Authentik endpoint serving the
  signing keys (the JWKS document) the admin tokens' signatures are
  verified against.  Cached per app (see :class:`api.auth.JwksCache`).

Unlike a dev convenience default, a missing or empty value is a
configuration ERROR, not a silent fallback: a default database path
would silently drop data at reboot, a default (or empty) service token
would either authenticate everyone or lock the panel plane out for
good, and a default (or empty) OIDC setting would silently leave the
admin plane trusting an issuer that was never configured.  All five
variables are therefore REQUIRED — ``ApiConfig.from_env`` RAISES when
any of them is unset or empty.  This mirrors the integration's
"explicit settings object" discipline (Feature 15's ``core.settings``):
the API never reads HA config; callers pass the resolved values into
the wiring.

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

#: Environment variable holding the Authentik OIDC issuer URL (D-012
#: admin plane): every admin JWT's ``iss`` claim must equal it.  Checked
#: by :func:`api.auth.require_admin_jwt`.  REQUIRED — unset or empty
#: raises :class:`ConfigError` from :meth:`ApiConfig.from_env`; a default
#: issuer would silently make the admin plane trust tokens from an
#: issuer nobody configured.
OIDC_ISSUER_ENV = "NESTQUEST_OIDC_ISSUER"

#: Environment variable holding the OIDC audience (the API service's
#: client id at Authentik): every admin JWT's ``aud`` claim must carry
#: it.  Checked by :func:`api.auth.require_admin_jwt`.  REQUIRED — unset
#: or empty raises :class:`ConfigError` from :meth:`ApiConfig.from_env`.
OIDC_AUDIENCE_ENV = "NESTQUEST_OIDC_AUDIENCE"

#: Environment variable holding the Authentik JWKS URL: the endpoint
#: serving the signing keys admin JWT signatures are verified against.
#: Fetched and cached by :class:`api.auth.JwksCache`.  REQUIRED — unset
#: or empty raises :class:`ConfigError` from :meth:`ApiConfig.from_env`;
#: without the provider's keys no token can be verified, so a silent
#: default would only move the failure to request time.
OIDC_JWKS_URL_ENV = "NESTQUEST_OIDC_JWKS_URL"


class ConfigError(RuntimeError):
    """Raised when required API configuration is missing or invalid."""


@dataclass(frozen=True)
class ApiConfig:
    """Resolved API configuration.

    Every field is required (no defaults): ``from_env`` rejects an
    unset or empty value for each, and a caller building the dataclass
    directly must pass explicit values — the token check and the JWT
    checks themselves fail closed on empty configured values, but
    expecting a caller to discover that at request time is a wiring
    mistake, so every field is mandatory.  Kept as a dataclass so later
    tasks (SSE, settings persistence) can extend it without touching
    the call sites that read ``db_path``.
    """

    db_path: str
    panel_token: str
    #: The Authentik OIDC issuer URL admin tokens' ``iss`` must equal.
    oidc_issuer: str
    #: The OIDC audience (the API service's client id) admin tokens'
    #: ``aud`` must carry.
    oidc_audience: str
    #: The Authentik JWKS URL the signing keys are fetched from.
    oidc_jwks_url: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ApiConfig":
        """Build configuration from the process environment.

        ``env`` defaults to ``os.environ``; tests pass an explicit dict
        so they are hermetic (no monkeypatch of the global environ).

        Raises :class:`ConfigError` when ANY of the five variables is
        unset or empty/whitespace-only — there is no silent default:

        - ``NESTQUEST_DB_PATH``: a default in the temp directory would
          silently lose data at reboot;
        - ``NESTQUEST_PANEL_TOKEN``: a default token is never invented —
          the panel plane is closed until a real one is configured;
        - the three OIDC variables: an unconfigured issuer/audience/JWKS
          URL must not silently leave the admin plane open (a default
          JWKS URL or issuer would point at a provider nobody set up).
        """
        source = env if env is not None else os.environ

        def require(env_var: str, reason: str) -> str:
            """Return the stripped env value or raise ConfigError."""
            value = source.get(env_var, "").strip()
            if not value:
                raise ConfigError(f"{env_var} {reason}")
            return value

        return cls(
            db_path=require(
                DB_PATH_ENV,
                "must be set to a writable SQLite file path (it is unset "
                "or empty — the API will not fall back to a temp directory "
                "and silently lose data)",
            ),
            panel_token=require(
                PANEL_TOKEN_ENV,
                "must be set to the panel service token (it is unset or "
                "empty — the API will not start without one, and no "
                "default token is invented)",
            ),
            oidc_issuer=require(
                OIDC_ISSUER_ENV,
                "must be set to the Authentik OIDC issuer URL (it is "
                "unset or empty — the admin plane will not trust tokens "
                "from an issuer nobody configured)",
            ),
            oidc_audience=require(
                OIDC_AUDIENCE_ENV,
                "must be set to the OIDC audience the admin tokens carry "
                "(it is unset or empty — the admin plane will not accept "
                "tokens without a configured audience)",
            ),
            oidc_jwks_url=require(
                OIDC_JWKS_URL_ENV,
                "must be set to the Authentik JWKS URL (it is unset or "
                "empty — admin token signatures cannot be verified "
                "without the provider's signing keys)",
            ),
        )


__all__ = [
    "ApiConfig",
    "ConfigError",
    "DB_PATH_ENV",
    "OIDC_AUDIENCE_ENV",
    "OIDC_ISSUER_ENV",
    "OIDC_JWKS_URL_ENV",
    "PANEL_TOKEN_ENV",
]
