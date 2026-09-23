"""Admin-plane missed-sweep trigger tests (task 058c7b69).

These tests exercise ``POST /api/v1/admin/missed-sweep`` — the admin
plane's trigger for the nightly missed-quest sweep — against a REAL
server (uvicorn on an ephemeral port, the SSE tests' documented
approach: httpx's ASGI transport buffers whole bodies, so a live
stream needs a live server), plus the API service's daily scheduler:

- The trigger requires the router's ONE ``require_admin`` check: a
  non-admin JWT is 403 and an absent credential is 401, and neither
  refusal runs the sweep.
- Seeded past-due open instances: ONE ``nestquest_quest_missed``
  transition per instance arrives on the LIVE SSE stream with the
  documented payload fields (child_id, child_name, instance_id,
  quest_title, window, due_date, due_time, occurred_at — §3), while
  the seeded TODAY-due instance publishes nothing (the sweep's rule
  is ``due_date`` strictly before ``today``).
- A same-day rerun publishes nothing (the core watermark).
- A run after downtime (``today`` advanced two days) publishes the
  accumulated window once — the instance due on day one fires on the
  catch-up run — and a further rerun is silent again.
- Publishing is the api/scheduler.py shape — the sweep-BUILT
  ``(event_type, payload)`` pairs go straight to the publisher, no
  per-event re-fetch: all events of one run share the run's ONE
  ``occurred_at`` stamp, and a deterministic concurrent-deletion case
  (the sweep is wrapped to delete one swept instance after it built
  its events and committed its watermark) still answers 200 and
  streams every built event — a re-fetch there would 500 and lose the
  missed event forever.
- The daily scheduler (:class:`api.scheduler.MissedSweepScheduler`)
  computes the delay to the configured ``day_rollover_time``, runs the
  sweep when the (injectable) clock reaches it, publishes the built
  events on its publisher, advances to the NEXT day's rollover, and
  cancels cleanly.

The household is seeded through the SAME core copy the app uses (the
``nestquest_core.*`` package registered by ``api/nestquest_core.py``;
see the two-copy caveat there) and the sweep's watermark is read back
through the same copy's :class:`~nestquest_core.dao_meta.MetaStateDao`
— on the SERVER's event loop for the uvicorn-hosted app (the database
belongs to that thread's loop, so assertions schedule there), on the
test's own loop for the scheduler test's standalone database.
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from api import routes_admin
from api.app import create_app
from api.auth import JwksCache
from api.config import ApiConfig
from api.database import _executor
from api.nestquest_core import core_db as _core_db
from api.nestquest_core import core_migrations as _core_migrations
from api.scheduler import MissedSweepScheduler
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    AUDIENCE,
    ISSUER,
    JWKS_URL,
    KID,
    StubbedFetch,
    jwks_for,
    make_token,
)
from tests.test_api_panel import PANEL_TOKEN
from tests.test_api_sse import EVENT_QUEST_MISSED, READ_TIMEOUT, _free_port, _stream

# The bundled core submodules, through the SAME copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy).
_children = importlib.import_module("nestquest_core.children")
_quest_definitions = importlib.import_module(
    "nestquest_core.quest_definitions"
)
_materialize = importlib.import_module("nestquest_core.materialize")
_recurrence = importlib.import_module("nestquest_core.recurrence")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_dao_meta = importlib.import_module("nestquest_core.dao_meta")
_settings_store = importlib.import_module("nestquest_core.settings_store")
_core_sweep = importlib.import_module("nestquest_core.sweep")

#: The well-known ``nestquest_meta_state`` key holding the sweep
#: watermark — asserted literally so the contract is pinned here.
SWEEP_WATERMARK_KEY = "missed_sweep_last_run_date"


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


async def _seed_missed_household(
    db_path: str, today: datetime.date
) -> SimpleNamespace:
    """Seed the missed-sweep household on ``db_path`` and return records.

    Two children; two quests whose ONLY instances are due YESTERDAY
    (created via ``materialize`` with ``today`` pinned to yesterday —
    the no-past guard accepts the rows, and they land past-due with no
    completion events: the sweep's targets), and one quest due TODAY
    (not past-due: the sweep must NOT announce it).  The yesterday
    rules carry ``end_date`` so the later today-walk cannot give them
    a second instance.  Opens, migrates, seeds and CLOSES its own
    connection so the app's lifespan connection never overlaps it.
    """
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(db_path)
    try:
        await _core_migrations.apply_migrations(database)
        today_iso = today.isoformat()
        yesterday = today - datetime.timedelta(days=1)
        yesterday_iso = yesterday.isoformat()

        ada = await _children.create_child(database, "Ada", sort_order=0)
        bo = await _children.create_child(database, "Bo", sort_order=1)

        yesterday_rule = _recurrence.ScheduleRule.from_dict(
            {
                "rule_type": "daily",
                "start_date": yesterday_iso,
                "end_date": yesterday_iso,
            }
        )
        await _quest_definitions.create_quest_definition(
            database,
            "Stale chore",
            yesterday_rule,
            [ada.id],
            [("morning", "09:00")],
        )
        await _quest_definitions.create_quest_definition(
            database,
            "Old chore",
            yesterday_rule,
            [bo.id],
            [("evening", "18:30")],
        )
        # Past-due open instances for the two yesterday quests (the
        # walk pins ``today`` to yesterday so the rows are accepted).
        await _materialize.materialize(
            database, yesterday_iso, yesterday_iso, today=yesterday
        )
        # Today's quest: created after the yesterday walk so it has no
        # past-due instance, then materialized for today only.
        await _quest_definitions.create_quest_definition(
            database,
            "Recoverable chore",
            _recurrence.ScheduleRule.from_dict(
                {"rule_type": "daily", "start_date": today_iso}
            ),
            [ada.id],
            [("afternoon", "17:00")],
        )
        await _materialize.materialize(
            database, today_iso, today_iso, today=today
        )

        instances = _dao_instances.QuestInstancesDao(database)
        ada_yesterday = await instances.list_by_child_and_date(
            ada.id, yesterday_iso
        )
        assert len(ada_yesterday) == 1
        stale = ada_yesterday[0]
        bo_yesterday = await instances.list_by_child_and_date(
            bo.id, yesterday_iso
        )
        assert len(bo_yesterday) == 1
        old = bo_yesterday[0]
        ada_today = await instances.list_by_child_and_date(ada.id, today_iso)
        assert len(ada_today) == 1
        recoverable = ada_today[0]
        return SimpleNamespace(
            ada=ada,
            bo=bo,
            stale_instance=stale,
            old_instance=old,
            recoverable_instance=recoverable,
            yesterday_iso=yesterday_iso,
            today_iso=today_iso,
        )
    finally:
        await database.close()


class _AdminServer:
    """Run the app with uvicorn on an ephemeral port, in a thread.

    The SSE tests' documented approach (see tests/test_api_sse.py):
    uvicorn's factory mode runs ``create_app`` INSIDE the server
    thread, so the lifespan — database, publisher, the daily sweep
    scheduler — belongs to that thread's event loop.  The app's JWKS
    cache is swapped for one built around the stubbed fetcher BEFORE
    the server starts, so admin JWTs genuinely verify with no network.
    """

    def __init__(self, db_path: str) -> None:
        self.port = _free_port()
        self._server_loop: asyncio.AbstractEventLoop | None = None
        self._server = uvicorn.Server(
            uvicorn.Config(
                self._make_app_factory(db_path),
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
            )
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def _make_app_factory(self, db_path: str):
        """The uvicorn app factory, closing over ``db_path``."""

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

    def __enter__(self) -> "_AdminServer":
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

    def run_on_loop(self, coro) -> object:
        """Run ``coro`` on the SERVER's event loop and wait for it.

        The app (and its database) lives on the uvicorn thread's loop,
        so database assertions schedule there.  Bounded by
        READ_TIMEOUT so a wedged schedule fails instead of hanging.
        """
        return asyncio.run_coroutine_threadsafe(
            coro, self._server_loop
        ).result(timeout=READ_TIMEOUT)


def _watermark(server: _AdminServer) -> str | None:
    """The stored sweep watermark, read on the server's own loop."""
    database = server.app.state.db.database
    return server.run_on_loop(
        _dao_meta.MetaStateDao(database).get(SWEEP_WATERMARK_KEY)
    )


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def missed_app(temp_db_path: str) -> SimpleNamespace:
    """The seeded household served by a live uvicorn app, clock pinned.

    ``routes_admin._local_now`` is pinned to today 12:00 (the same
    pinning discipline the panel/SSE tests use) BEFORE the server
    starts, so the trigger route's ``today`` matches the seed; the
    downtime test moves the pin forward mid-test.  Restored in
    ``finally`` even on failure.
    """
    now_local = datetime.datetime.now().astimezone()
    pinned_now = now_local.replace(hour=12, minute=0, second=0, microsecond=0)
    today = pinned_now.date()
    seed = await _seed_missed_household(temp_db_path, today)
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
                    today=today,
                    pinned_now=pinned_now,
                )
    finally:
        routes_admin._local_now = original


