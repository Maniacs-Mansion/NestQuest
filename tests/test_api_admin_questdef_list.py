"""Admin-plane quest-definition LIST route tests (task d4667573).

``GET /api/v1/admin/quest-definitions`` against the ASGI app with httpx,
reusing the shared local-RSA-key/stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely authenticates
with NO network access.

- An admin JWT lists EVERY definition — active AND inactive — in rising
  id order, each in the same documented shape as the create/edit
  responses (id, title, description, icon, is_active, rule, assignees,
  windows).
- An empty household lists nothing: 200 with an empty list.
- Authentication runs through the router's ONE ``require_admin``
  dependency: an absent credential is 401, the panel service token is
  refused outright (403, the credential-type detail), and a JWT without
  the nestquest-admins group is 403.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

#: The admin list route under test.
LIST_PATH = "/api/v1/admin/quest-definitions"

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


@pytest.fixture
async def admin_client(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client over a fresh (empty) household."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield client


async def _seed_active_and_inactive(client: object) -> tuple[int, int, int]:
    """Seed one child, an ACTIVE definition and an INACTIVE one.

    Returns ``(child_id, active_id, inactive_id)``.  Seeded through the
    admin routes so the rows are exactly what the admin plane writes.
    """
    child = await client.post(
        "/api/v1/admin/children",
        json={"display_name": "Ada"},
        headers=_admin_headers(),
    )
    assert child.status_code == 201
    child_id = child.json()["id"]

    active = await client.post(
        LIST_PATH,
        json={
            "title": "Tidy the den",
            "rule": {
                "rule_type": "weekly",
                "interval": 1,
                "weekday_set": [0, 2],
                "start_date": "2026-03-02",
            },
            "assignee_child_ids": [child_id],
            "windows": ["morning", ["evening", "19:30"]],
            "description": "Put everything back where it belongs.",
            "icon": "toy-box",
        },
        headers=_admin_headers(),
    )
    assert active.status_code == 201

    inactive = await client.post(
        LIST_PATH,
        json={
            "title": "Water the plants",
            "rule": {
                "rule_type": "daily",
                "interval": 1,
                "start_date": "2026-03-01",
            },
            "assignee_child_ids": [child_id],
            "windows": ["afternoon"],
        },
        headers=_admin_headers(),
    )
    assert inactive.status_code == 201
    inactive_id = inactive.json()["id"]
    deactivated = await client.patch(
        f"{LIST_PATH}/{inactive_id}/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200

    return child_id, active.json()["id"], inactive_id


async def test_admin_lists_active_and_inactive_definitions_with_full_shape(
    admin_client: object,
) -> None:
    """Both definitions come back, by rising id, in the documented shape."""
    child_id, active_id, inactive_id = await _seed_active_and_inactive(
        admin_client
    )

    response = await admin_client.get(LIST_PATH, headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {
        "definitions": [
            {
                "id": active_id,
                "title": "Tidy the den",
                "description": "Put everything back where it belongs.",
                "icon": "toy-box",
                "is_active": True,
                "skip_on_away": True,
                "rule": {
                    "rule_type": "weekly",
                    "interval": 1,
                    "weekday_set": [0, 2],
                    "day_of_month": None,
                    "nth_weekday": None,
                    "nth_weekday_weekday": None,
                    "month": None,
                    "start_date": "2026-03-02",
                    "end_date": None,
                },
                "assignees": [{"id": child_id, "display_name": "Ada"}],
                "windows": [
                    {"window": "morning", "due_time": None},
                    {"window": "evening", "due_time": "19:30"},
                ],
            },
            {
                "id": inactive_id,
                "title": "Water the plants",
                "description": None,
                "icon": None,
                "is_active": False,
                "skip_on_away": True,
                "rule": {
                    "rule_type": "daily",
                    "interval": 1,
                    "weekday_set": None,
                    "day_of_month": None,
                    "nth_weekday": None,
                    "nth_weekday_weekday": None,
                    "month": None,
                    "start_date": "2026-03-01",
                    "end_date": None,
                },
                "assignees": [{"id": child_id, "display_name": "Ada"}],
                "windows": [{"window": "afternoon", "due_time": None}],
            },
        ]
    }


async def test_list_items_match_the_create_response_shape(
    admin_client: object,
) -> None:
    """Each listed item is exactly what the create route returned."""
    child = await admin_client.post(
        "/api/v1/admin/children",
        json={"display_name": "Ben"},
        headers=_admin_headers(),
    )
    created = await admin_client.post(
        LIST_PATH,
        json={
            "title": "Feed the cat",
            "rule": {
                "rule_type": "daily",
                "interval": 1,
                "start_date": "2026-03-01",
            },
            "assignee_child_ids": [child.json()["id"]],
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201

    response = await admin_client.get(LIST_PATH, headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {"definitions": [created.json()]}


async def test_skip_on_away_round_trips_true_and_false_through_list(
    admin_client: object,
) -> None:
    """skip_on_away posted true, false, or omitted lists back as stored."""
    child = await admin_client.post(
        "/api/v1/admin/children",
        json={"display_name": "Cleo"},
        headers=_admin_headers(),
    )
    child_id = child.json()["id"]

    async def create(title: str, extra: dict[str, object]) -> dict:
        response = await admin_client.post(
            LIST_PATH,
            json={
                "title": title,
                "rule": {
                    "rule_type": "daily",
                    "interval": 1,
                    "start_date": "2026-03-01",
                },
                "assignee_child_ids": [child_id],
                "windows": ["morning"],
                **extra,
            },
            headers=_admin_headers(),
        )
        assert response.status_code == 201
        return response.json()

    skipping = await create("Skip when away", {"skip_on_away": True})
    keeping = await create("Keep when away", {"skip_on_away": False})
    defaulted = await create("Default", {})
    assert skipping["skip_on_away"] is True
    assert keeping["skip_on_away"] is False
    assert defaulted["skip_on_away"] is True

    response = await admin_client.get(LIST_PATH, headers=_admin_headers())

    assert response.status_code == 200
    listed = {item["id"]: item for item in response.json()["definitions"]}
    assert listed[skipping["id"]]["skip_on_away"] is True
    assert listed[keeping["id"]]["skip_on_away"] is False
    assert listed[defaulted["id"]]["skip_on_away"] is True
    assert response.json() == {"definitions": [skipping, keeping, defaulted]}


async def test_empty_household_lists_no_definitions(
    admin_client: object,
) -> None:
    """With no definitions stored the list is 200 and empty."""
    response = await admin_client.get(LIST_PATH, headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {"definitions": []}


async def test_list_without_credentials_is_401(admin_client: object) -> None:
    """An absent credential is the uniform 401."""
    response = await admin_client.get(LIST_PATH)

    assert response.status_code == 401


async def test_list_with_panel_service_token_is_403(
    admin_client: object,
) -> None:
    """The panel service token is refused outright, never a JWT."""
    response = await admin_client.get(
        LIST_PATH,
        headers={"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL


async def test_list_with_non_admin_jwt_is_403(admin_client: object) -> None:
    """A valid JWT without the nestquest-admins group is 403."""
    non_admin = make_token(groups=("some-other-group",))
    response = await admin_client.get(
        LIST_PATH, headers={"Authorization": f"Bearer {non_admin}"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL
