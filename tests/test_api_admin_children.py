"""Admin-plane children route tests (task e4845baa).

These tests exercise the admin plane's children routes against the
ASGI app with httpx, reusing the shared local-RSA-key/stubbed-JWKS
harness (:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.

Every done-condition case is proven against the DATABASE, read through
the SAME core copy the app uses (``nestquest_core.*``; see the two-copy
caveat in api/nestquest_core.py):

- Authentication runs through the router's ONE ``require_admin``
  dependency: an admin JWT passes, a JWT without the group is 403, an
  absent credential is 401 — and no row is written.
- ``POST /api/v1/admin/children``: the created child EXISTS with the
  given display name (and the optional colour/avatar_ref/sort_order).
- ``PATCH /api/v1/admin/children/{id}``: an edit PERSISTS the supplied
  fields and leaves omitted fields untouched (exclude_unset semantics —
  an omitted field is never passed to the core).
- ``PATCH /api/v1/admin/children/{id}/active`` with ``is_active: false``
  sets the active flag FALSE and the row STILL EXISTS (children are
  never hard-deleted).
- ``POST /api/v1/admin/children/reorder``: the posted order becomes the
  rows' sort_order; a list that is not a complete permutation is 422
  and leaves the stored order untouched.

Error mapping (documented in api/routes_admin.py): a core ValueError
for a non-existent child is 404; every other core ValueError (an empty
display name, an explicit null colour, a bad permutation) is 422 — the
same failure class FastAPI reports for malformed bodies.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import httpx
import pytest

from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

# The children business layer through the SAME core copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy) —
# used for the tests' database assertions only; the routes reach it
# through api.nestquest_core.
_children = importlib.import_module("nestquest_core.children")


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


async def _children_by_id(database: object) -> dict[int, object]:
    """Every child row through the app's core copy, keyed by id."""
    records = await _children.list_children(database)
    return {record.id: record for record in records}


