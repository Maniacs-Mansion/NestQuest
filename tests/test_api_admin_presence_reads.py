"""Admin-plane presence READ route tests (task 07fde892).

``GET /api/v1/admin/children/{child_id}/presence-patterns`` and
``GET /api/v1/admin/presence-overrides`` against the ASGI app with
httpx, through the shared stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) — no network access.

- The patterns read answers ``{"patterns": [...]}`` in the POST
  response's shape for seeded patterns, ordered by id (a child may have
  several), ``{"patterns": []}`` for a child with none (present every
  day — NOT a 404), and 404 for an unknown child.
- The overrides read answers ``{"overrides": [...]}`` in the POST
  response's shape, ordered by start date, child id, id; ``child_id``
  and the ``start``/``end`` range each narrow the list; a malformed or
  inverted range is 422 and an unknown ``child_id`` is 404.
- Both routes inherit the router's ONE ``require_admin``: no
  credential 401, the panel service token 403, a non-admin JWT 403, an
  admin JWT 200.

Seeding goes through the admin write routes, so the reads are proven
against rows the real write path stored.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.admin_jwt_harness import ADMIN_KEY, KID, AdminRunner, jwks_for, make_token

OVERRIDES_URL = "/api/v1/admin/presence-overrides"

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


def _patterns_url(child_id: int) -> str:
    return f"/api/v1/admin/children/{child_id}/presence-patterns"


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


async def _create_child(client: object, name: str) -> int:
    """Create one child through the admin children route; return the id."""
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": name},
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _create_override(
    client: object,
    child_id: int,
    start_date: str,
    end_date: str,
    *,
    is_present: bool = False,
    note: str | None = None,
) -> dict[str, object]:
    """Create one override through the admin write route; return it."""
    created = await client.post(
        OVERRIDES_URL,
        json={
            "child_id": child_id,
            "start_date": start_date,
            "end_date": end_date,
            "is_present": is_present,
            "note": note,
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.fixture
async def reads(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane client over a fresh database."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(client=client)


@pytest.fixture
async def seeded(reads: SimpleNamespace) -> SimpleNamespace:
    """Two children with interleaved overrides (Ada has a home pattern)."""
    client = reads.client
    ada = await _create_child(client, "Ada")
    ben = await _create_child(client, "Ben")
    created = await client.post(
        _patterns_url(ada),
        json={
            "name": "Custody",
            "kind": "home",
            "cycle_length_weeks": 2,
            "anchor_date": "2026-01-05",
            "pattern": {"0": [4, 0, 2], "1": []},
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201, created.text
    ada_custody = created.json()
    ada_march = await _create_override(
        client, ada, "2026-03-01", "2026-03-07", note="grandparents"
    )
    ben_january = await _create_override(
        client, ben, "2026-01-10", "2026-01-12", is_present=True
    )
    ben_march = await _create_override(client, ben, "2026-03-01", "2026-03-01")
    ada_may = await _create_override(client, ada, "2026-05-20", "2026-05-20")
    return SimpleNamespace(
        client=client,
        ada=ada,
        ben=ben,
        ada_march=ada_march,
        ben_january=ben_january,
        ben_march=ben_march,
        ada_may=ada_may,
        ada_custody=ada_custody,
    )


# --- presence patterns read ------------------------------------------------


async def test_patterns_read_returns_the_stored_patterns(
    seeded: SimpleNamespace,
) -> None:
    """A seeded pattern reads back in the POST response's shape."""
    response = await seeded.client.get(
        _patterns_url(seeded.ada), headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {
        "patterns": [
            {
                "id": seeded.ada_custody["id"],
                "child_id": seeded.ada,
                "name": "Custody",
                "kind": "home",
                "cycle_length_weeks": 2,
                "anchor_date": "2026-01-05",
                "pattern": {"0": [0, 2, 4], "1": []},
            }
        ]
    }
    assert response.json()["patterns"] == [seeded.ada_custody]


async def test_patterns_read_lists_several_patterns_in_id_order(
    seeded: SimpleNamespace,
) -> None:
    """A child's patterns (zero or more) are listed ordered by id."""
    client = seeded.client
    away = await client.post(
        _patterns_url(seeded.ada),
        json={
            "name": "Camp",
            "kind": "away",
            "cycle_length_weeks": 1,
            "anchor_date": "2026-01-05",
            "pattern": {"0": [6, 5]},
        },
        headers=_admin_headers(),
    )
    assert away.status_code == 201, away.text
    third = await client.post(
        _patterns_url(seeded.ada),
        json={
            "name": "Weekday lessons",
            "kind": "home",
            "cycle_length_weeks": 1,
            "anchor_date": "2026-01-05",
            "pattern": {"0": [1]},
        },
        headers=_admin_headers(),
    )
    assert third.status_code == 201, third.text

    response = await client.get(
        _patterns_url(seeded.ada), headers=_admin_headers()
    )
    assert response.status_code == 200
    patterns = response.json()["patterns"]
    assert patterns == [seeded.ada_custody, away.json(), third.json()]
    ids = [pattern["id"] for pattern in patterns]
    assert ids == sorted(ids)
    assert patterns[1]["pattern"] == {"0": [5, 6]}
    # Ben's list is untouched by Ada's patterns.
    ben = await client.get(_patterns_url(seeded.ben), headers=_admin_headers())
    assert ben.json() == {"patterns": []}


async def test_patterns_read_without_patterns_is_empty_not_404(
    seeded: SimpleNamespace,
) -> None:
    """A child with no pattern (present every day) is an empty list."""
    response = await seeded.client.get(
        _patterns_url(seeded.ben), headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"patterns": []}


async def test_patterns_read_unknown_child_is_404(
    reads: SimpleNamespace,
) -> None:
    """An unknown child is 404 with the children routes' detail."""
    response = await reads.client.get(
        _patterns_url(999), headers=_admin_headers()
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Child not found"}


async def test_old_presence_schedule_read_route_is_gone(
    seeded: SimpleNamespace,
) -> None:
    """The removed one-per-child schedule read no longer exists."""
    response = await seeded.client.get(
        f"/api/v1/admin/children/{seeded.ada}/presence-schedule",
        headers=_admin_headers(),
    )
    assert response.status_code in (404, 405)


# --- presence overrides read -----------------------------------------------


async def test_overrides_read_lists_all_in_stable_order(
    seeded: SimpleNamespace,
) -> None:
    """Unfiltered: every override, by start date, then child id, then id."""
    response = await seeded.client.get(
        OVERRIDES_URL, headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {
        "overrides": [
            seeded.ben_january,
            seeded.ada_march,
            seeded.ben_march,
            seeded.ada_may,
        ]
    }
    assert seeded.ada_march == {
        "id": seeded.ada_march["id"],
        "child_id": seeded.ada,
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "is_present": False,
        "note": "grandparents",
    }


async def test_overrides_read_empty_household(reads: SimpleNamespace) -> None:
    """No overrides at all is an empty list."""
    response = await reads.client.get(OVERRIDES_URL, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"overrides": []}


async def test_overrides_read_filters_by_child(
    seeded: SimpleNamespace,
) -> None:
    """child_id keeps only that child's overrides."""
    response = await seeded.client.get(
        OVERRIDES_URL,
        params={"child_id": seeded.ada},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {
        "overrides": [seeded.ada_march, seeded.ada_may]
    }


async def test_overrides_read_filters_by_overlapping_range(
    seeded: SimpleNamespace,
) -> None:
    """start/end keep overrides overlapping the closed range (inclusive)."""
    # 2026-03-07 is Ada's March override's LAST day: the boundary counts.
    response = await seeded.client.get(
        OVERRIDES_URL,
        params={"start": "2026-03-07", "end": "2026-05-20"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {
        "overrides": [seeded.ada_march, seeded.ada_may]
    }


async def test_overrides_read_open_ended_range_filters(
    seeded: SimpleNamespace,
) -> None:
    """start alone keeps later-ending, end alone keeps earlier-starting."""
    from_april = await seeded.client.get(
        OVERRIDES_URL, params={"start": "2026-04-01"}, headers=_admin_headers()
    )
    assert from_april.json() == {"overrides": [seeded.ada_may]}
    until_january = await seeded.client.get(
        OVERRIDES_URL, params={"end": "2026-01-31"}, headers=_admin_headers()
    )
    assert until_january.json() == {"overrides": [seeded.ben_january]}


async def test_overrides_read_combines_child_and_range(
    seeded: SimpleNamespace,
) -> None:
    """child_id and the range narrow together."""
    response = await seeded.client.get(
        OVERRIDES_URL,
        params={"child_id": seeded.ben, "start": "2026-02-01", "end": "2026-12-31"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {"overrides": [seeded.ben_march]}


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-03-10", "end": "2026-03-01"},
        {"start": "2026-3-1"},
        {"end": "not-a-date"},
        {"start": "2026-02-30"},
    ],
)
async def test_overrides_read_invalid_range_is_422(
    seeded: SimpleNamespace, params: dict[str, str]
) -> None:
    """A malformed date or an inverted range is the core's 422."""
    response = await seeded.client.get(
        OVERRIDES_URL, params=params, headers=_admin_headers()
    )
    assert response.status_code == 422


async def test_overrides_read_unknown_child_is_404(
    reads: SimpleNamespace,
) -> None:
    """An unknown child_id filter is 404, never an empty list."""
    response = await reads.client.get(
        OVERRIDES_URL, params={"child_id": 999}, headers=_admin_headers()
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Child not found"}


# --- authentication: the router's ONE require_admin --------------------------


@pytest.fixture(params=["patterns", "overrides"])
async def read_url(request: pytest.FixtureRequest, reads: SimpleNamespace) -> str:
    """Each read route's URL (the patterns route for a real child)."""
    if request.param == "overrides":
        return OVERRIDES_URL
    return _patterns_url(await _create_child(reads.client, "Ada"))


async def test_read_without_credential_is_401(
    reads: SimpleNamespace, read_url: str
) -> None:
    response = await reads.client.get(read_url)
    assert response.status_code == 401


async def test_read_refuses_panel_service_token(
    reads: SimpleNamespace, read_url: str
) -> None:
    response = await reads.client.get(
        read_url, headers={"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL


async def test_read_refuses_non_admin_jwt(
    reads: SimpleNamespace, read_url: str
) -> None:
    non_admin = make_token(groups=("some-other-group",))
    response = await reads.client.get(
        read_url, headers={"Authorization": f"Bearer {non_admin}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


async def test_read_admin_jwt_is_200(
    reads: SimpleNamespace, read_url: str
) -> None:
    response = await reads.client.get(read_url, headers=_admin_headers())
    assert response.status_code == 200