# --- the trigger: one missed transition per past-due open instance -----


async def test_trigger_publishes_one_missed_event_per_instance(
    missed_app,
) -> None:
    """The trigger streams one documented missed transition per instance.

    The stream is subscribed FIRST, the sweep is triggered through the
    route as an admin, and each emitted frame's type and every
    documented payload field are asserted; the TODAY-due instance must
    NOT appear (the sweep's rule is strictly past-due).
    """
    ns = missed_app
    seed = ns.seed
    stream = _stream(ns.server.url("/api/v1/panel/events"))
    async with stream:
        response = await ns.client.post(
            "/api/v1/admin/missed-sweep", headers=_admin_headers()
        )
        assert response.status_code == 200
        assert response.json() == {"fired": 2}

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_MISSED
        assert event_type == "nestquest_quest_missed"
        assert payload["child_id"] == seed.ada.id
        assert payload["child_name"] == "Ada"
        assert payload["instance_id"] == seed.stale_instance.id
        assert payload["quest_title"] == "Stale chore"
        assert payload["window"] == "morning"
        assert payload["due_date"] == seed.yesterday_iso
        assert payload["due_time"] == "09:00"
        assert payload["occurred_at"]  # strict UTC ISO-8601 stamp
        run_stamp = payload["occurred_at"]

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_MISSED
        assert payload["child_id"] == seed.bo.id
        assert payload["child_name"] == "Bo"
        assert payload["instance_id"] == seed.old_instance.id
        assert payload["quest_title"] == "Old chore"
        assert payload["window"] == "evening"
        assert payload["due_date"] == seed.yesterday_iso
        assert payload["due_time"] == "18:30"
        # One run, ONE stamp: the route publishes the sweep-built
        # payloads directly, so every event of this run carries the
        # same ``occurred_at`` the sweep computed for the whole run.
        assert payload["occurred_at"] == run_stamp

        # Exactly one transition per instance: today's not-past-due
        # quest never arrives.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)

    # The run recorded the watermark: the household-local date the
    # sweep ran for, under the well-known meta_state key.
    assert _watermark(ns.server) == seed.today_iso


