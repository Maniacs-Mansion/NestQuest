"""Admin-plane presence route tests (task e4a9d31b; schema 9 patterns).

These tests exercise the admin plane's presence routes against the ASGI
app with httpx, reusing the shared local-RSA-key/stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.

Every done-condition case is proven against the DATABASE and the DOMAIN,
read through the SAME core copy the app uses (``nestquest_core.*``; see
the two-copy caveat in api/nestquest_core.py):

- Authentication runs through the router's ONE ``require_admin``
  dependency on EVERY presence route (the four pattern routes and the
  override routes): an admin JWT passes, a JWT without the group or the
  panel service token is 403, an absent credential is 401 — and
  nothing is written.
- ``POST /api/v1/admin/children/{id}/presence-patterns`` ADDS a
  pattern: a child has zero or more, each create inserts a new row
  (never replacing an earlier one).  ``PATCH
  /api/v1/admin/presence-patterns/{id}`` changes only the supplied
  fields; ``DELETE`` removes the one pattern.  The removed one-per-child
  ``/presence-schedule`` route no longer exists.
- ``POST /api/v1/admin/presence-overrides`` creates the override (its
  ``id`` comes back) and ``DELETE /api/v1/admin/presence-overrides/{id}``
  removes it again.
- The child's RESOLVED presence changes accordingly: the pure
  :class:`~nestquest_core.presence.PresenceEngine` built from the
  stored rows answers differently before/after each write — a home
  pattern restricts the child's present weekdays, an away pattern beats
  a home one, an override beats every pattern for its range, and
  deleting the override (or the pattern) restores the earlier answer.
- The regeneration side effect lives in the core layer the route
  calls: adding an all-absent home pattern through the route deletes
  the child's future open quest instances and they are NOT rebuilt
  while the child is absent every day; deleting that pattern rebuilds
  them — the same proof the HA service test makes, through the API.

Error mapping (documented in api/routes_admin.py): a core ValueError
for a non-existent child (pattern or override create) is 404 "Child not
found", a non-existent pattern (edit/delete) 404 "Presence pattern not
found", a non-existent override (delete) 404; every other core
ValueError — a rejected pattern (name, kind, cycle length, pattern
coverage, anchor date) or override (malformed or inverted dates, an
overlapping range) — is 422 naming the field, the same failure class
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

#: A Monday anchoring every pattern: cycle week 0 starts here.
ANCHOR_MONDAY = "2026-01-05"
#: The Tuesday of that week — absent under the test home pattern.
TUESDAY = "2026-01-06"

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


def _patterns_url(child_id: int) -> str:
    """The child-scoped pattern list/create route."""
    return f"/api/v1/admin/children/{child_id}/presence-patterns"


def _pattern_url(pattern_id: int | str) -> str:
    """The id-scoped pattern edit/delete route."""
    return f"/api/v1/admin/presence-patterns/{pattern_id}"


def _pattern_body(
    cycle_length_weeks: object = 1,
    pattern: dict[str, object] | None = None,
    *,
    name: object = "Mum's house",
    kind: object = "home",
    anchor_date: object = ANCHOR_MONDAY,
) -> dict[str, object]:
    """A valid pattern body anchored to the test Monday (Mon/Wed/Fri home)."""
    return {
        "name": name,
        "kind": kind,
        "cycle_length_weeks": cycle_length_weeks,
        "anchor_date": anchor_date,
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


def _detail_names(response: object, field: str) -> bool:
    """True when a 422's detail names ``field``.

    A core ValueError arrives as a string detail naming the field; a
    Pydantic shape failure as a list of errors whose ``loc`` holds it.
    """
    detail = response.json()["detail"]
    if isinstance(detail, str):
        return field in detail
    return any(field in [str(part) for part in error["loc"]] for error in detail)


async def _create_child(client: object, name: str = "Ada") -> int:
    """Create one child through the admin children route; return the id."""
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": name},
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _create_pattern(
    client: object, child_id: int, body: dict[str, object] | None = None
) -> dict[str, object]:
    """Create one pattern through the admin route; return the payload."""
    created = await client.post(
        _patterns_url(child_id),
        json=_pattern_body() if body is None else body,
        headers=_admin_headers(),
    )
    assert created.status_code == 201, created.text
    return created.json()


def _engine(
    database: object,
    child_id: int,
    pattern_records: list[object],
    override_records: list[object],
) -> object:
    """Build the pure PresenceEngine from stored rows (the snapshot shape).

    Mirrors what the core snapshot builder assembles: the child's
    decoded patterns (none → present every day) plus its overrides,
    so :meth:`PresenceEngine.is_present` answers from the SAME rows the
    routes produced.
    """
    patterns = {
        child_id: [
            _presence.PresencePattern.decode(
                record.child_id,
                record.name,
                record.kind,
                record.anchor_date,
                record.pattern,
            )
            for record in pattern_records
        ]
    }
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
    return _presence.PresenceEngine(patterns, overrides)


async def _child_state(
    database: object, child_id: int
) -> tuple[list[object], list[object], object]:
    """The child's stored pattern records, overrides and PresenceEngine."""
    pattern_records = await _dao_presence.PresencePatternsDao(
        database
    ).list_by_child(child_id)
    override_records = await _dao_presence.PresenceOverridesDao(
        database
    ).list_by_child_and_range(child_id, "2020-01-01", "2030-01-01")
    engine = _engine(database, child_id, pattern_records, override_records)
    return pattern_records, override_records, engine


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

    forbidden_pattern = await client.post(
        _patterns_url(child_id),
        json=_pattern_body(),
        headers=non_admin_headers,
    )
    assert forbidden_pattern.status_code == 403
    assert forbidden_pattern.json()["detail"] == FORBIDDEN_DETAIL

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

    unauthenticated_pattern = await client.post(
        _patterns_url(child_id), json=_pattern_body()
    )
    assert unauthenticated_pattern.status_code == 401

    unauthenticated_override = await client.post(
        "/api/v1/admin/presence-overrides", json=_override_body(child_id)
    )
    assert unauthenticated_override.status_code == 401

    unauthenticated_delete = await client.delete(
        "/api/v1/admin/presence-overrides/1"
    )
    assert unauthenticated_delete.status_code == 401

    # No route ran its handler: the child still has no pattern and no
    # overrides (and is present every day, the no-pattern default).
    patterns, overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert patterns == []
    assert overrides == []
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True


