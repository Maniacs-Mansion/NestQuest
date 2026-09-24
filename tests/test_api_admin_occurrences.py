"""Admin-plane occurrence-preview route tests (task 5f843564).

These tests exercise ``POST /api/v1/admin/quest-definitions/occurrences-preview``
against the ASGI app with httpx, reusing the shared local-RSA-key/
stubbed-JWKS harness (:mod:`tests.admin_jwt_harness`) so an admin JWT
genuinely authenticates with NO network access.

- Authentication runs through the router's ONE ``require_admin``
  dependency: no credential is 401, the panel service token is 403
  (refused as a credential type), a JWT without the admin group is
  403, an admin JWT is 200.
- The returned dates are asserted EXACTLY for a weekly rule with an
  interval and a start_date, a daily rule with an interval, a rule
  with an end_date (the list stops at it), a month-end-clamped monthly
  rule, and the default start (the pinned host clock's today); one
  case also asserts parity with the core's own ``occurrences_between``
  over the documented window.
- A rejected rule (the same core ``from_dict`` validation create/edit
  use), a non-strict ``start_date`` and a ``count`` outside 1..50 are
  422.
"""
from __future__ import annotations

import datetime
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api import routes_admin
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

# The recurrence engine through the SAME core copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy).
_recurrence = importlib.import_module("nestquest_core.recurrence")

PREVIEW_URL = "/api/v1/admin/quest-definitions/occurrences-preview"

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

#: The pinned host instant: Wednesday 2026-09-23, noon UTC.
PINNED_NOW = datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=ZoneInfo("UTC"))


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _weekly_rule() -> dict[str, object]:
    """Every OTHER week's Tuesday and Friday, anchored on Tue 2026-03-03."""
    return {
        "rule_type": "weekly",
        "interval": 2,
        "weekday_set": [1, 4],
        "start_date": "2026-03-03",
    }


@pytest.fixture
async def preview(temp_db_path: str, monkeypatch) -> SimpleNamespace:
    """An admin-plane app client with the host clock pinned (and counted)."""
    clock_reads: list[datetime.datetime] = []

    def _admin_now() -> datetime.datetime:
        clock_reads.append(PINNED_NOW)
        return PINNED_NOW

    monkeypatch.setattr(routes_admin, "_local_now", _admin_now)
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(client=client, clock_reads=clock_reads)


async def _post(client: object, body: dict[str, object]) -> object:
    """POST a preview body with an admin JWT."""
    return await client.post(PREVIEW_URL, json=body, headers=_admin_headers())


# --- authentication: the ONE require_admin dependency ----------------------


async def test_preview_without_credential_is_401(
    preview: SimpleNamespace,
) -> None:
    """No Authorization header is the uniform 401."""
    response = await preview.client.post(
        PREVIEW_URL, json={"rule": _weekly_rule()}
    )
    assert response.status_code == 401