async def test_trigger_publishes_sweep_built_payloads_without_refetch(
    missed_app,
) -> None:
    """Publishing never re-fetches: a concurrently deleted instance
    cannot fail the trigger or lose its already-built missed event.

    The core sweep commits the idempotency watermark BEFORE returning,
    so a publish loop that re-fetches each instance opens a loss
    window: an instance deleted inside that window (e.g. a concurrent
    regenerate) would raise ``ValueError`` uncaught — a bare 500 — and
    the missed event would be gone forever (the watermark already
    advanced, so no future sweep re-examines it).  The route publishes
    the sweep-built ``(event_type, payload)`` pairs DIRECTLY (the
    api/scheduler.py shape), which this test exercises deterministically:
    the sweep is wrapped to delete one swept instance AFTER the sweep
    built its events and committed its watermark but BEFORE the route
    publishes, and the trigger must still answer 200 with ``fired: 2``
    and stream BOTH sweep-built payloads — the deleted instance's
    included, stamped with the run's ONE shared ``occurred_at``.
    """
    ns = missed_app
    seed = ns.seed
    database = ns.server.app.state.db.database
    original_sweep = _core_sweep.run_missed_sweep

    async def sweep_then_delete_stale(sweep_database, *, today):
        events = await original_sweep(sweep_database, today=today)
        # The concurrent deletion lands after the sweep built its
        # events and committed its watermark, but before the route
        # publishes: the row is gone while the built event survives.
        await sweep_database.execute(
            "DELETE FROM quest_instances WHERE id = ?",
            (seed.stale_instance.id,),
        )
        return events

    _core_sweep.run_missed_sweep = sweep_then_delete_stale
    try:
        stream = _stream(ns.server.url("/api/v1/panel/events"))
        async with stream:
            response = await ns.client.post(
                "/api/v1/admin/missed-sweep", headers=_admin_headers()
            )
            assert response.status_code == 200
            assert response.json() == {"fired": 2}

            # The FIRST event is the deleted instance's — published
            # from the payload built before the deletion, never
            # re-fetched after it (a re-fetch would 500 here).
            event_type, payload = await stream.next_event()
            assert event_type == EVENT_QUEST_MISSED
            assert payload["instance_id"] == seed.stale_instance.id
            assert payload["child_name"] == "Ada"
            assert payload["quest_title"] == "Stale chore"
            assert payload["window"] == "morning"
            assert payload["due_date"] == seed.yesterday_iso
            assert payload["occurred_at"]
            run_stamp = payload["occurred_at"]

            event_type, payload = await stream.next_event()
            assert event_type == EVENT_QUEST_MISSED
            assert payload["instance_id"] == seed.old_instance.id
            assert payload["occurred_at"] == run_stamp

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(stream.queue.get(), timeout=0.3)
    finally:
        _core_sweep.run_missed_sweep = original_sweep

    # The watermark advanced even though one instance was deleted
    # mid-flight — nothing was lost to the publish-time failure window.
    assert _watermark(ns.server) == seed.today_iso


