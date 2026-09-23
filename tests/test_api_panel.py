"""Panel-plane route tests: service token + snapshot (task ae7e90ae).

These tests exercise the NestQuest API's panel plane against the ASGI
app with httpx:

- ``GET /api/v1/panel/snapshot`` requires the panel service token
  (D-012): a request with NO ``Authorization`` header, a MALFORMED
  header, and a WRONG token all return 401; the correct Bearer token
  returns 200.
- The 200 body is the documented snapshot shape: ``today_iso``,
  ``cycle_day``, and ``children`` in the household's sort order, each
  carrying ``child_id``/``child_name``/``present``/``next_present``,
  the per-day rollup counts, and its instances in the documented panel
  payload shape (ENTITIES-AND-SERVICES.md §1) with missed instances
  OMITTED (D-009).
- ``ApiConfig.from_env`` requires ``NESTQUEST_PANEL_TOKEN`` with the
  same fail-fast discipline as ``NESTQUEST_DB_PATH``.

The household is seeded through the SAME core copy the app uses — the
``nestquest_core.*`` package registered by ``api/nestquest_core.py`` —
NOT the conftest-stubbed ``custom_components.nestquest.core`` copy (see
the two-copy caveat in api/nestquest_core.py's docstring: never compare
class or exception identity across the two copies).  The seed opens and
migrates its own connection on the app's SQLite path and closes BEFORE
the app's lifespan opens the file, so the two connections never
overlap.

The route's single clock read (:func:`api.routes_panel._local_now`) is
pinned with monkeypatch the same way the coordinator's ``_local_now``
is pinned in test_core_snapshot.py, so the seeded rows and the
snapshot's ``today`` can never straddle midnight.
"""
from __future__ import annotations

import datetime
import importlib
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import routes_panel
from api.app import create_app
from api.config import ApiConfig, ConfigError
from api.database import _executor
from api.nestquest_core import (
    core_db,
    core_migrations,
    core_snapshot,
)

#: The panel service token the test apps are configured with.
PANEL_TOKEN = "panel-service-token-test"

# The bundled core submodules, through the SAME copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy).
_children = importlib.import_module("nestquest_core.children")
_quest_definitions = importlib.import_module(
    "nestquest_core.quest_definitions"
)
_materialize = importlib.import_module("nestquest_core.materialize")
_recurrence = importlib.import_module("nestquest_core.recurrence")
_dao_presence = importlib.import_module("nestquest_core.dao_presence")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_completion = importlib.import_module("nestquest_core.completion")


