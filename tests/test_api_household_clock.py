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
Nothing sets the zone automatically: a timezone header on a panel
request never changes the stored settings (task 7f685179).
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api import host_zone, routes_admin, routes_panel
from api import scheduler as scheduler_module
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
_dao_meta = importlib.import_module("nestquest_core.dao_meta")

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
        yield SimpleNamespace(
            client=client,
            seed=seed,
            clock=clock,
            database=runner.app.state.db.database,
            app=runner.app,
        )


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


def test_settings_have_no_timezone_configured_marker() -> None:
    assert not hasattr(_settings.NestQuestSettings(), "timezone_configured")
    with pytest.raises(TypeError):
        _settings.NestQuestSettings(timezone_configured=True)
    # A stored document still carrying the removed key loads harmlessly.
    assert _settings.NestQuestSettings.from_options_resilient(
        {"timezone": HOUSEHOLD_ZONE, "timezone_configured": True}
    ) == _settings.NestQuestSettings(timezone=HOUSEHOLD_ZONE)


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


# --- nothing sets the zone automatically (task 7f685179) --------------------
#
# The zone is only ever set by an admin's explicit settings update.  A
# timezone header on a panel request — the one Home Assistant used to
# report, or any look-alike — is ignored, and no read writes settings.

#: Timezone-looking request headers a panel request might carry.
_TIMEZONE_HEADERS = [
    {"X-NestQuest-Timezone": HOUSEHOLD_ZONE},
    {"X-NestQuest-Time-Zone": HOUSEHOLD_ZONE},
    {"X-Timezone": HOUSEHOLD_ZONE},
    {"Time-Zone": HOUSEHOLD_ZONE},
]


async def _stored_document(household: SimpleNamespace) -> str | None:
    """The raw stored settings document (``None`` when never written)."""
    return await _dao_meta.MetaStateDao(household.database).get(
        _settings_store.SETTINGS_META_KEY
    )


async def _admin_settings(household: SimpleNamespace) -> dict:
    response = await household.client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("extra", _TIMEZONE_HEADERS)
async def test_panel_timezone_header_never_changes_settings(
    household: SimpleNamespace, extra: dict[str, str]
) -> None:
    """09:59:59 EDT on a UTC host, zone unset: the header is ignored."""
    household.clock["now"] = _utc(13, 59, 59)
    headers = {**_panel_headers(), **extra}
    snapshot = await household.client.get(
        "/api/v1/panel/snapshot", headers=headers
    )
    assert snapshot.status_code == 200
    seed = household.seed
    completed = await household.client.post(
        f"/api/v1/panel/instances/{seed.pack_bag_instance.id}/complete",
        headers=headers,
        json={"actor_child_id": seed.ada.id},
    )
    assert completed.status_code == 200
    # Nothing was written, and the clock stayed host local (UTC): the
    # 10:00 quest was overdue and the 13:59 UTC completion was late.
    assert await _stored_document(household) is None
    assert (await _admin_settings(household))["timezone"] == ""
    _today_iso, instance = await _pack_bag(household, "admin")
    assert instance["on_time"] is False


@pytest.mark.parametrize("extra", _TIMEZONE_HEADERS)
async def test_panel_timezone_header_never_replaces_the_stored_zone(
    household: SimpleNamespace, extra: dict[str, str]
) -> None:
    """A stored zone stays exactly as the admin saved it."""
    await _set_zone(household, "America/Los_Angeles")
    before = await _stored_document(household)
    household.clock["now"] = _utc(16, 59, 59)  # 09:59:59 PDT, 12:59:59 EDT
    response = await household.client.get(
        "/api/v1/panel/snapshot",
        headers={**_panel_headers(), **extra},
    )
    assert response.status_code == 200
    assert await _stored_document(household) == before
    _today_iso, instance = await _pack_bag(household, "panel")
    assert instance["overdue"] is False


