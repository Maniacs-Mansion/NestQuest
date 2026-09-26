"""Panel-plane routes for the NestQuest API service.

The panel plane (``/api/v1/panel/*``, D-012) serves the wall panel's
reads.  Every route on :data:`router` requires the panel service token
through the ONE reusable dependency :func:`api.dependencies.require_panel_token`
(declared once at the router level, so each later panel route added to
this router inherits the check).

The snapshot route is a thin adapter over the bundled core: it performs
NO business logic.  It reads the live database off ``app.state.db``,
resolves ONE timezone-aware ``now`` (the host clock re-expressed in the
stored household ``timezone`` setting — the API host may run UTC while
the household does not), calls the pure
:func:`nestquest_core.snapshot.build_snapshot`, shapes each child's
instances through :func:`nestquest_core.snapshot.instance_payload` with
``include_missed=False`` (D-009: missed instances are OMITTED from the
panel payload), and returns the documented JSON shape:

.. code-block:: json

    {
      "today_iso": "2026-09-22",
      "cycle_day": 2,
      "children": [
        {
          "child_id": 1,
          "child_name": "Ada",
          "present": false,
          "next_present": "2026-09-24",
          "due_today": 1,
          "completed_today": 0,
          "remaining_today": 1,
          "completion_pct": 0,
          "instances": [
            {"id": 7, "definition_id": 3, "child_id": 1,
             "title": "Pack bag", "icon": null, "window": "morning",
             "due_time": "10:00", "state": "open", "overdue": true,
             "completed_at": null, "on_time": null}
          ]
        }
      ]
    }

``children`` follows the household's sort order (the core builder lists
active children ``ORDER BY sort_order, id``); ``state`` is the
documented panel spelling ``open`` | ``completed`` (§1 of
design/ENTITIES-AND-SERVICES.md); ``cycle_day`` is today's 1-based day
in the first scheduled child's custody cycle (0 when no child has one).
The same :class:`PanelSnapshotResponse` Pydantic model is the route's
``response_model``, so the OpenAPI document carries the shape too.
"""
from __future__ import annotations

import datetime
import importlib

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from api.database import DatabaseState
from api.dependencies import require_panel_token
from api.nestquest_core import (
    core_completion,
    core_events,
    core_settings_store,
    core_snapshot,
)
from api import transitions as api_transitions
from api.sse import transition_event_stream

#: The instance DAO, imported on the app's core copy for the
#: child-mismatch guard on the complete route.
_dao_instances = importlib.import_module("nestquest_core.dao_instances")

#: All panel-plane routes share this router; the service-token check is
#: attached HERE so every panel route (current and later) requires it.
router = APIRouter(
    prefix="/api/v1/panel",
    dependencies=[Depends(require_panel_token)],
)


