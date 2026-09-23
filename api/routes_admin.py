"""Admin-plane routes for the NestQuest API service.

The admin plane (``/api/v1/admin/*``, D-012) serves the admin PWA.
Every route on :data:`router` requires a valid Authentik OIDC JWT
whose ``groups`` claim names ``nestquest-admins``, through the ONE
reusable dependency :func:`api.auth.require_admin` (declared once at
the router level, so each later admin route added to this router
inherits the check).  The panel service token is refused outright on
this plane (403), never treated as a JWT.

This task is the AUTH probe only: the ping route is a thin adapter
that performs NO business logic and NO auth of its own — it reuses the
router's already-verified claims (FastAPI caches a dependency's result
per request, so the check runs exactly once) and returns the status
plus the token's subject.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import require_admin

#: All admin-plane routes share this router; the ONE admin dependency
#: (service-token refusal + JWT verification + nestquest-admins group
#: gate) is attached HERE so every admin route (current and later)
#: requires it.
router = APIRouter(
    prefix="/api/v1/admin",
    dependencies=[Depends(require_admin)],
)


class AdminPingResponse(BaseModel):
    """The probe body: the status plus the verified token's subject."""

    status: str
    #: The JWT's ``sub`` claim — the subject the admin PWA authenticated
    #: as.  ``None`` only for a verified token that carries no ``sub``.
    sub: str | None


@router.get("/ping", summary="Admin plane probe")
async def admin_ping(
    claims: Annotated[dict[str, object], Depends(require_admin)],
) -> AdminPingResponse:
    """Return 200 for a verified JWT naming the nestquest-admins group.

    Requires a valid Authentik JWT with the admin group (checked by the
    router's shared :func:`~api.auth.require_admin` dependency — the
    ONE check; this handler performs NO auth of its own).  ``claims``
    is the SAME verified-claims dict that dependency produced (FastAPI's
    per-request dependency cache), so the token is verified exactly
    once per request.
    """
    sub = claims.get("sub")
    return AdminPingResponse(
        status="ok",
        sub=sub if isinstance(sub, str) else None,
    )


__all__ = ["router"]