async def test_preview_refuses_panel_service_token(
    preview: SimpleNamespace,
) -> None:
    """The panel service token is refused as a credential type (403)."""
    response = await preview.client.post(
        PREVIEW_URL,
        json={"rule": _weekly_rule()},
        headers={"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL


async def test_preview_refuses_non_admin_jwt(
    preview: SimpleNamespace,
) -> None:
    """A valid JWT without the nestquest-admins group is 403."""
    non_admin = make_token(groups=("some-other-group",))
    response = await preview.client.post(
        PREVIEW_URL,
        json={"rule": _weekly_rule()},
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


async def test_preview_admin_jwt_is_200(preview: SimpleNamespace) -> None:
    """An admin JWT is 200 with the documented ``dates`` shape."""
    response = await _post(
        preview.client, {"rule": _weekly_rule(), "start_date": "2026-03-01"}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"dates"}


# --- the returned dates ----------------------------------------------------


async def test_weekly_interval_rule_from_before_its_start(
    preview: SimpleNamespace,
) -> None:
    """Every other week's Tue/Fri, starting at the rule's own start_date.

    The preview starts on Sun 2026-03-01, before the rule's anchor, so
    the first date is the anchor itself; the off weeks (Mar 10-16,
    Mar 24-30) are skipped.
    """
    response = await _post(
        preview.client,
        {"rule": _weekly_rule(), "start_date": "2026-03-01", "count": 6},
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-03-03",
        "2026-03-06",
        "2026-03-17",
        "2026-03-20",
        "2026-03-31",
        "2026-04-03",
    ]


async def test_weekly_interval_rule_from_mid_cadence(
    preview: SimpleNamespace,
) -> None:
    """A start inside an on-week keeps the rule's anchor cadence."""
    response = await _post(
        preview.client,
        {"rule": _weekly_rule(), "start_date": "2026-03-18", "count": 4},
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-03-20",
        "2026-03-31",
        "2026-04-03",
        "2026-04-14",
    ]


async def test_daily_interval_rule(preview: SimpleNamespace) -> None:
    """Every third day from 2026-01-01, previewed from 2026-01-05."""
    response = await _post(
        preview.client,
        {
            "rule": {
                "rule_type": "daily",
                "interval": 3,
                "start_date": "2026-01-01",
            },
            "start_date": "2026-01-05",
            "count": 4,
        },
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-01-07",
        "2026-01-10",
        "2026-01-13",
        "2026-01-16",
    ]


async def test_rule_with_end_date_stops_at_it(
    preview: SimpleNamespace,
) -> None:
    """A daily rule ending 2026-05-04 yields only its four dates."""
    response = await _post(
        preview.client,
        {
            "rule": {
                "rule_type": "daily",
                "start_date": "2026-05-01",
                "end_date": "2026-05-04",
            },
            "start_date": "2026-04-28",
            "count": 10,
        },
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
        "2026-05-04",
    ]


async def test_monthly_day_rule_clamps_to_month_end(
    preview: SimpleNamespace,
) -> None:
    """The core's month-end policy: the 31st fires on Feb 28th."""
    response = await _post(
        preview.client,
        {
            "rule": {
                "rule_type": "monthly_day",
                "day_of_month": 31,
                "start_date": "2026-01-31",
            },
            "start_date": "2026-01-01",
            "count": 3,
        },
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
    ]


async def test_default_start_is_host_today_with_default_count(
    preview: SimpleNamespace,
) -> None:
    """No start_date: ONE clock read's date; no count: ten dates."""
    response = await _post(preview.client, {"rule": {"rule_type": "daily"}})
    assert response.status_code == 200
    expected = [
        (datetime.date(2026, 9, 23) + datetime.timedelta(days=n)).isoformat()
        for n in range(10)
    ]
    assert response.json()["dates"] == expected
    assert preview.clock_reads == [PINNED_NOW]


async def test_supplied_start_date_reads_no_clock(
    preview: SimpleNamespace,
) -> None:
    """A supplied start_date is used as-is: the host clock is not read."""
    response = await _post(
        preview.client, {"rule": _weekly_rule(), "start_date": "2026-03-01"}
    )
    assert response.status_code == 200
    assert preview.clock_reads == []


async def test_dates_match_core_occurrences_between_over_window(
    preview: SimpleNamespace,
) -> None:
    """The route's dates ARE the core's walk over the 366-day window."""
    rule_body = {
        "rule_type": "monthly_weekday",
        "nth_weekday": -1,
        "nth_weekday_weekday": 4,
        "start_date": "2026-01-01",
    }
    response = await _post(
        preview.client,
        {"rule": rule_body, "start_date": "2026-02-10", "count": 50},
    )
    assert response.status_code == 200
    core_dates = _recurrence.occurrences_between(
        _recurrence.ScheduleRule.from_dict(rule_body),
        "2026-02-10",
        "2027-02-11",
    )
    assert response.json()["dates"] == core_dates
    assert len(core_dates) == 12


async def test_yearly_rule_shows_next_occurrence_within_window(
    preview: SimpleNamespace,
) -> None:
    """The 366-day window always reaches a yearly rule's next date."""
    response = await _post(
        preview.client,
        {
            "rule": {
                "rule_type": "yearly",
                "month": 9,
                "day_of_month": 22,
                "start_date": "2020-09-22",
            },
            "start_date": "2026-09-23",
        },
    )
    assert response.status_code == 200
    assert response.json()["dates"] == ["2027-09-22"]


async def test_start_near_calendar_end_is_422(
    preview: SimpleNamespace,
) -> None:
    """A window that would reach 9999-12-31 is rejected, not clamped."""
    response = await _post(
        preview.client,
        {"rule": {"rule_type": "daily"}, "start_date": "9999-12-30"},
    )
    assert response.status_code == 422
    assert "too close to the end of the calendar" in response.json()["detail"]


async def test_latest_accepted_start_date(preview: SimpleNamespace) -> None:
    """The last start whose window ends before 9999-12-31 is accepted."""
    response = await _post(
        preview.client,
        {
            "rule": {"rule_type": "daily"},
            "start_date": "9998-12-29",
            "count": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["dates"] == ["9998-12-29"]


# --- rejections: 422 -------------------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        {"rule_type": "weekly"},  # weekly without weekday_set
        {"rule_type": "fortnightly"},  # unknown rule_type
        {"rule_type": "daily", "interval": 0},
        {"rule_type": "daily", "weekday_set": [1]},  # forbidden field
        {"rule_type": "daily", "start_date": "2026-3-1"},
        {
            "rule_type": "daily",
            "start_date": "2026-05-04",
            "end_date": "2026-05-01",
        },
    ],
)
async def test_malformed_rule_is_422(
    preview: SimpleNamespace, rule: dict[str, object]
) -> None:
    """A rule the core's from_dict rejects is 422, as on create/edit."""
    response = await _post(
        preview.client, {"rule": rule, "start_date": "2026-03-01"}
    )
    assert response.status_code == 422


async def test_missing_rule_is_422(preview: SimpleNamespace) -> None:
    """The rule is required: the body model's 422."""
    response = await _post(preview.client, {"start_date": "2026-03-01"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "start_date", ["2026-3-1", "20260301", "tomorrow", "2026-02-30", ""]
)
async def test_non_strict_start_date_is_422(
    preview: SimpleNamespace, start_date: str
) -> None:
    """start_date must be a strict YYYY-MM-DD date (the core's check)."""
    response = await _post(
        preview.client, {"rule": _weekly_rule(), "start_date": start_date}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("count", [0, -1, 51, 1000, True, "5", 2.5])
async def test_count_out_of_range_is_422(
    preview: SimpleNamespace, count: object
) -> None:
    """count must be a strict JSON integer in 1..50."""
    response = await _post(
        preview.client,
        {"rule": _weekly_rule(), "start_date": "2026-03-01", "count": count},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("count", [1, 50])
async def test_count_bounds_are_inclusive(
    preview: SimpleNamespace, count: int
) -> None:
    """count 1 and 50 are accepted and truncate the list exactly."""
    response = await _post(
        preview.client,
        {
            "rule": {"rule_type": "daily"},
            "start_date": "2026-01-01",
            "count": count,
        },
    )
    assert response.status_code == 200
    assert len(response.json()["dates"]) == count
