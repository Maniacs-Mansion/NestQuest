"""Admin-plane routes for the NestQuest API service.

The admin plane (``/api/v1/admin/*``, D-012) serves the admin PWA.
Every route on :data:`router` requires a valid Authentik OIDC JWT
through the ONE reusable dependency :func:`api.auth.require_admin_jwt`
(declared once at the router level, so each later admin route added to
this router inherits the check).

This task is the AUTH probe only: the ping route is a thin adapter
that performs NO business logic and NO auth of its own — it reuses the
router's already-verified claims (FastAPI caches a dependency's result
per request, so the check runs exactly once) and returns the status
plus the token's subject.  Authorization — membership in the
``nestquest-admins`` group — is the NEXT task, layered onto
:func:`api.auth.require_admin_jwt` so every admin route inherits it.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import require_admin_jwt

#: All admin-plane routes share this router; the JWT check is attached
#: HERE so every admin route (current and later) requires it.
router = APIRouter(
    prefix="/api/v1/admin",
    dependencies=[Depends(require_admin_jwt)],
)


class AdminPingResponse(BaseModel):
    """The probe body: the status plus the verified token's subject."""

    status: str
    #: The JWT's ``sub`` claim — the subject the admin PWA authenticated
    #: as.  ``None`` only for a verified token that carries no ``sub``.
    sub: str | None


@router.get("/ping", summary="Admin plane probe")
async def admin_ping(
    claims: Annotated[dict[str, object], Depends(require_admin_jwt)],
) -> AdminPingResponse:
    """Return 200 for a verified admin JWT (the plane's smoke probe).

    Requires a valid Authentik JWT (checked by the router's shared
    :func:`~api.auth.require_admin_jwt` dependency — the ONE token
    check; this handler performs NO auth of its own).  ``claims`` is
    the SAME verified-claims dict that dependency produced (FastAPI's
    per-request dependency cache), so the token is verified exactly
    once per request.
    """
    sub = claims.get("sub")
    return AdminPingResponse(
        status="ok",
        sub=sub if isinstance(sub, str) else None,
    )


__all__ = ["router"]