async def test_same_day_rerun_publishes_nothing(missed_app) -> None:
    """A second trigger the same day publishes nothing (the watermark)."""
    ns = missed_app
    headers = _admin_headers()
    first = await ns.client.post("/api/v1/admin/missed-sweep", headers=headers)
    assert first.status_code == 200
    assert first.json() == {"fired": 2}

    stream = _stream(ns.server.url("/api/v1/panel/events"))
    async with stream:
        second = await ns.client.post(
            "/api/v1/admin/missed-sweep", headers=headers
        )
        assert second.status_code == 200
        assert second.json() == {"fired": 0}
        with pytest.raises(asyncio.TimeoutError):
            # The watermark makes the rerun an empty no-op: the stream
            # stays silent.
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)


async def test_run_after_downtime_publishes_accumulated_window_once(
    missed_app,
) -> None:
    """After days of downtime the catch-up run sweeps the window once.

    The first trigger sweeps yesterday's instances (watermark := today).
    ``today`` then jumps two days: the accumulated window
    ``[watermark, today)`` holds exactly the seeded TODAY-due instance
    (no completion events), which fires once — and a same-day rerun is
    silent again.
    """
    ns = missed_app
    headers = _admin_headers()
    first = await ns.client.post("/api/v1/admin/missed-sweep", headers=headers)
    assert first.status_code == 200
    assert first.json() == {"fired": 2}

    # Advance the pinned clock two days: the app is "down" over the
    # rollovers in between.
    routes_admin._local_now = lambda: ns.pinned_now + datetime.timedelta(
        days=2
    )
    later_today = (ns.today + datetime.timedelta(days=2)).isoformat()
    stream = _stream(ns.server.url("/api/v1/panel/events"))
    async with stream:
        catchup = await ns.client.post(
            "/api/v1/admin/missed-sweep", headers=headers
        )
        assert catchup.status_code == 200
        assert catchup.json() == {"fired": 1}

        event_type, payload = await stream.next_event()
        assert event_type == EVENT_QUEST_MISSED
        assert payload["instance_id"] == ns.seed.recoverable_instance.id
        assert payload["child_id"] == ns.seed.ada.id
        assert payload["quest_title"] == "Recoverable chore"
        assert payload["window"] == "afternoon"
        assert payload["due_date"] == ns.seed.today_iso
        assert payload["due_time"] == "17:00"
        assert payload["occurred_at"]

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.queue.get(), timeout=0.3)

    # The watermark moved to the new today...
    assert _watermark(ns.server) == later_today
    # ...so a further rerun publishes nothing.
    again = await ns.client.post("/api/v1/admin/missed-sweep", headers=headers)
    assert again.status_code == 200
    assert again.json() == {"fired": 0}


# --- authentication: the router's ONE require_admin dependency ----------


