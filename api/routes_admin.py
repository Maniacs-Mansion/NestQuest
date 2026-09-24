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

The uncomplete and regenerate routes (task da0226b3) follow the same
pattern over :mod:`nestquest_core.completion` and
:mod:`nestquest_core.materialize`:

- ``POST /instances/{instance_id}/uncomplete`` reverses ONE completion:
  the handler takes the actor from the VERIFIED JWT (``actor_source``
  ``'user'`` with ``actor_user_id`` = the token's ``sub`` — the D-008
  user-actor shape, so the reversal is attributed to the admin who
  called it) and calls :func:`nestquest_core.completion.uncomplete_instance`.
  The append-only discipline lives in the core: a reversal APPENDS an
  ``uncompleted`` event after the original ``completed`` row — the
  original is never edited or deleted — and the instance's derived
  state (recomputed from the latest event) returns to ``open``.  On an
  ACTUAL reversal (``CompletionResult.appended`` True) the route
  publishes the ``nestquest_quest_uncompleted`` transition through
  :func:`api.transitions.publish_quest_uncompleted` (the payload built
  by the core builder); an already-open no-op publishes nothing.  The
  response carries the derived ``state`` and whether THIS call
  ``appended``.
- ``POST /regenerate`` re-materializes the rolling horizon through the
  same core path the integration's config/presence changes use.  The
  body names ONE scope: ``household`` (the default —
  :func:`nestquest_core.materialize.materialize` over
  ``[today, today + const.DEFAULT_HORIZON_DAYS]``, the core's default
  horizon; the API config carries no horizon knob of its own),
  ``definition`` (:func:`nestquest_core.materialize.regenerate_for_definition`
  — deletes the definition's open future instances and re-runs the
  walk), or ``child``
  (:func:`nestquest_core.materialize.regenerate_for_child`).
  The upsert is idempotent, so re-running never duplicates an
  instance.  The response carries the scope, the scoped id (if any)
  and the core's upsert ``count``.

The history routes (task 2d2dda53) follow the same pattern over
:mod:`nestquest_core.history` — the ONE read-only history layer, which
owns every rule so the two routes cannot drift:

- ``GET /history?filter=all|reversals|missed&start=YYYY-MM-DD&end=YYYY-MM-DD``
  returns the history rows for ONE filter over the CLOSED due-date
  range ``[start, end]``: ``all`` (every completion event — completed
  AND uncompleted — whose instance is due in the range), ``reversals``
  (the uncompleted events only) and ``missed`` (the DERIVED past-due
  open instances, computed by the core's own derive-state rule —
  ``missed`` is never a stored event_type and nothing is appended).
  The range scopes by the instance's ``due_date`` (the Feature 13
  rule: history asks what happened to the tasks due that day), not the
  event's wall-clock stamp.  The filter and date-range policies live
  in the core (strict ``YYYY-MM-DD``, ``end >= start``, a
  ``ValueError`` naming the offending field); the handler is a thin
  adapter that threads ONE clock read (:func:`_local_now`, the missed
  derivation's ``today``) and serializes the core's rows.
- ``GET /history.csv?...`` exports the SAME filtered range as CSV:
  ONE :func:`nestquest_core.history.export_history_csv` call — the
  same query path the JSON route uses — answered as ``text/csv`` with
  a ``Content-Disposition`` attachment filename and the documented,
  stable header row (Admin spec §5 event-row fields).

The snapshot route (task ef3f4877) is the admin-plane twin of the
panel's ``GET /api/v1/panel/snapshot`` for the admin PWA's Today tab —
the PWA is internet-facing and never holds the panel service token
(D-012), so it reads the same snapshot here:

- ``GET /snapshot`` threads ONE clock read (:func:`_local_now`) into
  :func:`nestquest_core.snapshot.build_snapshot` and shapes each
  child's instances through
  :func:`nestquest_core.snapshot.instance_payload` with
  ``include_missed=True`` — admin payloads KEEP missed instances with
  their ``missed`` state (D-009), where the panel omits them.  The
  body is the panel's documented shape (``today_iso``, ``cycle_day``,
  ``children`` with the per-child presence, rollup counts and
  ``instances``); the builder, the state derivation and the shaping
  all live in the core.

