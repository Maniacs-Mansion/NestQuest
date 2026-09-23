"""Admin-plane history route tests (task 2d2dda53).

These tests exercise the admin plane's history query and CSV export
routes against the ASGI app with httpx, reusing the shared
local-RSA-key/stubbed-JWKS harness (:mod:`tests.admin_jwt_harness`) so
an admin JWT genuinely authenticates — signature, issuer, audience,
expiry and the nestquest-admins group — with NO network access.  The
household is seeded with :func:`tests.test_api_panel._seed_household`
through the SAME core copy the app uses (``nestquest_core.*``; the
two-copy caveat in api/nestquest_core.py), and the reversal the
history tests read is appended through that same copy's
:func:`nestquest_core.completion.uncomplete_instance` — so the rows
the routes report are the rows the core's own write paths produced.

The seeded household (clock pinned to noon, the route's ``_local_now``
pinned to the same instant so nothing straddles midnight):

- Bo's ``Brush teeth`` TODAY instance: a ``completed`` event (panel
  tap, on time) plus the appended ``uncompleted`` reversal — the
  completion and the reversal the ``all`` and ``reversals`` filters
  report.
- Ada's ``Pack bag`` and ``Stale chore`` YESTERDAY instances and Bo's
  ``Brush teeth`` YESTERDAY instance: open, past due, no events — the
  DERIVED missed rows the ``missed`` filter reports.

Proven per the done-condition, everything read back through the API:

- ``GET /api/v1/admin/history`` returns the expected rows for EACH
  filter — ``all`` (the completed event AND the reversal),
  ``reversals`` (the uncompleted event only) and ``missed`` (the
  derived past-due open instances, actor ``nightly sweep``, no
  ``occurred_at``) — and the range scopes by the INSTANCE's due date
  (the Feature 13 rule), so the events sit under their instance's due
  day, not the wall-clock day.
- ``GET /api/v1/admin/history.csv`` answers ``text/csv`` with a
  ``Content-Disposition`` attachment filename, and the parsed body
  (csv.reader) carries the documented header columns and exactly the
  filtered rows.
- Authentication runs through the router's ONE ``require_admin``
  dependency: a non-admin JWT is 403 and an absent credential is 401
  on both routes.
- Malformed input — an unknown filter, a non-strict date, an inverted
  range, a missing parameter — is 422 on both routes (never a 500).
"""
from __future__ import annotations

import csv
import datetime
import importlib
import io
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api import routes_admin
from api.database import _executor
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    SUBJECT,
    AdminRunner,
    jwks_for,
    make_token,
)
from tests.test_api_panel import _seed_household

# The completion, instance-DAO and db layers through the SAME core copy
# the app uses (nestquest_core.*, NOT the conftest-stubbed
# custom_components copy) — used for the tests' seeding only; the
# routes reach them through api.nestquest_core.
_completion = importlib.import_module("nestquest_core.completion")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_core_db = importlib.import_module("nestquest_core.db")

#: The documented CSV columns (Admin spec §5 event-row fields), in
#: header order — asserted literally so the contract is pinned here,
#: independent of the core constant.
DOCUMENTED_CSV_COLUMNS = [
    "occurred_at",
    "event_type",
    "child_name",
    "child_id",
    "quest_title",
    "instance_id",
    "window",
    "due_date",
    "due_time",
    "actor",
    "was_on_time",
]


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _pinned_noon() -> tuple[datetime.date, datetime.datetime]:
    """One host clock read pinned to 12:00 UTC that day.

    The seed's completion, the reversal and the route's clock all
    anchor to this instant (the reversal five minutes later), so
    nothing can straddle midnight mid-test.
    """
    today = datetime.datetime.now().astimezone().date()
    return today, datetime.datetime(
        today.year, today.month, today.day, 12, 0, 0, tzinfo=ZoneInfo("UTC")
    )