async def test_fresh_install_zone_stays_empty_across_reads(
    household: SimpleNamespace,
) -> None:
    """Repeated panel and admin reads never write the settings document."""
    for hour in (3, 13, 23):
        household.clock["now"] = _utc(hour, 0)
        for extra in _TIMEZONE_HEADERS:
            response = await household.client.get(
                "/api/v1/panel/snapshot",
                headers={**_panel_headers(), **extra},
            )
            assert response.status_code == 200
        await _pack_bag(household, "admin")
        settings = await _admin_settings(household)
        assert settings["timezone"] == ""
        assert "timezone_configured" not in settings
    assert await _stored_document(household) is None


# --- the scheduler follows a changed zone (task 6351b36d) --------------------
#
# On a UTC host with no stored zone the scheduler first plans for UTC
# midnight; a zone stored while it sleeps must move the sweep to the
# household's midnight rather than sweep at 20:00 EDT.

#: 13:00 UTC (09:00 EDT) to UTC midnight.
_UTC_MIDNIGHT_DELAY = 11 * 3600
#: 13:00 UTC (09:00 EDT) to New York midnight (04:00 UTC).
_NEW_YORK_MIDNIGHT_DELAY = 15 * 3600


async def _store_zone(scheduler, database, zone: str) -> None:
    """Store ``zone`` the way a settings writer must: under the lock."""
    async with scheduler.settings_lock:
        settings = await _settings_store.update_settings(
            database, {"timezone": zone}
        )
        scheduler.settings_changed(settings)


async def test_scheduler_replans_when_zone_changes_while_sleeping(
    temp_db_path: str,
) -> None:
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner:
        app_state = runner.app.state
        await app_state.sweep_scheduler.stop()
        delays: list[float] = []
        slept = asyncio.Condition()

        async def sleep_stub(seconds: float) -> None:
            async with slept:
                delays.append(seconds)
                slept.notify_all()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            app_state.db.database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        app_state.sweep_scheduler = scheduler
        scheduler.start()
        try:
            async with slept:
                await asyncio.wait_for(
                    slept.wait_for(lambda: len(delays) == 1), timeout=5
                )
            await _store_zone(
                scheduler, app_state.db.database, HOUSEHOLD_ZONE
            )
            async with slept:
                await asyncio.wait_for(
                    slept.wait_for(lambda: len(delays) == 2), timeout=5
                )
        finally:
            await scheduler.stop()
    assert delays == [
        pytest.approx(_UTC_MIDNIGHT_DELAY),
        pytest.approx(_NEW_YORK_MIDNIGHT_DELAY),
    ]


async def test_scheduler_rechecks_settings_before_sweeping(
    temp_db_path: str, monkeypatch
) -> None:
    """A zone stored without a wake-up still stops the stale sweep."""
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        await _core_migrations.apply_migrations(database)
        sweeps: list[datetime.date] = []

        async def sweep_stub(_database, *, today):
            sweeps.append(today)
            return []

        monkeypatch.setattr(
            scheduler_module.core_sweep, "run_missed_sweep", sweep_stub
        )
        delays: list[float] = []
        replanned = asyncio.Event()

        async def sleep_stub(seconds: float) -> None:
            delays.append(seconds)
            if len(delays) == 1:
                # The UTC rollover "arrives" after the zone was stored
                # behind the scheduler's back.
                await _settings_store.update_settings(
                    database, {"timezone": HOUSEHOLD_ZONE}
                )
                return
            replanned.set()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        scheduler.start()
        try:
            await asyncio.wait_for(replanned.wait(), timeout=5)
        finally:
            await scheduler.stop()
        assert sweeps == []
        assert delays == [
            pytest.approx(_UTC_MIDNIGHT_DELAY),
            pytest.approx(_NEW_YORK_MIDNIGHT_DELAY),
        ]
    finally:
        await database.close()


# --- the admin settings route is the scheduler's writer (task 7e173881) ------
#
# ``PATCH /api/v1/admin/settings`` is the only settings writer: it holds
# the scheduler's settings lock across the write and tells the scheduler,
# so a saved zone or rollover re-plans a sleeping scheduler.


