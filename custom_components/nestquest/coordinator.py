"""The shared NestQuest DataUpdateCoordinator (Feature 10, Feature 18).

ONE refresh pass builds the whole entity snapshot: active children,
today's instances with their derived states (open / done / missed via
:func:`~.completion.derive_state`), each child's presence today, and
per-child rollup counts.  Every Feature 10 entity reads
``coordinator.data`` — no entity queries the database itself, so one
refresh updates the whole board coherently.

Since Feature 18 the snapshot no longer comes from the local database:
the coordinator polls the NestQuest API service's panel plane —
``GET /api/v1/panel/snapshot`` through
:class:`~.api_client.NestQuestApiClient` on its update interval — and
RECONSTRUCTS the same core dataclasses the local builder produced
(:class:`~.core.snapshot.NestQuestSnapshot`,
:class:`~.core.snapshot.ChildDaySnapshot`,
:class:`~.core.snapshot.QuestInstanceView`).  ``sensor.py`` and
``binary_sensor.py`` read ``coordinator.data`` and
:func:`~.core.snapshot.instance_payload` exactly as before, so every
entity_id and attribute payload shape is unchanged: the panel cards and
the four blueprints keep working untouched.

One loss is deliberate and documented (D-009 revisited): the panel
payload OMITS missed instances, so a snapshot rebuilt from the API can
no longer carry them — ``admin_instances`` (``include_missed=True``)
now equals ``instances`` (they can hold only open and completed rows).
The admin surface for missed quests is the PWA, which reads the API
service directly; the integration's entities never needed missed rows
for their states or counts (the counts arrive precomputed).

Failure handling: constructing the client fails fast (ValueError) when
the entry has no panel token configured, and a fetch failure raises the
typed :class:`~.api_client.NestQuestApiError`.  Neither crashes
integration setup: the constructor logs a clear message and hands back
a client-shaped stub whose refresh raises the same typed error, and
``_async_update_data`` converts every typed error into
:class:`~homeassistant.helpers.update_coordinator.UpdateFailed` — the
exception a HA ``DataUpdateCoordinator`` records as a failed pass
(``last_update_success = False``, ``data = None``), so the entities
come up unavailable.  The typed error is never swallowed silently: it
is logged with its message and chained into the UpdateFailed.  (The
conversion matters at setup: HA's real
``async_config_entry_first_refresh`` wraps any failed pass in
``ConfigEntryNotReady``, so a setup that keys on the original
exception type would never match it.)

Last-good cache and staleness: every successful pass refreshes a cache
of the rebuilt snapshot stamped with the :func:`time.monotonic`
instant of the success.  A typed failure is checked against that stamp
BEFORE the pass is declared failed: within the configured staleness
threshold (``CONF_SNAPSHOT_STALENESS``, seconds, default three update
intervals) the pass SUCCEEDS with the cached snapshot — the panel
keeps rendering last-good data and the entities stay available — and
the outage is logged as a warning.  Entities go unavailable only once
the cache is older than the threshold (or before the first success);
a later successful fetch refreshes the cache and the entities recover
on their own, without a config-entry reload.
"""
from __future__ import annotations

import asyncio
import datetime
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import NestQuestApiClient, NestQuestApiError, resolve_api_config
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL,
)
from .core.snapshot import (
    ChildDaySnapshot,
    NestQuestSnapshot,
    QuestInstanceView,
)

__all__ = [
    "ChildDaySnapshot",
    "NestQuestCoordinator",
    "NestQuestSnapshot",
    "QuestInstanceView",
]


def snapshot_from_api_payload(payload: dict[str, Any]) -> NestQuestSnapshot:
    """Reconstruct the core snapshot dataclasses from the API's JSON.

    The panel snapshot route (``api/routes_panel.py``) returns today's
    household as plain JSON — ``today_iso``, ``cycle_day``, and the
    per-child list with precomputed counts and the instances in the
    documented payload shape.  This function maps that shape BACK onto
    the dataclasses ``sensor.py`` / ``binary_sensor.py`` read, field by
    field:

    - the API's ``state`` ``"completed"`` maps back to the core view's
      ``"done"`` (so :func:`~.core.snapshot.instance_payload` renders
      ``"completed"`` again — the round-trip is identity for open and
      completed rows);
    - ``overdue``, ``on_time`` (→ ``was_on_time``), ``completed_at``,
      ``window``, ``due_time``, ``icon`` and the per-child counts pass
      through verbatim;
    - ``present`` and ``next_present`` pass through verbatim (the API
      resolved them through the same presence engine server-side);
    - the instance list is rebuilt IN ORDER, so the panel payload the
      sensors emit matches the route's order byte for byte.

    Because the route omits missed instances (D-009), a snapshot built
    here cannot contain any ``missed`` view — see the module docstring.
    """
    children: list[ChildDaySnapshot] = []
    for child in payload.get("children", []):
        views = tuple(
            QuestInstanceView(
                instance_id=instance["id"],
                definition_id=instance["definition_id"],
                child_id=instance["child_id"],
                title=instance["title"],
                icon=instance.get("icon"),
                window=instance["window"],
                # The API payload does not carry due_date: every row
                # is TODAY's instance (the route queries
                # [today, today]), so the view's due_date is the
                # snapshot's today_iso — the same value the local
                # builder stamped on every today row.
                due_date=payload["today_iso"],
                due_time=instance.get("due_time"),
                state=(
                    "done" if instance["state"] == "completed" else
                    instance["state"]
                ),
                overdue=instance["overdue"],
                completed_at=instance.get("completed_at"),
                was_on_time=instance.get("on_time"),
            )
            for instance in child.get("instances", [])
        )
        children.append(
            ChildDaySnapshot(
                child_id=child["child_id"],
                child_name=child["child_name"],
                instances=views,
                present=child["present"],
                due_today=child["due_today"],
                completed_today=child["completed_today"],
                remaining_today=child["remaining_today"],
                completion_pct=child["completion_pct"],
                next_present=child.get("next_present"),
            )
        )
    return NestQuestSnapshot(
        today_iso=payload["today_iso"],
        children=tuple(children),
        cycle_day=payload["cycle_day"],
    )


