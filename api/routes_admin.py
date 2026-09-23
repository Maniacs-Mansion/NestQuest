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

The quest-definition routes follow the same pattern over
:mod:`nestquest_core.quest_definitions`: the body model carries the
shape, the handler builds ONE
:class:`~nestquest_core.recurrence.ScheduleRule` from the request's
``rule`` object through the model's own ``from_dict`` (rule validation
is the MODEL's construction-time job — a bad combination raises
:class:`~nestquest_core.recurrence.RuleValidationError`, never
hand-rolled here), and the call goes to
``create_quest_definition`` / ``edit_quest_definition`` /
``set_quest_definition_active``.  The title policy, the window-name
and due-time policy, the assignee checks, the whole-set window
replacement and the never-hard-delete policy (deactivation is the only
removal path) all live in the core.  Assignment is NOT settable
through the API: the core's edit path takes no assignees.  The edit
route forwards only SUPPLIED fields (``exclude_unset``), like the
children edit.

The presence routes follow the same pattern over
:mod:`nestquest_core.presence_management` — the ONE presence write
layer the HA services share, so the two planes cannot drift:

- ``PUT /children/{child_id}/presence-schedule`` sets (UPSERTS) the
  child's repeating schedule: the body's ``cycle_length_weeks``,
  ``anchor_date`` and ``pattern`` go straight into ONE
  :class:`~nestquest_core.presence.PresenceSchedule` (the model
  validates cycle length, the strict anchor date and the pattern's
  week coverage at construction), the core upserts by child (setting
  again REPLACES the one schedule a child can have) and regenerates
  the child's future instances; the response is the STORED schedule
  decoded back through the model.
- ``POST /presence-overrides`` creates one date-range override: the
  body becomes ONE :class:`~nestquest_core.presence.PresenceOverride`
  (the model validates the dates, ``end >= start``, the real bool and
  the note), the core creates it — rejecting a range that overlaps the
  same child's existing override — and regenerates; the response is
  the stored record with its ``id``.
- ``DELETE /presence-overrides/{override_id}`` deletes one override
  (children are never hard-deleted; overrides are deletable by
  design) and regenerates that override's child.  It answers
  ``{"status": "ok"}``.

Error mapping (every children, quest-definition and presence route,
deliberately narrow):

- Malformed input the body model or the path parser rejects (a missing
  or wrong-typed field, a non-integer child or definition id) is
  FastAPI's 422 before any handler code runs.
- A core ``ValueError`` reporting a NON-EXISTENT child (edit or
  set_active on an unknown id) is mapped to 404.
- A core ``ValueError`` reporting a NON-EXISTENT DEFINITION (edit or
  set_active on an unknown id — the core prefixes that error with
  ``definition_id:``) is mapped to 404.  Create's rejected-assignee
  error names a child from the BODY, not a path id, so it maps to 422.
- Every OTHER core ``ValueError`` — an empty display name, an explicit
  ``null`` colour/avatar_ref (clearing is not supported), a reorder
  list that is not a complete permutation of the children (missing,
  duplicate, or unknown ids); a rejected rule
  (:class:`~nestquest_core.recurrence.RuleValidationError`: unknown
  ``rule_type``, a shape-missing field such as a weekly rule without
  weekdays, a malformed date, a forbidden field), a bad window name or
  due time, a rejected window or assignee list (empty, duplicate,
  wrong-typed); a rejected presence schedule or override (bad cycle
  length, a pattern not covering the cycle's weeks, a malformed or
  inverted date range, an override overlapping the same child's
  existing one) — is mapped to 422: the body was well-formed JSON but
  semantically invalid, the same failure class Pydantic reports.  The
  core rejects these BEFORE any write, so a 422 never leaves a
  half-applied change behind.
- A non-existent CHILD on a presence route (setting a schedule or
  creating an override for an unknown id) is mapped to 404 through the
  SAME :func:`_raise_child_error` the children routes use — the
  message reads ``child N does not exist``.  A non-existent OVERRIDE
  on the delete route is mapped to 404 through
  :func:`_raise_presence_override_error`, keyed on the
  ``override_id:`` prefix the core's unknown-id error carries (the
  same convention as the quest-definition 404).

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
from api.nestquest_core import (
    core_children,
    core_presence,
    core_presence_management,
    core_quest_definitions,
    core_recurrence,
)

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


