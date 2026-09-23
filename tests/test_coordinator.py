"""Tests for the shared NestQuest coordinator (Feature 10, Feature 18).

The coordinator now polls the API service's panel snapshot through the
API client (Feature 18) and reconstructs the core snapshot dataclasses
every entity reads.  The tests stub the client — NO network, NO aiohttp
— with a FIXTURE snapshot payload (the documented shape of the Feature
16 snapshot route, ``api/routes_panel.py``) and assert the
reconstruction: per-child counts and presence, the instance views
(``completed`` mapped back to ``done``), the household rollups, the
cycle day, and the unconfigured / failed-fetch behaviour.
"""
from __future__ import annotations

import datetime
import logging

import pytest

from conftest import set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry, async_unload_entry
from custom_components.nestquest.api_client import (
    NestQuestApiClient,
    NestQuestApiError,
)
from custom_components.nestquest.const import (
    CONF_SNAPSHOT_STALENESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.nestquest.coordinator import (
    NestQuestCoordinator,
    coordinator_client_from_entry,
    snapshot_from_api_payload,
)
from custom_components.nestquest.core.snapshot import instance_payload
from homeassistant.helpers.update_coordinator import UpdateFailed


def _today_iso() -> str:
    return datetime.date.today().isoformat()


class StubSnapshotClient:
    """A no-network stand-in for the API client's snapshot surface.

    Answers ``get_snapshot()`` from a scripted queue of outcomes — a
    payload dict or an exception per call, consumed in order — and
    records every call, so each test drives exactly one refresh.
    """

    def __init__(self, *outcomes) -> None:
        self.calls = 0
        self._outcomes = list(outcomes)
        self._last = outcomes[-1] if outcomes else None

    async def get_snapshot(self):
        self.calls += 1
        if not self._outcomes:
            # Re-serve the last outcome: setup's first refresh and the
            # test's explicit pass both poll the same scripted state.
            outcome = self._last
        else:
            outcome = self._outcomes.pop(0)
            self._last = outcome
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeMonotonic:
    """A deterministic stand-in for the staleness clock.

    The coordinator reads elapsed time through
    :func:`custom_components.nestquest.coordinator._monotonic`; tests
    patch that seam with an instance of this class and advance ``now``
    by whole seconds, so the staleness window is exercised without any
    real waiting.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


#: A fixture panel snapshot (the documented Feature 16 route shape):
#: two children — Ada owes one, owes none of it yet, is away today with
#: a returns date; Bo completed his only quest and is present.
FIXTURE_SNAPSHOT = {
    "today_iso": _today_iso(),
    "cycle_day": 3,
    "children": [
        {
            "child_id": 1,
            "child_name": "Ada",
            "present": False,
            "next_present": "2026-09-24",
            "due_today": 2,
            "completed_today": 1,
            "remaining_today": 1,
            "completion_pct": 50,
            "instances": [
                {
                    "id": 7,
                    "definition_id": 3,
                    "child_id": 1,
                    "title": "Brush teeth",
                    "icon": "🦷",
                    "window": "morning",
                    "due_time": "08:00",
                    "state": "completed",
                    "overdue": False,
                    "completed_at": f"{_today_iso()}T07:55:00+00:00",
                    "on_time": True,
                },
                {
                    "id": 8,
                    "definition_id": 3,
                    "child_id": 1,
                    "title": "Pack bag",
                    "icon": None,
                    "window": "morning",
                    "due_time": "10:00",
                    "state": "open",
                    "overdue": True,
                    "completed_at": None,
                    "on_time": None,
                },
            ],
        },
        {
            "child_id": 2,
            "child_name": "Bo",
            "present": True,
            "next_present": None,
            "due_today": 1,
            "completed_today": 1,
            "remaining_today": 0,
            "completion_pct": 100,
            "instances": [
                {
                    "id": 9,
                    "definition_id": 4,
                    "child_id": 2,
                    "title": "Make bed",
                    "icon": "🛏",
                    "window": "morning",
                    "due_time": "07:30",
                    "state": "completed",
                    "overdue": False,
                    "completed_at": f"{_today_iso()}T07:31:00+00:00",
                    "on_time": True,
                }
            ],
        },
    ],
}


async def _wire_entry(hass, make_entry, client, options=None):
    """Build an entry whose coordinator uses the scripted API client.

    The client is registered with the conftest override BEFORE setup:
    the first refresh at setup already polls the snapshot, so the
    platform setup sees real data and creates the whole entity set.
    """
    from conftest import set_coordinator_client

    entry = wire_entry_to_registry(
        make_entry(
            options=options,
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"},
        ),
        hass.registry,
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator.api_client is client
    return entry, coordinator


async def test_coordinator_builds_snapshot_from_fixture(hass, make_entry) -> None:
    """One refresh = one snapshot GET; the fixture's values land on the
    snapshot the entities read, per child and household-wide."""
    client = StubSnapshotClient(FIXTURE_SNAPSHOT)
    _entry, coordinator = await _wire_entry(hass, make_entry, client)
    calls_after_setup = client.calls
    snapshot = await coordinator._async_update_data()

    assert client.calls == calls_after_setup + 1
    assert snapshot.today_iso == _today_iso()
    assert snapshot.cycle_day == 3
    assert len(snapshot.children) == 2

    ada, bo = snapshot.children
    assert (ada.child_id, ada.child_name) == (1, "Ada")
    assert ada.due_today == 2
    assert ada.completed_today == 1
    assert ada.remaining_today == 1
    assert ada.completion_pct == 50
    assert ada.present is False
    assert ada.next_present == "2026-09-24"

    done_view, open_view = ada.instances
    assert done_view.instance_id == 7
    assert done_view.title == "Brush teeth"
    assert done_view.icon == "🦷"
    assert done_view.window == "morning"
    assert done_view.due_time == "08:00"
    assert done_view.due_date == _today_iso()
    # The API's "completed" maps back to the core view's "done".
    assert done_view.state == "done"
    assert done_view.overdue is False
    assert done_view.completed_at == f"{_today_iso()}T07:55:00+00:00"
    assert done_view.was_on_time is True

    assert open_view.state == "open"
    assert open_view.overdue is True
    assert open_view.completed_at is None
    assert open_view.was_on_time is None

    assert (bo.child_id, bo.child_name) == (2, "Bo")
    assert bo.due_today == 1
    assert bo.completed_today == 1
    assert bo.remaining_today == 0
    assert bo.completion_pct == 100
    assert bo.present is True
    assert bo.next_present is None

    # Household rollups: the sums the household sensors compute.
    assert sum(child.due_today for child in snapshot.children) == 3
    assert sum(child.completed_today for child in snapshot.children) == 2
    assert sum(child.remaining_today for child in snapshot.children) == 1


async def test_coordinator_refresh_publishes_to_listeners(hass, make_entry) -> None:
    """The refresh pass notifies listeners and reports success — the
    ONE refresh pass every entity reads from."""
    client = StubSnapshotClient(FIXTURE_SNAPSHOT)
    _entry, coordinator = await _wire_entry(hass, make_entry, client)
    called = []
    coordinator.async_add_listener(lambda: called.append("entity"))
    await coordinator.async_refresh()
    assert called == ["entity"]
    assert coordinator.last_update_success is True
    assert coordinator.data is not None
    assert coordinator.data.children[0].child_name == "Ada"


async def test_instance_payload_shape_is_unchanged(hass, make_entry) -> None:
    """The per-child instance attribute payload the due-today sensor
    emits keeps its exact documented shape, and admin_instances now
    equals instances (the API omits missed rows — D-009; the admin
    surface for missed quests is the PWA)."""
    client = StubSnapshotClient(FIXTURE_SNAPSHOT)
    _entry, coordinator = await _wire_entry(hass, make_entry, client)
    snapshot = await coordinator._async_update_data()
    ada = snapshot.children[0]

    panel = instance_payload(ada.instances, include_missed=False)
    assert panel == [
        {
            "id": 7,
            "definition_id": 3,
            "child_id": 1,
            "title": "Brush teeth",
            "icon": "🦷",
            "window": "morning",
            "due_time": "08:00",
            "state": "completed",
            "overdue": False,
            "completed_at": f"{_today_iso()}T07:55:00+00:00",
            "on_time": True,
        },
        {
            "id": 8,
            "definition_id": 3,
            "child_id": 1,
            "title": "Pack bag",
            "icon": None,
            "window": "morning",
            "due_time": "10:00",
            "state": "open",
            "overdue": True,
            "completed_at": None,
            "on_time": None,
        },
    ]
    # The API payload omits missed rows, so include_missed cannot
    # re-add them: admin_instances == instances, byte for byte.
    assert instance_payload(ada.instances, include_missed=True) == panel


async def test_coordinator_entities_read_the_api_snapshot(hass, make_entry) -> None:
    """The registered sensors and binary sensors read the rebuilt
    snapshot: entity values come from the fixture, with the SAME
    entity_ids as ever."""
    client = StubSnapshotClient(FIXTURE_SNAPSHOT)
    entry, coordinator = await _wire_entry(hass, make_entry, client)
    await coordinator.async_refresh()

    ada_due = hass.entities[f"{DOMAIN}_child_1_quests_due_today"]
    assert ada_due.native_value == 2
    attributes = ada_due.extra_state_attributes
    assert attributes["child_id"] == 1
    assert attributes["child_name"] == "Ada"
    assert attributes["present"] is False
    assert [row["id"] for row in attributes["instances"]] == [7, 8]

    assert (
        hass.entities[f"{DOMAIN}_child_1_quests_completed_today"].native_value
        == 1
    )
    assert (
        hass.entities[f"{DOMAIN}_child_1_quests_remaining_today"].native_value
        == 1
    )
    assert (
        hass.entities[f"{DOMAIN}_child_1_completion_pct_today"].native_value
        == 50
    )
    assert hass.entities[f"{DOMAIN}_child_1_next_quest"].native_value == (
        "Pack bag"
    )
    # Ada owes one still: not all done; away today.
    assert hass.entities[f"{DOMAIN}_child_1_all_done"].is_on is False
    assert hass.entities[f"{DOMAIN}_child_1_present_today"].is_on is False

    assert (
        hass.entities[f"{DOMAIN}_child_2_completion_pct_today"].native_value
        == 100
    )
    # Bo had a quest and owes none of it: all done, present today.
    assert hass.entities[f"{DOMAIN}_child_2_all_done"].is_on is True
    assert hass.entities[f"{DOMAIN}_child_2_present_today"].is_on is True
    bo_attributes = hass.entities[
        f"{DOMAIN}_child_2_present_today"
    ].extra_state_attributes
    assert bo_attributes["next_present"] is None

    assert (
        hass.entities[f"{DOMAIN}_household_quests_due_today"].native_value == 3
    )
    assert (
        hass.entities[f"{DOMAIN}_household_quests_completed_today"].native_value
        == 2
    )
    cycle = hass.entities[f"{DOMAIN}_cycle_day"]
    assert cycle.native_value == 3
    assert cycle.extra_state_attributes == {
        "cycle_day": 3,
        "today": _today_iso(),
    }

    await async_unload_entry(hass, entry)


async def test_coordinator_failed_fetch_marks_unavailable(
    hass, make_entry, monkeypatch
) -> None:
    """A failed fetch (transport failure or non-2xx — both typed) PAST
    the staleness threshold is a FAILED refresh pass: the update pass
    converts the typed error to UpdateFailed (the exception HA's
    coordinator machinery records as a failed pass, chaining the typed
    error as ``__cause__``), the refresh records the failure instead of
    raising, and data keeps its last good value.  (Within the threshold
    the last-good cache serves instead — the staleness tests below.)"""
    import custom_components.nestquest.coordinator as coordinator_module

    clock = FakeMonotonic()
    monkeypatch.setattr(coordinator_module, "_monotonic", clock)
    error = NestQuestApiError(
        "NestQuest API GET /api/v1/panel/snapshot failed with HTTP 503",
        status=503,
    )
    # The stub serves the good snapshot for setup's first refresh, then
    # the scripted failure.
    client = StubSnapshotClient(FIXTURE_SNAPSHOT, error)
    _entry, coordinator = await _wire_entry(hass, make_entry, client)
    # First refresh (at setup) served the good snapshot.
    assert coordinator.data is not None
    assert coordinator.last_update_success is True

    # The next pass hits the scripted failure AFTER the cache went
    # stale — one second past the shipped 900 s default threshold: the
    # update pass converts the typed error to UpdateFailed, with the
    # typed error chained.
    clock.now += DEFAULT_SNAPSHOT_STALENESS + 1
    with pytest.raises(UpdateFailed, match="HTTP 503") as excinfo:
        await coordinator._async_update_data()
    assert isinstance(excinfo.value.__cause__, NestQuestApiError)

    # The refresh pass records the failure the HA way — it does NOT
    # raise: last_update_success goes False, data keeps the last GOOD
    # snapshot, and the failed pass lands on last_exception as the
    # converted UpdateFailed with the typed error chained.
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert coordinator.data.children[0].child_name == "Ada"
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert isinstance(coordinator.last_exception.__cause__, NestQuestApiError)


async def test_coordinator_serves_cached_snapshot_within_staleness(
    hass, make_entry, monkeypatch, caplog
) -> None:
    """API down WITHIN the staleness threshold: the failed fetch serves
    the last-good cache — the pass succeeds with the SAME snapshot, so
    ``last_update_success`` stays True (entities remain available) and
    the outage is logged as a clear warning, never silently."""
    import custom_components.nestquest.coordinator as coordinator_module

    clock = FakeMonotonic()
    monkeypatch.setattr(coordinator_module, "_monotonic", clock)
    error = NestQuestApiError(
        "NestQuest API GET /api/v1/panel/snapshot failed with HTTP 503",
        status=503,
    )
    # Setup's first refresh consumes the good snapshot; the two test
    # passes hit the scripted failure.
    client = StubSnapshotClient(FIXTURE_SNAPSHOT, error, error)
    _entry, coordinator = await _wire_entry(
        hass,
        make_entry,
        client,
        options={CONF_UPDATE_INTERVAL: 300, CONF_SNAPSHOT_STALENESS: 900},
    )
    # The successful first pass cached the snapshot (stamped at the
    # fake clock's start).
    first = coordinator.data
    assert first is not None
    assert coordinator.last_update_success is True

    # The API goes down 900 s after that success — exactly the
    # threshold, still WITHIN the inclusive window: the pass serves the
    # cached snapshot instead of failing.
    clock.now += 900
    with caplog.at_level(
        logging.WARNING, logger="custom_components.nestquest"
    ):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data is first
    assert coordinator.data.children[0].child_name == "Ada"
    # The fetch WAS attempted (and failed) — the cache is a fallback,
    # not a replacement for polling.
    assert client.calls == 2
    assert any(
        "last-good" in record.getMessage() for record in caplog.records
    )


async def test_coordinator_recovers_without_reload_after_outage(
    hass, make_entry, monkeypatch
) -> None:
    """The full outage arc: within the threshold the cache serves, past
    it the entities go unavailable, and when the API comes back the
    next pass succeeds with the FRESH snapshot, re-arms the cache, and
    the entities recover — without any config-entry reload."""
    import custom_components.nestquest.coordinator as coordinator_module

    clock = FakeMonotonic()
    monkeypatch.setattr(coordinator_module, "_monotonic", clock)
    outage = NestQuestApiError(
        "NestQuest API GET /api/v1/panel/snapshot failed with HTTP 503",
        status=503,
    )
    post_recovery_outage = NestQuestApiError(
        "NestQuest API GET /api/v1/panel/snapshot failed with HTTP 502",
        status=502,
    )
    fresh = {**FIXTURE_SNAPSHOT, "cycle_day": 4}
    client = StubSnapshotClient(
        FIXTURE_SNAPSHOT, outage, outage, fresh, post_recovery_outage
    )
    _entry, coordinator = await _wire_entry(
        hass,
        make_entry,
        client,
        options={CONF_UPDATE_INTERVAL: 300, CONF_SNAPSHOT_STALENESS: 900},
    )
    first = coordinator.data
    assert first.cycle_day == 3

    # Within the threshold: the outage serves the cache.
    clock.now += 300
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data is first

    # Past the threshold: the outage fails the pass (unavailable).
    clock.now += 901
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    # The API returns: the next pass succeeds with the fresh snapshot
    # and no reload was involved anywhere.
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    fresh_data = coordinator.data
    assert fresh_data.cycle_day == 4
    assert hass.registry.reloaded == []

    # The success re-armed the cache with the FRESH stamp: another
    # outage within the threshold serves the new snapshot now, not the
    # pre-outage one.
    clock.now += 300
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data is fresh_data
    assert client.calls == 5


async def test_setup_creates_coordinator_with_configured_staleness(
    hass, make_entry
) -> None:
    """The staleness threshold rides the entry options into the
    coordinator, alongside the update interval."""
    entry = wire_entry_to_registry(
        make_entry(
            options={CONF_UPDATE_INTERVAL: 60, CONF_SNAPSHOT_STALENESS: 600}
        ),
        hass.registry,
    )
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator._staleness_seconds == 600


async def test_setup_staleness_below_interval_falls_back_to_default(
    hass, make_entry
) -> None:
    """A stored threshold below the update interval (a raw hand-edited
    option) never reaches the coordinator as-is: it falls back to the
    shipped default, which still spans the configured interval."""
    entry = wire_entry_to_registry(
        make_entry(
            options={CONF_UPDATE_INTERVAL: 600, CONF_SNAPSHOT_STALENESS: 60}
        ),
        hass.registry,
    )
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator._staleness_seconds == DEFAULT_SNAPSHOT_STALENESS


async def test_coordinator_staleness_floor_never_below_interval(hass) -> None:
    """A threshold below the interval falls back to whichever of
    default/interval is larger, so the cache can always span at least
    one failed poll (here the interval exceeds the shipped default)."""
    coordinator = NestQuestCoordinator(
        hass,
        entry_id="floor",
        api_client=StubSnapshotClient(),
        update_interval_seconds=1800,
        staleness_seconds=60,
    )
    assert coordinator._staleness_seconds == 1800


async def test_failed_first_refresh_does_not_crash_setup(
    hass, make_entry
) -> None:
    """A failed fetch at the FIRST refresh (at setup) does not crash
    setup: the coordinator reports last_update_success=False, the setup
    catches the ConfigEntryNotReady that HA's real first refresh raises
    for a failed pass, and the platforms still forward so the entities
    come up unavailable."""
    # The stub fails every snapshot fetch (HTTP 503), including setup's
    # first refresh.
    client = StubSnapshotClient(
        NestQuestApiError(
            "NestQuest API GET /api/v1/panel/snapshot failed with HTTP 503",
            status=503,
        )
    )
    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator.api_client is client
    # The failed first pass: the entities' surface stays unavailable.
    assert coordinator.last_update_success is False
    assert coordinator.data is None
    # Setup survived the failed first refresh — the platforms were
    # forwarded (the regression the review caught: a first-refresh
    # failure used to abort setup before any entity was created).
    assert hass.config_entries.forwarded_platforms == [
        "sensor",
        "binary_sensor",
    ]
    # The unload after the failed-first-refresh setup stays clean.
    assert await async_unload_entry(hass, entry) is True


async def test_coordinator_unconfigured_api_does_not_crash_setup(
    hass, make_entry, monkeypatch
) -> None:
    """An entry with no panel token set up fine: the coordinator gets
    the typed-error stub, the first refresh fails cleanly (unavailable
    entities), and setup does NOT crash."""
    # Restore the production factory: the conftest default would serve
    # the local snapshot, but this test exercises the token guard.
    import custom_components.nestquest as nq

    monkeypatch.setattr(
        nq, "coordinator_client_from_entry", coordinator_client_from_entry
    )
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    from custom_components.nestquest.coordinator import _UnconfiguredApiClient

    assert isinstance(coordinator.api_client, _UnconfiguredApiClient)
    # A real NestQuestApiClient was never built (it would ValueError).
    assert not isinstance(coordinator.api_client, NestQuestApiClient)
    # The first refresh failed the HA way: the update pass converted
    # the stub's typed error to UpdateFailed, the first refresh raised
    # ConfigEntryNotReady, and setup tolerated it — platforms forwarded
    # so the entities come up unavailable.
    assert coordinator.last_update_success is False
    assert coordinator.data is None
    with pytest.raises(UpdateFailed, match="not configured"):
        await coordinator._async_update_data()
    assert hass.config_entries.forwarded_platforms == [
        "sensor",
        "binary_sensor",
    ]
    assert await async_unload_entry(hass, entry) is True


async def test_coordinator_configured_token_builds_real_client(
    hass, make_entry
) -> None:
    """An entry WITH a panel token builds the real client through the
    production factory (a stub transport injected via session_factory,
    the mock-only harness having no aiohttp module to hand in), and the
    coordinator's refresh polls the snapshot route end to end."""
    import json as json_module

    class _OneShotSession:
        """A session-shaped stub answering every request with the fixture."""

        def __init__(self, payload) -> None:
            self._body = json_module.dumps(payload)

        def request(self, method, url, **kwargs):
            body = self._body

            class _Response:
                def __init__(self) -> None:
                    self.status = 200

                async def text(self):
                    return body

            class _Context:
                async def __aenter__(self):
                    return _Response()

                async def __aexit__(self, *exc):
                    return False

            return _Context()

    def _session_factory(_hass):
        return _OneShotSession(FIXTURE_SNAPSHOT)

    entry = wire_entry_to_registry(
        make_entry(
            data={"api_base_url": "http://api.test:8000", "panel_token": "tok"}
        ),
        hass.registry,
    )
    real_client = coordinator_client_from_entry(
        hass, entry, session_factory=_session_factory
    )
    assert isinstance(real_client, NestQuestApiClient)

    set_coordinator_client(entry, real_client)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert isinstance(coordinator.api_client, NestQuestApiClient)
    # The real client polls the stub transport; the snapshot lands.
    await coordinator.async_refresh()
    assert coordinator.data.children[0].child_name == "Ada"


async def test_setup_creates_coordinator_with_configured_interval(
    hass, make_entry
) -> None:
    entry = wire_entry_to_registry(
        make_entry(options={CONF_UPDATE_INTERVAL: 60}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert isinstance(coordinator, NestQuestCoordinator)
    assert coordinator.update_interval == datetime.timedelta(seconds=60)


async def test_setup_defaults_to_five_minute_interval(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    assert coordinator.update_interval == datetime.timedelta(
        seconds=DEFAULT_UPDATE_INTERVAL
    )


async def test_unload_shuts_coordinator_down(hass, make_entry) -> None:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data.coordinator
    torn_down = []

    async def _shutdown():
        torn_down.append(coordinator)

    coordinator.async_shutdown = _shutdown
    assert await async_unload_entry(hass, entry) is True
    assert torn_down == [coordinator]


async def test_setup_failure_after_registration_shuts_coordinator_down(
    hass, make_entry, monkeypatch
) -> None:
    """A setup failure after coordinator creation must not leak its
    listeners or leave a stale runtime record behind.

    The runtime record registers in ``hass.data`` BEFORE the platform
    forward, so a forward failure reaches the unwind with the record
    already registered.  The unwind must shut the coordinator down,
    clear ``entry.runtime_data``, AND remove the stale ``hass.data``
    entry — otherwise a later unload picks up the stale, already-torn-
    down record and re-invokes the already-consumed update-listener
    remover, which raises.  (A failed first refresh is NOT such a
    failure: HA's real first refresh wraps it in ConfigEntryNotReady,
    which setup deliberately tolerates so entities come up
    unavailable.)
    """
    from custom_components.nestquest import async_setup_entry
    import custom_components.nestquest.coordinator as coordinator_module

    shutdown_calls = []

    async def _record_shutdown(self):
        shutdown_calls.append(self.entry_id)

    monkeypatch.setattr(
        coordinator_module.NestQuestCoordinator,
        "async_shutdown",
        _record_shutdown,
    )

    async def _boom(entry, platforms):
        raise RuntimeError("platform forward failed")

    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        _boom,
    )

    entry = wire_entry_to_registry(make_entry(), hass.registry)
    with pytest.raises(RuntimeError, match="platform forward failed"):
        await async_setup_entry(hass, entry)
    assert shutdown_calls == [entry.entry_id]
    assert getattr(entry, "runtime_data", None) is None
    # The stale hass.data registration was removed with the runtime
    # record: the unload below finds nothing stale, must not raise,
    # and must leave no residue behind.
    assert await async_unload_entry(hass, entry) is True
    assert DOMAIN not in hass.data
    assert hass.data == {}
    assert hass.registry.size == 0
    assert hass.time_change.size == 0
    assert entry.runtime_data is None


async def test_snapshot_from_api_payload_empty_household() -> None:
    """An empty household (no children) is a valid snapshot: empty
    children tuple, cycle day passes through."""
    snapshot = snapshot_from_api_payload(
        {"today_iso": "2026-09-23", "cycle_day": 0, "children": []}
    )
    assert snapshot.children == ()
    assert snapshot.cycle_day == 0
    assert snapshot.today_iso == "2026-09-23"
