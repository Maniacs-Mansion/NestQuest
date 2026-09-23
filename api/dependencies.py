"""Reusable FastAPI dependencies for the NestQuest API routes.

The panel plane (``/api/v1/panel/*``) is authenticated by the static
service token configured through ``NESTQUEST_PANEL_TOKEN`` (D-012): the
HA integration presents it as a Bearer credential on every panel
request.  :func:`require_panel_token` is the ONE implementation of that
check — every panel route (this task's snapshot route and each later
panel route) declares it as a dependency rather than re-implementing
token handling, so the credential, the failure behaviour, and the
401 contract stay in exactly one place.

The dependency FAILS CLOSED: a missing ``Authorization`` header, a
malformed one (wrong scheme or empty credential), a token that does not
match the configured value, and an empty configured token all yield
HTTP 401.  The comparison is constant-time (:func:`secrets.compare_digest`)
so the wall-clock difference between "wrong length" and "wrong value"
cannot be used to probe the token byte by byte, and every rejection
carries the same detail — nothing in the response distinguishes which
part of the check failed.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request

#: The authorization scheme the panel plane expects.  Matched
#: case-insensitively, as RFC 9110 requires for scheme names.
_BEARER_SCHEME = "bearer"

#: The 401 detail shared by every rejection — deliberately uniform so
#: the response never reveals which part of the check failed.
_REJECTION_DETAIL = "Missing or invalid panel service token"

#: Challenge header returned with a 401, per the Bearer auth scheme.
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def _reject() -> HTTPException:
    """Build the single 401 the dependency raises for every failure."""
    return HTTPException(
        status_code=401,
        detail=_REJECTION_DETAIL,
        headers=_WWW_AUTHENTICATE,
    )


async def require_panel_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request with 401 unless it carries the panel token.

    Reads the configured token off ``app.state.config`` (set by
    :func:`api.app.create_app`) so the dependency stays reusable across
    routes and carries no module state of its own.  A missing or
    malformed ``Authorization`` header, a non-matching credential, and
    an EMPTY configured token (a wiring mistake) all raise the same
    ``HTTPException(401)`` — the check is closed even when the service
    is misconfigured.

    Returns ``None`` on success; FastAPI discards a ``None`` return,
    the route handler simply proceeds.
    """
    config = getattr(request.app.state, "config", None)
    expected = config.panel_token if config is not None else ""
    if not expected or authorization is None:
        raise _reject()
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != _BEARER_SCHEME or not credential.strip():
        raise _reject()
    # compare_digest on bytes so a non-ASCII token raises nothing and a
    # timing side channel on the str path is not available.
    if not secrets.compare_digest(
        credential.strip().encode("utf-8"), expected.encode("utf-8")
    ):
        raise _reject()


__all__ = ["require_panel_token"]