async def test_trigger_refuses_non_admin_and_absent_credentials(
    missed_app,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401; none sweep."""
    ns = missed_app
    non_admin = make_token(groups=("some-other-group",))
    forbidden = await ns.client.post(
        "/api/v1/admin/missed-sweep",
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )
    absent = await ns.client.post("/api/v1/admin/missed-sweep")
    assert absent.status_code == 401

    # Neither refusal ran the sweep: the watermark is still unset, and
    # the next admin trigger fires the full seeded set.
    assert _watermark(ns.server) is None
    after = await ns.client.post(
        "/api/v1/admin/missed-sweep", headers=_admin_headers()
    )
    assert after.status_code == 200
    assert after.json() == {"fired": 2}


# --- the daily scheduler -------------------------------------------------


class _RecordingPublisher:
    """A transition-publisher stub recording every published event."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, event_type: str, payload: dict) -> None:
        self.published.append((event_type, payload))


async def test_scheduler_runs_sweep_at_rollover_and_cancels_cleanly(
    temp_db_path: str,
) -> None:
    """The scheduler sweeps at the configured rollover and stops clean.

    The injectable clock starts at 10:00 and the settings pin the
    rollover to 10:05, so the first computed delay is five minutes;
    the injectable sleep fast-forwards the clock, the sweep runs for
    the (now advanced) clock's date, and the seeded past-due open
    instance is published on the recording publisher exactly once.
    The next cycle schedules for the NEXT day's rollover (23h55m).
    ``stop`` cancels the loop task and the scheduler reports stopped.
    """
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        await _core_migrations.apply_migrations(database)
        now_local = datetime.datetime.now().astimezone()
        start = now_local.replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        ada = await _children.create_child(database, "Ada", sort_order=0)
        yesterday = (start.date() - datetime.timedelta(days=1)).isoformat()
        await _quest_definitions.create_quest_definition(
            database,
            "Stale chore",
            _recurrence.ScheduleRule.from_dict(
                {
                    "rule_type": "daily",
                    "start_date": yesterday,
                    "end_date": yesterday,
                }
            ),
            [ada.id],
            [("morning", "09:00")],
        )
        await _materialize.materialize(
            database, yesterday, yesterday, today=start.date() - datetime.timedelta(days=1)
        )
        await _settings_store.update_settings(
            database, {"day_rollover_time": "10:05"}
        )

        clock_state = {"now": start}
        delays: list[float] = []

        def clock() -> datetime.datetime:
            return clock_state["now"]

        async def sleep_stub(seconds: float) -> None:
            delays.append(seconds)
            if len(delays) == 1:
                # Fast-forward the clock across the rollover wait ONCE,
                # so the first sweep runs at the rollover instant; the
                # clock then stays frozen at that instant, so the
                # follow-up cycles sweep the same (already-watermarked)
                # date and the assertions read a stable state.
                clock_state["now"] = clock_state["now"] + datetime.timedelta(
                    seconds=seconds
                )
            await asyncio.sleep(0)

        publisher = _RecordingPublisher()
        scheduler = MissedSweepScheduler(
            database, publisher=publisher, clock=clock, sleep=sleep_stub
        )
        scheduler.start()
        try:
            deadline = time.monotonic() + READ_TIMEOUT
            while not publisher.published:
                if time.monotonic() > deadline:
                    pytest.fail("scheduler never published a missed event")
                await asyncio.sleep(0.01)
            # The second cycle's scheduling decision may lag the first
            # publication by a few awaits; wait for it the same way.
            while len(delays) < 2:
                if time.monotonic() > deadline:
                    pytest.fail("scheduler never scheduled a second cycle")
                await asyncio.sleep(0.01)

            event_type, payload = publisher.published[0]
            assert event_type == "nestquest_quest_missed"
            assert payload["child_id"] == ada.id
            assert payload["quest_title"] == "Stale chore"
            assert payload["window"] == "morning"
            assert payload["due_date"] == yesterday
            assert payload["due_time"] == "09:00"
            assert payload["occurred_at"]

            # The rollover delay was honored exactly...
            assert delays[0] == pytest.approx(300.0)
            # ...and the next cycle targets the NEXT day's rollover
            # (the just-passed instant schedules for tomorrow).
            assert delays[1] == pytest.approx(86400.0)
            # The watermark pins the run to the sweep-day's date.
            watermark = await _dao_meta.MetaStateDao(database).get(
                SWEEP_WATERMARK_KEY
            )
            assert watermark == start.date().isoformat()
        finally:
            await scheduler.stop()
        assert not scheduler.running
        # Exactly one announcement: the watermark makes every further
        # cycle an empty no-op.
        assert len(publisher.published) == 1
    finally:
        await database.close()