async def _sleeping_scheduler(household: SimpleNamespace):
    """Swap in a scheduler on the pinned clock; return it and its delays.

    Waits until it sleeps on its first plan.
    """
    await household.app.state.sweep_scheduler.stop()
    delays: list[float] = []
    slept = asyncio.Condition()

    async def sleep_stub(seconds: float) -> None:
        async with slept:
            delays.append(seconds)
            slept.notify_all()
        await asyncio.Event().wait()

    scheduler = MissedSweepScheduler(
        household.database,
        clock=lambda: household.clock["now"],
        sleep=sleep_stub,
    )
    household.app.state.sweep_scheduler = scheduler
    scheduler.start()

    async def wait_for_sleeps(count: int) -> None:
        async with slept:
            await asyncio.wait_for(
                slept.wait_for(lambda: len(delays) == count), timeout=5
            )

    await wait_for_sleeps(1)
    return scheduler, delays, wait_for_sleeps


@pytest.mark.parametrize(
    ("changes", "replanned_delay"),
    [
        # 13:00 UTC is 09:00 EDT: New York midnight is 15 hours away.
        ({"timezone": HOUSEHOLD_ZONE}, _NEW_YORK_MIDNIGHT_DELAY),
        # Still UTC: 13:00 to a 14:30 rollover is 90 minutes.
        ({"day_rollover_time": "14:30"}, 90 * 60),
    ],
    ids=["timezone", "day_rollover_time"],
)
async def test_admin_settings_patch_replans_a_sleeping_scheduler(
    household: SimpleNamespace, changes: dict, replanned_delay: float
) -> None:
    household.clock["now"] = _utc(13, 0)
    scheduler, delays, wait_for_sleeps = await _sleeping_scheduler(household)
    try:
        response = await household.client.patch(
            "/api/v1/admin/settings", json=changes, headers=_admin_headers()
        )
        assert response.status_code == 200
        await wait_for_sleeps(2)
    finally:
        await scheduler.stop()
    assert delays == [
        pytest.approx(_UTC_MIDNIGHT_DELAY),
        pytest.approx(replanned_delay),
    ]