class AdminRuleResponse(BaseModel):
    """A definition's schedule rule as the admin plane serializes it.

    Mirrors :meth:`nestquest_core.recurrence.ScheduleRule.to_dict`: the
    model-name ``rule_type`` (e.g. ``monthly_weekday``), the weekday
    set as a sorted list, and ``None`` for every field the rule's shape
    does not use.
    """

    rule_type: str
    interval: int
    weekday_set: list[int] | None
    day_of_month: int | None
    nth_weekday: int | None
    nth_weekday_weekday: int | None
    month: int | None
    start_date: str
    end_date: str | None


class AdminAssigneeResponse(BaseModel):
    """One assigned child: the id and display name the PWA renders."""

    id: int
    display_name: str


class AdminDefinitionWindowResponse(BaseModel):
    """One window declaration: its name and optional HH:MM due time."""

    window: str
    due_time: str | None


class AdminQuestDefinitionResponse(BaseModel):
    """One quest definition as the admin plane serializes it.

    Mirrors the core's
    :class:`~nestquest_core.quest_definitions.CreatedQuestDefinition`
    bundle: the stored row (minus the internal ``schedule_rule_id``/
    ``due_time``/``created_at`` columns) plus its decoded rule,
    assignees and windows.
    """

    id: int
    title: str
    description: str | None
    icon: str | None
    is_active: bool
    rule: AdminRuleResponse
    assignees: list[AdminAssigneeResponse]
    windows: list[AdminDefinitionWindowResponse]


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


class AdminRuleRequest(BaseModel):
    """The ``rule`` object of a quest-definition create or edit body.

    The fields of :class:`~nestquest_core.recurrence.ScheduleRule` —
    nothing more: the shape is the model's, the defaults are the
    model's (``interval`` 1, ``start_date`` 1970-01-01).  Only
    ``rule_type`` is required.  The COMBINATION policy (which fields a
    shape requires and forbids, the 1..31/1..12/0..6 ranges, the strict
    ISO dates) is enforced by the model's constructor, which the route
    builds through ``from_dict`` — this model only guards the SHAPE.
    """

    rule_type: str
    interval: int = 1
    weekday_set: list[int] | None = None
    day_of_month: int | None = None
    nth_weekday: int | None = None
    nth_weekday_weekday: int | None = None
    month: int | None = None
    start_date: str = "1970-01-01"
    end_date: str | None = None


class AdminQuestDefinitionCreateRequest(BaseModel):
    """The body of ``POST /api/v1/admin/quest-definitions``.

    ``title``, ``rule``, ``assignee_child_ids`` and ``windows`` are
    required (the core rejects an empty title, a non-list or empty
    assignee/window list, and unknown window names); ``description``
    and ``icon`` are optional and default to NULL through the core.
    ``windows`` entries are a window name (``morning``) or a two-item
    ``[window, due_time]`` pair whose due time is a strict 24-hour
    HH:MM (or ``null`` for none) — both forms the core normalizes.
    """

    title: str
    rule: AdminRuleRequest
    assignee_child_ids: list[int]
    windows: list[str | tuple[str, str | None]]
    description: str | None = None
    icon: str | None = None


class AdminQuestDefinitionEditRequest(BaseModel):
    """The body of ``PATCH /api/v1/admin/quest-definitions/{definition_id}``.

    Every field is optional; ONLY the fields the request supplies are
    forwarded to :func:`nestquest_core.quest_definitions.edit_quest_definition`
    (the route dumps the model with ``exclude_unset``), so an omitted
    field stays unchanged.  An explicit ``null`` ``description``/
    ``icon`` IS passed and CLEARS the stored value (the core supports
    clearing here, unlike the children edit); an explicit ``null``
    ``rule`` or ``windows`` is passed and rejected by the core.  A
    supplied ``windows`` list REPLACES the whole window set, and
    ``assignees`` are deliberately absent — assignment is not settable
    through this route.
    """

    title: str | None = None
    description: str | None = None
    icon: str | None = None
    rule: AdminRuleRequest | None = None
    windows: list[str | tuple[str, str | None]] | None = None


class AdminQuestDefinitionActiveRequest(BaseModel):
    """The body of ``PATCH /api/v1/admin/quest-definitions/{id}/active``."""

    is_active: bool


class AdminPresenceScheduleRequest(BaseModel):
    """The body of ``PUT /api/v1/admin/children/{child_id}/presence-schedule``.

    The shape of :class:`~nestquest_core.presence.PresenceSchedule` —
    nothing more.  ``pattern`` maps each cycle week index (JSON object
    keys, coerced to ints by the model) to that week's present weekdays
    (Monday=0); every week of the cycle must be covered, which the
    PRESENCE MODEL enforces at construction, not this shape.  A week
    with an empty list means absent every day of that week.
    """

    cycle_length_weeks: int
    anchor_date: str
    pattern: dict[int, list[int]]