class PanelInstancePayload(BaseModel):
    """One instance in the documented panel payload shape (§1).

    Mirrors :func:`nestquest_core.snapshot.instance_payload`:
    ``state`` is ``open`` | ``completed`` (missed instances never reach
    the panel payload), ``on_time`` passes the completion event's flag
    through verbatim (``None`` for an open instance), and
    ``completed_at`` is the event's UTC timestamp when completed.
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


class PanelChildPayload(BaseModel):
    """One child's day: presence, rollup counts, and today's instances."""

    child_id: int
    child_name: str
    present: bool
    #: ISO date of the child's next present day while they are away
    #: (the away plate renders ``Returns <weekday>, <Mon D>`` from it);
    #: ``None`` when the child is present today.
    next_present: str | None
    due_today: int
    completed_today: int
    remaining_today: int
    completion_pct: int
    instances: list[PanelInstancePayload]


class PanelSnapshotResponse(BaseModel):
    """The whole household snapshot the panel renders from.

    ``today_iso`` anchors the payload's day; ``cycle_day`` is today's
    1-based day in the first scheduled child's custody cycle (0 when no
    child has a schedule); ``children`` is in the household's sort
    order.
    """

    today_iso: str
    cycle_day: int
    children: list[PanelChildPayload]


class PanelCompleteRequest(BaseModel):
    """The body of ``POST /api/v1/panel/instances/{id}/complete``.

    Matches the panel's ``nestquest.complete_quest`` payload (§2 of
    design/ENTITIES-AND-SERVICES.md): ``actor_child_id`` is the tapped
    profile.  A positive integer is required — the core completion
    layer rejects non-int (and bool) ids anyway, but rejecting them
    here with 422 keeps the contract visible in the OpenAPI document
    and fails before any database work.
    """

    actor_child_id: int

    model_config = {
        "json_schema_extra": {
            "description": (
                "The tapped child profile the completion is "
                "attributed to (decision 9)."
            )
        }
    }

    @field_validator("actor_child_id")
    @classmethod
    def _positive(cls, value: int) -> int:
        """Reject zero and negative ids with a validation error."""
        if value < 1:
            raise ValueError("actor_child_id must be a positive integer")
        return value


def _local_now() -> datetime.datetime:
    """Return the API host's local time as ONE timezone-aware clock read.

    ``now().astimezone()`` attaches the host's local timezone to a
    single clock read, so the calendar date and wall-clock time the
    builder derives can never disagree.  Kept as a module function (not
    inlined) so tests pin the instant the same way the coordinator's
    ``_local_now`` is pinned.
    """
    return datetime.datetime.now().astimezone()


async def _household_clock(
    database: object,
) -> tuple[object, datetime.datetime]:
    """Return the stored settings and ONE household-local clock read.

    The API host may run UTC while the household does not, so the one
    :func:`_local_now` read is re-expressed in the stored settings'
    ``timezone`` (:meth:`NestQuestSettings.household_now`); an unset
    zone keeps the host's local time.
    """
    settings = await core_settings_store.load_settings(database)
    return settings, settings.household_now(_local_now())


@router.get(
    "/snapshot",
    summary="Today's household snapshot",
    response_model=PanelSnapshotResponse,
)
async def panel_snapshot(request: Request) -> PanelSnapshotResponse:
    """Return today's full household snapshot for the panel.

    Requires the panel service token (checked by the router's shared
    :func:`~api.dependencies.require_panel_token` dependency).  Builds
    the snapshot through the pure core builder against the live
    database and shapes each child's instances with
    ``instance_payload(include_missed=False)`` — missed instances are
    OMITTED from the panel payload (D-009) — then returns the shape
    documented in this module's docstring and
    :class:`PanelSnapshotResponse`.
    """
    state: DatabaseState = request.app.state.db
    settings, now = await _household_clock(state.database)
    snapshot = await core_snapshot.build_snapshot(
        state.database, settings, now
    )
    return PanelSnapshotResponse(
        today_iso=snapshot.today_iso,
        cycle_day=snapshot.cycle_day,
        children=[
            PanelChildPayload(
                child_id=child.child_id,
                child_name=child.child_name,
                present=child.present,
                next_present=child.next_present,
                due_today=child.due_today,
                completed_today=child.completed_today,
                remaining_today=child.remaining_today,
                completion_pct=child.completion_pct,
                instances=[
                    PanelInstancePayload.model_validate(instance)
                    for instance in core_snapshot.instance_payload(
                        child.instances, include_missed=False
                    )
                ],
            )
            for child in snapshot.children
        ],
    )


@router.post(
    "/instances/{instance_id}/complete",
    summary="Complete one quest instance",
    status_code=200,
)
async def panel_complete_instance(
    instance_id: int, body: PanelCompleteRequest, request: Request
) -> dict[str, str]:
    """Complete one quest instance as the tapped child profile.

    Requires the panel service token (checked by the router's shared
    :func:`~api.dependencies.require_panel_token` dependency — the ONE
    token check; this handler performs NO auth of its own).

    Thin adapter only: resolves the live database off ``app.state.db``,
    reads ONE timezone-aware clock (:func:`_local_now`), and delegates
    to :func:`nestquest_core.completion.complete_instance` with
    ``actor_source="panel"`` and the tapped ``actor_child_id`` — the
    append/idempotence logic, the lock, and the actor-shape validation
    all live in the core layer, never here.

    Response and idempotence: ``complete_instance`` returns a
    :class:`~nestquest_core.completion.CompletionResult` whose
    ``appended`` flag reports whether THIS call wrote an event; a
    repeat call for an already-completed instance is a no-op inside
    the core layer (no duplicate event) and this route still answers
    ``{"status": "done"}`` either way, so a retried panel tap succeeds.

    Error mapping (deliberately narrow): the ONLY ``ValueError`` mapped
    to 404 is the unknown-``instance_id`` one, identified by the
    ``instance_id:`` prefix ``complete_instance`` names the failing
    field with.  Every other ``ValueError`` (an invalid actor shape,
    which the body model and the panel actor contract already make
    unreachable) re-raises to the framework's 500 — nothing else is
    turned into a 404 or a 500 of our own making.

    Child mismatch: ``complete_instance`` verifies the tapped
    ``actor_child_id`` exists but does NOT check it is the child the
    instance belongs to.  The route performs that check here (one
    ``QuestInstancesDao.get_by_id`` read) and answers 404 when the
    instance's ``child_id`` differs — completing another child's quest
    from the wrong profile must not succeed, and 404 (not 403) keeps
    the instance's existence from leaking to a wrong-profile tap.
    """
    state: DatabaseState = request.app.state.db
    database = state.database

    # Child-mismatch guard (see docstring): the instance must belong to
    # the tapped profile before the completion layer is entered.
    instance = await _dao_instances.QuestInstancesDao(database).get_by_id(
        instance_id
    )
    if instance is not None and instance.child_id != body.actor_child_id:
        raise HTTPException(
            status_code=404,
            detail="Quest instance not found for this child",
        )

    _settings, now = await _household_clock(database)
    try:
        result = await core_completion.complete_instance(
            database,
            instance_id,
            actor_source="panel",
            actor_child_id=body.actor_child_id,
            now=now,
        )
    except ValueError as error:
        message = str(error)
        if message.startswith("instance_id:"):
            # complete_instance names the field in its ValueError:
            # "instance_id: quest instance N does not exist".
            raise HTTPException(
                status_code=404,
                detail="Quest instance not found",
            ) from error
        raise
    # The derived state is "done" in both the appended and no-op cases;
    # ``result.appended`` distinguishes them for callers that care —
    # the panel route returns the same success either way.
    if result.appended:
        # An ACTUAL transition: publish the SSE transition event.  The
        # payload is built by the core builder (never hand-built here)
        # and fan-out is fire-and-forget (see api/events.py).
        event_type, payload = await core_events.build_quest_completed_event(
            database, instance_id, was_on_time=result.was_on_time
        )
        request.app.state.publisher.publish(event_type, payload)
        # THEN evaluate the day-complete rule off the completed event's
        # payload (the core builder decides when the child's whole day
        # is cleared — a zero-quest day and a non-today instance never
        # fire it).  ``today`` comes from the route's single clock read
        # so the calendar date can never disagree with the completion's.
        await api_transitions.publish_child_day_complete(
            database,
            payload,
            now.date(),
            request.app.state.publisher,
        )
    return {"status": str(result)}


@router.get(
    "/events",
    summary="Stream panel transition events (SSE)",
)
async def panel_events(request: Request) -> StreamingResponse:
    """Stream the app's transition events to the panel (Server-Sent
    Events).

    Requires the panel service token (checked by the router's shared
    :func:`~api.dependencies.require_panel_token` dependency — the ONE
    token check; this handler performs NO auth of its own).

    Returns the shared :func:`api.sse.transition_event_stream` response
    off the app's single in-process publisher (``app.state.publisher``,
    installed in the lifespan).  The stream ends when the client
    disconnects, at which point the subscription is torn down (its
    queue removed) with nothing leaked.
    """
    return transition_event_stream(request)


__all__ = ["router"]
