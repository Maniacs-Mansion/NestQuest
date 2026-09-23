"""Admin-plane routes for the NestQuest API service.

The admin plane (``/api/v1/admin/*``, D-012) serves the admin PWA.
Every route on :data:`router` requires a valid Authentik OIDC JWT
whose ``groups`` claim names ``nestquest-admins``, through the ONE
reusable dependency :func:`api.auth.require_admin` (declared once at
the router level, so each later admin route added to this router
inherits the check).  The panel service token is refused outright on
this plane (403), never treated as a JWT.

The children routes are THIN adapters over the bundled core (Feature
15): each handler validates the request's shape with a Pydantic model,
resolves the live database off ``app.state.db``, calls ONE
:mod:`nestquest_core.children` business function — the name policy,
the no-explicit-NULL rule, the real-bool check and the permutation
check all live THERE, never in a handler — and serializes the returned
:class:`~nestquest_core.dao_children.ChildRecord` into the documented
payload (``id``, ``display_name``, ``colour``, ``avatar_ref``,
``sort_order``, ``is_active``).

Error mapping (every children route, deliberately narrow):

- Malformed input the body model or the path parser rejects (a missing
  or wrong-typed field, a non-integer child id) is FastAPI's 422 before
  any handler code runs.
- A core ``ValueError`` reporting a NON-EXISTENT child (edit or
  set_active on an unknown id) is mapped to 404.
- Every OTHER core ``ValueError`` — an empty display name, an explicit
  ``null`` colour/avatar_ref (clearing is not supported), a reorder
  list that is not a complete permutation of the children (missing,
  duplicate, or unknown ids) — is mapped to 422: the body was
  well-formed JSON but semantically invalid, the same failure class
  Pydantic reports.  The core rejects these BEFORE any write, so a 422
  never leaves a half-applied change behind.

PATCH edit semantics: the body model's fields are optional and only
SUPPLIED fields are forwarded (``model_dump(exclude_unset=True)``), so
an omitted field is never passed to
:func:`nestquest_core.children.edit_child` and stays unchanged — while
an explicit ``null`` IS passed and is rejected by the core rather than
silently ignored.
"""
from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import require_admin
from api.database import DatabaseState
from api.nestquest_core import core_children

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


class AdminChildResponse(BaseModel):
    """One child profile as the admin plane serializes it.

    Mirrors :class:`~nestquest_core.dao_children.ChildRecord` minus the
    internal ``created_at`` stamp.
    """

    id: int
    display_name: str
    colour: str | None
    avatar_ref: str | None
    sort_order: int
    is_active: bool


class AdminChildListResponse(BaseModel):
    """The children list: every profile in the household's display order."""

    children: list[AdminChildResponse]


class AdminChildCreateRequest(BaseModel):
    """The body of ``POST /api/v1/admin/children``.

    ``display_name`` is required (the core trims it and rejects an
    empty name); the other fields are optional and default through the
    core layer (``colour``/``avatar_ref`` NULL, ``sort_order`` 0).
    """

    display_name: str
    colour: str | None = None
    avatar_ref: str | None = None
    sort_order: int = 0


class AdminChildEditRequest(BaseModel):
    """The body of ``PATCH /api/v1/admin/children/{child_id}``.

    Every field is optional; ONLY the fields the request supplies are
    forwarded to :func:`nestquest_core.children.edit_child` (the route
    dumps the model with ``exclude_unset``), so an omitted field stays
    unchanged while an explicit ``null`` — a supplied value — reaches
    the core and is rejected there rather than silently ignored.
    """

    display_name: str | None = None
    colour: str | None = None
    avatar_ref: str | None = None
    sort_order: int | None = None


class AdminChildActiveRequest(BaseModel):
    """The body of ``PATCH /api/v1/admin/children/{child_id}/active``."""

    is_active: bool


class AdminChildReorderRequest(BaseModel):
    """The body of ``POST /api/v1/admin/children/reorder``.

    ``ordered_ids`` must be a complete permutation of the household's
    child ids (the core rejects a partial, duplicate, or unknown list
    before any write).
    """

    ordered_ids: list[int]


#: 404 detail for a child id the core layer reports as non-existent.
_CHILD_NOT_FOUND_DETAIL = "Child not found"


def _raise_child_error(error: ValueError) -> NoReturn:
    """Map a core children ``ValueError`` onto 404 or 422 and raise it.

    The core layer raises ``ValueError`` for two distinct situations,
    and this mapping is the children routes' one piece of adapter
    logic: a non-existent child on a single-id route (edit, set_active
    — the message reads ``child N does not exist``) becomes 404, the
    admin plane's not-found answer; every other core ``ValueError``
    becomes 422 with the core's message as the detail — it names the
    field and what to fix, and leaks nothing but that validation rule.
    """
    if "does not exist" in str(error):
        raise HTTPException(
            status_code=404, detail=_CHILD_NOT_FOUND_DETAIL
        ) from error
    raise HTTPException(status_code=422, detail=str(error)) from error


