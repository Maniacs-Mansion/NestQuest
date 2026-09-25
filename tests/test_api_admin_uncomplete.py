"""Admin-plane uncomplete and regenerate route tests (task da0226b3).

These tests exercise the admin plane's completion-reversal and
re-materialization routes against the ASGI app with httpx, reusing the
shared local-RSA-key/stubbed-JWKS harness
(:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.  The household is
seeded with :func:`tests.test_api_panel._seed_household` through the
SAME core copy the app uses (``nestquest_core.*``; the two-copy caveat
in api/nestquest_core.py), and the route's ONE clock read
(:func:`api.routes_admin._local_now`) is pinned the same way the panel
route's is, so seeded rows and route stamps cannot straddle midnight.

Every done-condition case is proven against the DATABASE, read through
that same core copy:

- Authentication runs through the router's ONE ``require_admin``
  dependency: an admin JWT passes, a JWT without the group is 403, an
  absent credential is 401 — and nothing is written.
- ``POST /api/v1/admin/instances/{id}/uncomplete``: the completion
  events log for the instance holds the ORIGINAL ``completed`` row
  UNTOUCHED plus ONE appended ``uncompleted`` row attributed to the
  verified token's ``sub`` (actor_source ``user``), and the instance's
  DERIVED state is ``open`` again; a second uncomplete is a no-op that
  appends nothing.
- On an ACTUAL reversal the ``nestquest_quest_uncompleted`` transition
  arrives on the SSE stream exactly once (subscribed live as
  :mod:`tests.test_api_sse` does); a no-op uncomplete publishes
  nothing.
- ``POST /api/v1/admin/regenerate`` re-materializes without
  duplicating: running it twice (household, definition and child
  scopes) leaves the instance count stable, and the scoped variants
  rebuild only their own scope's rows.

Error mapping (documented in api/routes_admin.py): an unknown
instance is 404 (the core's ``instance_id:`` prefix, the same key the
panel complete route uses); unknown definition/child scope ids are 404
from the route's own existence reads; malformed input — a bad scope,
a scope/id mismatch, a zero id, a non-integer path id — is 422 before
any handler code runs.
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import routes_admin
from api.app import create_app
from api.auth import JwksCache
from api.config import ApiConfig
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    AUDIENCE,
    ISSUER,
    JWKS_URL,
    KID,
    AdminRunner,
    StubbedFetch,
    SUBJECT,
    jwks_for,
    make_token,
)
from tests.test_api_panel import PANEL_TOKEN, _seed_household
from tests.test_api_sse import _EventStream, _Server, _stream

# The completion and instance-DAO layers through the SAME core copy the
# app uses (nestquest_core.*, NOT the conftest-stubbed
# custom_components copy) — used for the tests' database assertions
# only; the routes reach them through api.nestquest_core.
_completion = importlib.import_module("nestquest_core.completion")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")

#: The documented quest-uncompleted event name (core const, §3).
EVENT_QUEST_UNCOMPLETED = importlib.import_module(
    "nestquest_core.const"
).EVENT_QUEST_UNCOMPLETED


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _pinned_noon() -> tuple[datetime.date, datetime.datetime]:
    """One host clock read pinned to 12:00 UTC that day.

    The seed's completion and the route's clock both anchor to this
    instant, so nothing can straddle midnight mid-test.
    """
    today = datetime.datetime.now().astimezone().date()
    return today, datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=ZoneInfo("UTC")
    )


async def _instance_count(database: object) -> int:
    """The whole ``quest_instances`` row count (the sanctioned probe)."""
    row = await database.fetch_one("SELECT COUNT(*) FROM quest_instances")
    return row[0]


async def _events_for_instance(
    database: object, instance_id: int
) -> list:
    """The instance's completion events, in append order."""
    dao = _dao_instances.CompletionEventsDao(database)
    return await dao.list_by_instance(instance_id)


async def _derived_state(
    database: object, instance_id: int, today: datetime.date
) -> str:
    """The instance's derived state through the app's core copy."""
    dao = _dao_instances.QuestInstancesDao(database)
    instance = await dao.get_by_id(instance_id)
    assert instance is not None
    latest = await _dao_instances.CompletionEventsDao(
        database
    ).get_latest_for_instance(instance_id)
    return _completion.derive_state(instance, latest, today)


