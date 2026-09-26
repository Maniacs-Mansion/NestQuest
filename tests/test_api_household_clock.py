"""Household-local clock tests for the API service (task fa7475ba).

The deployed API container runs UTC while the household is US Eastern,
so reading the HOST clock marked every morning quest overdue from the
small hours.  The API now re-expresses its ONE host clock read in the
stored ``timezone`` setting (``NestQuestSettings.household_now``).

Every test pins the host clock to a UTC instant (the deployed
container's zone) and sets the household zone through the real admin
``PATCH /api/v1/admin/settings`` route, then reads BOTH snapshot shapes:

- one second before the 10:00 due time: NOT overdue (previously
  flagged, because 13:59:59 UTC > 10:00);
- exactly at 10:00:00: NOT overdue (the builder's strict
  ``now.time() > due`` convention);
- one second after: overdue;
- 23:30 household time, already the next day in UTC: ``today_iso`` is
  still the household's day.

An unset zone keeps the historical host-local behaviour, and the
missed-sweep scheduler waits for the rollover in household time.
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api import routes_admin, routes_panel
from api.database import _executor
from api.scheduler import MissedSweepScheduler, _delay_seconds
from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)
from tests.test_api_panel import _seed_household

_settings = importlib.import_module("nestquest_core.settings")
_settings_store = importlib.import_module("nestquest_core.settings_store")
_core_db = importlib.import_module("nestquest_core.db")
_core_migrations = importlib.import_module("nestquest_core.migrations")

#: The panel service token the admin harness app is configured with.
HARNESS_PANEL_TOKEN = "admin-test-panel-token"

UTC = ZoneInfo("UTC")
HOUSEHOLD_ZONE = "America/New_York"

#: A fixed household day on Eastern Daylight Time (UTC-4).
TODAY = datetime.date(2026, 9, 26)


def _utc(hour: int, minute: int, second: int = 0, *, day: int = 26):
    """An aware UTC instant on September ``day`` 2026."""
    return datetime.datetime(2026, 9, day, hour, minute, second, tzinfo=UTC)


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def _panel_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"}


@pytest.fixture
async def household(temp_db_path: str, monkeypatch) -> SimpleNamespace:
    """The seeded household on the admin-plane app, host clock pinnable.

    Ada's open "Pack bag" quest is due 10:00 on :data:`TODAY`.  Both
    routes' host clock read returns ``clock["now"]`` (a UTC instant).
    """
    seed = await _seed_household(temp_db_path, TODAY, _utc(16, 0))
    clock = {"now": _utc(12, 0)}
    monkeypatch.setattr(routes_admin, "_local_now", lambda: clock["now"])
    monkeypatch.setattr(routes_panel, "_local_now", lambda: clock["now"])
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(client=client, seed=seed, clock=clock)


async def _set_zone(household: SimpleNamespace, zone: str) -> None:
    response = await household.client.patch(
        "/api/v1/admin/settings",
        json={"timezone": zone},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == zone


async def _pack_bag(household: SimpleNamespace, plane: str) -> tuple[str, dict]:
    """Return ``(today_iso, Ada's Pack bag instance)`` from one snapshot."""
    headers = _admin_headers() if plane == "admin" else _panel_headers()
    response = await household.client.get(
        f"/api/v1/{plane}/snapshot", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    ada = next(
        child
        for child in body["children"]
        if child["child_id"] == household.seed.ada.id
    )
    (instance,) = ada["instances"]
    assert instance["title"] == "Pack bag"
    assert instance["due_time"] == "10:00"
    return body["today_iso"], instance


@pytest.mark.parametrize("plane", ["panel", "admin"])
@pytest.mark.parametrize(
    ("host_now", "overdue"),
    [
        # 09:59:59 EDT — the pre-fix code compared 13:59:59 (UTC) > 10:00.
        (_utc(13, 59, 59), False),
        # 10:00:00 EDT exactly — strict ``>``: not yet overdue.
        (_utc(14, 0, 0), False),
        # 10:00:01 EDT — overdue.
        (_utc(14, 0, 1), True),
    ],
    ids=["before-due", "at-due", "after-due"],
)
async def test_overdue_boundary_uses_household_zone(
    household: SimpleNamespace,
    plane: str,
    host_now: datetime.datetime,
    overdue: bool,
) -> None:
    await _set_zone(household, HOUSEHOLD_ZONE)
    household.clock["now"] = host_now
    today_iso, instance = await _pack_bag(household, plane)
    assert today_iso == TODAY.isoformat()
    assert instance["state"] == "open"
    assert instance["overdue"] is overdue


@pytest.mark.parametrize("plane", ["panel", "admin"])
async def test_household_day_survives_utc_midnight(
    household: SimpleNamespace, plane: str
) -> None:
    """23:30 EDT is already tomorrow in UTC; the household day is today."""
    await _set_zone(household, HOUSEHOLD_ZONE)
    household.clock["now"] = _utc(3, 30, day=27)
    today_iso, instance = await _pack_bag(household, plane)
    assert today_iso == TODAY.isoformat()
    assert instance["overdue"] is True


@pytest.mark.parametrize("plane", ["panel", "admin"])
async def test_unset_zone_keeps_host_local_time(
    household: SimpleNamespace, plane: str
) -> None:
    """Backward compatible: no stored zone reads the host clock as-is."""
    household.clock["now"] = _utc(13, 59, 59)
    today_iso, instance = await _pack_bag(household, plane)
    assert today_iso == TODAY.isoformat()
    assert instance["overdue"] is True


async def test_panel_completion_on_time_uses_household_zone(
    household: SimpleNamespace,
) -> None:
    """A 09:30 EDT tap on a 10:00 quest is on time (13:30 UTC is not)."""
    await _set_zone(household, HOUSEHOLD_ZONE)
    household.clock["now"] = _utc(13, 30)
    seed = household.seed
    response = await household.client.post(
        f"/api/v1/panel/instances/{seed.pack_bag_instance.id}/complete",
        headers=_panel_headers(),
        json={"actor_child_id": seed.ada.id},
    )
    assert response.status_code == 200
    _today_iso, instance = await _pack_bag(household, "admin")
    assert instance["state"] == "completed"
    assert instance["on_time"] is True


async def test_invalid_zone_is_rejected(household: SimpleNamespace) -> None:
    response = await household.client.patch(
        "/api/v1/admin/settings",
        json={"timezone": "Mars/Olympus_Mons"},
        headers=_admin_headers(),
    )
    assert response.status_code == 422
    assert "timezone" in str(response.json()["detail"])
    reread = await household.client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert reread.json()["timezone"] == ""


# --- the settings object ---------------------------------------------------


def test_settings_timezone_defaults_to_host_local() -> None:
    settings = _settings.NestQuestSettings()
    assert settings.timezone == ""
    instant = _utc(13, 0)
    assert settings.household_now(instant) is instant


def test_settings_household_now_converts_the_same_instant() -> None:
    settings = _settings.NestQuestSettings(timezone=HOUSEHOLD_ZONE)
    local = settings.household_now(_utc(13, 0))
    assert local == _utc(13, 0)
    assert (local.date(), local.time()) == (TODAY, datetime.time(9, 0))


@pytest.mark.parametrize("value", ["Mars/Olympus_Mons", "../etc/passwd", 5, None])
def test_settings_rejects_invalid_timezone(value: object) -> None:
    with pytest.raises(ValueError, match="timezone"):
        _settings.NestQuestSettings(timezone=value)


def test_from_options_reads_and_resiliently_defaults_timezone() -> None:
    assert (
        _settings.NestQuestSettings.from_options(
            {"timezone": HOUSEHOLD_ZONE}
        ).timezone
        == HOUSEHOLD_ZONE
    )
    assert _settings.NestQuestSettings.from_options({}).timezone == ""
    assert (
        _settings.NestQuestSettings.from_options_resilient(
            {"timezone": "Nowhere/Land", "horizon_days": 9}
        ).timezone
        == ""
    )


# --- the missed-sweep scheduler ----------------------------------------------


async def test_scheduler_waits_for_rollover_in_household_time(
    temp_db_path: str,
) -> None:
    """09:00 EDT (13:00 UTC) to a 10:05 rollover is 65 minutes away."""
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        await _core_migrations.apply_migrations(database)
        await _settings_store.update_settings(
            database,
            {"day_rollover_time": "10:05", "timezone": HOUSEHOLD_ZONE},
        )
        delays: list[float] = []
        first_sleep = asyncio.Event()

        async def sleep_stub(seconds: float) -> None:
            delays.append(seconds)
            first_sleep.set()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        scheduler.start()
        try:
            await asyncio.wait_for(first_sleep.wait(), timeout=5)
        finally:
            await scheduler.stop()
        assert delays == [pytest.approx(65 * 60)]
    finally:
        await database.close()


# --- the rollover delay across DST (America/New_York) ------------------------

NEW_YORK = ZoneInfo("America/New_York")


def _ny(*args: int, fold: int = 0) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=NEW_YORK, fold=fold)


@pytest.mark.parametrize(
    ("now", "target", "expected"),
    [
        # Ordinary EDT day: 09:00 -> 10:05 is 65 minutes.
        (_ny(2026, 6, 15, 9, 0), datetime.time(10, 5), 65 * 60),
        # An equal time schedules for tomorrow (strictly after now).
        (_ny(2026, 6, 15, 10, 5), datetime.time(10, 5), 86400),
        # Spring-forward: 01:00 EST -> 03:00 EDT is one real hour.
        (_ny(2026, 3, 8, 1, 0), datetime.time(3, 0), 3600),
        # Fall-back: 00:30 EDT -> 02:00 EST is two and a half real hours.
        (_ny(2026, 11, 1, 0, 30), datetime.time(2, 0), 9000),
        # Nonexistent 02:30 on spring-forward day: the first valid instant
        # at/after it is 03:00 EDT, one real hour after 01:00 EST.
        (_ny(2026, 3, 8, 1, 0), datetime.time(2, 30), 3600),
        # Ambiguous 01:30 on fall-back day resolves to the FIRST (EDT)
        # occurrence: from 00:30 EDT that is one real hour.
        (_ny(2026, 11, 1, 0, 30), datetime.time(1, 30), 3600),
        # Already past the first 01:30 (now is 01:15 EST, the repeated
        # hour): not the second occurrence, but tomorrow's 01:30 EST.
        (_ny(2026, 11, 1, 1, 15, fold=1), datetime.time(1, 30), 87300),
    ],
)
def test_delay_seconds_is_true_elapsed_time_across_dst(
    now: datetime.datetime, target: datetime.time, expected: float
) -> None:
    assert _delay_seconds(target, now) == expected