class _UnconfiguredApiClient:
    """Client-shaped stand-in used when the entry has no panel token.

    Constructing a real :class:`~.api_client.NestQuestApiClient` with an
    empty token raises ValueError by design (fail fast on a client that
    could only ever 401).  An entry that simply has not been configured
    yet must not crash integration setup, so the coordinator swaps in
    this stub: every refresh raises the SAME typed
    :class:`~.api_client.NestQuestApiError` a transport failure would,
    carrying a clear "API not configured" message;
    :meth:`NestQuestCoordinator._async_update_data` converts it to
    :class:`~homeassistant.helpers.update_coordinator.UpdateFailed`, so
    the coordinator marks the entities unavailable and the HA standard
    retry cycle applies.  The error is logged, never silent.
    """

    __slots__ = ()

    async def get_snapshot(self) -> dict[str, Any]:
        """Always raise: there is no configured API to fetch from."""
        raise NestQuestApiError(
            "NestQuest API not configured: set the panel token in the "
            "integration options"
        )


def _monotonic() -> float:
    """The monotonic clock the staleness math reads.

    A one-line indirection over :func:`time.monotonic` so the staleness
    tests can drive the clock deterministically (patch THIS function,
    never the stdlib clock).  Monotonic is deliberate: wall-clock jumps
    (NTP corrections, suspends) must not shorten or extend the window.
    """
    return time.monotonic()