@pytest.fixture
async def admin_api(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database.

    The same runner the auth and children tests use (stubbed JWKS, no
    network); the fixture exposes the app's ONE database connection so
    tests assert the routes' effects on the stored rows themselves.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


@pytest.fixture
async def admin_household(temp_db_path: str, monkeypatch) -> SimpleNamespace:
    """A seeded household served by the admin-plane app, clock pinned.

    ``_seed_household`` completes Bo's today instance (17:00 due, 12:00
    pinned — on time), which is the completion the uncomplete tests
    reverse.  The route's ``_local_now`` is pinned to the same instant.
    """
    today, pinned_now = _pinned_noon()
    seed = await _seed_household(temp_db_path, today, pinned_now)
    monkeypatch.setattr(routes_admin, "_local_now", lambda: pinned_now)
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            seed=seed,
            database=runner.app.state.db.database,
            today=today,
        )


class _AdminServer(_Server):
    """:mod:`tests.test_api_sse`'s live-uvicorn server, admin-enabled.

    Same ephemeral-port uvicorn thread (httpx's ASGI transport buffers
    SSE bodies, so a live server is the only way to stream), but the
    app factory swaps the JWKS cache for one built around the harness's
    stub fetcher, so a real admin JWT verifies with NO network access.
    """

    def _make_app_factory(self, db_path: str):
        """The uvicorn app factory with the stubbed JWKS cache."""

        def factory():
            app = create_app(
                ApiConfig(
                    db_path=db_path,
                    panel_token=PANEL_TOKEN,
                    oidc_issuer=ISSUER,
                    oidc_audience=AUDIENCE,
                    oidc_jwks_url=JWKS_URL,
                )
            )
            app.state.jwks_cache = JwksCache(
                JWKS_URL, fetcher=StubbedFetch(jwks_for(ADMIN_KEY, KID))
            )
            self._server_loop = asyncio.get_running_loop()
            self.app = app
            return app

        return factory


@pytest.fixture
async def admin_sse(temp_db_path: str) -> SimpleNamespace:
    """A seeded household served by a live uvicorn app, clock pinned.

    Same pinning discipline as the panel tests, applied to
    :func:`api.routes_admin._local_now` BEFORE the server starts (the
    app is created inside uvicorn's factory thread).
    """
    today, pinned_now = _pinned_noon()
    seed = await _seed_household(temp_db_path, today, pinned_now)
    original = routes_admin._local_now
    routes_admin._local_now = lambda: pinned_now
    try:
        with _AdminServer(temp_db_path) as server:
            client = httpx.AsyncClient(base_url=server.url(""))
            async with client:
                yield SimpleNamespace(
                    client=client,
                    seed=seed,
                    server=server,
                    database=server.app.state.db.database,
                    today=today,
                )
    finally:
        routes_admin._local_now = original


# --- authentication: the ONE require_admin dependency guards every route ---