@pytest.fixture
async def history_household(temp_db_path: str, monkeypatch) -> SimpleNamespace:
    """A seeded household served by the admin-plane app, clock pinned.

    Beyond :func:`_seed_household`'s rows (Bo's today completion, the
    past-due open yesterday instances), the fixture appends ONE
    ``uncompleted`` reversal on Bo's today instance through the core
    completion layer — attributed to the harness subject, stamped five
    minutes after the pinned completion — and exposes the yesterday
    instances the missed filter must report.
    """
    today, pinned_now = _pinned_noon()
    yesterday = today - datetime.timedelta(days=1)
    seed = await _seed_household(temp_db_path, today, pinned_now)

    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        instances = _dao_instances.QuestInstancesDao(database)
        ada_yesterday = await instances.list_by_child_and_date(
            seed.ada.id, yesterday.isoformat()
        )
        pack_bag_yesterday = next(
            record for record in ada_yesterday if record.due_time == "10:00"
        )
        bo_yesterday = await instances.list_by_child_and_date(
            seed.bo.id, yesterday.isoformat()
        )
        brush_teeth_yesterday = next(
            record for record in bo_yesterday if record.due_time == "17:00"
        )
        await _completion.uncomplete_instance(
            database,
            seed.brush_teeth_instance.id,
            actor_source="user",
            actor_user_id=SUBJECT,
            now=pinned_now + datetime.timedelta(minutes=5),
            today=today,
        )
    finally:
        await database.close()

    monkeypatch.setattr(routes_admin, "_local_now", lambda: pinned_now)
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            seed=seed,
            database=runner.app.state.db.database,
            today=today,
            yesterday=yesterday,
            pack_bag_yesterday=pack_bag_yesterday,
            brush_teeth_yesterday=brush_teeth_yesterday,
        )


# --- authentication: the ONE require_admin dependency guards both routes ----


