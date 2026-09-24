"""Admin override consequence-count route tests (task 7616e3eb).

``POST /api/v1/admin/presence-overrides/consequence`` answers, BEFORE an
override is saved, how many of the child's upcoming open quest
instances saving it would remove (``{"removed": N}``) — the ADMIN-SPEC
§6 "This removes N upcoming tasks" warning.  These tests exercise it
against the ASGI app with the shared stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`):

- a two-week custody pattern (present the whole first week of the
  cycle, absent the whole second) where an absent override over a
  known span removes an EXACT number of instances;
- ranges that remove nothing (already-absent days, a present
  override) count 0;
- an instance with a completion event inside the range is NOT counted
  (D-005 — regeneration never deletes it);
- a ``skip_on_away = false`` definition contributes nothing;
- the count MATCHES a direct materialise comparison: the override is
  then actually created (which regenerates the child) and the removed
  open future instances are counted from the database;
- the preview writes nothing;
- the four auth outcomes, an unknown child 404 and a malformed range
  422.

The cycle is anchored on the REAL host "today" (the create route's
regeneration reads the host clock, so the comparison test cannot pin
it): days today..today+6 are cycle week 0 (present every day), days
today+7..today+13 week 1 (absent every day), today+14 week 0 again.
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

# The DAOs and materializer through the SAME core copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy).
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_dao_presence = importlib.import_module("nestquest_core.dao_presence")
_materialize = importlib.import_module("nestquest_core.materialize")

CONSEQUENCE_URL = "/api/v1/admin/presence-overrides/consequence"
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

#: The two-week custody pattern: week 0 every weekday, week 1 none.
CUSTODY_PATTERN = {"0": [0, 1, 2, 3, 4, 5, 6], "1": []}


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _day(offset: int) -> str:
    """The ISO date ``offset`` days after the host's today."""
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


def _body(
    child_id: int, start: int, end: int, *, is_present: bool = False
) -> dict[str, object]:
    """A consequence body over ``[today+start, today+end]``."""
    return {
        "child_id": child_id,
        "start_date": _day(start),
        "end_date": _day(end),
        "is_present": is_present,
    }