async def test_uncomplete_and_regenerate_refuse_non_admin_and_absent(
    admin_household: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401: nothing written."""
    client = admin_household.client
    database = admin_household.database
    brush = admin_household.seed.brush_teeth_instance
    non_admin = make_token(groups=("some-other-group",))
    events_before = await _events_for_instance(database, brush.id)
    instances_before = await _instance_count(database)

    uncomplete_url = f"/api/v1/admin/instances/{brush.id}/uncomplete"
    forbidden = await client.post(
        uncomplete_url,
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )
    unauthenticated = await client.post(uncomplete_url)
    assert unauthenticated.status_code == 401

    regenerate_bodies = (
        {},
        {"scope": "household"},
        {"scope": "child", "child_id": 1},
    )
    for body in regenerate_bodies:
        forbidden = await client.post(
            "/api/v1/admin/regenerate",
            json=body,
            headers={"Authorization": f"Bearer {non_admin}"},
        )
        assert forbidden.status_code == 403, body
        unauthenticated = await client.post(
            "/api/v1/admin/regenerate", json=body
        )
        assert unauthenticated.status_code == 401, body

    # No handler ran: the seeded completion is still the ONLY event for
    # the instance and the instance table is untouched.
    assert (
        await _events_for_instance(database, brush.id) == events_before
    )
    assert await _instance_count(database) == instances_before


# --- uncomplete: the append-only reversal -----------------------------------


async def test_uncomplete_appends_reversal_and_derived_state_is_open(
    admin_household: SimpleNamespace,
) -> None:
    """A reversal APPENDS an uncompleted event; the instance is open again.

    The original completed row is proven byte-identical after the call
    (frozen-dataclass equality), the new row carries the verified
    token's ``sub`` as the user actor, and the DERIVED state —
    recomputed from the latest event — is ``open`` again.
    """
    client = admin_household.client
    database = admin_household.database
    brush = admin_household.seed.brush_teeth_instance
    today = admin_household.today

    before = await _events_for_instance(database, brush.id)
    assert [event.event_type for event in before] == ["completed"]
    assert await _derived_state(database, brush.id, today) == "done"

    response = await client.post(
        f"/api/v1/admin/instances/{brush.id}/uncomplete",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "instance_id": brush.id,
        "state": "open",
        "appended": True,
    }

    events = await _events_for_instance(database, brush.id)
    assert len(events) == 2
    # The original completed row is UNTOUCHED — never edited, never
    # deleted (append-only completion_events).
    assert events[0] == before[0]
    assert events[0].event_type == "completed"
    assert events[0].actor_source == "panel"
    # The reversal is the NEW row, attributed to the verified token.
    reversal = events[1]
    assert reversal.event_type == "uncompleted"
    assert reversal.instance_id == brush.id
    assert reversal.child_id == brush.child_id
    assert reversal.actor_source == "user"
    assert reversal.actor_user_id == SUBJECT
    assert reversal.actor_child_id is None
    assert reversal.was_on_time is None
    # The derived state is recomputed from the latest event: open again.
    assert await _derived_state(database, brush.id, today) == "open"


async def test_second_uncomplete_is_a_noop_that_appends_nothing(
    admin_household: SimpleNamespace,
) -> None:
    """A repeat uncomplete appends NOTHING and still succeeds."""
    client = admin_household.client
    database = admin_household.database
    brush = admin_household.seed.brush_teeth_instance
    today = admin_household.today

    first = await client.post(
        f"/api/v1/admin/instances/{brush.id}/uncomplete",
        headers=_admin_headers(),
    )
    assert first.status_code == 200
    assert first.json()["appended"] is True

    second = await client.post(
        f"/api/v1/admin/instances/{brush.id}/uncomplete",
        headers=_admin_headers(),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["appended"] is False
    assert body["state"] == "open"

    events = await _events_for_instance(database, brush.id)
    assert len(events) == 2
    assert [event.event_type for event in events] == [
        "completed",
        "uncompleted",
    ]
    assert await _derived_state(database, brush.id, today) == "open"


async def test_uncomplete_unknown_instance_is_404_and_malformed_is_422(
    admin_household: SimpleNamespace,
) -> None:
    """An unknown instance is 404; a non-integer path id is 422."""
    client = admin_household.client
    brush = admin_household.seed.brush_teeth_instance
    before = await _events_for_instance(
        admin_household.database, brush.id
    )

    unknown = await client.post(
        "/api/v1/admin/instances/999/uncomplete",
        headers=_admin_headers(),
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Quest instance not found"

    malformed = await client.post(
        "/api/v1/admin/instances/not-an-int/uncomplete",
        headers=_admin_headers(),
    )
    assert malformed.status_code == 422

    # Neither rejection wrote anything.
    assert (
        await _events_for_instance(admin_household.database, brush.id)
        == before
    )


async def test_uncomplete_already_open_past_due_reports_missed(
    admin_household: SimpleNamespace,
) -> None:
    """A no-op uncomplete still reports the honest DERIVED state.

    The seeded stale instance is open and past due: uncompleting it is
    a no-op (nothing appended) and the derived state is ``missed`` —
    open-but-past-due, never an event type.
    """
    client = admin_household.client
    database = admin_household.database
    stale = admin_household.seed.stale_instance
    today = admin_household.today
    assert await _derived_state(database, stale.id, today) == "missed"

    response = await client.post(
        f"/api/v1/admin/instances/{stale.id}/uncomplete",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["appended"] is False
    assert body["state"] == "missed"

    # The no-op appended nothing: the instance still has NO events.
    assert await _events_for_instance(database, stale.id) == []


# --- the SSE transition on an actual reversal --------------------------------


async def test_uncomplete_publishes_exactly_one_uncompleted_transition(
    admin_sse: SimpleNamespace,
) -> None:
    """An actual reversal streams ONE quest-uncompleted event; a no-op none.

    The stream is subscribed FIRST (test_api_sse's live-server reader),
    the completed instance is reversed through the admin route, and the
    documented payload fields are asserted; the no-op second call adds
    no frame.
    """
    seed = admin_sse.seed
    brush = seed.brush_teeth_instance
    stream = _stream(admin_sse.server.url("/api/v1/panel/events"))
    async with stream:
        first = await admin_sse.client.post(
            f"/api/v1/admin/instances/{brush.id}/uncomplete",
            headers=_admin_headers(),
        )
        assert first.status_code == 200
        assert first.json()["appended"] is True

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_UNCOMPLETED
        assert event_type == "nestquest_quest_uncompleted"
        assert payload["child_id"] == seed.bo.id
        assert payload["child_name"] == "Bo"
        assert payload["instance_id"] == brush.id
        assert payload["quest_title"] == "Brush teeth"
        assert payload["window"] == "morning"
        assert payload["due_date"] == brush.due_date
        assert payload["due_time"] == "17:00"
        assert payload["occurred_at"]  # strict UTC ISO-8601 stamp
        assert "was_on_time" not in payload

        # The no-op second call publishes nothing: the stream stays
        # silent past the window.
        second = await admin_sse.client.post(
            f"/api/v1/admin/instances/{brush.id}/uncomplete",
            headers=_admin_headers(),
        )
        assert second.status_code == 200
        assert second.json()["appended"] is False
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)


# --- regenerate: re-materialize without duplicating --------------------------


async def _create_child(client: object, name: str) -> int:
    """Create one child through the admin children route."""
    created = await client.post(
        "/api/v1/admin/children",
        json={"display_name": name},
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _create_daily_definition(
    client: object, assignee_ids: list[int]
) -> int:
    """Create one daily one-window definition for the given assignees."""
    created = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Tidy the den",
            "rule": {"rule_type": "daily", "start_date": "2026-03-02"},
            "assignee_child_ids": assignee_ids,
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def test_regenerate_household_never_duplicates(
    admin_household: SimpleNamespace,
) -> None:
    """Two household regenerations leave the instance count stable.

    The first call re-materializes the rolling horizon
    ``[today, today + DEFAULT_HORIZON_DAYS]``; the second walks the
    SAME tuples and upserts them in place — the row count never grows
    and the core reports the same upsert count both times.
    """
    client = admin_household.client
    database = admin_household.database

    # The seed's creates materialized the horizon BEFORE Ada's custody
    # pattern existed, so the first household walk may legitimately
    # drop her away-day rows; only the second run must be stable.
    assert await _instance_count(database) > 0

    first = await client.post(
        "/api/v1/admin/regenerate", json={}, headers=_admin_headers()
    )
    assert first.status_code == 200
    body = first.json()
    assert body["scope"] == "household"
    assert body["definition_id"] is None
    assert body["child_id"] is None
    assert body["count"] > 0
    after_first = await _instance_count(database)

    second = await client.post(
        "/api/v1/admin/regenerate", json={}, headers=_admin_headers()
    )
    assert second.status_code == 200
    assert second.json()["count"] == body["count"]
    # The idempotent walk: the second run's row count is EXACTLY the
    # first's — no duplicated instances.
    assert await _instance_count(database) == after_first


async def test_regenerate_definition_scope_rematerializes(
    admin_api: SimpleNamespace,
) -> None:
    """The definition scope rebuilds that definition's horizon, twice, stably.

    Creating a definition through the admin route already materializes
    its horizon (the core's create path regenerates); the scoped
    regenerate call rebuilds the same rows, and re-running it leaves
    the row count exactly where the create left it.
    """
    client = admin_api.client
    database = admin_api.database
    ada = await _create_child(client, "Ada")
    definition_id = await _create_daily_definition(client, [ada])

    created_count = await _instance_count(database)
    assert created_count > 0

    first = await client.post(
        "/api/v1/admin/regenerate",
        json={"scope": "definition", "definition_id": definition_id},
        headers=_admin_headers(),
    )
    assert first.status_code == 200
    body = first.json()
    assert body["scope"] == "definition"
    assert body["definition_id"] == definition_id
    assert body["child_id"] is None
    assert body["count"] > 0
    after_first = await _instance_count(database)
    assert after_first == body["count"] == created_count

    second = await client.post(
        "/api/v1/admin/regenerate",
        json={"scope": "definition", "definition_id": definition_id},
        headers=_admin_headers(),
    )
    assert second.status_code == 200
    assert second.json()["count"] == body["count"]
    assert await _instance_count(database) == after_first


async def test_regenerate_child_scope_touches_only_that_child(
    admin_api: SimpleNamespace,
) -> None:
    """The child scope rebuilds that child's rows and no others'.

    Two children share one daily definition; the household walk
    materializes both.  A child-scoped regenerate for Ada re-runs her
    side of the walk (same count) while Bo's rows keep their identity,
    and re-running it never grows the table.
    """
    client = admin_api.client
    database = admin_api.database
    instances = _dao_instances.QuestInstancesDao(database)
    ada = await _create_child(client, "Ada")
    bo = await _create_child(client, "Bo")
    # One daily definition assigned to BOTH children: the household walk
    # gives each child its own rows.
    await _create_daily_definition(client, [ada, bo])

    # Materialize the household first so BOTH children have rows.
    seeded = await client.post(
        "/api/v1/admin/regenerate", json={}, headers=_admin_headers()
    )
    assert seeded.status_code == 200
    assert seeded.json()["scope"] == "household"

    ada_rows = await instances.list_by_date_range(
        ada, "2026-03-02", "2100-01-01"
    )
    bo_rows = await instances.list_by_date_range(
        bo, "2026-03-02", "2100-01-01"
    )
    assert ada_rows and bo_rows
    total = await _instance_count(database)
    assert total == len(ada_rows) + len(bo_rows)

    for expected_count in (len(ada_rows), len(ada_rows)):
        response = await client.post(
            "/api/v1/admin/regenerate",
            json={"scope": "child", "child_id": ada},
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "scope": "child",
            "definition_id": None,
            "child_id": ada,
            "count": expected_count,
        }
        # Ada's side re-materialized the same number of rows and Bo's
        # rows kept their identity; the table never grew.
        assert await instances.list_by_date_range(
            ada, "2026-03-02", "2100-01-01"
        )
        assert await instances.list_by_date_range(
            bo, "2026-03-02", "2100-01-01"
        ) == bo_rows
        assert await _instance_count(database) == total


async def test_regenerate_unknown_scope_ids_are_404(
    admin_api: SimpleNamespace,
) -> None:
    """An unknown definition or child scope id is 404, nothing written."""
    client = admin_api.client

    unknown_definition = await client.post(
        "/api/v1/admin/regenerate",
        json={"scope": "definition", "definition_id": 999},
        headers=_admin_headers(),
    )
    assert unknown_definition.status_code == 404
    assert unknown_definition.json()["detail"] == "Quest definition not found"

    unknown_child = await client.post(
        "/api/v1/admin/regenerate",
        json={"scope": "child", "child_id": 999},
        headers=_admin_headers(),
    )
    assert unknown_child.status_code == 404
    assert unknown_child.json()["detail"] == "Child not found"

    assert await _instance_count(admin_api.database) == 0


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "galaxy"},  # unknown scope
        {"scope": "definition"},  # scope without its id
        {"scope": "child"},  # scope without its id
        {"scope": "household", "child_id": 1},  # id without its scope
        {"scope": "household", "definition_id": 1},  # id without its scope
        {
            "scope": "definition",
            "definition_id": 1,
            "child_id": 2,
        },  # scope mismatch
        {"scope": "child", "child_id": 0},  # zero id
        {"scope": "child", "child_id": "seven"},  # wrong type
    ],
)
async def test_regenerate_malformed_bodies_are_422(
    admin_api: SimpleNamespace, body: dict[str, object]
) -> None:
    """Malformed scope/id combinations are 422 before any core call."""
    response = await admin_api.client.post(
        "/api/v1/admin/regenerate", json=body, headers=_admin_headers()
    )
    assert response.status_code == 422, body
    assert await _instance_count(admin_api.database) == 0