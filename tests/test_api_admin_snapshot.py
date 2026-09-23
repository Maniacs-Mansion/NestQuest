"""Admin-plane snapshot route tests (task ef3f4877).

These tests exercise ``GET /api/v1/admin/snapshot`` against the ASGI
app with httpx, reusing the shared local-RSA-key/stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates with NO network access.  The household is seeded with
:func:`tests.test_api_panel._seed_household` through the SAME core
copy the app uses (``nestquest_core.*``), and both routes' single
clock read (``_local_now``) is pinned to noon so nothing straddles
midnight.

Proven per the done-condition:

- An admin JWT returns 200 with the documented shape: ``today_iso``,
  ``cycle_day`` and, per child, the presence fields, the rollup counts
  and ``instances`` in the core ``instance_payload`` shape.
- A MISSED instance is KEPT in the admin payload (D-009) and still
  OMITTED from the panel payload.  The core builder lists only
  instances due on ``now.date()``, and ``derive_state`` calls an
  instance missed only when its due date is BEFORE that day — so a
  real snapshot never carries a missed view.  The test therefore
  wraps the real builder to add the seeded past-due instance as a
  view whose state the core's own ``derive_state`` computes
  (``missed``), and reads it through both routes.
- Auth runs through the router's ONE ``require_admin`` dependency: no
  credential is 401, the panel service token is refused outright
  (403, the credential-type detail), and a non-admin JWT is 403.
- The handler performs exactly ONE clock read per request.
"""
from __future__ import annotations

import dataclasses
import datetime
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api import routes_admin, routes_panel
from api.nestquest_core import core_snapshot
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)
from tests.test_api_panel import _seed_household

# The completion layer through the SAME core copy the app uses — the
# missed test derives its view's state with the core's own rule.
_completion = importlib.import_module("nestquest_core.completion")

#: The panel service token the harness app is configured with.
HARNESS_PANEL_TOKEN = "admin-test-panel-token"

#: The 403 detail for the panel service token on an admin route.
PANEL_TOKEN_REJECTION_DETAIL = (
    "This credential type is not accepted for admin access"
)

#: The 403 detail for a valid JWT without the admin group.
FORBIDDEN_DETAIL = (
    "Admin access requires membership in the nestquest-admins group"
)


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _panel_headers() -> dict[str, str]:
    """The Authorization header carrying the harness panel token."""
    return {"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"}


@pytest.fixture
async def snapshot_household(
    temp_db_path: str, monkeypatch
) -> SimpleNamespace:
    """A seeded household served by the admin-plane app, clock pinned.

    ``today`` comes from one host clock read; the pinned instant is
    12:00 UTC that day (past Ada's 10:00 due, before Bo's 17:00).  Both
    the admin and the panel route's ``_local_now`` return it, and the
    admin one counts its calls.
    """
    today = datetime.datetime.now().astimezone().date()
    pinned_now = datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=ZoneInfo("UTC")
    )
    seed = await _seed_household(temp_db_path, today, pinned_now)

    clock_reads: list[datetime.datetime] = []

    def _admin_now() -> datetime.datetime:
        clock_reads.append(pinned_now)
        return pinned_now

    monkeypatch.setattr(routes_admin, "_local_now", _admin_now)
    monkeypatch.setattr(routes_panel, "_local_now", lambda: pinned_now)
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            seed=seed,
            today=today,
            pinned_now=pinned_now,
            pinned_utc_iso=pinned_now.astimezone(
                datetime.timezone.utc
            ).isoformat(),
            clock_reads=clock_reads,
        )


# --- authentication: the ONE require_admin dependency ----------------------


async def test_snapshot_without_credential_is_401(
    snapshot_household: SimpleNamespace,
) -> None:
    """No Authorization header is the uniform 401."""
    response = await snapshot_household.client.get("/api/v1/admin/snapshot")
    assert response.status_code == 401


async def test_snapshot_refuses_panel_service_token_outright(
    snapshot_household: SimpleNamespace,
) -> None:
    """The panel service token is refused as a credential type (403).

    403 with the credential-type detail — not the uniform 401 and not
    the non-admin group detail — proves the token was refused outright,
    never tried as a JWT.
    """
    response = await snapshot_household.client.get(
        "/api/v1/admin/snapshot", headers=_panel_headers()
    )
    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL


async def test_snapshot_refuses_non_admin_jwt(
    snapshot_household: SimpleNamespace,
) -> None:
    """A valid JWT without the nestquest-admins group is 403."""
    non_admin = make_token(groups=("some-other-group",))
    response = await snapshot_household.client.get(
        "/api/v1/admin/snapshot",
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


# --- the payload -----------------------------------------------------------


async def test_admin_jwt_returns_documented_snapshot(
    snapshot_household: SimpleNamespace,
) -> None:
    """An admin JWT returns 200 with the documented snapshot shape.

    Every field is asserted as an explicit literal, with ONE clock
    read for the request.  With no missed view in the real snapshot,
    the admin body equals the panel body for the same household.
    """
    client = snapshot_household.client
    seed = snapshot_household.seed

    response = await client.get(
        "/api/v1/admin/snapshot", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert len(snapshot_household.clock_reads) == 1
    body = response.json()

    assert body == {
        "today_iso": snapshot_household.today.isoformat(),
        # Ada's 2-week cycle anchored yesterday => today is cycle day 2.
        "cycle_day": 2,
        "children": [
            {
                "child_id": seed.ada.id,
                "child_name": "Ada",
                "present": False,
                "next_present": seed.returns_date.isoformat(),
                "due_today": 1,
                "completed_today": 0,
                "remaining_today": 1,
                "completion_pct": 0,
                "instances": [
                    {
                        "id": seed.pack_bag_instance.id,
                        "definition_id": seed.pack_bag_instance.definition_id,
                        "child_id": seed.ada.id,
                        "title": "Pack bag",
                        "icon": None,
                        "window": "morning",
                        "due_time": "10:00",
                        "state": "open",
                        "overdue": True,
                        "completed_at": None,
                        "on_time": None,
                    }
                ],
            },
            {
                "child_id": seed.bo.id,
                "child_name": "Bo",
                "present": True,
                "next_present": None,
                "due_today": 1,
                "completed_today": 1,
                "remaining_today": 0,
                "completion_pct": 100,
                "instances": [
                    {
                        "id": seed.brush_teeth_instance.id,
                        "definition_id": (
                            seed.brush_teeth_instance.definition_id
                        ),
                        "child_id": seed.bo.id,
                        "title": "Brush teeth",
                        "icon": None,
                        "window": "morning",
                        "due_time": "17:00",
                        "state": "completed",
                        "overdue": False,
                        "completed_at": snapshot_household.pinned_utc_iso,
                        "on_time": True,
                    }
                ],
            },
        ],
    }

    panel = await client.get(
        "/api/v1/panel/snapshot", headers=_panel_headers()
    )
    assert panel.status_code == 200
    assert panel.json() == body


async def test_admin_keeps_missed_instance_panel_omits_it(
    snapshot_household: SimpleNamespace, monkeypatch
) -> None:
    """A missed view is KEPT by the admin route, OMITTED by the panel's.

    The real builder is wrapped to add the seeded past-due Stale chore
    instance to Ada's views, its state derived by the core's own
    ``derive_state`` (no events, due yesterday => ``missed``).  Both
    routes read the SAME wrapped snapshot, so the only difference is
    each route's ``include_missed`` flag.
    """
    client = snapshot_household.client
    seed = snapshot_household.seed
    stale = seed.stale_instance
    missed_state = _completion.derive_state(
        stale, None, snapshot_household.today
    )
    assert missed_state == "missed"
    missed_view = core_snapshot.QuestInstanceView(
        instance_id=stale.id,
        definition_id=stale.definition_id,
        child_id=stale.child_id,
        title="Stale chore",
        icon=None,
        window=stale.window,
        due_date=stale.due_date,
        due_time=stale.due_time,
        state=missed_state,
        overdue=False,
        completed_at=None,
        was_on_time=None,
    )
    real_build_snapshot = core_snapshot.build_snapshot

    async def _with_missed_view(database, settings, now):
        snapshot = await real_build_snapshot(database, settings, now)
        return dataclasses.replace(
            snapshot,
            children=tuple(
                dataclasses.replace(
                    child, instances=(*child.instances, missed_view)
                )
                if child.child_id == seed.ada.id
                else child
                for child in snapshot.children
            ),
        )

    monkeypatch.setattr(core_snapshot, "build_snapshot", _with_missed_view)

    admin = await client.get(
        "/api/v1/admin/snapshot", headers=_admin_headers()
    )
    assert admin.status_code == 200
    admin_ada = admin.json()["children"][0]
    assert admin_ada["child_id"] == seed.ada.id
    assert [instance["id"] for instance in admin_ada["instances"]] == [
        seed.pack_bag_instance.id,
        stale.id,
    ]
    assert admin_ada["instances"][1] == {
        "id": stale.id,
        "definition_id": stale.definition_id,
        "child_id": seed.ada.id,
        "title": "Stale chore",
        "icon": None,
        "window": "morning",
        "due_time": "09:00",
        "state": "missed",
        "overdue": False,
        "completed_at": None,
        "on_time": None,
    }

    panel = await client.get(
        "/api/v1/panel/snapshot", headers=_panel_headers()
    )
    assert panel.status_code == 200
    panel_ada = panel.json()["children"][0]
    assert [instance["id"] for instance in panel_ada["instances"]] == [
        seed.pack_bag_instance.id
    ], "the panel payload must still omit missed instances"