The settings routes (task 2b3de7e5) follow the same pattern over
:mod:`nestquest_core.settings_store` — the API's OWN durable settings
store.  The API now OWNS settings in the database (a validated JSON
document in the existing ``nestquest_meta_state`` key/value table); the
integration's Home-Assistant config-entry options remain a temporary,
SEPARATE source until Feature 18 wires the client to the API — the two
are deliberately not unified here:

- ``GET /settings`` returns the current effective settings: all ten
  documented fields (the rolling horizon, the day rollover time, the
  notify target, the three notification times and the four enable
  toggles) — the defaults on a fresh database.
- ``PATCH /settings`` updates ONLY the supplied fields: the body is a
  JSON object of settings field names to new values, passed STRAIGHT
  to :func:`nestquest_core.settings_store.update_settings` — the
  unknown-field rejection, the per-field validation (the core settings
  validators: a positive int, strict ``HH:MM`` strings, real booleans)
  and the validate-everything-before-write atomicity all live in the
  core, so a rejected update never changes the stored settings.  A
  JSON ``null`` value resets its field to the default (the settings
  module's uniform None-as-absent rule).  The response is the updated
  effective settings, the same shape ``GET`` returns.

The missed-sweep trigger (task 058c7b69) follows the same pattern over
:mod:`nestquest_core.sweep` — the HA-free sweep policy the
integration's rollover listener shares:

- ``POST /missed-sweep`` runs the sweep for the API host's local
  ``today`` (ONE :func:`_local_now` clock read threaded into the core
  call) and publishes each returned ``(event_type, payload)`` pair
  DIRECTLY on the app's ONE transition publisher — the sweep-built
  payload, never re-fetched (the core commits its watermark before
  returning, so a failed re-fetch after it would lose the missed event
  forever), the same publish-what-the-core-built shape
  api/scheduler.py uses.  The watermark rule
  (a same-day rerun announces nothing, a post-downtime run sweeps the
  accumulated window once), the no-completion-event rule and the
  read-only-over-the-domain-tables guarantee all live in the core; the
  response reports how many transitions were published.

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
- The UNCOMPLETE route maps the core completion layer's unknown-
  ``instance_id`` error (prefixed ``instance_id:``, the same
  convention the panel complete route keys on) to 404; every other
  core ``ValueError`` — a rejected actor shape, which a verified token
  without a usable ``sub`` claim produces — is 422: the credential
  authenticated but the reversal it asks for names no subject to
  attribute.  Anything ELSE re-raises: no unexpected failure is
  swallowed into a 4xx.
- The REGENERATE route's only 404s are the unknown scope ids, decided
  by ONE existence read (the definitions/children DAO ``get``) BEFORE
  any core call — the core's regenerate path itself takes no existence
  stance.  Every core ``ValueError`` (a rejected horizon, a malformed
  date — unreachable from this body model, but mapped anyway) is 422;
  anything else re-raises.
- The HISTORY routes have no path ids, so they have no 404 case: a
  missing query parameter (the request's shape) is FastAPI's 422
  before any handler code runs, and every core ``ValueError`` — an
  unknown filter, a non-strict or inverted date range, each naming the
  offending field (``filter`` / ``start`` / ``end``) — is 422
  (:func:`_raise_history_error`): well-formed but semantically
  invalid, the same failure class Pydantic reports.  Only
  ``ValueError`` is caught, so an unexpected failure re-raises rather
  than becoming a 4xx.
- The SETTINGS routes have no path ids either, so they have no 404
  case: a body that is not a JSON object is FastAPI's 422 before any
  handler code runs, and every core ``ValueError`` — an unknown field
  or an invalid value, each naming the offending field, raised BEFORE
  any write so the stored settings are never half-changed — is 422
  (:func:`_raise_settings_error`).  Only ``ValueError`` is caught, so
  an unexpected failure re-raises rather than becoming a 4xx.

PATCH edit semantics: the body model's fields are optional and only
SUPPLIED fields are forwarded (``model_dump(exclude_unset=True)``), so
an omitted field is never passed to
:func:`nestquest_core.children.edit_child` and stays unchanged — while
an explicit ``null`` IS passed and is rejected by the core rather than
silently ignored.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator, model_validator

from api import transitions as api_transitions
from api.auth import require_admin
from api.database import DatabaseState
from api.nestquest_core import (
    core_children,
    core_completion,
    core_const,
    core_dao_children,
    core_dao_rules,
    core_history,
    core_materialize,
    core_presence,
    core_presence_management,
    core_quest_definitions,
    core_recurrence,
    core_settings,
    core_settings_store,
    core_snapshot,
    core_sweep,
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


class AdminQuestDefinitionListResponse(BaseModel):
    """The definitions list: every definition, active AND inactive, by id."""

    definitions: list[AdminQuestDefinitionResponse]


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


class AdminUncompleteResponse(BaseModel):
    """The result of ``POST /api/v1/admin/instances/{id}/uncomplete``.

    ``state`` is the instance's derived state AFTER the reversal —
    ``open``, or ``missed`` when it is past due — and ``appended``
    reports whether THIS call appended the reversal event (``False``
    for an already-open no-op).
    """

    instance_id: int
    state: str
    appended: bool


class AdminRegenerateRequest(BaseModel):
    """The body of ``POST /api/v1/admin/regenerate``.

    ONE scope per request: ``household`` (the default) re-materializes
    every active definition over the rolling horizon; ``definition``
    and ``child`` scope the rebuild to one id.  The model enforces the
    scope/id pairing so the handler never has to guess: an id without
    its scope, a scope without its id, or a zero/negative id is a
    validation error (422) before any handler code runs.
    """

    scope: Literal["household", "definition", "child"] = "household"
    definition_id: int | None = None
    child_id: int | None = None

    @field_validator("definition_id", "child_id")
    @classmethod
    def _positive(cls, value: int | None) -> int | None:
        """Reject zero and negative ids with a validation error."""
        if value is not None and value < 1:
            raise ValueError(
                "definition_id and child_id must be positive integers"
            )
        return value

    @model_validator(mode="after")
    def _scope_matches_ids(self) -> "AdminRegenerateRequest":
        """Reject an id that does not belong to the requested scope."""
        if self.scope == "household":
            if self.definition_id is not None or self.child_id is not None:
                raise ValueError(
                    "scope 'household' takes no definition_id or child_id"
                )
        elif self.scope == "definition":
            if self.definition_id is None:
                raise ValueError("scope 'definition' requires definition_id")
            if self.child_id is not None:
                raise ValueError("scope 'definition' must not carry child_id")
        else:
            if self.child_id is None:
                raise ValueError("scope 'child' requires child_id")
            if self.definition_id is not None:
                raise ValueError(
                    "scope 'child' must not carry definition_id"
                )
        return self


class AdminRegenerateResponse(BaseModel):
    """What a regenerate request rebuilt.

    ``scope`` echoes the request; ``definition_id``/``child_id`` carry
    the scoped id (both ``None`` for the household); ``count`` is the
    number of instances the core walk upserted — the core's idempotent
    count, so a re-run refreshes rows in place and never duplicates.
    """

    scope: str
    definition_id: int | None
    child_id: int | None
    count: int


class AdminHistoryRow(BaseModel):
    """One history row as the admin plane serializes it.

    Mirrors :class:`nestquest_core.history.HistoryRow` — the Admin spec
    §5 event-row fields, the same set the CSV export's header carries.
    A stored event carries its UTC ``occurred_at`` stamp and the
    ``completed``/``uncompleted`` ``event_type``; a derived missed row
    (``missed`` is NEVER a stored event_type) carries ``event_type``
    ``'missed'``, ``occurred_at`` ``None`` (there is no event) and the
    ``nightly sweep`` actor.
    """

    occurred_at: str | None
    event_type: str
    child_name: str
    child_id: int
    quest_title: str
    instance_id: int
    window: str
    due_date: str
    due_time: str | None
    actor: str
    was_on_time: bool | None


class AdminHistoryResponse(BaseModel):
    """The history query's answer.

    ``filter``/``start``/``end`` echo the request, ``count`` is the row
    count, and ``rows`` are the core's rows in its deterministic order
    (``due_date``, then instance, then event id — the per-instance
    append order, so a completion and its reversal keep their order).
    """

    filter: str
    start: str
    end: str
    count: int
    rows: list[AdminHistoryRow]


class AdminSettingsResponse(BaseModel):
    """The effective settings as the admin plane serializes them.

    Mirrors the core :class:`~nestquest_core.settings.NestQuestSettings`
    — all TEN documented fields, resolved (every absent stored field
    already fell back to its default in the core).  The same shape both
    the GET and the PATCH route answer with.
    """

    horizon_days: int
    day_rollover_time: str
    notify_target: str
    morning_summary_time: str
    afternoon_reminder_time: str
    end_of_day_report_time: str
    morning_summary_enabled: bool
    afternoon_reminder_enabled: bool
    end_of_day_report_enabled: bool
    celebration_enabled: bool


class AdminMissedSweepResponse(BaseModel):
    """The result of ``POST /api/v1/admin/missed-sweep``.

    ``fired`` is the number of ``nestquest_quest_missed`` transitions
    the run built AND this route published on the SSE stream — zero
    when the sweep's watermark already covers today (a same-day rerun).
    """

    fired: int


class AdminInstancePayload(BaseModel):
    """One instance in the admin snapshot payload.

    Mirrors :func:`nestquest_core.snapshot.instance_payload` with
    ``include_missed=True``: ``state`` is ``open`` | ``completed`` |
    ``missed`` (admin payloads keep missed instances, D-009),
    ``on_time`` passes the completion event's flag through verbatim
    (``None`` unless completed), and ``completed_at`` is the event's
    UTC timestamp when completed.
    """

    id: int
    definition_id: int
    child_id: int
    title: str
    icon: str | None
    window: str
    due_time: str | None
    state: str
    overdue: bool
    completed_at: str | None
    on_time: bool | None


class AdminChildSnapshotPayload(BaseModel):
    """One child's day: presence, rollup counts, and today's instances."""

    child_id: int
    child_name: str
    present: bool
    #: ISO date of the child's next present day while they are away;
    #: ``None`` when the child is present today.
    next_present: str | None
    due_today: int
    completed_today: int
    remaining_today: int
    completion_pct: int
    instances: list[AdminInstancePayload]


class AdminSnapshotResponse(BaseModel):
    """Today's whole household snapshot for the admin Today tab.

    The panel snapshot's shape (``today_iso``, ``cycle_day``,
    ``children`` in the household's sort order), with missed instances
    kept in each child's ``instances``.
    """

    today_iso: str
    cycle_day: int
    children: list[AdminChildSnapshotPayload]


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


#: 404 detail for an instance id the core layer reports as non-existent.
_QUEST_INSTANCE_NOT_FOUND_DETAIL = "Quest instance not found"


def _raise_instance_error(error: ValueError) -> NoReturn:
    """Map a core completion ``ValueError`` onto 404 or 422 and raise it.

    The uncomplete route's mapping, keyed the same way the panel
    complete route keys its 404: the core names a missing instance by
    prefixing its error with ``instance_id:``
    (:func:`nestquest_core.completion.uncomplete_instance` on an
    unknown id), and that one case is this route's 404.  Every other
    ``ValueError`` — a rejected actor shape, which a verified token
    without a usable ``sub`` claim produces — is 422 with the core's
    message as the detail.  The route catches ONLY ``ValueError``, so
    an unexpected failure propagates untouched.
    """
    if str(error).startswith("instance_id:"):
        raise HTTPException(
            status_code=404, detail=_QUEST_INSTANCE_NOT_FOUND_DETAIL
        ) from error
    raise HTTPException(status_code=422, detail=str(error)) from error


def _raise_regenerate_error(error: ValueError) -> NoReturn:
    """Map a core materialization ``ValueError`` onto 422 and raise it.

    The regenerate route's 404s are decided BEFORE the core call (the
    handler's own existence reads of the scoped id), so every
    ``ValueError`` that survives to here is a rejected argument — a
    malformed horizon or date the core refuses before any write — and
    is 422 with the core's message as the detail.  Nothing else is
    caught: an unexpected failure re-raises rather than becoming a 4xx.
    """
    raise HTTPException(status_code=422, detail=str(error)) from error


def _raise_history_error(error: ValueError) -> NoReturn:
    """Map a core history ``ValueError`` onto 422 and raise it.

    The history routes have no path ids, so they have no 404 case:
    every ``ValueError`` that survives to here is a rejected argument —
    an unknown filter, a non-strict date, or an inverted range, each
    raised by the core naming the offending field (``filter`` /
    ``start`` / ``end``) BEFORE any read — and is 422 with the core's
    message as the detail.  Only ``ValueError`` is caught by the
    handlers, so an unexpected failure re-raises rather than becoming a
    4xx.
    """
    raise HTTPException(status_code=422, detail=str(error)) from error


def _raise_settings_error(error: ValueError) -> NoReturn:
    """Map a core settings-store ``ValueError`` onto 422 and raise it.

    The settings routes have no path ids either, so they have no 404
    case: every ``ValueError`` that survives to here is a rejected
    change — an unknown field or an invalid value, each raised by the
    core naming the offending field BEFORE any write, so the stored
    settings are never half-changed — and is 422 with the core's
    message as the detail.  Only ``ValueError`` is caught, so an
    unexpected failure re-raises rather than becoming a 4xx.
    """
    raise HTTPException(status_code=422, detail=str(error)) from error


def _raise_sweep_error(error: ValueError) -> NoReturn:
    """Map a core missed-sweep ``ValueError`` onto 422 and raise it.

    The sweep route has no path ids, so it has no 404 case: a core
    ``ValueError`` — a rejected date the sweep's query refuses before
    any read, unreachable from this handler because ``today`` comes
    from the route's own clock read — is 422 with the core's message
    as the detail.  Only ``ValueError`` is caught, so an unexpected
    failure re-raises rather than becoming a 4xx.
    """
    raise HTTPException(status_code=422, detail=str(error)) from error


def _local_now() -> datetime.datetime:
    """Return the API host's local time as ONE timezone-aware clock read.

    Same discipline as the panel route's clock read: a single
    ``now().astimezone()`` read anchors the household-local date the
    regenerate horizon and the uncomplete stamp derive from, so the
    calendar date can never disagree inside one request.  Kept as a
    module function so tests pin the instant the same way the panel
    route's ``_local_now`` is pinned.
    """
    return datetime.datetime.now().astimezone()


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


@router.get(
    "/quest-definitions",
    summary="List quest definitions",
    response_model=AdminQuestDefinitionListResponse,
)
async def admin_list_quest_definitions(
    request: Request,
) -> AdminQuestDefinitionListResponse:
    """Return every quest definition in rising id order.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: one
    :func:`nestquest_core.quest_definitions.list_all_definitions` call,
    active AND inactive definitions included (the admin screen manages
    both), each serialized exactly as the create/edit responses are.
    """
    state: DatabaseState = request.app.state.db
    bundles = await core_quest_definitions.list_all_definitions(
        state.database
    )
    return AdminQuestDefinitionListResponse(
        definitions=[_quest_definition_response(bundle) for bundle in bundles]
    )


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


@router.post(
    "/instances/{instance_id}/uncomplete",
    summary="Reverse one completion (append a reversal event)",
    response_model=AdminUncompleteResponse,
)
async def admin_uncomplete_instance(
    instance_id: int,
    request: Request,
    claims: Annotated[dict[str, object], Depends(require_admin)],
) -> AdminUncompleteResponse:
    """Reverse one completion; the original event is never touched.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  ``claims`` is the SAME
    verified-claims dict that dependency produced (FastAPI's
    per-request dependency cache), and the reversal is attributed to
    it: ``actor_source="user"`` with ``actor_user_id`` = the token's
    ``sub`` — the D-008 user-actor shape, ``actor_child_id`` never
    sent — so the completion log records WHICH admin reversed it.

    Thin adapter: ONE timezone-aware clock read (:func:`_local_now`)
    and ONE :func:`nestquest_core.completion.uncomplete_instance` call
    — the append-only discipline (a reversal APPENDS an ``uncompleted``
    event after the original ``completed`` row, which is never edited
    or deleted), the already-open no-op and the derived-state
    recomputation all live in the core layer.

    On an ACTUAL reversal (``CompletionResult.appended`` True) the
    route publishes the ``nestquest_quest_uncompleted`` transition on
    the SSE stream through
    :func:`api.transitions.publish_quest_uncompleted` (the payload is
    built by the core builder, never hand-built here; fan-out is
    fire-and-forget, see api/events.py).  An already-open no-op
    (``appended`` False) publishes nothing.

    Response: the derived ``state`` after the reversal — ``open``, or
    ``missed`` when the instance is past due — and whether THIS call
    ``appended``.  Error mapping (:func:`_raise_instance_error`): an
    unknown instance is 404; every other core ``ValueError`` is 422.
    """
    state: DatabaseState = request.app.state.db
    database = state.database
    now = _local_now()
    sub = claims.get("sub")
    try:
        result = await core_completion.uncomplete_instance(
            database,
            instance_id,
            actor_source="user",
            actor_user_id=sub if isinstance(sub, str) else None,
            now=now,
        )
    except ValueError as error:
        _raise_instance_error(error)
    if result.appended:
        # An ACTUAL reversal: announce the transition once.  A no-op
        # (already open) publishes nothing.
        await api_transitions.publish_quest_uncompleted(
            database, instance_id, request.app.state.publisher
        )
    return AdminUncompleteResponse(
        instance_id=instance_id,
        state=str(result),
        appended=result.appended,
    )


@router.post(
    "/regenerate",
    summary="Re-materialize the rolling horizon for one scope",
    response_model=AdminRegenerateResponse,
)
async def admin_regenerate(
    body: AdminRegenerateRequest, request: Request
) -> AdminRegenerateResponse:
    """Re-materialize the rolling horizon for the requested scope.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter over the SAME
    materialization path the integration's config/presence changes
    trigger, one scope per request:

    - ``household`` (the default): ONE
      :func:`nestquest_core.materialize.materialize` call over
      ``[today, today + const.DEFAULT_HORIZON_DAYS]`` — the core's
      default horizon, which sizes the window here because the API
      config carries no horizon knob of its own.  The walk is an
      idempotent upsert: re-running refreshes rows in place and never
      duplicates an instance.
    - ``definition``: ONE existence read
      (:class:`~nestquest_core.dao_rules.QuestDefinitionsDao.get` — an
      unknown id is 404 BEFORE any core call, which the core's
      regenerate path itself takes no stance on), then
      :func:`nestquest_core.materialize.regenerate_for_definition`.
    - ``child``: the same shape through
      :class:`~nestquest_core.dao_children.ChildrenDao.get` and
      :func:`nestquest_core.materialize.regenerate_for_child`.

    The ONE clock read (:func:`_local_now`) threads the household-local
    ``today`` into every core call so the walk's no-past guard and the
    delete cutoff share one anchor.  Every core call returns the
    upsert ``count``, which the response passes through.  Error
    mapping (:func:`_raise_regenerate_error`): every core
    ``ValueError`` is 422; the scope-id 404s are decided above.
    """
    state: DatabaseState = request.app.state.db
    database = state.database
    today = _local_now().date()

    if body.scope == "household":
        end_date = today + datetime.timedelta(
            days=core_const.DEFAULT_HORIZON_DAYS
        )
        try:
            count = await core_materialize.materialize(
                database,
                today.isoformat(),
                end_date.isoformat(),
                today=today,
            )
        except ValueError as error:
            _raise_regenerate_error(error)
        return AdminRegenerateResponse(
            scope="household", definition_id=None, child_id=None,
            count=count,
        )

    if body.scope == "definition":
        definition_id = body.definition_id
        # The request model's scope/id consistency validator already
        # guarantees the id for this scope; this only narrows the type.
        assert definition_id is not None
        definition = await core_dao_rules.QuestDefinitionsDao(
            database
        ).get(definition_id)
        if definition is None:
            raise HTTPException(
                status_code=404, detail=_QUEST_DEFINITION_NOT_FOUND_DETAIL
            )
        try:
            count = await core_materialize.regenerate_for_definition(
                database, definition_id, today=today
            )
        except ValueError as error:
            _raise_regenerate_error(error)
        return AdminRegenerateResponse(
            scope="definition",
            definition_id=definition_id,
            child_id=None,
            count=count,
        )

    child_id = body.child_id
    # Same model guarantee as the definition scope above.
    assert child_id is not None
    child = await core_dao_children.ChildrenDao(database).get(child_id)
    if child is None:
        raise HTTPException(status_code=404, detail=_CHILD_NOT_FOUND_DETAIL)
    try:
        count = await core_materialize.regenerate_for_child(
            database, child_id, today=today
        )
    except ValueError as error:
        _raise_regenerate_error(error)
    return AdminRegenerateResponse(
        scope="child", definition_id=None, child_id=child_id, count=count
    )


def _history_row_response(row: core_history.HistoryRow) -> AdminHistoryRow:
    """Serialize one core HistoryRow into the documented payload."""
    return AdminHistoryRow(
        occurred_at=row.occurred_at,
        event_type=row.event_type,
        child_name=row.child_name,
        child_id=row.child_id,
        quest_title=row.quest_title,
        instance_id=row.instance_id,
        window=row.window,
        due_date=row.due_date,
        due_time=row.due_time,
        actor=row.actor,
        was_on_time=row.was_on_time,
    )


def _settings_response(
    settings: core_settings.NestQuestSettings,
) -> AdminSettingsResponse:
    """Serialize one core NestQuestSettings into the documented payload.

    Explicit field-by-field (not ``dataclasses.asdict``) so the payload
    stays pinned to the ten documented fields even if the core
    dataclass later grows another one.
    """
    return AdminSettingsResponse(
        horizon_days=settings.horizon_days,
        day_rollover_time=settings.day_rollover_time,
        notify_target=settings.notify_target,
        morning_summary_time=settings.morning_summary_time,
        afternoon_reminder_time=settings.afternoon_reminder_time,
        end_of_day_report_time=settings.end_of_day_report_time,
        morning_summary_enabled=settings.morning_summary_enabled,
        afternoon_reminder_enabled=settings.afternoon_reminder_enabled,
        end_of_day_report_enabled=settings.end_of_day_report_enabled,
        celebration_enabled=settings.celebration_enabled,
    )


@router.get(
    "/history",
    summary="Query the completion history for one filter and range",
    response_model=AdminHistoryResponse,
)
async def admin_history_query(
    request: Request,
    start: str,
    end: str,
    filter: str = "all",
) -> AdminHistoryResponse:
    """Return the history rows for one filter over the closed range.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: ``filter``
    (default ``all``), ``start`` and ``end`` go straight to
    :func:`nestquest_core.history.query_history` as STRINGS — the
    filter policy (``all`` / ``reversals`` / ``missed``) and the
    date-range policy (strict ``YYYY-MM-DD``, ``end >= start``) live in
    the core, which raises a ``ValueError`` naming the offending field;
    the handler only threads ONE clock read (:func:`_local_now`) as the
    missed derivation's ``today`` and serializes the returned rows.
    ``start``/``end`` are required query parameters (missing is
    FastAPI's 422 before any handler code runs); every core
    ``ValueError`` is 422 (:func:`_raise_history_error`).
    """
    state: DatabaseState = request.app.state.db
    today = _local_now().date()
    try:
        rows = await core_history.query_history(
            state.database, filter, start, end, today=today
        )
    except ValueError as error:
        _raise_history_error(error)
    return AdminHistoryResponse(
        filter=filter,
        start=start,
        end=end,
        count=len(rows),
        rows=[_history_row_response(row) for row in rows],
    )


@router.get(
    "/history.csv",
    summary="Export the completion history as CSV",
    response_class=Response,
)
async def admin_history_csv(
    request: Request,
    start: str,
    end: str,
    filter: str = "all",
) -> Response:
    """Export the SAME filtered history range as a CSV attachment.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter over ONE
    :func:`nestquest_core.history.export_history_csv` call — the same
    query path the JSON route uses, so the CSV can never drift from the
    query's filtered range — with the core's validation policy and the
    :mod:`csv`-based serialization (stable documented header row, RFC
    4180 quoting) living in the core.  The answer is ``text/csv`` with
    a ``Content-Disposition`` attachment filename naming the range;
    the range is core-validated strict ``YYYY-MM-DD`` by the time the
    filename is built, so it is injection-safe.  Error mapping is the
    JSON route's (:func:`_raise_history_error`).
    """
    state: DatabaseState = request.app.state.db
    today = _local_now().date()
    try:
        csv_text = await core_history.export_history_csv(
            state.database, filter, start, end, today=today
        )
    except ValueError as error:
        _raise_history_error(error)
    filename = f"nestquest-history-{start}-to-{end}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get(
    "/settings",
    summary="Read the effective settings",
    response_model=AdminSettingsResponse,
)
async def admin_get_settings(request: Request) -> AdminSettingsResponse:
    """Return the current effective settings (all ten documented fields).

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: ONE
    :func:`nestquest_core.settings_store.load_settings` call — the API
    owns settings in the database (the integration's HA options remain
    a temporary separate source until Feature 18 wires the client to
    the API), and the stored-document decode, the per-field validation
    and the defaults-for-absent-fields fallback all live in the core.
    A corrupt stored document never fails the read: the core falls
    back to the defaults (per field where possible).
    """
    state: DatabaseState = request.app.state.db
    settings = await core_settings_store.load_settings(state.database)
    return _settings_response(settings)


@router.patch(
    "/settings",
    summary="Update the supplied settings fields",
    response_model=AdminSettingsResponse,
)
async def admin_update_settings(
    changes: dict[str, object], request: Request
) -> AdminSettingsResponse:
    """Update the supplied settings fields and return the new state.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: the body — a
    JSON object of settings field names to new values — goes STRAIGHT
    to :func:`nestquest_core.settings_store.update_settings`, which
    rejects an unknown field, resolves each supplied field through the
    core settings validators (a JSON ``null`` resets its field to the
    default) and merges onto the current effective settings only after
    every value has validated — so a rejected update never changes the
    stored settings.  Every core ``ValueError`` is 422
    (:func:`_raise_settings_error`); anything else re-raises.
    """
    state: DatabaseState = request.app.state.db
    try:
        settings = await core_settings_store.update_settings(
            state.database, changes
        )
    except ValueError as error:
        _raise_settings_error(error)
    return _settings_response(settings)


@router.post(
    "/missed-sweep",
    summary="Run the nightly missed-quest sweep now",
    response_model=AdminMissedSweepResponse,
)
async def admin_run_missed_sweep(
    request: Request,
) -> AdminMissedSweepResponse:
    """Run the missed-quest sweep and publish what it built.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter over the SAME
    HA-free sweep policy the integration's rollover listener runs
    (:mod:`nestquest_core.sweep`): ONE timezone-aware clock read
    (:func:`_local_now`) pins the API host's local ``today``, and ONE
    :func:`nestquest_core.sweep.run_missed_sweep` call does everything
    else — the past-due open-instance query, the documented payload
    build and the watermark update (a same-day rerun is an empty
    no-op, and a run after downtime sweeps the accumulated window
    once).  The route is read-only over the domain tables: it never
    mutates an instance and never writes a completion event.

    Each returned ``(event_type, payload)`` pair is published DIRECTLY
    on the app's ONE transition publisher (``request.app.state.publisher``,
    fan-out fire-and-forget, see api/events.py) — the exact payload the
    sweep built, never re-fetched and never hand-built here, the same
    publish-what-the-core-built shape api/scheduler.py uses.  This is a
    correctness rule, not a style preference: the core commits the
    idempotency watermark BEFORE returning, so a re-fetch-based publish
    loop opens a loss window — a concurrent regenerate deleting the
    instance, or a transient database error, would raise uncaught (a
    bare 500) AFTER the watermark advanced, and no future sweep would
    ever re-examine that instance.  Publishing the built payload leaves
    no such window, and every event of one run keeps the ONE shared
    ``occurred_at`` stamp the sweep computed for it.  The response
    reports ``fired`` — the number of transitions published.  Error
    mapping (:func:`_raise_sweep_error`): every core ``ValueError`` is
    422; anything else re-raises.
    """
    state: DatabaseState = request.app.state.db
    database = state.database
    today = _local_now().date()
    try:
        events = await core_sweep.run_missed_sweep(database, today=today)
    except ValueError as error:
        _raise_sweep_error(error)
    for event_type, payload in events:
        request.app.state.publisher.publish(event_type, payload)
    return AdminMissedSweepResponse(fired=len(events))


@router.get(
    "/snapshot",
    summary="Today's household snapshot",
    response_model=AdminSnapshotResponse,
)
async def admin_snapshot(request: Request) -> AdminSnapshotResponse:
    """Return today's full household snapshot for the admin Today tab.

    Requires a valid admin JWT (the router's shared
    :func:`~api.auth.require_admin` dependency — the ONE check; this
    handler performs NO auth of its own).  Thin adapter: ONE clock read
    (:func:`_local_now`) goes into
    :func:`nestquest_core.snapshot.build_snapshot` against the live
    database, and each child's instances are shaped with
    ``instance_payload(include_missed=True)`` — missed instances are
    KEPT in the admin payload (D-009) — into
    :class:`AdminSnapshotResponse`.
    """
    state: DatabaseState = request.app.state.db
    snapshot = await core_snapshot.build_snapshot(
        state.database, core_settings.NestQuestSettings(), _local_now()
    )
    return AdminSnapshotResponse(
        today_iso=snapshot.today_iso,
        cycle_day=snapshot.cycle_day,
        children=[
            AdminChildSnapshotPayload(
                child_id=child.child_id,
                child_name=child.child_name,
                present=child.present,
                next_present=child.next_present,
                due_today=child.due_today,
                completed_today=child.completed_today,
                remaining_today=child.remaining_today,
                completion_pct=child.completion_pct,
                instances=[
                    AdminInstancePayload.model_validate(instance)
                    for instance in core_snapshot.instance_payload(
                        child.instances, include_missed=True
                    )
                ],
            )
            for child in snapshot.children
        ],
    )


__all__ = ["router"]