async def test_admin_saved_zone_is_authoritative_across_surfaces(
    household: SimpleNamespace,
) -> None:
    """ONE instant, read by every surface in exactly the admin's zone.

    Asia/Kolkata (UTC+05:30) matches neither the UTC host nor any other
    zone in play.  04:30:01 UTC is 10:00:01 there: the 10:00 quest is
    overdue on both snapshots (it would not be in UTC, 04:30), the
    household day is the 26th, and the scheduler sleeps the 299 s to a
    10:05 rollover (UTC would be 5h35m).
    """
    household.clock["now"] = _utc(4, 30, 1)
    scheduler, delays, wait_for_sleeps = await _sleeping_scheduler(household)
    try:
        response = await household.client.patch(
            "/api/v1/admin/settings",
            json={"timezone": "Asia/Kolkata", "day_rollover_time": "10:05"},
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        await wait_for_sleeps(2)
        for plane in ("panel", "admin"):
            today_iso, instance = await _pack_bag(household, plane)
            assert today_iso == TODAY.isoformat(), plane
            assert instance["overdue"] is True, plane
    finally:
        await scheduler.stop()
    assert delays[1] == pytest.approx(299)


async def test_empty_zone_publishes_the_api_host_zone_to_panel_and_admin(
    household: SimpleNamespace, monkeypatch
) -> None:
    """With no zone stored, the API reads the host's local time — and the
    panel snapshot and the admin settings both publish that host's own
    zone, so the cards and the admin app format in the API's zone, never
    Home Assistant's or the browser's.

    The host runs Pacific/Auckland: 12:30 UTC on the 26th is already
    00:30 on the 27th there, so the API's household day is the 27th while
    a UTC Home Assistant or browser would still read the 26th.  Once the
    admin saves a zone, both publish exactly that zone.
    """
    host = "Pacific/Auckland"
    monkeypatch.setattr(host_zone, "host_timezone", lambda: host)
    household.clock["now"] = _utc(12, 30).astimezone(ZoneInfo(host))

    panel = await household.client.get(
        "/api/v1/panel/snapshot", headers=_panel_headers()
    )
    assert panel.status_code == 200
    settings = await _admin_settings(household)
    assert settings["timezone"] == ""
    assert panel.json()["timezone"] == settings["effective_timezone"] == host
    # The published zone reproduces the API's own household day.
    assert panel.json()["today_iso"] == "2026-09-27"
    assert (
        _utc(12, 30).astimezone(ZoneInfo(host)).date().isoformat()
        == panel.json()["today_iso"]
    )

    await _set_zone(household, "America/Chicago")
    panel = await household.client.get(
        "/api/v1/panel/snapshot", headers=_panel_headers()
    )
    settings = await _admin_settings(household)
    assert settings["timezone"] == "America/Chicago"
    assert panel.json()["timezone"] == settings["effective_timezone"]
    assert settings["effective_timezone"] == "America/Chicago"


# --- settings writes are serialised with planning and sweeping (TZ-003) ------
#
# A zone write racing the loop's own settings reads must never leave a
# stale plan behind.  Each test holds the loop at one of its reads and
# issues a locked zone write there; when the scheduler's settings lock
# is held at that point the write provably cannot commit until the
# loop moves on, otherwise it is awaited to commit inside the window.


def _hold_scheduler_read(monkeypatch, scheduler, nth: int, during):
    """Run ``during(settings)`` inside the scheduler task's ``nth`` read."""
    real_load = _settings_store.load_settings
    reads = {"count": 0}

    async def load_settings(database):
        settings = await real_load(database)
        if asyncio.current_task() is scheduler._task:
            reads["count"] += 1
            if reads["count"] == nth:
                await during(settings)
        return settings

    monkeypatch.setattr(
        scheduler_module.core_settings_store, "load_settings", load_settings
    )
    return real_load


async def _store_inside_read(scheduler, database, zone: str) -> asyncio.Task:
    """Start a locked write of ``zone``; let it commit unless serialised."""
    write = asyncio.create_task(_store_zone(scheduler, database, zone))
    if not scheduler.settings_lock.locked():
        await write
    return write


async def test_scheduler_follows_successive_zone_changes(
    temp_db_path: str, monkeypatch
) -> None:
    """New York -> UTC -> New York while the re-plan read is in flight."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner:
        app_state = runner.app.state
        database = app_state.db.database
        await app_state.sweep_scheduler.stop()
        delays: list[float] = []
        slept = asyncio.Condition()

        async def sleep_stub(seconds: float) -> None:
            async with slept:
                delays.append(seconds)
                slept.notify_all()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        app_state.sweep_scheduler = scheduler
        await _store_zone(scheduler, database, HOUSEHOLD_ZONE)
        writes: list[asyncio.Task] = []

        async def back_to_new_york(_settings) -> None:
            writes.append(
                await _store_inside_read(scheduler, database, HOUSEHOLD_ZONE)
            )

        # Read 1 plans New York; read 2 is the re-plan after UTC.
        _hold_scheduler_read(monkeypatch, scheduler, 2, back_to_new_york)
        scheduler.start()
        try:
            async with slept:
                await asyncio.wait_for(
                    slept.wait_for(lambda: len(delays) == 1), timeout=5
                )
            await _store_zone(scheduler, database, "UTC")
            async with slept:
                await asyncio.wait_for(
                    slept.wait_for(lambda: len(delays) == 3), timeout=5
                )
            (write,) = writes
            await write
        finally:
            await scheduler.stop()
    # The in-flight read planned UTC; the New York write that followed
    # it woke the wait, so the scheduler sleeps on New York midnight.
    assert delays == [
        pytest.approx(_NEW_YORK_MIDNIGHT_DELAY),
        pytest.approx(_UTC_MIDNIGHT_DELAY),
        pytest.approx(_NEW_YORK_MIDNIGHT_DELAY),
    ]


async def test_zone_write_after_presweep_check_cannot_precede_the_sweep(
    temp_db_path: str, monkeypatch
) -> None:
    """No sweep runs once a zone write has replaced its plan."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner:
        app_state = runner.app.state
        await app_state.sweep_scheduler.stop()
        delays: list[float] = []
        replanned = asyncio.Event()

        async def sleep_stub(seconds: float) -> None:
            delays.append(seconds)
            if len(delays) == 1:
                return  # the UTC rollover arrives
            replanned.set()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            app_state.db.database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        app_state.sweep_scheduler = scheduler
        writes: list[asyncio.Task] = []

        async def store_new_york(_settings) -> None:
            writes.append(
                await _store_inside_read(
                    scheduler, app_state.db.database, HOUSEHOLD_ZONE
                )
            )

        # Read 1 plans UTC; read 2 is the pre-sweep re-check.
        real_load = _hold_scheduler_read(
            monkeypatch, scheduler, 2, store_new_york
        )
        swept_under: list[str] = []

        async def sweep_stub(database, *, today):
            swept_under.append((await real_load(database)).timezone)
            return []

        monkeypatch.setattr(
            scheduler_module.core_sweep, "run_missed_sweep", sweep_stub
        )
        scheduler.start()
        try:
            await asyncio.wait_for(replanned.wait(), timeout=5)
            (write,) = writes
            await write
        finally:
            await scheduler.stop()
    # The sweep ran for the UTC plan with UTC still stored, never after
    # New York had been stored; the next plan is New York midnight.
    assert swept_under == [""]
    assert delays == [
        pytest.approx(_UTC_MIDNIGHT_DELAY),
        pytest.approx(_NEW_YORK_MIDNIGHT_DELAY),
    ]


# --- the wait's child tasks (TZ-004) ------------------------------------------


async def test_failed_sleep_is_retried_not_swept(
    temp_db_path: str, monkeypatch
) -> None:
    """A sleep that raises backs off and re-plans; nothing is swept."""
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        await _core_migrations.apply_migrations(database)
        sweeps: list[datetime.date] = []

        async def sweep_stub(_database, *, today):
            sweeps.append(today)
            return []

        monkeypatch.setattr(
            scheduler_module.core_sweep, "run_missed_sweep", sweep_stub
        )
        delays: list[float] = []
        replanned = asyncio.Event()

        async def sleep_stub(seconds: float) -> None:
            delays.append(seconds)
            if len(delays) == 1:
                raise RuntimeError("timer failed")
            if len(delays) == 2:
                return  # the retry backoff
            replanned.set()
            await asyncio.Event().wait()

        scheduler = MissedSweepScheduler(
            database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        scheduler.start()
        try:
            await asyncio.wait_for(replanned.wait(), timeout=5)
        finally:
            await scheduler.stop()
        assert sweeps == []
        assert delays == [
            pytest.approx(_UTC_MIDNIGHT_DELAY),
            scheduler_module._RETRY_BACKOFF_SECONDS,
            pytest.approx(_UTC_MIDNIGHT_DELAY),
        ]
    finally:
        await database.close()


async def test_stop_waits_for_the_sleep_to_finish_cancelling(
    temp_db_path: str,
) -> None:
    database = _core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        await _core_migrations.apply_migrations(database)
        sleeping = asyncio.Event()
        sleepers: list[asyncio.Task] = []
        cleaned_up: list[bool] = []

        async def sleep_stub(_seconds: float) -> None:
            sleepers.append(asyncio.current_task())
            sleeping.set()
            try:
                await asyncio.Event().wait()
            finally:
                # Cancellation cleanup that takes a loop turn.
                await asyncio.sleep(0)
                cleaned_up.append(True)

        scheduler = MissedSweepScheduler(
            database, clock=lambda: _utc(13, 0), sleep=sleep_stub
        )
        scheduler.start()
        try:
            await asyncio.wait_for(sleeping.wait(), timeout=5)
        finally:
            await scheduler.stop()
        (sleeper,) = sleepers
        assert sleeper.done()
        assert cleaned_up == [True]
    finally:
        await database.close()