async def _seed_household(
    db_path: str,
    today: datetime.date,
    pinned_now: datetime.datetime,
) -> SimpleNamespace:
    """Seed a two-child household on ``db_path`` and return its records.

    Mirrors the test_core_snapshot.py household: an AWAY child (2-week
    custody cycle anchored yesterday, empty week 0, an override returns
    her today+2) with an open quest due 10:00 — overdue at the pinned
    12:00 — and a present child whose 17:00 quest is completed at
    12:00 (on time).  A third quest's instance is materialized due
    YESTERDAY (via ``materialize`` with ``today`` pinned to yesterday,
    since the no-past guard refuses past-dated writes): a past-due OPEN
    instance, i.e. the "missed" view the panel payload must omit.

    Opens, migrates, seeds, and CLOSES its own connection so the app's
    lifespan connection never overlaps it.
    """
    database = core_db.NestQuestDatabase(_executor)
    await database.open(db_path)
    try:
        await core_migrations.apply_migrations(database)
        today_iso = today.isoformat()
        yesterday = today - datetime.timedelta(days=1)
        yesterday_iso = yesterday.isoformat()

        ada = await _children.create_child(database, "Ada", sort_order=0)
        bo = await _children.create_child(database, "Bo", sort_order=1)

        # Every rule starts YESTERDAY so the yesterday materialization
        # below (which pins ``today`` to yesterday) fires them.
        await _quest_definitions.create_quest_definition(
            database,
            "Pack bag",
            _recurrence.ScheduleRule.from_dict(
                {"rule_type": "daily", "start_date": yesterday_iso}
            ),
            [ada.id],
            [("morning", "10:00")],
        )
        await _quest_definitions.create_quest_definition(
            database,
            "Brush teeth",
            _recurrence.ScheduleRule.from_dict(
                {"rule_type": "daily", "start_date": yesterday_iso}
            ),
            [bo.id],
            [("morning", "17:00")],
        )
        # Today's instances first, while Ada has no presence schedule
        # (she is present every day, so her instance IS generated).
        await _materialize.materialize(
            database,
            today_iso,
            (today + datetime.timedelta(days=3)).isoformat(),
            today=today,
        )
        # The stale quest is created AFTER the today walk, so its only
        # instance is the yesterday one written below.
        await _quest_definitions.create_quest_definition(
            database,
            "Stale chore",
            _recurrence.ScheduleRule.from_dict(
                {"rule_type": "daily", "start_date": yesterday_iso}
            ),
            [ada.id],
            [("morning", "09:00")],
        )
        # Materialize yesterday with ``today`` pinned to yesterday: the
        # no-past guard accepts the rows, and they land past-due (no
        # completion events) — the missed view.
        await _materialize.materialize(
            database, yesterday_iso, yesterday_iso, today=yesterday
        )
        instances = _dao_instances.QuestInstancesDao(database)

        ada_today = await instances.list_by_child_and_date(ada.id, today_iso)
        assert len(ada_today) == 1
        pack_bag_instance = ada_today[0]
        bo_today = await instances.list_by_child_and_date(bo.id, today_iso)
        assert len(bo_today) == 1
        brush_teeth_instance = bo_today[0]
        ada_yesterday = await instances.list_by_child_and_date(
            ada.id, yesterday_iso
        )
        stale_instance = next(
            record
            for record in ada_yesterday
            if record.due_time == "09:00"
        )

        # Ada's custody schedule, added AFTER materialization (the
        # same order test_core_snapshot.py seeds): 2-week cycle
        # anchored yesterday, empty week 0 covers today => absent
        # today; an override returns her on today+2.
        await _dao_presence.PresenceSchedulesDao(database).upsert_by_child(
            ada.id,
            cycle_length_weeks=2,
            anchor_date=yesterday_iso,
            pattern="|0,1,2,3,4,5,6",
        )
        returns_date = today + datetime.timedelta(days=2)
        await _dao_presence.PresenceOverridesDao(database).create(
            ada.id,
            returns_date.isoformat(),
            returns_date.isoformat(),
            is_present=True,
            note="visit",
        )

        # Complete Bo's today instance at the pinned 12:00 (17:00 due
        # => on time).
        await _completion.complete_instance(
            database,
            brush_teeth_instance.id,
            actor_source="panel",
            actor_child_id=bo.id,
            now=pinned_now,
            today=today,
        )
        return SimpleNamespace(
            ada=ada,
            bo=bo,
            pack_bag_instance=pack_bag_instance,
            brush_teeth_instance=brush_teeth_instance,
            stale_instance=stale_instance,
            returns_date=returns_date,
        )
    finally:
        await database.close()


class _PanelRunner:
    """Run the app's lifespan around an httpx AsyncClient.

    Same pattern as test_api_health.py's ``_AppRunner``: httpx's ASGI
    transport does not run the lifespan, so it is driven explicitly and
    shut down in ``__aexit__``'s finally block even on failure.
    """

    def __init__(
        self, db_path: str, panel_token: str = PANEL_TOKEN
    ) -> None:
        self.app = create_app(
            ApiConfig(db_path=db_path, panel_token=panel_token)
        )

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc) -> None:
        try:
            await self._client.__aexit__(*exc)
        finally:
            await self._lifespan.__aexit__(*exc)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def panel_client(temp_db_path: str) -> httpx.AsyncClient:
    """An app client with an empty (migrated) household database."""
    async with _PanelRunner(temp_db_path) as client:
        yield client


