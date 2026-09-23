"""Admin-plane presence route tests (task e4a9d31b).

These tests exercise the admin plane's presence routes against the ASGI
app with httpx, reusing the shared local-RSA-key/stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.

Every done-condition case is proven against the DATABASE and the DOMAIN,
read through the SAME core copy the app uses (``nestquest_core.*``; see
the two-copy caveat in api/nestquest_core.py):

- Authentication runs through the router's ONE ``require_admin``
  dependency: an admin JWT passes, a JWT without the group is 403, an
  absent credential is 401 — and nothing is written.
- ``PUT /api/v1/admin/children/{id}/presence-schedule`` UPSERTS: the
  first set persists the schedule, setting again REPLACES it — one
  schedule row per child, never a duplicate.
- ``POST /api/v1/admin/presence-overrides`` creates the override (its
  ``id`` comes back) and ``DELETE /api/v1/admin/presence-overrides/{id}``
  removes it again.
- The child's RESOLVED presence changes accordingly: the pure
  :class:`~nestquest_core.presence.PresenceEngine` built from the
  stored rows answers differently before/after each write — a schedule
  restricts the child's present weekdays, an override beats the pattern
  for its range, and deleting the override restores the pattern's
  answer.
- The regeneration side effect lives in the core layer the route
  calls: setting an all-absent schedule through the route deletes the
  child's future open quest instances and they are NOT rebuilt while
  the child is absent every day — the same proof the HA service test
  makes, through the API instead.

Error mapping (documented in api/routes_admin.py): a core ValueError
for a non-existent child (schedule or override create) or override
(delete) is 404; every other core ValueError — a rejected schedule
(cycle length, pattern coverage, anchor date) or override (malformed or
inverted dates, an overlapping range) — is 422, the same failure class
FastAPI reports for malformed bodies.
"""
from __future__ import annotations

import datetime
import importlib
from types import SimpleNamespace

import pytest

from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

# The presence model, DAOs, business layer and materializer through the
# SAME core copy the app uses (nestquest_core.*, NOT the conftest-stubbed
# custom_components copy) — used for the tests' database and resolved-
# presence assertions only; the routes reach them through api.nestquest_core.
_children = importlib.import_module("nestquest_core.children")
_dao_presence = importlib.import_module("nestquest_core.dao_presence")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_materialize = importlib.import_module("nestquest_core.materialize")
_presence = importlib.import_module("nestquest_core.presence")

#: A Monday anchoring every schedule: cycle week 0 starts here.
ANCHOR_MONDAY = "2026-01-05"
#: The Tuesday of that week — absent under the test schedule.
TUESDAY = "2026-01-06"


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _schedule_body(
    cycle_length_weeks: int = 1, pattern: dict[int, list[int]] | None = None
) -> dict[str, object]:
    """A valid schedule body anchored to the test Monday."""
    return {
        "cycle_length_weeks": cycle_length_weeks,
        "anchor_date": ANCHOR_MONDAY,
        "pattern": {"0": [0, 2, 4]} if pattern is None else pattern,
    }


def _override_body(
    child_id: int,
    *,
    start_date: str = TUESDAY,
    end_date: str = TUESDAY,
    is_present: bool = True,
) -> dict[str, object]:
    """A valid single-day override body for the test child."""
    return {
        "child_id": child_id,
        "start_date": start_date,
        "end_date": end_date,
        "is_present": is_present,
        "note": "grandmother's week",
    }


async def _create_child(client: object, name: str = "Ada") -> int:
    """Create one child through the admin children route; return the id."""
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": name},
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


