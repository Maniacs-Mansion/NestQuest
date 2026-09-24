"""Admin-plane SSE tests: the admin transition stream (task 92f75680).

These tests exercise ``GET /api/v1/admin/events`` — the admin plane's
Server-Sent Events stream for the Admin PWA — against a REAL server:

- The stream inherits the admin router's ONE ``require_admin``
  dependency: an absent credential is 401, the panel service token and
  a non-admin JWT are 403, all before any stream is established.
- An admin JWT subscribes; each of the four documented transitions
  (quest-completed, quest-uncompleted, quest-missed, child-day-complete)
  arrives as an ``event: <type>`` / ``data: <json>`` frame carrying its
  documented payload fields (design/ENTITIES-AND-SERVICES.md §3).
- The admin and panel streams are fed by the SAME in-process publisher:
  one transition arrives, identically, on both.

Streaming approach: :mod:`tests.test_api_sse`'s live-uvicorn reader
(httpx's ASGITransport buffers SSE bodies), on the admin-enabled
:class:`tests.test_api_admin_uncomplete._AdminServer` whose JWKS cache
is stubbed, so a real admin JWT verifies with NO network access.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import routes_admin, routes_panel
from tests.admin_jwt_harness import make_token
from tests.test_api_admin_uncomplete import _AdminServer
from tests.test_api_panel import PANEL_TOKEN, _seed_household
from tests.test_api_sse import (
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_MISSED,
    EVENT_QUEST_UNCOMPLETED,
    READ_TIMEOUT,
    _stream,
)

EVENTS_PATH = "/api/v1/admin/events"


@pytest.fixture
def temp_db_path(tmp_path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def admin_live(temp_db_path: str) -> SimpleNamespace:
    """A seeded household served by a live admin-enabled uvicorn app.

    Both planes' clocks are pinned to 12:00 UTC (past Ada's 10:00 due,
    before Bo's 17:00) BEFORE the server starts — the app is created
    inside uvicorn's factory thread.
    """
    today = datetime.datetime.now().astimezone().date()
    pinned_now = datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=ZoneInfo("UTC")
    )
    seed = await _seed_household(temp_db_path, today, pinned_now)
    original_panel = routes_panel._local_now
    original_admin = routes_admin._local_now
    routes_panel._local_now = lambda: pinned_now
    routes_admin._local_now = lambda: pinned_now
    try:
        with _AdminServer(temp_db_path) as server:
            client = httpx.AsyncClient(
                base_url=server.url(""), timeout=READ_TIMEOUT
            )
            async with client:
                yield SimpleNamespace(client=client, seed=seed, server=server)
    finally:
        routes_panel._local_now = original_panel
        routes_admin._local_now = original_admin


async def _panel_complete(live: SimpleNamespace, instance_id: int, child_id: int):
    """Complete ``instance_id`` through the panel route (a real transition)."""
    response = await live.client.post(
        f"/api/v1/panel/instances/{instance_id}/complete",
        headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
        json={"actor_child_id": child_id},
    )
    assert response.status_code == 200


# --- auth: the ONE require_admin dependency, no stream on refusal ----------


async def test_admin_events_refuses_absent_panel_and_non_admin(
    admin_live: SimpleNamespace,
) -> None:
    """No credential is 401; the panel token and a non-admin JWT are 403.

    Each refusal is a complete (non-streaming) JSON error response, so
    no stream is established for any of them.
    """
    client = admin_live.client

    absent = await client.get(EVENTS_PATH)
    assert absent.status_code == 401
    assert not absent.headers["content-type"].startswith("text/event-stream")

    panel = await client.get(
        EVENTS_PATH, headers={"Authorization": f"Bearer {PANEL_TOKEN}"}
    )
    assert panel.status_code == 403
    assert panel.json()["detail"] == (
        "This credential type is not accepted for admin access"
    )

    non_admin = await client.get(
        EVENTS_PATH,
        headers={
            "Authorization": f"Bearer {make_token(groups=('other-group',))}"
        },
    )
    assert non_admin.status_code == 403
    assert non_admin.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )


async def test_admin_jwt_is_not_accepted_on_panel_events(
    admin_live: SimpleNamespace,
) -> None:
    """The panel plane is unchanged: an admin JWT does not open it."""
    response = await admin_live.client.get(
        "/api/v1/panel/events",
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    assert response.status_code == 401


async def test_admin_events_sets_no_cache(admin_live: SimpleNamespace) -> None:
    """The admin stream is ``text/event-stream`` with ``no-cache``."""
    async with admin_live.client.stream(
        "GET",
        EVENTS_PATH,
        headers={"Authorization": f"Bearer {make_token()}"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"


# --- the four documented transitions on the admin stream -------------------


async def test_admin_stream_carries_completed_and_day_complete(
    admin_live: SimpleNamespace,
) -> None:
    """A panel completion streams quest-completed then child-day-complete.

    Ada's only quest today is Pack bag, so completing it also clears her
    day; both frames arrive on the ADMIN stream with their documented
    payload fields.
    """
    seed = admin_live.seed
    pack_bag = seed.pack_bag_instance
    stream = _stream(admin_live.server.url(EVENTS_PATH), make_token())
    async with stream:
        await _panel_complete(admin_live, pack_bag.id, seed.ada.id)

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_COMPLETED == "nestquest_quest_completed"
        assert payload["child_id"] == seed.ada.id
        assert payload["child_name"] == "Ada"
        assert payload["instance_id"] == pack_bag.id
        assert payload["quest_title"] == "Pack bag"
        assert payload["window"] == "morning"
        assert payload["due_date"] == pack_bag.due_date
        assert payload["due_time"] == "10:00"
        assert payload["occurred_at"]
        assert payload["was_on_time"] is False  # 10:00 due, 12:00 now
        completed_at = payload["occurred_at"]

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_CHILD_DAY_COMPLETE
        assert event_type == "nestquest_child_day_complete"
        assert payload["child_id"] == seed.ada.id
        assert payload["child_name"] == "Ada"
        assert payload["quests_due"] == 1
        assert payload["quests_completed"] == 1
        assert payload["occurred_at"] == completed_at


async def test_admin_stream_carries_uncompleted(
    admin_live: SimpleNamespace,
) -> None:
    """The admin uncomplete route's reversal streams quest-uncompleted."""
    seed = admin_live.seed
    brush = seed.brush_teeth_instance
    admin_headers = {"Authorization": f"Bearer {make_token()}"}
    stream = _stream(admin_live.server.url(EVENTS_PATH), make_token())
    async with stream:
        response = await admin_live.client.post(
            f"/api/v1/admin/instances/{brush.id}/uncomplete",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["appended"] is True

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
    assert payload["occurred_at"]
    assert "was_on_time" not in payload


async def test_admin_stream_carries_missed(admin_live: SimpleNamespace) -> None:
    """The missed-sweep publisher's transition streams to the admin client.

    Drives the API-side helper the sweep calls, on the SERVER's loop,
    against the app's own database and its ONE publisher.
    """
    from api import transitions

    seed = admin_live.seed
    stale = seed.stale_instance
    app = admin_live.server.app
    stream = _stream(admin_live.server.url(EVENTS_PATH), make_token())
    async with stream:
        admin_live.server.run_on_loop(
            transitions.publish_quest_missed(
                app.state.db.database, stale.id, app.state.publisher
            )
        )
        event_type, payload = await stream.next_event()
    assert event_type == EVENT_QUEST_MISSED == "nestquest_quest_missed"
    assert payload["child_id"] == seed.ada.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == stale.id
    assert payload["quest_title"] == "Stale chore"
    assert payload["window"] == "morning"
    assert payload["due_date"] == stale.due_date
    assert payload["due_time"] == "09:00"
    assert payload["occurred_at"]


# --- one publisher feeds both planes ---------------------------------------


async def test_admin_and_panel_streams_share_one_publisher(
    admin_live: SimpleNamespace,
) -> None:
    """One transition arrives, identically, on the admin AND panel streams.

    The route publishes once to ``app.state.publisher``; both planes'
    subscribers receive the same frames (same ``occurred_at``), which a
    second, admin-only publisher could never produce.
    """
    seed = admin_live.seed
    pack_bag = seed.pack_bag_instance
    admin_stream = _stream(admin_live.server.url(EVENTS_PATH), make_token())
    panel_stream = _stream(admin_live.server.url("/api/v1/panel/events"))
    async with admin_stream, panel_stream:
        await _panel_complete(admin_live, pack_bag.id, seed.ada.id)

        admin_events = [
            await admin_stream.next_event(),
            await admin_stream.next_event(),
        ]
        panel_events = [
            await panel_stream.next_event(),
            await panel_stream.next_event(),
        ]
    assert [event_type for event_type, _ in admin_events] == [
        EVENT_QUEST_COMPLETED,
        EVENT_CHILD_DAY_COMPLETE,
    ]
    assert admin_events == panel_events