@pytest.fixture
async def seeded_panel(temp_db_path: str, monkeypatch) -> SimpleNamespace:
    """A seeded household served by the app, with the clock pinned.

    One host clock read anchors ``today``; the pinned instant is
    12:00 UTC that day (past Ada's 10:00 due, before Bo's 17:00).  The
    route's ``_local_now`` is patched to return the pinned instant.
    """
    today = datetime.datetime.now().astimezone().date()
    time_zone = ZoneInfo("UTC")
    pinned_now = datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=time_zone
    )
    seed = await _seed_household(temp_db_path, today, pinned_now)
    monkeypatch.setattr(routes_panel, "_local_now", lambda: pinned_now)
    async with _PanelRunner(temp_db_path) as client:
        yield SimpleNamespace(
            client=client,
            seed=seed,
            today=today,
            pinned_now=pinned_now,
            pinned_utc_iso=pinned_now.astimezone(
                datetime.timezone.utc
            ).isoformat(),
        )


# --- ApiConfig.from_env: the panel token --------------------------------


def test_from_env_reads_panel_token() -> None:
    """A set, non-empty NESTQUEST_PANEL_TOKEN is returned verbatim."""
    cfg = ApiConfig.from_env(
        {
            "NESTQUEST_DB_PATH": "/data/nq.db",
            "NESTQUEST_PANEL_TOKEN": "panel-token",
        }
    )
    assert cfg.panel_token == "panel-token"


def test_from_env_requires_panel_token_when_missing() -> None:
    """A missing panel token raises ConfigError (no silent default)."""
    with pytest.raises(ConfigError):
        ApiConfig.from_env({"NESTQUEST_DB_PATH": "/data/nq.db"})


def test_from_env_requires_panel_token_when_empty() -> None:
    """An empty/whitespace panel token raises ConfigError."""
    with pytest.raises(ConfigError):
        ApiConfig.from_env(
            {
                "NESTQUEST_DB_PATH": "/data/nq.db",
                "NESTQUEST_PANEL_TOKEN": "   ",
            }
        )


# --- service-token auth --------------------------------------------------


async def test_missing_token_is_unauthorized(
    panel_client: httpx.AsyncClient,
) -> None:
    """A request with no Authorization header returns 401."""
    response = await panel_client.get("/api/v1/panel/snapshot")
    assert response.status_code == 401
    assert "www-authenticate" in {
        key.lower() for key in response.headers
    }


async def test_wrong_token_is_unauthorized(
    panel_client: httpx.AsyncClient,
) -> None:
    """A wrong Bearer token returns 401."""
    response = await panel_client.get(
        "/api/v1/panel/snapshot",
        headers={"Authorization": "Bearer not-the-panel-token"},
    )
    assert response.status_code == 401


async def test_malformed_authorization_header_is_unauthorized(
    panel_client: httpx.AsyncClient,
) -> None:
    """A malformed Authorization header returns 401.

    Wrong scheme, empty credential, and an empty header all fail the
    same way — the response never reveals which part failed.
    """
    for header in (
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer   ",
        "Token not-the-panel-token",
        "",
    ):
        response = await panel_client.get(
            "/api/v1/panel/snapshot",
            headers={"Authorization": header},
        )
        assert response.status_code == 401, f"header {header!r} passed"


# --- snapshot payload ----------------------------------------------------