def _engine(
    database: object,
    child_id: int,
    schedule_record: object | None,
    override_records: list[object],
) -> object:
    """Build the pure PresenceEngine from stored rows (the snapshot shape).

    Mirrors what the core snapshot builder assembles: the child's
    decoded schedule (absent → present every day) plus its overrides,
    so :meth:`PresenceEngine.is_present` answers from the SAME rows the
    routes produced.
    """
    schedules: dict[int, object] = {}
    if schedule_record is not None:
        schedules[child_id] = _presence.PresenceSchedule.decode(
            schedule_record.child_id,
            schedule_record.anchor_date,
            schedule_record.pattern,
        )
    overrides = {
        child_id: [
            _presence.PresenceOverride(
                record.child_id,
                record.start_date,
                record.end_date,
                record.is_present,
                note=record.note,
            )
            for record in override_records
        ]
    }
    return _presence.PresenceEngine(schedules, overrides)


async def _child_state(
    database: object, child_id: int
) -> tuple[object | None, list[object], object]:
    """The child's stored schedule record, overrides and PresenceEngine."""
    schedule_record = await _dao_presence.PresenceSchedulesDao(
        database
    ).get_by_child(child_id)
    override_records = await _dao_presence.PresenceOverridesDao(
        database
    ).list_by_child_and_range(child_id, "2020-01-01", "2030-01-01")
    engine = _engine(database, child_id, schedule_record, override_records)
    return schedule_record, override_records, engine