def _non_admin_headers() -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {make_token(groups=('some-other-group',))}"
        )
    }


_CREDENTIALS = {
    "absent": (lambda: {}, 401, None),
    "panel-token": (
        lambda: {"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"},
        403,
        PANEL_TOKEN_REJECTION_DETAIL,
    ),
    "non-admin-jwt": (_non_admin_headers, 403, FORBIDDEN_DETAIL),
}


@pytest.mark.parametrize("credential", sorted(_CREDENTIALS))
@pytest.mark.parametrize("route", ["list", "create", "edit", "delete"])
async def test_pattern_routes_enforce_admin_auth(
    admin_presence: SimpleNamespace, route: str, credential: str
) -> None:
    """Every pattern route rejects absent, panel and non-admin credentials.

    Each refused request leaves the stored pattern exactly as it was: a
    refused create adds no row, a refused edit changes nothing, a
    refused delete removes nothing.
    """
    client = admin_presence.client
    child_id = await _create_child(client)
    existing = await _create_pattern(client, child_id)
    make_headers, status, detail = _CREDENTIALS[credential]

    if route == "list":
        response = await client.get(
            _patterns_url(child_id), headers=make_headers()
        )
    elif route == "create":
        response = await client.post(
            _patterns_url(child_id),
            json=_pattern_body(name="Dad's house"),
            headers=make_headers(),
        )
    elif route == "edit":
        response = await client.patch(
            _pattern_url(existing["id"]),
            json={"name": "Renamed"},
            headers=make_headers(),
        )
    else:
        response = await client.delete(
            _pattern_url(existing["id"]), headers=make_headers()
        )

    assert response.status_code == status
    if detail is not None:
        assert response.json()["detail"] == detail
    listed = await client.get(_patterns_url(child_id), headers=_admin_headers())
    assert listed.json() == {"patterns": [existing]}