def _child_response(record: core_children.ChildRecord) -> AdminChildResponse:
    """Serialize one core ChildRecord into the documented payload."""
    return AdminChildResponse(
        id=record.id,
        display_name=record.display_name,
        colour=record.colour,
        avatar_ref=record.avatar_ref,
        sort_order=record.sort_order,
        is_active=record.is_active,
    )


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


@router.get(
    "/children",
    summary="List child profiles",
    response_model=AdminChildListResponse,
)
async def admin_list_children(request: Request) -> AdminChildListResponse:
    """Return every child profile in display order.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: one
    :func:`nestquest_core.children.list_children` call, active AND
    inactive children included (the admin screen manages both), in the
    core's display order (``sort_order``, then ``id``).
    """
    state: DatabaseState = request.app.state.db
    records = await core_children.list_children(state.database)
    return AdminChildListResponse(
        children=[_child_response(record) for record in records]
    )


@router.post(
    "/children",
    summary="Create a child profile",
    status_code=201,
    response_model=AdminChildResponse,
)
async def admin_create_child(
    body: AdminChildCreateRequest, request: Request
) -> AdminChildResponse:
    """Create a child profile and return it as stored.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the body model
    carries the shape, and the name policy (trim, reject empty), the
    duplicate-name warning and the created_at stamp all live in
    :func:`nestquest_core.children.create_child`.  Errors are mapped by
    :func:`_raise_child_error` — create names no existing child, so a
    rejection here is always 422.
    """
    state: DatabaseState = request.app.state.db
    try:
        record = await core_children.create_child(
            state.database,
            body.display_name,
            colour=body.colour,
            avatar_ref=body.avatar_ref,
            sort_order=body.sort_order,
        )
    except ValueError as error:
        _raise_child_error(error)
    return _child_response(record)


@router.patch(
    "/children/{child_id}",
    summary="Edit a child profile",
    response_model=AdminChildResponse,
)
async def admin_edit_child(
    child_id: int, body: AdminChildEditRequest, request: Request
) -> AdminChildResponse:
    """Edit a child profile; only supplied fields change.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the supplied
    fields are forwarded with ``exclude_unset`` semantics so an omitted
    field is never passed to :func:`nestquest_core.children.edit_child`
    and stays unchanged, while an explicit ``null`` is passed and
    rejected by the core (clearing is not supported).  An unknown child
    id is mapped to 404 and any other core ``ValueError`` to 422
    (:func:`_raise_child_error`).
    """
    state: DatabaseState = request.app.state.db
    try:
        record = await core_children.edit_child(
            state.database,
            child_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as error:
        _raise_child_error(error)
    return _child_response(record)


@router.patch(
    "/children/{child_id}/active",
    summary="Set a child's active flag",
    response_model=AdminChildResponse,
)
async def admin_set_child_active(
    child_id: int, body: AdminChildActiveRequest, request: Request
) -> AdminChildResponse:
    """Deactivate (or reactivate) a child; the profile is NEVER deleted.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: ``is_active``
    is passed straight to
    :func:`nestquest_core.children.set_child_active` — deactivation is
    the only removal path (the core has no delete, so completion
    history keeps its references).  An unknown child id is mapped to
    404 (:func:`_raise_child_error`); the body model already makes the
    core's real-bool check unreachable from this route.
    """
    state: DatabaseState = request.app.state.db
    try:
        record = await core_children.set_child_active(
            state.database, child_id, body.is_active
        )
    except ValueError as error:
        _raise_child_error(error)
    return _child_response(record)


@router.post(
    "/children/reorder",
    summary="Reorder the children's panel display order",
)
async def admin_reorder_children(
    body: AdminChildReorderRequest, request: Request
) -> dict[str, str]:
    """Rewrite the children's display order in one atomic core call.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the posted id
    order goes straight to
    :func:`nestquest_core.children.reorder_children`, which rejects a
    list that is not a complete permutation of the household (missing,
    duplicate, or unknown ids) BEFORE any write — mapped to 422 by
    :func:`_raise_child_error`, leaving the stored order untouched.  On
    success the core returns ``None``; the route answers
    ``{"status": "ok"}`` (the fresh order is read back via
    ``GET /children``).
    """
    state: DatabaseState = request.app.state.db
    try:
        await core_children.reorder_children(
            state.database, body.ordered_ids
        )
    except ValueError as error:
        _raise_child_error(error)
    return {"status": "ok"}


__all__ = ["router"]
