"""SSE endpoint tests: the panel event stream (task 4d7bae00).

These tests exercise ``GET /api/v1/panel/events`` — the panel plane's
Server-Sent Events stream — against a REAL server:

- The stream requires the panel service token (D-012): no/wrong token
  returns 401 (the router-level shared dependency, no second check).
- The response is ``text/event-stream`` and each transition arrives as
  an ``event: <type>`` / ``data: <json>`` frame.
- Completing an instance through the panel complete route publishes
  the ``nestquest_quest_completed`` transition carrying the documented
  payload fields (design/ENTITIES-AND-SERVICES.md §3).
- A no-op re-complete publishes nothing (no second completed event).

Streaming approach (documented): httpx's ASGITransport BUFFERS the
whole response body before returning, so an endless SSE stream hangs
it — exactly the awkward case this task anticipated.  These tests
therefore run the app with uvicorn on an ephemeral port (port 0, so
the OS picks a free one) in a daemon thread, and httpx streams from
``http://127.0.0.1:<port>``.  Every read is bounded by a timeout so a
wedged stream fails an assertion instead of hanging the suite; the
server is shut down in the fixture's finally block.
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
import uvicorn

from api import routes_panel
from api.app import create_app
from api.config import ApiConfig
from tests.test_api_panel import PANEL_TOKEN, _seed_household

#: The documented quest-completed event name (core const, §3).
_core_const = importlib.import_module("nestquest_core.const")
EVENT_QUEST_COMPLETED = _core_const.EVENT_QUEST_COMPLETED
EVENT_QUEST_UNCOMPLETED = _core_const.EVENT_QUEST_UNCOMPLETED
EVENT_QUEST_MISSED = _core_const.EVENT_QUEST_MISSED
EVENT_CHILD_DAY_COMPLETE = _core_const.EVENT_CHILD_DAY_COMPLETE

#: Upper bound for any single stream read; bounds the whole test so a
#: wedged stream fails the assertion instead of hanging the suite.
READ_TIMEOUT = 5.0


def _free_port() -> int:
    """Ask the OS for one free TCP port (bound then released)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Server:
    """Run the app with uvicorn on an ephemeral port, in a thread.

    ``create_app`` runs INSIDE the server thread (uvicorn's factory
    mode), so the lifespan — including ``app.state.publisher`` — is
    set up per test on the server's own event loop.  Daemon thread +
    explicit ``should_exit`` shutdown in the fixture's finally block.
    """

    def __init__(self, db_path: str) -> None:
        self.port = _free_port()
        self._server_loop: asyncio.AbstractEventLoop | None = None
        self._server = uvicorn.Server(
            uvicorn.Config(
                # A closure factory that captures the app's event loop
                # as it is created INSIDE the server thread: the
                # lifespan's database and publisher belong to that
                # thread's loop, so tests driving an API-side
                # transition helper directly schedule it there.
                self._make_app_factory(db_path),
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
            )
        )
        self._thread = threading.Thread(
            target=self._server.run, daemon=True
        )

    def _make_app_factory(self, db_path: str):
        """The uvicorn app factory, closing over ``db_path``.

        Records the running loop the first time uvicorn calls it (in
        the server thread) so :meth:`run_on_loop` can target it.
        """

        def factory():
            app = create_app(
                ApiConfig(db_path=db_path, panel_token=PANEL_TOKEN)
            )
            self._server_loop = asyncio.get_running_loop()
            self.app = app
            return app

        return factory

    def __enter__(self) -> "_Server":
        self._thread.start()
        deadline = time.monotonic() + READ_TIMEOUT
        while not self._server.started:
            if time.monotonic() > deadline or not self._thread.is_alive():
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.01)
        return self

    def __exit__(self, *exc) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=READ_TIMEOUT)

    def url(self, path: str) -> str:
        """The full URL for ``path`` on this server."""
        return f"http://127.0.0.1:{self.port}{path}"

    def run_on_loop(self, coro) -> None:
        """Run ``coro`` on the SERVER's event loop and wait for it.

        The app (its database and publisher) lives on the uvicorn
        thread's loop, so a test that drives an API-side transition
        helper directly must schedule it there: the helper awaits core
        DAO calls and calls ``publisher.publish`` synchronously, and
        both must run on the loop that owns them.  Bounded by
        READ_TIMEOUT so a wedged schedule fails instead of hanging.
        """
        return asyncio.run_coroutine_threadsafe(
            coro, self._server_loop
        ).result(timeout=READ_TIMEOUT)