@pytest.fixture
async def admin_children(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database.

    The same runner the auth tests use (stubbed JWKS, no network); the
    fixture also exposes the app's ONE database connection so tests
    assert the routes' effects on the stored rows themselves.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


# --- authentication: the ONE require_admin dependency guards every route ---


async def test_children_routes_refuse_non_admin_and_absent_credentials(
    admin_children: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401: nothing written."""
    client = admin_children.client
    body = {"display_name": "Ada"}
    non_admin = make_token(groups=("some-other-group",))

    forbidden = await client.post(
        "/api/v1/admin/children",
        json=body,
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )

    unauthenticated = await client.post("/api/v1/admin/children", json=body)
    assert unauthenticated.status_code == 401

    unauthenticated_list = await client.get("/api/v1/admin/children")
    assert unauthenticated_list.status_code == 401

    # No route ran its handler: the household is still empty.
    assert await _children_by_id(admin_children.database) == {}


# --- create -----------------------------------------------------------------


async def test_create_child_persists_the_given_name(
    admin_children: SimpleNamespace,
) -> None:
    """POST /children creates the row; the child exists with that name."""
    response = await admin_children.client.post(
        "/api/v1/admin/children",
        json={
            "display_name": "Ada",
            "colour": "#ff8800",
            "avatar_ref": "avatar:bee",
            "sort_order": 2,
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Ada"
    assert body["colour"] == "#ff8800"
    assert body["avatar_ref"] == "avatar:bee"
    assert body["sort_order"] == 2
    assert body["is_active"] is True

    stored = (await _children_by_id(admin_children.database))[body["id"]]
    assert stored.display_name == "Ada"
    assert stored.colour == "#ff8800"
    assert stored.avatar_ref == "avatar:bee"
    assert stored.sort_order == 2
    assert stored.is_active is True


async def test_create_child_with_only_a_name_uses_core_defaults(
    admin_children: SimpleNamespace,
) -> None:
    """Omitted optional fields default through the core layer."""
    response = await admin_children.client.post(
        "/api/v1/admin/children",
        json={"display_name": "Bo"},
        headers=_admin_headers(),
    )
    assert response.status_code == 201
    stored = (await _children_by_id(admin_children.database))[
        response.json()["id"]
    ]
    assert stored.display_name == "Bo"
    assert stored.colour is None
    assert stored.avatar_ref is None
    assert stored.sort_order == 0
    assert stored.is_active is True


@pytest.mark.parametrize(
    "body",
    [
        {},  # display_name missing
        {"display_name": 5},  # wrong type
        {"display_name": ""},  # empty: the core rejects it
        {"display_name": "   "},  # whitespace-only: empty to a parent
        {"display_name": "Ada", "sort_order": "first"},  # wrong type
    ],
)
async def test_create_child_malformed_input_is_422(
    admin_children: SimpleNamespace, body: dict[str, object]
) -> None:
    """Malformed bodies are 422 and never create a row."""
    response = await admin_children.client.post(
        "/api/v1/admin/children", json=body, headers=_admin_headers()
    )
    assert response.status_code == 422
    assert await _children_by_id(admin_children.database) == {}


# --- edit -------------------------------------------------------------------


async def test_edit_child_persists_supplied_fields_and_skips_omitted_ones(
    admin_children: SimpleNamespace,
) -> None:
    """PATCH persists exactly the supplied fields (exclude_unset)."""
    client = admin_children.client
    created = await client.post(
        "/api/v1/admin/children",
        json={
            "display_name": "Ada",
            "colour": "#ff8800",
            "avatar_ref": "avatar:bee",
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    child_id = created.json()["id"]

    # Only display_name and sort_order: colour/avatar_ref must survive.
    edited = await client.patch(
        f"/api/v1/admin/children/{child_id}",
        json={"display_name": "Ada Lovelace", "sort_order": 4},
        headers=_admin_headers(),
    )
    assert edited.status_code == 200
    assert edited.json()["display_name"] == "Ada Lovelace"
    assert edited.json()["sort_order"] == 4
    stored = (await _children_by_id(admin_children.database))[child_id]
    assert stored.display_name == "Ada Lovelace"
    assert stored.sort_order == 4
    # The omitted fields were never passed to the core: unchanged.
    assert stored.colour == "#ff8800"
    assert stored.avatar_ref == "avatar:bee"

    # A second edit touching only colour leaves the name alone.
    recoloured = await client.patch(
        f"/api/v1/admin/children/{child_id}",
        json={"colour": "#00aa55"},
        headers=_admin_headers(),
    )
    assert recoloured.status_code == 200
    stored = (await _children_by_id(admin_children.database))[child_id]
    assert stored.colour == "#00aa55"
    assert stored.display_name == "Ada Lovelace"


async def test_edit_unknown_child_is_404(
    admin_children: SimpleNamespace,
) -> None:
    """An edit naming a child that does not exist is 404."""
    response = await admin_children.client.patch(
        "/api/v1/admin/children/999",
        json={"display_name": "Nobody"},
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Child not found"


async def test_edit_explicit_null_colour_is_422_and_changes_nothing(
    admin_children: SimpleNamespace,
) -> None:
    """An explicit null (clearing) is passed through and rejected by the core.

    Only the fields the request SUPPLIES are forwarded: a null colour is
    a supplied None, which the core refuses (the DAO cannot express
    NULL) — mapped to 422, with the stored colour left untouched.
    """
    created = await admin_children.client.post(
        "/api/v1/admin/children",
        json={"display_name": "Ada", "colour": "#ff8800"},
        headers=_admin_headers(),
    )
    child_id = created.json()["id"]
    response = await admin_children.client.patch(
        f"/api/v1/admin/children/{child_id}",
        json={"colour": None},
        headers=_admin_headers(),
    )
    assert response.status_code == 422
    stored = (await _children_by_id(admin_children.database))[child_id]
    assert stored.colour == "#ff8800"


# --- set_active -------------------------------------------------------------


async def test_deactivation_sets_the_flag_false_and_never_deletes(
    admin_children: SimpleNamespace,
) -> None:
    """is_active=false deactivates the row; the row STILL exists."""
    client = admin_children.client
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": "Ada"},
        headers=_admin_headers(),
    )
    child_id = created.json()["id"]

    deactivated = await client.patch(
        f"/api/v1/admin/children/{child_id}/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # Database proof: the flag is False and the row was NOT hard-deleted.
    rows = await _children_by_id(admin_children.database)
    stored = rows[child_id]
    assert stored.is_active is False
    assert stored.display_name == "Ada"

    # Reactivation goes through the same route: the flag is set, not
    # one-way.
    reactivated = await client.patch(
        f"/api/v1/admin/children/{child_id}/active",
        json={"is_active": True},
        headers=_admin_headers(),
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    rows = await _children_by_id(admin_children.database)
    assert rows[child_id].is_active is True


async def test_set_active_unknown_child_is_404(
    admin_children: SimpleNamespace,
) -> None:
    """A set_active naming a child that does not exist is 404."""
    response = await admin_children.client.patch(
        "/api/v1/admin/children/999/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Child not found"


async def test_set_active_malformed_body_is_422(
    admin_children: SimpleNamespace,
) -> None:
    """A non-bool is_active is rejected by the body model (422)."""
    response = await admin_children.client.patch(
        "/api/v1/admin/children/1/active",
        json={"is_active": "maybe"},
        headers=_admin_headers(),
    )
    assert response.status_code == 422


# --- reorder ----------------------------------------------------------------


async def test_reorder_writes_the_posted_order_to_sort_order(
    admin_children: SimpleNamespace,
) -> None:
    """The posted id order becomes the rows' sort_order."""
    client = admin_children.client
    ids = []
    for name in ("Ada", "Bo", "Cyd"):
        created = await client.post(
            "/api/v1/admin/children",
            json={"display_name": name},
            headers=_admin_headers(),
        )
        assert created.status_code == 201
        ids.append(created.json()["id"])

    response = await client.post(
        "/api/v1/admin/children/reorder",
        json={"ordered_ids": [ids[2], ids[0], ids[1]]},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Database proof: each posted position became that child's sort_order.
    rows = await _children_by_id(admin_children.database)
    assert rows[ids[2]].sort_order == 0
    assert rows[ids[0]].sort_order == 1
    assert rows[ids[1]].sort_order == 2


async def test_reorder_rejects_non_permutations_and_writes_nothing(
    admin_children: SimpleNamespace,
) -> None:
    """A list that is not a complete permutation is 422, order intact.

    The core rejects the list BEFORE any write, so the stored sort_order
    values survive every rejected call unchanged.
    """
    client = admin_children.client
    ids = []
    for name in ("Ada", "Bo"):
        created = await client.post(
            "/api/v1/admin/children",
            json={"display_name": name},
            headers=_admin_headers(),
        )
        assert created.status_code == 201
        ids.append(created.json()["id"])

    bad_lists = [
        ids[:1],  # partial: missing an existing child
        [ids[0], ids[0], ids[1]],  # duplicate id
        [*ids, ids[1] + 999],  # unknown id
    ]
    for ordered_ids in bad_lists:
        response = await client.post(
            "/api/v1/admin/children/reorder",
            json={"ordered_ids": ordered_ids},
            headers=_admin_headers(),
        )
        assert response.status_code == 422, ordered_ids

    # A non-integer id never reaches the core either (body model).
    malformed = await client.post(
        "/api/v1/admin/children/reorder",
        json={"ordered_ids": ["first", "second"]},
        headers=_admin_headers(),
    )
    assert malformed.status_code == 422

    # Database proof: no write happened for any rejected call.
    rows = await _children_by_id(admin_children.database)
    assert [rows[child_id].sort_order for child_id in ids] == [0, 0]


# --- list (the read model the admin PWA re-renders from) ---------------------


async def test_list_children_returns_all_in_display_order(
    admin_children: SimpleNamespace,
) -> None:
    """GET /children returns every child (inactive included) in order."""
    client = admin_children.client
    ada = await client.post(
        "/api/v1/admin/children",
        json={"display_name": "Ada", "sort_order": 5},
        headers=_admin_headers(),
    )
    bo = await client.post(
        "/api/v1/admin/children",
        json={"display_name": "Bo", "sort_order": 1},
        headers=_admin_headers(),
    )
    deactivated = await client.patch(
        f"/api/v1/admin/children/{ada.json()['id']}/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200

    response = await client.get(
        "/api/v1/admin/children", headers=_admin_headers()
    )
    assert response.status_code == 200
    children = response.json()["children"]
    assert [child["id"] for child in children] == [
        bo.json()["id"],
        ada.json()["id"],
    ]
    by_id = {child["id"]: child for child in children}
    assert by_id[ada.json()["id"]]["is_active"] is False
    assert by_id[bo.json()["id"]]["is_active"] is True
    # The serialized shape is the documented child payload.
    assert set(by_id[bo.json()["id"]]) == {
        "id",
        "display_name",
        "colour",
        "avatar_ref",
        "sort_order",
        "is_active",
    }