class AdminPresenceScheduleResponse(BaseModel):
    """A child's repeating presence schedule as the admin plane serializes it.

    The stored schedule decoded back through
    :meth:`nestquest_core.presence.PresenceSchedule.decode`: each
    pattern week is the sorted list of present weekdays, and the child
    has exactly ONE schedule (setting again replaces it).
    """

    child_id: int
    cycle_length_weeks: int
    anchor_date: str
    pattern: dict[int, list[int]]


class AdminPresenceOverrideCreateRequest(BaseModel):
    """The body of ``POST /api/v1/admin/presence-overrides``.

    The shape of :class:`~nestquest_core.presence.PresenceOverride` —
    the strict ISO dates, the ``end_date >= start_date`` order, the
    real ``is_present`` bool and the optional note are ALL enforced by
    the model's constructor, which the route builds directly from this
    body; this model only guards the SHAPE.
    """

    child_id: int
    start_date: str
    end_date: str
    is_present: bool
    note: str | None = None


class AdminPresenceOverrideResponse(BaseModel):
    """One presence override as the admin plane serializes it.

    Mirrors
    :class:`~nestquest_core.dao_presence.PresenceOverrideRecord` — the
    ``id`` is the handle the DELETE route takes.
    """

    id: int
    child_id: int
    start_date: str
    end_date: str
    is_present: bool
    note: str | None


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


#: 404 detail for a definition id the core layer reports as non-existent.
_QUEST_DEFINITION_NOT_FOUND_DETAIL = "Quest definition not found"


def _raise_quest_definition_error(error: ValueError) -> NoReturn:
    """Map a core quest-definitions ``ValueError`` onto 404 or 422.

    The mapping mirrors :func:`_raise_child_error` and stays narrow:
    the core names a missing definition by prefixing its error with
    ``definition_id:`` (edit or set_active on an unknown id — its id
    validator's message reads ``definition_id must be an integer``
    WITHOUT the colon, so a malformed id stays 422), and that one case
    is the quest-definition routes' 404.  Every other ``ValueError`` —
    including :class:`~nestquest_core.recurrence.RuleValidationError`,
    which subclasses it — becomes 422 with the core's message as the
    detail: create's rejected assignee names a child from the BODY (not
    a path id, so not 404), a rejected rule/window/title names the
    field and what to fix, and none of it leaks more than the rule it
    enforces.
    """
    if str(error).startswith("definition_id:"):
        raise HTTPException(
            status_code=404, detail=_QUEST_DEFINITION_NOT_FOUND_DETAIL
        ) from error
    raise HTTPException(status_code=422, detail=str(error)) from error


#: 404 detail for an override id the core layer reports as non-existent.
_PRESENCE_OVERRIDE_NOT_FOUND_DETAIL = "Presence override not found"


def _raise_presence_override_error(error: ValueError) -> NoReturn:
    """Map a core presence ``ValueError`` from the DELETE route onto 404/422.

    The mapping mirrors :func:`_raise_quest_definition_error`: the core
    names a missing override by prefixing its error with
    ``override_id:`` (an unknown id), and that one case is this route's
    404.  Every other ``ValueError`` — a non-integer id the path
    parser's ``int`` already makes unreachable — becomes 422.  The
    schedule and override-CREATE routes do NOT use this mapper: their
    only 404 is an unknown CHILD, mapped by :func:`_raise_child_error`.
    """
    if str(error).startswith("override_id:"):
        raise HTTPException(
            status_code=404, detail=_PRESENCE_OVERRIDE_NOT_FOUND_DETAIL
        ) from error
    raise HTTPException(status_code=422, detail=str(error)) from error


def _rule_from_request(rule: AdminRuleRequest) -> core_recurrence.ScheduleRule:
    """Build the core ScheduleRule from the request's ``rule`` object.

    The recurrence model validates AT CONSTRUCTION — through its own
    ``from_dict`` here, which raises
    :class:`~nestquest_core.recurrence.RuleValidationError` (a
    ``ValueError``) for any bad combination — so the route re-implements
    no rule policy of its own.
    """
    return core_recurrence.ScheduleRule.from_dict(
        rule.model_dump(exclude_unset=True)
    )


def _rule_response(rule: core_recurrence.ScheduleRule) -> AdminRuleResponse:
    """Serialize one core ScheduleRule via its lossless dict form."""
    return AdminRuleResponse(**rule.to_dict())