class _EventStream:
    """A subscribed SSE reader over a live httpx connection.

    Parses frames (``event:``/``data:`` pairs) into
    ``(event_type, payload)`` tuples; ``next_event`` awaits the next
    parsed frame with a timeout.
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._stream_cm = None
        self._response: httpx.Response | None = None

    async def __aenter__(self) -> "_EventStream":
        self._client = httpx.AsyncClient(timeout=READ_TIMEOUT)
        self._stream_cm = self._client.stream(
            "GET",
            self.url,
            headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
        )
        self._response = await self._stream_cm.__aenter__()
        assert self._response.status_code == 200
        assert self._response.headers["content-type"].startswith(
            "text/event-stream"
        )
        self._task = asyncio.create_task(self._pump())
        return self

    def _set_url(self, url: str) -> "_EventStream":
        """Record the stream URL (called before ``__aenter__``)."""
        self.url = url
        return self

    async def _pump(self) -> None:
        """Read the stream and push parsed frames onto the queue."""
        event_type: str | None = None
        data_lines: list[str] = []
        try:
            async for chunk in self._response.aiter_text():
                for line in chunk.splitlines():
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())
                    elif not line and event_type is not None:
                        payload = json.loads("\n".join(data_lines))
                        await self.queue.put((event_type, payload))
                        event_type = None
                        data_lines = []
        except Exception as error:  # pragma: no cover - teardown path
            await self.queue.put(error)

    async def next_event(self) -> tuple[str, dict]:
        """The next parsed ``(event_type, payload)``, with a timeout."""
        item = await asyncio.wait_for(
            self.queue.get(), timeout=READ_TIMEOUT
        )
        if isinstance(item, Exception):
            raise item
        return item

    async def __aexit__(self, *exc) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._stream_cm.__aexit__(*exc)
        await self._client.__aexit__(*exc)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def seeded_panel(temp_db_path: str) -> SimpleNamespace:
    """A seeded household served by a live uvicorn app, clock pinned.

    Same pinning discipline as the panel tests (12:00 UTC, past Ada's
    10:00 due, before Bo's 17:00): the route's ``_local_now`` is
    patched so the completion's ``was_on_time`` is deterministic.  The
    app is created inside uvicorn's factory, so the patch must happen
    BEFORE the server starts.
    """
    today = datetime.datetime.now().astimezone().date()
    pinned_now = datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=ZoneInfo("UTC")
    )
    seed = await _seed_household(temp_db_path, today, pinned_now)
    # The app is created inside uvicorn's factory (in the server
    # thread), so the patch must be applied BEFORE the server starts.
    original = routes_panel._local_now
    routes_panel._local_now = lambda: pinned_now
    try:
        with _Server(temp_db_path) as server:
            client = httpx.AsyncClient(base_url=server.url(""))
            async with client:
                yield SimpleNamespace(
                    client=client,
                    seed=seed,
                    server=server,
                    url=server.url,
                )
    finally:
        routes_panel._local_now = original


def _stream(url: str) -> _EventStream:
    """A subscribed SSE reader for ``url``."""
    return _EventStream()._set_url(url)


# --- auth and content type ----------------------------------------------


async def test_events_requires_panel_token(seeded_panel) -> None:
    """The SSE route inherits the router's token check (no second one)."""
    response = await seeded_panel.client.get("/api/v1/panel/events")
    assert response.status_code == 401


# --- the quest-completed transition --------------------------------------


async def test_complete_publishes_quest_completed_event(
    seeded_panel,
) -> None:
    """A panel completion emits the documented completed transition.

    The stream is subscribed FIRST, the instance is completed through
    the panel route, and the emitted frame's type and every documented
    payload field (child_id, child_name, instance_id, quest_title,
    window, due_date, due_time, occurred_at, was_on_time) are asserted.
    """
    seed = seeded_panel.seed
    pack_bag = seed.pack_bag_instance
    stream = _stream(seeded_panel.url("/api/v1/panel/events"))
    async with stream:
        response = await seeded_panel.client.post(
            f"/api/v1/panel/instances/{pack_bag.id}/complete",
            headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
            json={"actor_child_id": seed.ada.id},
        )
        assert response.status_code == 200

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_COMPLETED
        assert event_type == "nestquest_quest_completed"
        assert payload["child_id"] == seed.ada.id
        assert payload["child_name"] == "Ada"
        assert payload["instance_id"] == pack_bag.id
        assert payload["quest_title"] == "Pack bag"
        assert payload["window"] == "morning"
        assert payload["due_date"] == pack_bag.due_date
        assert payload["due_time"] == "10:00"
        assert payload["occurred_at"]  # strict UTC ISO-8601 stamp
        assert payload["was_on_time"] is False  # 10:00 due, 12:00 now


async def test_no_op_recomplete_publishes_nothing(seeded_panel) -> None:
    """A second complete call emits NO second completed event.

    After the first (real) transition, a re-complete is a no-op in the
    core layer; the stream must stay silent.
    """
    seed = seeded_panel.seed
    url = f"/api/v1/panel/instances/{seed.pack_bag_instance.id}/complete"
    body = {"actor_child_id": seed.ada.id}
    headers = {"Authorization": f"Bearer {PANEL_TOKEN}"}
    stream = _stream(seeded_panel.url("/api/v1/panel/events"))
    async with stream:
        first = await seeded_panel.client.post(url, headers=headers, json=body)
        assert first.status_code == 200
        event_type, _ = await stream.next_event()
        assert event_type == EVENT_QUEST_COMPLETED
        # Ada's only quest today: the completion also clears her whole
        # day, so the day-complete event follows (task 44c93cfd).
        event_type, _ = await stream.next_event()
        assert event_type == EVENT_CHILD_DAY_COMPLETE

        second = await seeded_panel.client.post(
            url, headers=headers, json=body
        )
        assert second.status_code == 200
        with pytest.raises(asyncio.TimeoutError):
            # Nothing arrives within the window: the no-op re-complete
            # must publish nothing.
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)