async def _create_child(client: object, name: str = "Ada") -> int:
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": name},
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _create_daily_definition(
    client: object,
    child_id: int,
    title: str,
    windows: list[str],
    *,
    skip_on_away: bool = True,
) -> int:
    created = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": title,
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [child_id],
            "windows": windows,
            "skip_on_away": skip_on_away,
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _set_custody_schedule(client: object, child_id: int) -> None:
    """Anchor the two-week custody cycle on today (week 0 starts today)."""
    response = await client.put(
        f"/api/v1/admin/children/{child_id}/presence-schedule",
        json={
            "cycle_length_weeks": 2,
            "anchor_date": _day(0),
            "pattern": CUSTODY_PATTERN,
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 200


async def _materialize_horizon(database: object) -> None:
    """Materialize the household horizon so the stored state is current."""
    today = datetime.date.today()
    await _materialize.materialize(
        database, _day(0), _day(14), today=today
    )


async def _open_future_keys(database: object, child_id: int) -> set[tuple]:
    """The child's stored open (no completion event) future instance keys."""
    instances = await _dao_instances.QuestInstancesDao(
        database
    ).list_by_date_range(child_id, _day(0), _day(60))
    events = _dao_instances.CompletionEventsDao(database)
    keys = set()
    for instance in instances:
        if not await events.list_by_instance(instance.id):
            keys.add(
                (instance.definition_id, instance.due_date, instance.window)
            )
    return keys


async def _complete(
    database: object, child_id: int, definition_id: int, due_date: str,
    window: str,
) -> None:
    """Append a completion event to the stored instance."""
    instance = await _dao_instances.QuestInstancesDao(database).get(
        definition_id, child_id, due_date, window
    )
    assert instance is not None
    await _dao_instances.CompletionEventsDao(database).append(
        instance.id,
        child_id,
        "completed",
        "user",
        datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        True,
        actor_user_id="admin-user-1",
    )


async def _consequence(client: object, body: dict[str, object]) -> int:
    response = await client.post(
        CONSEQUENCE_URL, json=body, headers=_admin_headers()
    )
    assert response.status_code == 200, response.text
    return response.json()["removed"]


@pytest.fixture
async def custody(temp_db_path: str) -> SimpleNamespace:
    """A child on the two-week custody cycle with a two-window chore.

    Also assigns a ``skip_on_away = false`` daily chore (generated
    regardless of presence) and materializes the horizon, so the stored
    instances are the walk's current output.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        database = runner.app.state.db.database
        child_id = await _create_child(client)
        chore_id = await _create_daily_definition(
            client, child_id, "Brush teeth", ["morning", "evening"]
        )
        always_id = await _create_daily_definition(
            client, child_id, "Feed the fish", ["afternoon"],
            skip_on_away=False,
        )
        await _set_custody_schedule(client, child_id)
        await _materialize_horizon(database)
        yield SimpleNamespace(
            client=client,
            database=database,
            child_id=child_id,
            chore_id=chore_id,
            always_id=always_id,
        )


# --- the count ---------------------------------------------------------------


async def test_custody_override_removes_a_known_number(
    custody: SimpleNamespace,
) -> None:
    """Absent over today+2..today+8 removes days +2..+6 x two windows.

    Days +7 and +8 are already absent (cycle week 1), and the
    skip_on_away=false chore is generated regardless of presence, so
    exactly 5 present days x 2 windows = 10 instances would go.
    """
    removed = await _consequence(
        custody.client, _body(custody.child_id, 2, 8)
    )
    assert removed == 10


async def test_already_absent_range_removes_nothing(
    custody: SimpleNamespace,
) -> None:
    """An absent override over cycle week 1 changes nothing: 0."""
    assert await _consequence(
        custody.client, _body(custody.child_id, 7, 13)
    ) == 0


async def test_present_override_removes_nothing(
    custody: SimpleNamespace,
) -> None:
    """A present override only ever adds instances: 0."""
    assert await _consequence(
        custody.client, _body(custody.child_id, 2, 8, is_present=True)
    ) == 0


async def test_past_range_removes_nothing(custody: SimpleNamespace) -> None:
    """A range entirely before today touches no upcoming instance: 0."""
    assert await _consequence(
        custody.client, _body(custody.child_id, -20, -1)
    ) == 0


async def test_completed_instance_in_range_is_not_counted(
    custody: SimpleNamespace,
) -> None:
    """D-005: an instance with a completion event is never removed."""
    await _complete(
        custody.database, custody.child_id, custody.chore_id, _day(3),
        "morning",
    )
    removed = await _consequence(
        custody.client, _body(custody.child_id, 2, 8)
    )
    assert removed == 9


async def test_skip_on_away_false_definition_contributes_nothing(
    temp_db_path: str,
) -> None:
    """A child whose only chore ignores presence: absent removes 0."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        database = runner.app.state.db.database
        child_id = await _create_child(client)
        await _create_daily_definition(
            client, child_id, "Feed the fish", ["morning"],
            skip_on_away=False,
        )
        await _set_custody_schedule(client, child_id)
        await _materialize_horizon(database)
        assert await _consequence(client, _body(child_id, 0, 14)) == 0


async def test_count_matches_a_direct_materialise_comparison(
    custody: SimpleNamespace,
) -> None:
    """Saving the override removes EXACTLY the previewed instances.

    With a completed instance inside the range, the preview is taken,
    then the override is really created (its core path regenerates the
    child) and the open future instances that disappeared are counted
    from the database.  The completed instance survives the regeneration.
    """
    client, database = custody.client, custody.database
    await _complete(
        database, custody.child_id, custody.chore_id, _day(4), "evening"
    )
    body = _body(custody.child_id, 1, 9)
    removed = await _consequence(client, body)

    before = await _open_future_keys(database, custody.child_id)
    created = await client.post(
        OVERRIDES_URL, json=body, headers=_admin_headers()
    )
    assert created.status_code == 201
    after = await _open_future_keys(database, custody.child_id)

    assert after <= before
    assert len(before - after) == removed
    # Days +1..+6 present x two windows, minus the completed one.
    assert removed == 11
    completed = await _dao_instances.QuestInstancesDao(database).get(
        custody.chore_id, custody.child_id, _day(4), "evening"
    )
    assert completed is not None


async def test_preview_writes_nothing(custody: SimpleNamespace) -> None:
    """No override is stored and no instance is removed by the preview."""
    client, database = custody.client, custody.database
    before = await _open_future_keys(database, custody.child_id)
    assert await _consequence(client, _body(custody.child_id, 0, 14)) > 0
    assert await _open_future_keys(database, custody.child_id) == before
    overrides = await _dao_presence.PresenceOverridesDao(
        database
    ).list_by_child_and_range(custody.child_id, "2000-01-01", "2100-01-01")
    assert overrides == []


# --- errors ------------------------------------------------------------------


async def test_unknown_child_is_404(custody: SimpleNamespace) -> None:
    response = await custody.client.post(
        CONSEQUENCE_URL, json=_body(9999, 1, 2), headers=_admin_headers()
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "2026-02-30"},
        {"end_date": "2026-1-5"},
        {"start_date": "2026-03-10", "end_date": "2026-03-01"},
        {"is_present": "sometimes"},
        {"child_id": "one"},
    ],
)
async def test_malformed_range_or_status_is_422(
    custody: SimpleNamespace, overrides: dict[str, object]
) -> None:
    body = {**_body(custody.child_id, 1, 2), **overrides}
    response = await custody.client.post(
        CONSEQUENCE_URL, json=body, headers=_admin_headers()
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"child_id": True},
        {"child_id": False},
        {"child_id": "1"},
        {"child_id": 1.0},
        {"is_present": 1},
        {"is_present": 0},
        {"is_present": "true"},
        {"is_present": "false"},
    ],
)
async def test_coercible_child_id_or_status_is_422(
    custody: SimpleNamespace, overrides: dict[str, object]
) -> None:
    """Strict fields: a bool id or a numeric/string status is rejected.

    The fixture child's id is 1, so a coerced ``true`` would otherwise
    target it and return 200.  Nothing is stored and nothing removed.
    """
    assert custody.child_id == 1
    database = custody.database
    before = await _open_future_keys(database, custody.child_id)
    body = {**_body(custody.child_id, 0, 14), **overrides}
    response = await custody.client.post(
        CONSEQUENCE_URL, json=body, headers=_admin_headers()
    )
    assert response.status_code == 422
    assert await _open_future_keys(database, custody.child_id) == before
    overrides_stored = await _dao_presence.PresenceOverridesDao(
        database
    ).list_by_child_and_range(custody.child_id, "2000-01-01", "2100-01-01")
    assert overrides_stored == []


# --- authentication: the router's ONE require_admin --------------------------


async def test_no_credential_is_401(custody: SimpleNamespace) -> None:
    response = await custody.client.post(
        CONSEQUENCE_URL, json=_body(custody.child_id, 1, 2)
    )
    assert response.status_code == 401


async def test_panel_service_token_is_403(custody: SimpleNamespace) -> None:
    response = await custody.client.post(
        CONSEQUENCE_URL,
        json=_body(custody.child_id, 1, 2),
        headers={"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL


async def test_non_admin_jwt_is_403(custody: SimpleNamespace) -> None:
    non_admin = make_token(groups=("some-other-group",))
    response = await custody.client.post(
        CONSEQUENCE_URL,
        json=_body(custody.child_id, 1, 2),
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


async def test_admin_jwt_is_200(custody: SimpleNamespace) -> None:
    response = await custody.client.post(
        CONSEQUENCE_URL,
        json=_body(custody.child_id, 1, 2),
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {"removed": 4}