async def test_valid_token_returns_full_snapshot(
    seeded_panel: SimpleNamespace,
) -> None:
    """The correct token returns 200 with the documented snapshot shape.

    Children in sort order (Ada sort_order 0, Bo 1); per-child counts,
    presence, next_present, and cycle day all asserted as explicit
    literals; each child's instances are in the documented panel
    payload shape (done -> completed spelling, on_time passthrough).
    """
    seed = seeded_panel.seed
    response = await seeded_panel.client.get(
        "/api/v1/panel/snapshot",
        headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["today_iso"] == seeded_panel.today.isoformat()
    # Ada's 2-week cycle anchored yesterday => today is cycle day 2.
    assert body["cycle_day"] == 2

    children = body["children"]
    assert [child["child_id"] for child in children] == [
        seed.ada.id,
        seed.bo.id,
    ], "children appear in sort_order"

    ada, bo = children

    # Ada: away today, returns on the override date; her 10:00 quest
    # is open and overdue at the pinned 12:00.
    assert ada["child_name"] == "Ada"
    assert ada["present"] is False
    assert ada["next_present"] == seed.returns_date.isoformat()
    assert ada["due_today"] == 1
    assert ada["completed_today"] == 0
    assert ada["remaining_today"] == 1
    assert ada["completion_pct"] == 0
    assert ada["instances"] == [
        {
            "id": seed.pack_bag_instance.id,
            "definition_id": seed.pack_bag_instance.definition_id,
            "child_id": seed.ada.id,
            "title": "Pack bag",
            "icon": None,
            "window": "morning",
            "due_time": "10:00",
            "state": "open",
            "overdue": True,
            "completed_at": None,
            "on_time": None,
        }
    ]

    # Bo: present, completed his 17:00 quest at the pinned 12:00
    # (on time), so the panel spelling is "completed".
    assert bo["child_name"] == "Bo"
    assert bo["present"] is True
    assert bo["next_present"] is None
    assert bo["due_today"] == 1
    assert bo["completed_today"] == 1
    assert bo["remaining_today"] == 0
    assert bo["completion_pct"] == 100
    assert bo["instances"] == [
        {
            "id": seed.brush_teeth_instance.id,
            "definition_id": seed.brush_teeth_instance.definition_id,
            "child_id": seed.bo.id,
            "title": "Brush teeth",
            "icon": None,
            "window": "morning",
            "due_time": "17:00",
            "state": "completed",
            "overdue": False,
            "completed_at": seeded_panel.pinned_utc_iso,
            "on_time": True,
        }
    ]


async def test_missed_instances_are_omitted_from_panel_payload(
    seeded_panel: SimpleNamespace,
) -> None:
    """A missed instance never reaches the panel payload (D-009).

    The household carries a past-due OPEN instance due yesterday (the
    state the panel reads as "missed"); it must not appear anywhere in
    the response, and Ada's payload carries exactly her ONE today
    instance — the past-due rows (the stale chore AND her pack bag due
    yesterday) are both omitted rather than rendered.
    """
    seed = seeded_panel.seed
    response = await seeded_panel.client.get(
        "/api/v1/panel/snapshot",
        headers={"Authorization": f"Bearer {PANEL_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()

    payload_instances = [
        instance
        for child in body["children"]
        for instance in child["instances"]
    ]
    assert "missed" not in [
        instance["state"] for instance in payload_instances
    ]
    past_due_ids = {seed.stale_instance.id}
    assert past_due_ids.isdisjoint(
        instance["id"] for instance in payload_instances
    ), "the past-due open instance leaked into the panel payload"

    ada = next(
        child
        for child in body["children"]
        if child["child_id"] == seed.ada.id
    )
    assert [instance["id"] for instance in ada["instances"]] == [
        seed.pack_bag_instance.id
    ]


def test_panel_shaper_drops_missed_views() -> None:
    """The route's shaper omits a missed view (D-009), on the app's copy.

    ``instance_payload(include_missed=False)`` is what the snapshot
    route shapes every child's instances with; exercised here on the
    SAME core copy the app uses (the two-copy caveat makes this a
    distinct object from the conftest-stubbed copy's identical source).
    """
    missed_view = core_snapshot.QuestInstanceView(
        instance_id=999,
        definition_id=1,
        child_id=1,
        title="Stale chore",
        icon=None,
        window="morning",
        due_date="2026-09-21",
        due_time="09:00",
        state="missed",
        overdue=False,
        completed_at=None,
        was_on_time=None,
    )
    assert core_snapshot.instance_payload(
        [missed_view], include_missed=False
    ) == []


# --- route documentation -------------------------------------------------


async def test_snapshot_route_is_documented(
    panel_client: httpx.AsyncClient,
) -> None:
    """The snapshot route and its response shape are in the OpenAPI doc."""
    response = await panel_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/panel/snapshot" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/panel/snapshot"]
    documented = {
        model["title"]
        for model in schema["components"]["schemas"].values()
    }
    assert "PanelSnapshotResponse" in documented
    assert "PanelChildPayload" in documented
    assert "PanelInstancePayload" in documented