# --- the remaining documented transitions (task 44c93cfd) -----------------


async def test_publish_quest_uncompleted_streams_event(seeded_panel) -> None:
    """The reusable uncompleted publisher streams the documented
    uncompleted transition with its documented payload fields.

    The admin uncomplete route does not exist yet (deferred to task
    da0226b3); the test drives the API-side helper the route will call.
    The helper runs on the SERVER's event loop (``run_coroutine_threadsafe``
    on the uvicorn thread's loop) against the app's own live database,
    exactly the way the later route handler will call it.
    """
    from api import transitions

    seed = seeded_panel.seed
    pack_bag = seed.pack_bag_instance
    app = seeded_panel.server.app
    database = app.state.db.database
    stream = _stream(seeded_panel.url("/api/v1/panel/events"))
    async with stream:
        seeded_panel.server.run_on_loop(
            transitions.publish_quest_uncompleted(
                database, pack_bag.id, app.state.publisher
            )
        )
        event_type, payload = await stream.next_event()
    assert event_type == EVENT_QUEST_UNCOMPLETED
    assert event_type == "nestquest_quest_uncompleted"
    assert payload["child_id"] == seed.ada.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == pack_bag.id
    assert payload["quest_title"] == "Pack bag"
    assert payload["window"] == "morning"
    assert payload["due_date"] == pack_bag.due_date
    assert payload["due_time"] == "10:00"
    assert payload["occurred_at"]
    assert "was_on_time" not in payload


async def test_last_quest_of_day_publishes_day_complete(seeded_panel) -> None:
    """Completing the child's LAST open quest of the day emits the
    completed event AND the child-day-complete event carrying
    ``quests_due`` and ``quests_completed``.

    Ada has exactly one instance today (Pack bag), so completing it
    clears her whole day; a no-op re-complete afterwards publishes
    nothing.
    """
    seed = seeded_panel.seed
    pack_bag = seed.pack_bag_instance
    stream = _stream(seeded_panel.url("/api/v1/panel/events"))
    async with stream:
        response = await seeded_panel.client.post(
            f"/api/v1/panel/instances/{pack_bag.id}/complete",
            headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
            json={"actor_child_id": seed.ada.id},
        )
        assert response.status_code == 200

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_COMPLETED
        completed_occurred_at = payload["occurred_at"]
        event_type, payload = await stream.next_event()
        assert event_type == EVENT_CHILD_DAY_COMPLETE
        assert event_type == "nestquest_child_day_complete"
        assert payload["child_id"] == seed.ada.id
        assert payload["child_name"] == "Ada"
        assert payload["quests_due"] == 1
        assert payload["quests_completed"] == 1
        # One transition, one shared timestamp (the core builder
        # reuses the completed event's stamp).
        assert payload["occurred_at"] == completed_occurred_at

        # No-op re-complete: nothing further on the stream.
        second = await seeded_panel.client.post(
            f"/api/v1/panel/instances/{pack_bag.id}/complete",
            headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
            json={"actor_child_id": seed.ada.id},
        )
        assert second.status_code == 200
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)


async def test_publish_quest_missed_streams_event(seeded_panel) -> None:
    """The reusable missed publisher streams the documented missed
    transition with its documented payload fields (the sweep payload).

    The API-side missed sweep does not exist yet at this queue
    position; the test drives the API-side helper the sweep will call
    against the seeded past-due open instance, on the server's own
    event loop and database.
    """
    from api import transitions

    seed = seeded_panel.seed
    stale = seed.stale_instance
    app = seeded_panel.server.app
    database = app.state.db.database
    stream = _stream(seeded_panel.url("/api/v1/panel/events"))
    async with stream:
        seeded_panel.server.run_on_loop(
            transitions.publish_quest_missed(
                database, stale.id, app.state.publisher
            )
        )
        event_type, payload = await stream.next_event()
    assert event_type == EVENT_QUEST_MISSED
    assert event_type == "nestquest_quest_missed"
    assert payload["child_id"] == seed.ada.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == stale.id
    assert payload["quest_title"] == "Stale chore"
    assert payload["window"] == "morning"
    assert payload["due_date"] == stale.due_date
    assert payload["due_time"] == "09:00"
    assert payload["occurred_at"]