def _quest_definition_response(
    bundle: core_quest_definitions.CreatedQuestDefinition,
) -> AdminQuestDefinitionResponse:
    """Serialize one core CreatedQuestDefinition into the payload."""
    return AdminQuestDefinitionResponse(
        id=bundle.definition.id,
        title=bundle.definition.title,
        description=bundle.definition.description,
        icon=bundle.definition.icon,
        is_active=bundle.definition.is_active,
        rule=_rule_response(bundle.rule),
        assignees=[
            AdminAssigneeResponse(id=child.id, display_name=child.display_name)
            for child in bundle.assignees
        ],
        windows=[
            AdminDefinitionWindowResponse(
                window=window.window, due_time=window.due_time
            )
            for window in bundle.windows
        ],
    )


def _presence_schedule_response(
    schedule: core_presence.PresenceSchedule,
) -> AdminPresenceScheduleResponse:
    """Serialize one decoded core PresenceSchedule into the payload."""
    return AdminPresenceScheduleResponse(
        child_id=schedule.child_id,
        cycle_length_weeks=schedule.cycle_length_weeks,
        anchor_date=schedule.anchor_date.isoformat(),
        pattern={
            week: sorted(days) for week, days in schedule.pattern.items()
        },
    )


def _presence_override_response(
    record: core_presence_management.PresenceOverrideRecord,
) -> AdminPresenceOverrideResponse:
    """Serialize one core PresenceOverrideRecord into the payload."""
    return AdminPresenceOverrideResponse(
        id=record.id,
        child_id=record.child_id,
        start_date=record.start_date,
        end_date=record.end_date,
        is_present=record.is_present,
        note=record.note,
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


@router.post(
    "/quest-definitions",
    summary="Create a quest definition",
    status_code=201,
    response_model=AdminQuestDefinitionResponse,
)
async def admin_create_quest_definition(
    body: AdminQuestDefinitionCreateRequest, request: Request
) -> AdminQuestDefinitionResponse:
    """Create a quest definition (rule + assignees + windows) and return it.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the body model
    carries the shape, the request's ``rule`` becomes ONE
    :class:`~nestquest_core.recurrence.ScheduleRule` (validated by the
    model's constructor, :func:`_rule_from_request`), and the title
    policy, the assignee and window policies and the atomic
    rule+definition+assignees+windows persistence all live in
    :func:`nestquest_core.quest_definitions.create_quest_definition`.
    Create names no existing definition, so a missing definition can
    never be its error: every rejection here is 422
    (:func:`_raise_quest_definition_error`).
    """
    state: DatabaseState = request.app.state.db
    try:
        bundle = await core_quest_definitions.create_quest_definition(
            state.database,
            body.title,
            _rule_from_request(body.rule),
            body.assignee_child_ids,
            body.windows,
            description=body.description,
            icon=body.icon,
        )
    except ValueError as error:
        _raise_quest_definition_error(error)
    return _quest_definition_response(bundle)


@router.patch(
    "/quest-definitions/{definition_id}",
    summary="Edit a quest definition",
    response_model=AdminQuestDefinitionResponse,
)
async def admin_edit_quest_definition(
    definition_id: int,
    body: AdminQuestDefinitionEditRequest,
    request: Request,
) -> AdminQuestDefinitionResponse:
    """Edit a quest definition; only supplied fields change.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the supplied
    fields are forwarded with ``exclude_unset`` semantics so an omitted
    field is never passed to
    :func:`nestquest_core.quest_definitions.edit_quest_definition` and
    stays unchanged; a supplied ``windows`` list replaces the WHOLE
    window set in the core, and a supplied ``rule`` is rebuilt into a
    ScheduleRule (:func:`_rule_from_request`, validated by the model).
    An explicit ``null`` ``rule``/``windows`` reaches the core as None
    and is rejected there (422), while an explicit ``null``
    ``description``/``icon`` clears the stored value — the core edit
    path supports clearing, unlike the children edit.  An unknown
    definition id is mapped to 404 and any other core ``ValueError``
    to 422 (:func:`_raise_quest_definition_error`).
    """
    state: DatabaseState = request.app.state.db
    supplied = body.model_dump(exclude_unset=True)
    try:
        if isinstance(body.rule, AdminRuleRequest):
            supplied["rule"] = _rule_from_request(body.rule)
        bundle = await core_quest_definitions.edit_quest_definition(
            state.database, definition_id, **supplied
        )
    except ValueError as error:
        _raise_quest_definition_error(error)
    return _quest_definition_response(bundle)


@router.patch(
    "/quest-definitions/{definition_id}/active",
    summary="Set a quest definition's active flag",
    response_model=AdminQuestDefinitionResponse,
)
async def admin_set_quest_definition_active(
    definition_id: int,
    body: AdminQuestDefinitionActiveRequest,
    request: Request,
) -> AdminQuestDefinitionResponse:
    """Deactivate (or reactivate) a definition; it is NEVER deleted.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: ``is_active``
    goes straight to
    :func:`nestquest_core.quest_definitions.set_quest_definition_active`
    — deactivation is the only removal path (the row, rule, assignees
    and windows all survive, so completion history keeps its
    references).  An unknown definition id is mapped to 404
    (:func:`_raise_quest_definition_error`); the body model already
    makes the core's real-bool check unreachable from this route.
    """
    state: DatabaseState = request.app.state.db
    try:
        bundle = await core_quest_definitions.set_quest_definition_active(
            state.database, definition_id, body.is_active
        )
    except ValueError as error:
        _raise_quest_definition_error(error)
    return _quest_definition_response(bundle)


@router.put(
    "/children/{child_id}/presence-schedule",
    summary="Set a child's repeating presence schedule",
    response_model=AdminPresenceScheduleResponse,
)
async def admin_set_presence_schedule(
    child_id: int, body: AdminPresenceScheduleRequest, request: Request
) -> AdminPresenceScheduleResponse:
    """Set (upsert) a child's repeating presence schedule.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the body model
    carries the shape, and the cycle-length, anchor-date and
    pattern-coverage policies all live in the
    :class:`~nestquest_core.presence.PresenceSchedule` constructor the
    core builds the schedule with — setting again REPLACES the child's
    one schedule, and the core regenerates the child's future instances
    so they track the new presence.  Errors are mapped by
    :func:`_raise_child_error`: an unknown child is 404, a rejected
    schedule 422.
    """
    state: DatabaseState = request.app.state.db
    try:
        schedule = await core_presence_management.set_presence_schedule(
            state.database,
            child_id,
            body.cycle_length_weeks,
            body.anchor_date,
            body.pattern,
        )
    except ValueError as error:
        _raise_child_error(error)
    return _presence_schedule_response(schedule)


@router.post(
    "/presence-overrides",
    summary="Create a date-range presence override",
    status_code=201,
    response_model=AdminPresenceOverrideResponse,
)
async def admin_create_presence_override(
    body: AdminPresenceOverrideCreateRequest, request: Request
) -> AdminPresenceOverrideResponse:
    """Create one date-range presence override and return it with its id.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the body model
    carries the shape, and the date/order/bool/note policies live in
    the :class:`~nestquest_core.presence.PresenceOverride` constructor
    while the same-child no-overlap policy lives in the core's create
    path — which then regenerates the child's future instances so an
    absent range removes them and a present range restores them.  The
    response carries the stored ``id``, the handle
    ``DELETE /presence-overrides/{id}`` takes.

    Errors are mapped by :func:`_raise_child_error`: an unknown child
    is 404; a rejected override (malformed or inverted dates, an
    overlapping range) is 422.
    """
    state: DatabaseState = request.app.state.db
    try:
        record = await core_presence_management.create_presence_override(
            state.database,
            body.child_id,
            body.start_date,
            body.end_date,
            body.is_present,
            note=body.note,
        )
    except ValueError as error:
        _raise_child_error(error)
    return _presence_override_response(record)


@router.delete(
    "/presence-overrides/{override_id}",
    summary="Delete a presence override",
)
async def admin_delete_presence_override(
    override_id: int, request: Request
) -> dict[str, str]:
    """Delete one presence override; children are never hard-deleted.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the id goes
    straight to
    :func:`nestquest_core.presence_management.delete_presence_override`,
    which looks the override up first (an unknown id is refused BEFORE
    any delete), removes it and regenerates ITS child's future
    instances — the id, never a caller-supplied child, decides which
    child's presence is rebuilt.  On success the route answers
    ``{"status": "ok"}``.

    Error mapping (:func:`_raise_presence_override_error`): an unknown
    override id is 404; every other core ``ValueError`` is 422.
    """
    state: DatabaseState = request.app.state.db
    try:
        await core_presence_management.delete_presence_override(
            state.database, override_id
        )
    except ValueError as error:
        _raise_presence_override_error(error)
    return {"status": "ok"}


__all__ = ["router"]
