"""Panel-plane routes for the NestQuest API service.

The panel plane (``/api/v1/panel/*``, D-012) serves the wall panel's
reads.  Every route on :data:`router` requires the panel service token
through the ONE reusable dependency :func:`api.dependencies.require_panel_token`
(declared once at the router level, so each later panel route added to
this router inherits the check).

The snapshot route is a thin adapter over the bundled core: it performs
NO business logic.  It reads the live database off ``app.state.db``,
resolves ONE timezone-aware ``now`` (the API host's local time — the
API is the household's "local" host now that the domain no longer lives
inside Home Assistant), calls the pure
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

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.database import DatabaseState
from api.dependencies import require_panel_token
from api.nestquest_core import core_snapshot, core_settings

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


def _local_now() -> datetime.datetime:
    """Return the API host's local time as ONE timezone-aware clock read.

    ``now().astimezone()`` attaches the host's local timezone to a
    single clock read, so the calendar date and wall-clock time the
    builder derives can never disagree.  Kept as a module function (not
    inlined) so tests pin the instant the same way the coordinator's
    ``_local_now`` is pinned.
    """
    return datetime.datetime.now().astimezone()


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
    snapshot = await core_snapshot.build_snapshot(
        state.database, core_settings.NestQuestSettings(), _local_now()
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


__all__ = ["router"]