async def test_history_routes_refuse_non_admin_and_absent(
    history_household: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401, both routes."""
    client = history_household.client
    query = f"start={history_household.yesterday.isoformat()}"
    query += f"&end={history_household.today.isoformat()}"
    non_admin = make_token(groups=("some-other-group",))
    for path in ("/api/v1/admin/history", "/api/v1/admin/history.csv"):
        forbidden = await client.get(
            f"{path}?{query}",
            headers={"Authorization": f"Bearer {non_admin}"},
        )
        assert forbidden.status_code == 403, path
        assert forbidden.json()["detail"] == (
            "Admin access requires membership in the nestquest-admins group"
        )
        unauthenticated = await client.get(f"{path}?{query}")
        assert unauthenticated.status_code == 401, path


# --- the JSON history query: the expected rows per filter --------------------


async def test_history_all_returns_completed_and_reversal(
    history_household: SimpleNamespace,
) -> None:
    """``all`` returns the completed event AND the reversal, in order.

    Both events belong to Bo's Brush teeth instance due TODAY, so the
    due-date-scoped range [yesterday, today] reports them under today;
    the rows are ordered by due date, then instance, then event id —
    the completed row before its reversal.
    """
    client = history_household.client
    seed = history_household.seed
    brush = seed.brush_teeth_instance
    yesterday_iso = history_household.yesterday.isoformat()
    today_iso = history_household.today.isoformat()

    response = await client.get(
        "/api/v1/admin/history",
        params={"filter": "all", "start": yesterday_iso, "end": today_iso},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filter"] == "all"
    assert body["start"] == yesterday_iso
    assert body["end"] == today_iso
    assert body["count"] == 2

    completed, reversal = body["rows"]
    assert completed == {
        "occurred_at": f"{today_iso}T12:00:00+00:00",
        "event_type": "completed",
        "child_name": "Bo",
        "child_id": brush.child_id,
        "quest_title": "Brush teeth",
        "instance_id": brush.id,
        "window": "morning",
        "due_date": today_iso,
        "due_time": "17:00",
        "actor": "panel (Bo)",
        "was_on_time": True,
    }
    assert reversal == {
        "occurred_at": f"{today_iso}T12:05:00+00:00",
        "event_type": "uncompleted",
        "child_name": "Bo",
        "child_id": brush.child_id,
        "quest_title": "Brush teeth",
        "instance_id": brush.id,
        "window": "morning",
        "due_date": today_iso,
        "due_time": "17:00",
        "actor": SUBJECT,
        "was_on_time": None,
    }


async def test_history_reversals_returns_only_the_uncompleted_event(
    history_household: SimpleNamespace,
) -> None:
    """``reversals`` returns the uncompleted event only, user-attributed."""
    client = history_household.client
    seed = history_household.seed
    brush = seed.brush_teeth_instance
    today_iso = history_household.today.isoformat()

    response = await client.get(
        "/api/v1/admin/history",
        params={
            "filter": "reversals",
            "start": today_iso,
            "end": today_iso,
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filter"] == "reversals"
    assert body["count"] == 1
    (reversal,) = body["rows"]
    assert reversal["event_type"] == "uncompleted"
    assert reversal["instance_id"] == brush.id
    assert reversal["actor"] == SUBJECT
    assert reversal["occurred_at"] == f"{today_iso}T12:05:00+00:00"
    assert reversal["was_on_time"] is None


async def test_history_missed_returns_derived_missed_instances(
    history_household: SimpleNamespace,
) -> None:
    """``missed`` returns the DERIVED past-due open instances.

    Three seeded instances are open and due yesterday: Ada's Pack bag
    and Stale chore and Bo's Brush teeth.  Each is a DERIVED row —
    never a stored event: no ``occurred_at``, ``was_on_time`` None and
    the spec's ``nightly sweep`` actor.
    """
    client = history_household.client
    seed = history_household.seed
    yesterday_iso = history_household.yesterday.isoformat()

    response = await client.get(
        "/api/v1/admin/history",
        params={
            "filter": "missed",
            "start": yesterday_iso,
            "end": yesterday_iso,
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filter"] == "missed"
    assert body["count"] == 3

    rows = body["rows"]
    assert all(row["event_type"] == "missed" for row in rows)
    assert all(row["occurred_at"] is None for row in rows)
    assert all(row["was_on_time"] is None for row in rows)
    assert all(row["actor"] == "nightly sweep" for row in rows)
    assert all(row["due_date"] == yesterday_iso for row in rows)
    assert {
        (row["child_name"], row["quest_title"], row["due_time"])
        for row in rows
    } == {
        ("Ada", "Pack bag", "10:00"),
        ("Bo", "Brush teeth", "17:00"),
        ("Ada", "Stale chore", "09:00"),
    }
    assert {
        row["instance_id"]
        for row in rows
    } == {
        history_household.pack_bag_yesterday.id,
        history_household.brush_teeth_yesterday.id,
        seed.stale_instance.id,
    }
    # Deterministic order: due date, then instance id.
    keys = [(row["due_date"], row["instance_id"]) for row in rows]
    assert keys == sorted(keys)


async def test_history_range_scopes_by_the_instance_due_date(
    history_household: SimpleNamespace,
) -> None:
    """The range scopes by the INSTANCE's due date, not the wall clock.

    Both events OCCURRED today but belong to the instance due today, so
    a yesterday-only ``all`` range reports nothing; the missed filter
    over a today-only range reports nothing either (a due-TODAY open
    instance is not past due).
    """
    client = history_household.client
    yesterday_iso = history_household.yesterday.isoformat()
    today_iso = history_household.today.isoformat()

    yesterday_all = await client.get(
        "/api/v1/admin/history",
        params={"filter": "all", "start": yesterday_iso, "end": yesterday_iso},
        headers=_admin_headers(),
    )
    assert yesterday_all.status_code == 200
    assert yesterday_all.json()["count"] == 0

    today_missed = await client.get(
        "/api/v1/admin/history",
        params={"filter": "missed", "start": today_iso, "end": today_iso},
        headers=_admin_headers(),
    )
    assert today_missed.status_code == 200
    assert today_missed.json()["count"] == 0


# --- the CSV export: documented columns and the filtered rows ----------------


async def test_history_csv_carries_documented_columns_and_all_rows(
    history_household: SimpleNamespace,
) -> None:
    """The CSV export carries the documented header and the filtered rows.

    The body is parsed with csv.reader: the first row is the documented
    column set, the remaining rows are exactly the ``all`` filter's
    rows (the completion and its reversal) in the same order the JSON
    query reports them.
    """
    client = history_household.client
    seed = history_household.seed
    brush = seed.brush_teeth_instance
    yesterday_iso = history_household.yesterday.isoformat()
    today_iso = history_household.today.isoformat()

    response = await client.get(
        "/api/v1/admin/history.csv",
        params={"filter": "all", "start": yesterday_iso, "end": today_iso},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert (
        f'filename="nestquest-history-{yesterday_iso}-to-{today_iso}.csv"'
        in disposition
    )

    parsed = list(csv.reader(io.StringIO(response.text)))
    assert parsed[0] == DOCUMENTED_CSV_COLUMNS
    assert len(parsed) == 3  # header + completed + reversal
    assert parsed[1] == [
        f"{today_iso}T12:00:00+00:00",
        "completed",
        "Bo",
        str(brush.child_id),
        "Brush teeth",
        str(brush.id),
        "morning",
        today_iso,
        "17:00",
        "panel (Bo)",
        "true",
    ]
    assert parsed[2] == [
        f"{today_iso}T12:05:00+00:00",
        "uncompleted",
        "Bo",
        str(brush.child_id),
        "Brush teeth",
        str(brush.id),
        "morning",
        today_iso,
        "17:00",
        SUBJECT,
        "",
    ]


async def test_history_csv_missed_rows_are_derived_rows(
    history_household: SimpleNamespace,
) -> None:
    """The CSV export of the ``missed`` filter carries the derived rows.

    Same filtered range as the JSON query's missed answer: three rows
    with an empty ``occurred_at`` (no event exists), the ``missed``
    event type and the ``nightly sweep`` actor.
    """
    client = history_household.client
    seed = history_household.seed
    yesterday_iso = history_household.yesterday.isoformat()

    response = await client.get(
        "/api/v1/admin/history.csv",
        params={
            "filter": "missed",
            "start": yesterday_iso,
            "end": yesterday_iso,
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    parsed = list(csv.reader(io.StringIO(response.text)))
    assert parsed[0] == DOCUMENTED_CSV_COLUMNS
    assert len(parsed) == 4  # header + the three derived missed rows
    missed_rows = parsed[1:]
    assert all(row[1] == "missed" for row in missed_rows)
    assert all(row[0] == "" for row in missed_rows)
    assert all(row[9] == "nightly sweep" for row in missed_rows)
    assert all(row[10] == "" for row in missed_rows)
    assert {
        (row[2], row[4], row[8]) for row in missed_rows
    } == {
        ("Ada", "Pack bag", "10:00"),
        ("Bo", "Brush teeth", "17:00"),
        ("Ada", "Stale chore", "09:00"),
    }
    assert {row[5] for row in missed_rows} == {
        str(history_household.pack_bag_yesterday.id),
        str(history_household.brush_teeth_yesterday.id),
        str(seed.stale_instance.id),
    }


# --- validation: malformed filter and date range are 422, never 500 ----------


@pytest.mark.parametrize(
    "params",
    [
        {"filter": "everything", "start": "2026-03-01", "end": "2026-03-02"},
        {"filter": "all", "start": "2026/03/01", "end": "2026-03-02"},
        {"filter": "all", "start": "2026-3-1", "end": "2026-03-02"},
        {"filter": "all", "start": "2026-03-02", "end": "2026-03-01"},
        {"filter": "all", "start": "not-a-date", "end": "2026-03-02"},
    ],
)
async def test_history_query_rejects_malformed_params_as_422(
    history_household: SimpleNamespace, params: dict[str, str]
) -> None:
    """An unknown filter or a rejected range is 422 naming the field."""
    client = history_household.client
    response = await client.get(
        "/api/v1/admin/history", params=params, headers=_admin_headers()
    )
    assert response.status_code == 422, params
    detail = response.json()["detail"]
    assert any(
        name in detail for name in ("filter", "start", "end")
    ), detail


async def test_history_csv_rejects_malformed_params_as_422(
    history_household: SimpleNamespace,
) -> None:
    """The CSV route maps the same rejections to 422."""
    client = history_household.client
    unknown_filter = await client.get(
        "/api/v1/admin/history.csv",
        params={"filter": "galaxy", "start": "2026-03-01", "end": "2026-03-02"},
        headers=_admin_headers(),
    )
    assert unknown_filter.status_code == 422
    assert "filter" in unknown_filter.json()["detail"]

    inverted = await client.get(
        "/api/v1/admin/history.csv",
        params={"filter": "all", "start": "2026-03-02", "end": "2026-03-01"},
        headers=_admin_headers(),
    )
    assert inverted.status_code == 422
    assert "end must be on or after start" in inverted.json()["detail"]


async def test_history_query_missing_params_are_422(
    history_household: SimpleNamespace,
) -> None:
    """A missing required query parameter is FastAPI's 422 (the shape)."""
    client = history_household.client
    no_params = await client.get(
        "/api/v1/admin/history", headers=_admin_headers()
    )
    assert no_params.status_code == 422
    missing_start = await client.get(
        "/api/v1/admin/history",
        params={"end": "2026-03-02"},
        headers=_admin_headers(),
    )
    assert missing_start.status_code == 422
    missing_end = await client.get(
        "/api/v1/admin/history",
        params={"start": "2026-03-01"},
        headers=_admin_headers(),
    )
    assert missing_end.status_code == 422