class NestQuestCoordinator(DataUpdateCoordinator):
    """Shared refresh cycle for every NestQuest entity.

    One refresh pass = one ``GET /api/v1/panel/snapshot`` through the
    API client, reconstructed into the core snapshot dataclasses every
    entity reads.  A failed pass (unconfigured API, transport failure,
    non-2xx response) raises the typed error out of the client;
    ``_async_update_data`` converts it to
    :class:`~homeassistant.helpers.update_coordinator.UpdateFailed`, the
    exception HA's coordinator machinery records as a failed pass: the
    coordinator's ``data`` keeps its last good value while
    ``last_update_success`` goes False — HA marks the entities
    unavailable until a later pass succeeds.  An unexpected
    non-typed error still propagates out of ``_async_update_data``
    and is logged (with its traceback) by HA's machinery, the same way.

    Forced refreshes (the service paths pushing an immediate update
    after a completion) are SERIALIZED per entry: overlapping
    complete/uncomplete calls must not interleave their snapshot
    passes, or an older pass could publish a stale snapshot AFTER a
    newer one and leave entities wrong until the next poll.  Real
    HA's coordinator already serializes internally; the lock keeps
    the same guarantee on the stand-in and costs nothing upstream.

    Last-good cache: a successful pass stamps the rebuilt snapshot
    with the :func:`~.coordinator._monotonic` instant of the success;
    a typed failure within the configured staleness threshold
    (``staleness_seconds``, from ``CONF_SNAPSHOT_STALENESS``) serves
    that cached snapshot instead of failing the pass, so a short API
    outage keeps the board up.  Past the threshold — or before the
    first success — the pass fails as above, and a later successful
    pass refreshes the cache and recovers the entities on its own.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        api_client: NestQuestApiClient,
        update_interval_seconds: int | None = None,
        staleness_seconds: int | None = None,
    ) -> None:
        interval = update_interval_seconds
        if (
            not isinstance(interval, int)
            or isinstance(interval, bool)
            or interval < MIN_UPDATE_INTERVAL
        ):
            interval = DEFAULT_UPDATE_INTERVAL
        staleness = staleness_seconds
        if (
            not isinstance(staleness, int)
            or isinstance(staleness, bool)
            or staleness < interval
        ):
            # A missing or nonsensical threshold falls back to the
            # shipped default; a configured-but-too-short one (below
            # even one poll interval) falls back to whichever of
            # default/interval spans at least one failed poll, so the
            # cache is never dead on arrival.  (The options flow
            # validates the same rule at the form.)
            staleness = max(DEFAULT_SNAPSHOT_STALENESS, interval)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=interval),
        )
        self.entry_id = entry_id
        self.api_client = api_client
        self._refresh_lock = asyncio.Lock()
        #: The configured last-good window, in SECONDS (const.py:
        #: CONF_SNAPSHOT_STALENESS / DEFAULT_SNAPSHOT_STALENESS).
        self._staleness_seconds = staleness
        #: The last-good cache: the snapshot from the most recent
        #: SUCCESSFUL fetch and the :func:`time.monotonic` instant it
        #: landed.  Both stay None until the first success.
        self._last_good_snapshot: NestQuestSnapshot | None = None
        self._last_good_monotonic: float | None = None

    async def async_refresh(self) -> None:
        """One refresh at a time; a queued refresh runs AFTER the
        in-flight one publishes, so the last snapshot always reflects
        the latest mutation."""
        async with self._refresh_lock:
            await super().async_refresh()

    async def _async_update_data(self) -> NestQuestSnapshot:
        """One refresh pass: fetch the panel snapshot and rebuild it.

        A successful pass rebuilds the snapshot and refreshes the
        last-good cache (the snapshot plus the
        :func:`time.monotonic` instant of the success).

        A typed API failure (unconfigured token stub, transport
        failure, non-2xx response) is first checked against that
        stamp: WITHIN the configured staleness threshold (elapsed time
        since the last successful fetch, inclusive of the threshold
        itself) the pass SUCCEEDS with the cached snapshot — the panel
        keeps rendering last-good data, the entities stay available —
        and the outage is logged as a clear warning (never silent).
        With no cache yet, or past the threshold, the typed error is
        converted to
        :class:`~homeassistant.helpers.update_coordinator.UpdateFailed`
        — the exception HA's coordinator machinery records as a failed
        pass (``last_update_success = False``, ``data`` unchanged) so
        entities go unavailable and the setup-time first refresh
        arrives as ``ConfigEntryNotReady`` — with the typed error
        logged and chained.  Anything else still propagates.
        """
        try:
            payload = await self.api_client.get_snapshot()
        except NestQuestApiError as err:
            now = _monotonic()
            cached = self._last_good_snapshot
            fetched_at = self._last_good_monotonic
            if (
                cached is not None
                and fetched_at is not None
                and now - fetched_at <= self._staleness_seconds
            ):
                LOGGER.warning(
                    "NestQuest API refresh failed (%s); serving the "
                    "last-good snapshot fetched %.0f s ago, within the "
                    "%d s staleness threshold",
                    err,
                    now - fetched_at,
                    self._staleness_seconds,
                )
                return cached
            LOGGER.error(
                "NestQuest coordinator refresh failed: %s", err
            )
            raise UpdateFailed(str(err)) from err
        snapshot = snapshot_from_api_payload(payload)
        self._last_good_snapshot = snapshot
        self._last_good_monotonic = _monotonic()
        return snapshot


def coordinator_client_from_entry(
    hass: HomeAssistant, entry: Any, *, session_factory: Any = None
) -> Any:
    """Build the refresh client for a config entry, tolerating no token.

    Reads ``(base_url, panel_token)`` off the entry and constructs the
    real client.  An entry with no panel token configured (the shipped
    default is the empty string) makes the constructor raise ValueError
    by design; integration setup must not crash on an unconfigured
    entry, so this factory swaps in the typed-error stub instead and
    logs ONE clear message.  The ValueError itself is never re-raised
    past this point — it is converted, with the reason logged.

    ``session_factory`` overrides where the HTTP session comes from
    (production: HA's shared aiohttp session via
    :func:`~.api_client.client_from_entry`); it exists so tests can
    inject a stub transport without importing aiohttp — the mock-only
    test harness has no ``homeassistant.helpers.aiohttp_client``.
    """
    base_url, panel_token = resolve_api_config(entry)
    if not isinstance(panel_token, str) or not panel_token.strip():
        LOGGER.warning(
            "NestQuest API panel token is not configured for entry %s: "
            "entities will stay unavailable until a token is set in the "
            "integration options",
            entry.entry_id,
        )
        return _UnconfiguredApiClient()
    if session_factory is not None:
        return NestQuestApiClient(
            base_url, panel_token, session_factory(hass)
        )
    from custom_components.nestquest.api_client import client_from_entry

    return client_from_entry(hass, entry)


#: Test seam: entry_id → client, consulted by the conftest's client
#: factory BEFORE the production path.  Always empty in production
#: (nothing in the integration writes to it); tests register scripted
#: clients through it and clear it between tests.
_COORDINATOR_CLIENT_OVERRIDES: dict[str, Any] = {}