# --- the removed one-per-child schedule route ----------------------------------


async def test_old_presence_schedule_route_is_gone(
    admin_presence: SimpleNamespace,
) -> None:
    """PUT/GET /presence-schedule no longer exist; nothing is written."""
    client = admin_presence.client
    child_id = await _create_child(client)
    url = f"/api/v1/admin/children/{child_id}/presence-schedule"

    put = await client.put(
        url,
        json={
            "cycle_length_weeks": 1,
            "anchor_date": ANCHOR_MONDAY,
            "pattern": {"0": [0]},
        },
        headers=_admin_headers(),
    )
    assert put.status_code in (404, 405)
    get = await client.get(url, headers=_admin_headers())
    assert get.status_code in (404, 405)
    patterns, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert patterns == []


# --- pattern create ---------------------------------------------------------


async def test_pattern_create_persists_and_adds_a_row_per_create(
    admin_presence: SimpleNamespace,
) -> None:
    """POST /presence-patterns persists; a second POST ADDS another row."""
    client = admin_presence.client
    child_id = await _create_child(client)

    first = await client.post(
        _patterns_url(child_id),
        json=_pattern_body(),
        headers=_admin_headers(),
    )
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload == {
        "id": first_payload["id"],
        "child_id": child_id,
        "name": "Mum's house",
        "kind": "home",
        "cycle_length_weeks": 1,
        "anchor_date": ANCHOR_MONDAY,
        "pattern": {"0": [0, 2, 4]},
    }
    # Database proof: ONE pattern row, stored as encoded CSV.
    patterns, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert [record.id for record in patterns] == [first_payload["id"]]
    assert patterns[0].name == "Mum's house"
    assert patterns[0].kind == "home"
    assert patterns[0].cycle_length_weeks == 1
    assert patterns[0].anchor_date == ANCHOR_MONDAY
    assert patterns[0].pattern == "0,2,4"

    # Creating again ADDS a second pattern beside the first — the first
    # row is untouched (schema 9 has no one-per-child constraint).
    second = await client.post(
        _patterns_url(child_id),
        json=_pattern_body(
            cycle_length_weeks=2,
            pattern={"0": [], "1": [3, 1]},
            name="  Holiday rota  ",
            kind="away",
        ),
        headers=_admin_headers(),
    )
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload == {
        "id": second_payload["id"],
        "child_id": child_id,
        "name": "Holiday rota",
        "kind": "away",
        "cycle_length_weeks": 2,
        "anchor_date": ANCHOR_MONDAY,
        "pattern": {"0": [], "1": [1, 3]},
    }
    assert second_payload["id"] != first_payload["id"]
    patterns, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert [record.id for record in patterns] == [
        first_payload["id"],
        second_payload["id"],
    ]
    assert patterns[0].pattern == "0,2,4"
    assert patterns[1].pattern == "|1,3"


async def test_pattern_changes_the_childs_resolved_presence(
    admin_presence: SimpleNamespace,
) -> None:
    """The resolved presence (PresenceEngine) follows the stored patterns."""
    client = admin_presence.client
    child_id = await _create_child(client)

    # Before any pattern the child is present every day.
    _patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True
    assert engine.is_present(child_id, TUESDAY) is True

    # Home Mon/Wed/Fri only, week 0 of a one-week cycle.
    await _create_pattern(client, child_id)
    _patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True
    assert engine.is_present(child_id, TUESDAY) is False

    # An away pattern covering Monday beats the home pattern there.
    await _create_pattern(
        client,
        child_id,
        _pattern_body(pattern={"0": [0]}, name="Swim camp", kind="away"),
    )
    _patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is False
    assert engine.is_present(child_id, "2026-01-07") is True  # Wednesday
    assert engine.is_present(child_id, TUESDAY) is False


