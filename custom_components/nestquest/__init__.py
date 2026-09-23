"""The NestQuest integration (Feature 18: a thin client of the NestQuest API service).

The integration owns NO database: the API service (Feature 16) owns the
SQLite file, the migrations, and every business rule.  Setup builds the
entry's ONE shared API client, the coordinator that polls the panel
snapshot through it, and the SSE subscription that re-fires the API's
transition frames on the HA bus, registers the single
``nestquest.complete_quest`` proxy service, and forwards the sensor and
binary_sensor platforms.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_SNAPSHOT_STALENESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SNAPSHOT_STALENESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
)
from .coordinator import NestQuestCoordinator, coordinator_client_from_entry
from .frontend import async_register_frontend
from .services import async_deregister_services, async_register_services
from .sse import NestQuestEventStream

_LOGGER = LOGGER


@dataclass
class NestQuestRuntimeData:
    """Runtime data stored on a NestQuest config entry."""

    entry_id: str
    remove_update_listener: Callable[[], Any]
    coordinator: Any = None
    event_stream: NestQuestEventStream | None = None


def _find_live_runtime_data(hass: HomeAssistant) -> NestQuestRuntimeData | None:
    """Return a live runtime record with a coordinator, or None.

    The domain-global service (the panel completion proxy) has no
    database of its own; it resolves whichever config entry's runtime
    data is currently live at call time, so it cannot hold a stale
    handle to an unloaded entry's coordinator.
    """
    for runtime_data in hass.data.get(DOMAIN, {}).values():
        if getattr(runtime_data, "coordinator", None) is not None:
            return runtime_data
    return None


def _register_services(hass: HomeAssistant) -> None:
    """Register the domain-global NestQuest service once.

    The service is DOMAIN-global — registered exactly once (guarded by
    ``has_service``) and NOT bound to any config entry — so the panel
    completion proxy resolves the currently-live runtime at call time
    and a name collision or duplicate setup is impossible.  Removal is
    handled by the unload path only once the LAST entry is removed
    (see :func:`_deregister_services`).
    """
    async_register_services(hass, find_runtime=_find_live_runtime_data)


def _deregister_services(hass: HomeAssistant) -> None:
    """Remove domain-global NestQuest services when the last entry unloads."""
    async_deregister_services(hass)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the NestQuest integration. YAML configuration is not used, returns True."""
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NestQuest from a config entry."""
    await async_register_frontend(hass)
    hass.data.setdefault(DOMAIN, {})

    async def _async_update_listener(
        listener_hass: HomeAssistant, listener_entry: ConfigEntry
    ) -> None:
        """Reload the entry when its options change."""
        await listener_hass.config_entries.async_reload(listener_entry.entry_id)

    remove_update_listener: Callable[[], Any] | None = None
    coordinator: Any = None
    event_stream: NestQuestEventStream | None = None
    try:
        remove_update_listener = entry.add_update_listener(_async_update_listener)
        _register_services(hass)
        # ONE API client for the entry, shared by the coordinator's
        # snapshot polling, the SSE subscription, and the completion
        # proxy (the client is stateless — one session, one connection
        # pool).  An entry with no panel token yet gets the
        # typed-error stub (unavailable entities, never a setup crash).
        api_client = coordinator_client_from_entry(hass, entry)
        # The shared coordinator: one refresh cycle every entity reads
        # from (CONF_UPDATE_INTERVAL seconds, default five minutes).
        # It polls the API service's panel snapshot; a failed poll
        # keeps the entities rendering the last-good snapshot within
        # CONF_SNAPSHOT_STALENESS, unavailable past it.
        coordinator = NestQuestCoordinator(
            hass,
            entry_id=entry.entry_id,
            api_client=api_client,
            update_interval_seconds=entry.options.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
            staleness_seconds=entry.options.get(
                CONF_SNAPSHOT_STALENESS, DEFAULT_SNAPSHOT_STALENESS
            ),
        )
        # The panel event subscription (the SSE task): a background
        # task consumes the API service's transition-event stream and
        # re-fires the four documented HA bus events.  It reuses the
        # coordinator's client, so it only starts when that client
        # actually offers a stream — an unconfigured-token stub (or a
        # test snapshot client without ``stream_events``) leaves it
        # unstarted, and the typed-error path already covers
        # availability for those entries.
        if callable(getattr(api_client, "stream_events", None)):
            event_stream = NestQuestEventStream(hass, api_client)
            event_stream.start()
        runtime_data = NestQuestRuntimeData(
            entry_id=entry.entry_id,
            remove_update_listener=remove_update_listener,
            coordinator=coordinator,
            event_stream=event_stream,
        )
        # The runtime record is registered BEFORE the first refresh:
        # the service proxy resolves the entry's runtime state through
        # hass.data, and it must find the live coordinator there —
        # never a half-set-up entry.  The platforms forward below reads
        # the coordinator off the entry (the HA runtime-data contract);
        # a forward failure below unwinds it through the except path.
        hass.data[DOMAIN][entry.entry_id] = runtime_data
        entry.runtime_data = runtime_data
        # The first refresh polls the API snapshot; an API failure
        # (unconfigured token, API service down) does NOT crash setup:
        # the coordinator reports last_update_success=False, entities
        # come up unavailable, and HA's standard retry cycle applies
        # once the API is reachable.  HA's real
        # ``async_config_entry_first_refresh`` wraps ANY failed update
        # pass in ConfigEntryNotReady — the original error survives
        # only as ``__cause__``, never as the raised exception — so the
        # catch keys on ConfigEntryNotReady, NOT on the typed API
        # error.  Everything else (a platform-forward failure,
        # cancellation) still unwinds through the except block below.
        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            pass
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # A failure anywhere after the listener was registered must not
        # leak it (or the SSE task): unwind EVERYTHING acquired before
        # the failure, keeping the original error as the one raised.
        # Removal is best-effort — a failing step must not mask the
        # setup error that triggered it.
        if event_stream is not None:
            try:
                await event_stream.stop()
            except BaseException:
                pass
        if remove_update_listener is not None:
            try:
                remove_update_listener()
            except BaseException:
                pass
        # A coordinator created before the failure holds entity
        # listeners pointed at the never-registered runtime — shut it
        # down so no scheduled refresh outlives the failed setup.
        if coordinator is not None:
            try:
                await coordinator.async_shutdown()
            except BaseException:
                pass
        # A platform-forward failure reached this unwind AFTER
        # runtime_data was assigned: clear it so no later unload path
        # re-invokes the already-consumed update-listener remover
        # through the stale record.
        if getattr(entry, "runtime_data", None) is not None:
            entry.runtime_data = None
        # The runtime record was ALSO registered in hass.data before
        # the first refresh: remove it here on ANY failure, or a later
        # unload picks up the stale, already-torn-down record
        # (hass.data wins over entry.runtime_data there) and
        # re-invokes the already-consumed update-listener remover.
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    # The runtime record was already registered before the first
    # refresh; re-assert the (unchanged) record so the return path
    # stays readable as one registration site.
    hass.data[DOMAIN][entry.entry_id] = runtime_data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime_data = domain_data.pop(entry.entry_id, None)
    is_last = not domain_data
    if is_last:
        hass.data.pop(DOMAIN, None)
    if runtime_data is None:
        runtime_data = getattr(entry, "runtime_data", None)
    # Platforms unload FIRST (mirroring HA conventions): entity
    # listeners must not outlive the coordinator the teardown below
    # shuts down.
    platforms_unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if platforms_unloaded is False and runtime_data is not None:
        # Home Assistant KEPT one or more platforms loaded — their
        # entities still live and must keep their coordinator.  Restore
        # the runtime record popped above and report failure so HA
        # retries the unload later instead of leaving live entities
        # backed by a torn-down coordinator.
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data
        return False
    unload_error: BaseException | None = None
    if runtime_data is not None:
        # The SSE subscription is stopped FIRST: its task must be gone
        # (no frame can fire) before anything else is torn down.
        event_stream = getattr(runtime_data, "event_stream", None)
        if event_stream is not None:
            stop_stream = getattr(event_stream, "stop", None)
            if stop_stream is not None:
                await stop_stream()
        remove_update_listener = getattr(
            runtime_data, "remove_update_listener", None
        )
        try:
            if remove_update_listener is not None:
                result = remove_update_listener()
                if inspect.isawaitable(result):
                    await result
        except BaseException as err:
            # A failing remover must not skip the coordinator shutdown
            # below; the first error is retained and re-raised only
            # after the teardown ran.
            if unload_error is None:
                unload_error = err
        finally:
            # The coordinator's entity listeners must stop here: a
            # scheduled refresh must never outlive the unload.
            coordinator = getattr(runtime_data, "coordinator", None)
            if coordinator is not None:
                shutdown = getattr(coordinator, "async_shutdown", None)
                if shutdown is not None:
                    await shutdown()
    # Domain-global services are torn down only once the FINAL entry
    # unloads (``hass.data[DOMAIN]`` is now empty), never when a sibling
    # entry is still loaded.
    if is_last:
        _deregister_services(hass)
    if getattr(entry, "runtime_data", None) is not None:
        entry.runtime_data = None
    if unload_error is not None:
        raise unload_error
    return True