@pytest.fixture
async def admin_presence(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database.

    The same runner the auth, children and quest-definition tests use
    (stubbed JWKS, no network); the fixture also exposes the app's ONE
    database connection so tests assert the routes' effects on the
    stored rows and the resolved presence built from them.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


# --- authentication: the ONE require_admin dependency guards every route ---


async def test_presence_routes_refuse_non_admin_and_absent_credentials(
    admin_presence: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401: nothing written."""
    client = admin_presence.client
    child_id = await _create_child(client)
    non_admin = make_token(groups=("some-other-group",))
    non_admin_headers = {"Authorization": f"Bearer {non_admin}"}

    forbidden_schedule = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(),
        headers=non_admin_headers,
    )
    assert forbidden_schedule.status_code == 403
    assert forbidden_schedule.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )

    forbidden_override = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(child_id),
        headers=non_admin_headers,
    )
    assert forbidden_override.status_code == 403

    forbidden_delete = await client.delete(
        "/api/v1/admin/presence-overrides/1", headers=non_admin_headers
    )
    assert forbidden_delete.status_code == 403

    unauthenticated_schedule = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(),
    )
    assert unauthenticated_schedule.status_code == 401

    unauthenticated_override = await client.post(
        "/api/v1/admin/presence-overrides", json=_override_body(child_id)
    )
    assert unauthenticated_override.status_code == 401

    unauthenticated_delete = await client.delete(
        "/api/v1/admin/presence-overrides/1"
    )
    assert unauthenticated_delete.status_code == 401

    # No route ran its handler: the child still has no schedule and no
    # overrides (and is present every day, the no-schedule default).
    _schedule, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert _schedule is None
    assert _overrides == []
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True


# --- schedule upsert --------------------------------------------------------


async def test_schedule_upserts_and_replaces_one_row_per_child(
    admin_presence: SimpleNamespace,
) -> None:
    """PUT /presence-schedule persists, and setting again REPLACES it."""
    client = admin_presence.client
    child_id = await _create_child(client)

    first = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(),
        headers=_admin_headers(),
    )
    assert first.status_code == 200
    assert first.json() == {
        "child_id": child_id,
        "cycle_length_weeks": 1,
        "anchor_date": ANCHOR_MONDAY,
        "pattern": {"0": [0, 2, 4]},
    }
    # Database proof: exactly ONE schedule row (the schema's
    # UNIQUE(child_id) makes a second row unrepresentable), stored as
    # encoded CSV.
    schedule, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert schedule is not None
    row_id = schedule.id
    assert schedule.cycle_length_weeks == 1
    assert schedule.anchor_date == ANCHOR_MONDAY
    assert schedule.pattern == "0,2,4"

    # Setting again UPSERTS: the SAME row is updated in place — new
    # values, unchanged id — never a duplicate or a stale first set.
    second = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(
            cycle_length_weeks=2, pattern={"0": [], "1": [1, 3]}
        ),
        headers=_admin_headers(),
    )
    assert second.status_code == 200
    assert second.json() == {
        "child_id": child_id,
        "cycle_length_weeks": 2,
        "anchor_date": ANCHOR_MONDAY,
        "pattern": {"0": [], "1": [1, 3]},
    }
    schedule, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert schedule is not None
    assert schedule.id == row_id
    assert schedule.cycle_length_weeks == 2
    assert schedule.pattern == "|1,3"


async def test_schedule_changes_the_childs_resolved_presence(
    admin_presence: SimpleNamespace,
) -> None:
    """The resolved presence (PresenceEngine) follows the stored schedule."""
    client = admin_presence.client
    child_id = await _create_child(client)

    # Before any schedule the child is present every day.
    _schedule, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True
    assert engine.is_present(child_id, TUESDAY) is True

    # Mon/Wed/Fri only, week 0 of a one-week cycle.
    response = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(),
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    _schedule, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True
    assert engine.is_present(child_id, TUESDAY) is False


async def test_schedule_upsert_regenerates_future_instances(
    admin_presence: SimpleNamespace,
) -> None:
    """Setting an all-absent schedule deletes the child's future instances.

    The regeneration side effect lives in the core layer the route
    calls: the child's open instances at or after today are deleted
    across ALL its definitions and NOT rebuilt while the child is
    absent every day — the same proof the HA service test makes,
    exercised here through the API route instead.
    """
    client = admin_presence.client
    database = admin_presence.database
    child_id = await _create_child(client)
    created = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child_id],
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201

    today = datetime.date.today()
    start = today.isoformat()
    end = (today + datetime.timedelta(days=14)).isoformat()
    await _materialize.materialize(database, start, end, today=today)
    instances = _dao_instances.QuestInstancesDao(database)
    assert await instances.list_by_date_range(child_id, start, end)

    # The route's write must regenerate: absent every day removes every
    # open future instance.
    response = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(pattern={"0": []}),
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert await instances.list_by_date_range(child_id, start, end) == []


# --- override create + delete -----------------------------------------------


async def test_override_is_created_then_deleted_and_presence_resolves(
    admin_presence: SimpleNamespace,
) -> None:
    """POST creates the override, DELETE removes it; presence follows."""
    client = admin_presence.client
    database = admin_presence.database
    child_id = await _create_child(client)
    schedule_response = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=_schedule_body(),
        headers=_admin_headers(),
    )
    assert schedule_response.status_code == 200

    # Create: the override comes back with its id and the posted shape.
    created = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(child_id),
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    payload = created.json()
    assert set(payload) == {
        "id",
        "child_id",
        "start_date",
        "end_date",
        "is_present",
        "note",
    }
    assert payload["child_id"] == child_id
    assert payload["start_date"] == TUESDAY
    assert payload["end_date"] == TUESDAY
    assert payload["is_present"] is True
    assert payload["note"] == "grandmother's week"

    # Database proof: the row exists — and the RESOLVED presence for the
    # affected date flips: the override beats the Tuesday-absent pattern.
    _schedule, overrides, engine = await _child_state(database, child_id)
    assert [record.id for record in overrides] == [payload["id"]]
    assert engine.is_present(child_id, TUESDAY) is True
    # A date the override does not cover keeps the pattern's answer.
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True

    # Delete: the row is gone and the resolved presence follows the
    # pattern again.
    deleted = await client.delete(
        f"/api/v1/admin/presence-overrides/{payload['id']}",
        headers=_admin_headers(),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "ok"}
    assert (
        await _dao_presence.PresenceOverridesDao(database).get(payload["id"])
        is None
    )
    _schedule, overrides, engine = await _child_state(database, child_id)
    assert overrides == []
    assert engine.is_present(child_id, TUESDAY) is False


# --- error mapping: 404 vs 422 ----------------------------------------------


async def test_schedule_and_override_for_unknown_child_are_404(
    admin_presence: SimpleNamespace,
) -> None:
    """A presence write naming a child that does not exist is 404."""
    client = admin_presence.client

    schedule = await client.put(
        "/api/v1/admin/children/999/presence-schedule",
        json=_schedule_body(),
        headers=_admin_headers(),
    )
    assert schedule.status_code == 404
    assert schedule.json()["detail"] == "Child not found"

    override = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(999),
        headers=_admin_headers(),
    )
    assert override.status_code == 404
    assert override.json()["detail"] == "Child not found"


@pytest.mark.parametrize(
    "body",
    [
        _schedule_body(cycle_length_weeks=0),  # below the 1..4 range
        _schedule_body(cycle_length_weeks=5),  # above the documented cap
        # week 1 of the cycle missing:
        _schedule_body(cycle_length_weeks=2, pattern={"0": [0]}),
        {
            "cycle_length_weeks": 1,
            "anchor_date": "2026-13-40",
            "pattern": {"0": [0]},
        },
        _schedule_body(pattern={"0": [7]}),  # weekday out of 0..6
        _schedule_body(pattern={"nope": [0]}),  # week index not an integer
        _schedule_body(pattern={"0": "0,2,4"}),  # weekdays not a list
    ],
)
async def test_rejected_schedule_is_422(
    admin_presence: SimpleNamespace, body: dict[str, object]
) -> None:
    """A rejected schedule is 422 and stores nothing."""
    client = admin_presence.client
    child_id = await _create_child(client)
    response = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json=body,
        headers=_admin_headers(),
    )
    assert response.status_code == 422
    assert (
        await _dao_presence.PresenceSchedulesDao(
            admin_presence.database
        ).get_by_child(child_id)
        is None
    )


@pytest.mark.parametrize(
    "body",
    [
        _override_body(1, start_date="2026-01-07", end_date="2026-01-06"),
        _override_body(1, start_date="2026-02-30", end_date="2026-02-30"),
        dict(_override_body(1), note=5),
        dict(_override_body(1), child_id="one"),
    ],
)
async def test_rejected_override_is_422(
    admin_presence: SimpleNamespace, body: dict[str, object]
) -> None:
    """A rejected override (inverted/malformed dates, bad note/id) is 422.

    The shape failures (a non-string note, a non-integer child id) are
    the body model's; the date failures are the PresenceOverride
    model's.  A string ``is_present`` like ``"yes"`` is deliberately
    absent: Pydantic's lax bool COERCES it to ``True`` (the same design
    as the children active route), so it never reaches the model's
    real-bool check.
    """
    response = await admin_presence.client.post(
        "/api/v1/admin/presence-overrides", json=body, headers=_admin_headers()
    )
    assert response.status_code == 422


async def test_overlapping_override_is_422_and_first_survives(
    admin_presence: SimpleNamespace,
) -> None:
    """An override overlapping the child's existing one is 422.

    The conflicting write persists nothing: the child's original
    override survives unchanged.
    """
    client = admin_presence.client
    child_id = await _create_child(client)
    created = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(child_id),
        headers=_admin_headers(),
    )
    assert created.status_code == 201

    response = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(child_id, is_present=False),
        headers=_admin_headers(),
    )
    assert response.status_code == 422
    _schedule, overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert [record.id for record in overrides] == [created.json()["id"]]


async def test_delete_unknown_override_is_404(
    admin_presence: SimpleNamespace,
) -> None:
    """Deleting an override id that does not exist is 404."""
    response = await admin_presence.client.delete(
        "/api/v1/admin/presence-overrides/999", headers=_admin_headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Presence override not found"

    malformed = await admin_presence.client.delete(
        "/api/v1/admin/presence-overrides/not-an-id",
        headers=_admin_headers(),
    )
    assert malformed.status_code == 422