async def test_pattern_writes_regenerate_future_instances(
    admin_presence: SimpleNamespace,
) -> None:
    """An all-absent home pattern deletes the child's future instances.

    The regeneration side effect lives in the core layer the route
    calls: the child's open instances at or after today are deleted
    across ALL its definitions and NOT rebuilt while the child is
    absent every day; deleting the pattern rebuilds them.
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

    # The route's write must regenerate: a home pattern covering no day
    # makes the child absent every day and removes every open instance.
    pattern = await _create_pattern(
        client, child_id, _pattern_body(pattern={"0": []})
    )
    assert await instances.list_by_date_range(child_id, start, end) == []

    # Deleting it regenerates too: present every day again, rebuilt.
    deleted = await client.delete(
        _pattern_url(pattern["id"]), headers=_admin_headers()
    )
    assert deleted.status_code == 200
    assert await instances.list_by_date_range(child_id, start, end)


async def test_pattern_edit_regenerates_future_instances(
    admin_presence: SimpleNamespace,
) -> None:
    """PATCH regenerates: flipping an empty home pattern to away rebuilds."""
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
    pattern = await _create_pattern(
        client, child_id, _pattern_body(pattern={"0": []})
    )
    await _materialize.materialize(database, start, end, today=today)
    instances = _dao_instances.QuestInstancesDao(database)
    assert await instances.list_by_date_range(child_id, start, end) == []

    # An away pattern covering no day leaves no home pattern: present
    # every day, so the edit's regeneration builds the instances.
    edited = await client.patch(
        _pattern_url(pattern["id"]),
        json={"kind": "away"},
        headers=_admin_headers(),
    )
    assert edited.status_code == 200
    assert await instances.list_by_date_range(child_id, start, end)


# --- pattern edit (PATCH) ------------------------------------------------------


async def test_pattern_patch_changes_only_supplied_fields(
    admin_presence: SimpleNamespace,
) -> None:
    """A partial PATCH changes the supplied fields and keeps the rest."""
    client = admin_presence.client
    child_id = await _create_child(client)
    original = await _create_pattern(client, child_id)
    sibling = await _create_pattern(
        client, child_id, _pattern_body(name="Sibling", kind="away")
    )

    renamed = await client.patch(
        _pattern_url(original["id"]),
        json={"name": "Weekday home"},
        headers=_admin_headers(),
    )
    assert renamed.status_code == 200
    assert renamed.json() == dict(original, name="Weekday home")

    reshaped = await client.patch(
        _pattern_url(original["id"]),
        json={"cycle_length_weeks": 2, "pattern": {"0": [1], "1": [6, 5]}},
        headers=_admin_headers(),
    )
    assert reshaped.status_code == 200
    assert reshaped.json() == dict(
        original,
        name="Weekday home",
        cycle_length_weeks=2,
        pattern={"0": [1], "1": [5, 6]},
    )

    moved = await client.patch(
        _pattern_url(original["id"]),
        json={"anchor_date": "2026-01-12", "kind": "away"},
        headers=_admin_headers(),
    )
    assert moved.status_code == 200
    expected = dict(
        reshaped.json(), anchor_date="2026-01-12", kind="away"
    )
    assert moved.json() == expected

    # Database proof: the edited row, same id, and the sibling untouched.
    patterns, _overrides, _engine = await _child_state(
        admin_presence.database, child_id
    )
    assert [record.id for record in patterns] == [
        original["id"],
        sibling["id"],
    ]
    assert patterns[0].name == "Weekday home"
    assert patterns[0].kind == "away"
    assert patterns[0].cycle_length_weeks == 2
    assert patterns[0].anchor_date == "2026-01-12"
    assert patterns[0].pattern == "1|5,6"
    listed = await client.get(_patterns_url(child_id), headers=_admin_headers())
    assert listed.json() == {"patterns": [expected, sibling]}


async def test_pattern_patch_unknown_id_is_404(
    admin_presence: SimpleNamespace,
) -> None:
    """Editing a pattern id that does not exist is 404."""
    response = await admin_presence.client.patch(
        _pattern_url(999), json={"name": "Nope"}, headers=_admin_headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Presence pattern not found"

    malformed = await admin_presence.client.patch(
        _pattern_url("not-an-id"),
        json={"name": "Nope"},
        headers=_admin_headers(),
    )
    assert malformed.status_code == 422


@pytest.mark.parametrize(
    ("edit", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": None}, "name"),
        ({"kind": "sometimes"}, "kind"),
        ({"kind": None}, "kind"),
        ({"cycle_length_weeks": 0}, "cycle_length_weeks"),
        ({"cycle_length_weeks": 5}, "cycle_length_weeks"),
        ({"cycle_length_weeks": 2.5}, "cycle_length_weeks"),
        ({"cycle_length_weeks": "2"}, "cycle_length_weeks"),
        ({"cycle_length_weeks": None}, "cycle_length_weeks"),
        # A longer cycle without a matching pattern leaves week 1 uncovered.
        ({"cycle_length_weeks": 2}, "pattern"),
        ({"anchor_date": "2026-13-40"}, "anchor_date"),
        ({"anchor_date": None}, "anchor_date"),
        ({"pattern": {}}, "pattern"),
        ({"pattern": None}, "pattern"),
        ({"pattern": {"0": [7]}}, "pattern"),  # weekday out of 0..6
        # Strict JSON integer weekdays: no bool, string or float coercion.
        ({"pattern": {"0": [True]}}, "pattern"),
        ({"pattern": {"0": [False]}}, "pattern"),
        ({"pattern": {"0": ["1"]}}, "pattern"),
        ({"pattern": {"0": [1.0]}}, "pattern"),
    ],
)
async def test_rejected_pattern_patch_is_422_and_changes_nothing(
    admin_presence: SimpleNamespace, edit: dict[str, object], field: str
) -> None:
    """A rejected edit (incl. explicit null) is 422 naming the field."""
    client = admin_presence.client
    child_id = await _create_child(client)
    original = await _create_pattern(client, child_id)

    response = await client.patch(
        _pattern_url(original["id"]), json=edit, headers=_admin_headers()
    )
    assert response.status_code == 422, response.text
    assert _detail_names(response, field), response.json()
    listed = await client.get(_patterns_url(child_id), headers=_admin_headers())
    assert listed.json() == {"patterns": [original]}


# --- pattern delete ------------------------------------------------------------


async def test_pattern_delete_removes_one_pattern_and_presence_resolves(
    admin_presence: SimpleNamespace,
) -> None:
    """DELETE removes the one pattern; its siblings and presence follow."""
    client = admin_presence.client
    child_id = await _create_child(client)
    home = await _create_pattern(client, child_id)
    away = await _create_pattern(
        client,
        child_id,
        _pattern_body(pattern={"0": [0]}, name="Swim camp", kind="away"),
    )
    _patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert engine.is_present(child_id, ANCHOR_MONDAY) is False

    deleted = await client.delete(
        _pattern_url(away["id"]), headers=_admin_headers()
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "ok"}
    assert (
        await _dao_presence.PresencePatternsDao(admin_presence.database).get(
            away["id"]
        )
        is None
    )
    patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert [record.id for record in patterns] == [home["id"]]
    assert engine.is_present(child_id, ANCHOR_MONDAY) is True
    assert engine.is_present(child_id, TUESDAY) is False

    # Deleting the last pattern: present every day again.
    deleted = await client.delete(
        _pattern_url(home["id"]), headers=_admin_headers()
    )
    assert deleted.status_code == 200
    patterns, _overrides, engine = await _child_state(
        admin_presence.database, child_id
    )
    assert patterns == []
    assert engine.is_present(child_id, TUESDAY) is True

    # A second delete of the same id is 404: it no longer exists.
    again = await client.delete(
        _pattern_url(home["id"]), headers=_admin_headers()
    )
    assert again.status_code == 404
    assert again.json()["detail"] == "Presence pattern not found"


async def test_delete_unknown_pattern_is_404(
    admin_presence: SimpleNamespace,
) -> None:
    """Deleting a pattern id that does not exist is 404."""
    response = await admin_presence.client.delete(
        _pattern_url(999), headers=_admin_headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Presence pattern not found"

    malformed = await admin_presence.client.delete(
        _pattern_url("not-an-id"), headers=_admin_headers()
    )
    assert malformed.status_code == 422


# --- override create + delete -----------------------------------------------


async def test_override_is_created_then_deleted_and_presence_resolves(
    admin_presence: SimpleNamespace,
) -> None:
    """POST creates the override, DELETE removes it; presence follows."""
    client = admin_presence.client
    database = admin_presence.database
    child_id = await _create_child(client)
    await _create_pattern(client, child_id)

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
    _patterns, overrides, engine = await _child_state(database, child_id)
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
    _patterns, overrides, engine = await _child_state(database, child_id)
    assert overrides == []
    assert engine.is_present(child_id, TUESDAY) is False


# --- error mapping: 404 vs 422 ----------------------------------------------


async def test_pattern_and_override_for_unknown_child_are_404(
    admin_presence: SimpleNamespace,
) -> None:
    """A presence write naming a child that does not exist is 404."""
    client = admin_presence.client

    pattern = await client.post(
        _patterns_url(999),
        json=_pattern_body(),
        headers=_admin_headers(),
    )
    assert pattern.status_code == 404
    assert pattern.json()["detail"] == "Child not found"

    override = await client.post(
        "/api/v1/admin/presence-overrides",
        json=_override_body(999),
        headers=_admin_headers(),
    )
    assert override.status_code == 404
    assert override.json()["detail"] == "Child not found"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (_pattern_body(cycle_length_weeks=0), "cycle_length_weeks"),
        (_pattern_body(cycle_length_weeks=5), "cycle_length_weeks"),
        # Strict JSON integers only: no float or string coercion.
        (_pattern_body(cycle_length_weeks=2.5), "cycle_length_weeks"),
        (_pattern_body(cycle_length_weeks="2"), "cycle_length_weeks"),
        (_pattern_body(cycle_length_weeks=1.0), "cycle_length_weeks"),
        # week 1 of the cycle missing:
        (_pattern_body(cycle_length_weeks=2, pattern={"0": [0]}), "pattern"),
        (_pattern_body(pattern={}), "pattern"),
        (_pattern_body(anchor_date="2026-13-40"), "anchor_date"),
        (_pattern_body(anchor_date="05/01/2026"), "anchor_date"),
        (_pattern_body(pattern={"0": [7]}), "pattern"),  # weekday out of 0..6
        # Strict JSON integer weekdays: no bool, string or float coercion.
        (_pattern_body(pattern={"0": [True]}), "pattern"),
        (_pattern_body(pattern={"0": [False]}), "pattern"),
        (_pattern_body(pattern={"0": ["1"]}), "pattern"),
        (_pattern_body(pattern={"0": [1.0]}), "pattern"),
        (_pattern_body(pattern={"nope": [0]}), "pattern"),  # non-int week
        (_pattern_body(pattern={"0": "0,2,4"}), "pattern"),  # not a list
        (_pattern_body(kind="sometimes"), "kind"),
        (_pattern_body(kind="HOME"), "kind"),
        (_pattern_body(name=""), "name"),
        (_pattern_body(name="   "), "name"),
    ],
)
async def test_rejected_pattern_is_422(
    admin_presence: SimpleNamespace, body: dict[str, object], field: str
) -> None:
    """A rejected pattern is 422 naming the field, and stores nothing."""
    client = admin_presence.client
    child_id = await _create_child(client)
    response = await client.post(
        _patterns_url(child_id),
        json=body,
        headers=_admin_headers(),
    )
    assert response.status_code == 422, response.text
    assert _detail_names(response, field), response.json()
    assert (
        await _dao_presence.PresencePatternsDao(
            admin_presence.database
        ).list_by_child(child_id)
        == []
    )


@pytest.mark.parametrize("missing", ["name", "kind"])
async def test_pattern_missing_required_field_is_422(
    admin_presence: SimpleNamespace, missing: str
) -> None:
    """The new required fields cannot be omitted (an old schedule body)."""
    client = admin_presence.client
    child_id = await _create_child(client)
    body = _pattern_body()
    del body[missing]
    response = await client.post(
        _patterns_url(child_id), json=body, headers=_admin_headers()
    )
    assert response.status_code == 422
    assert _detail_names(response, missing)


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
    _patterns, overrides, _engine = await _child_state(
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
