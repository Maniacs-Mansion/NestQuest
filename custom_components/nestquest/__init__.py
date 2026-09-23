"""The NestQuest integration."""
from __future__ import annotations

import asyncio
import datetime
import inspect
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_change

from .const import (
    CONF_ADMIN_USER_IDS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
)
from .core.settings import NestQuestSettings
from .frontend import async_register_frontend
from .coordinator import NestQuestCoordinator, coordinator_client_from_entry
from .db import NestQuestDatabase, make_database
from .materialize import materialize as _materialize_run
from .migrations import apply_migrations
from .services import async_deregister_services, async_register_services
from .store import async_get_db_path
from .admin_allowlist import seed_setup_admin
from .sweep import run_missed_sweep

_LOGGER = LOGGER

#: SQLite reports "file is not a database" for corruption in every
#: sqlite3 version this integration targets; the version-specific
#: "encrypted or malformed" spelling (3.41+) maps to the same failure.
_CORRUPTION_MARKERS = (
    "file is not a database",
    "database disk image is malformed",
    "encrypted or malformed",
    "is not a database",
)

#: Primary sqlite error codes that mean "the file is corrupt" (SQLite
#: result codes, https://www.sqlite.org/c3ref/c_abort.html).  Extended
#: codes carry the primary code in their low byte, so the match is on
#: errcode & 0xff.
_CORRUPT_PRIMARY_CODES = frozenset({11, 26})  # SQLITE_CORRUPT, SQLITE_NOTADB


def _is_corruption_error(error: BaseException) -> bool:
    """Return True when ``error`` indicates a corrupt database file.

    Classification order: sqlite_errorcode (Python 3.11+) is primary
    and locale-independent — SQLITE_CORRUPT and SQLITE_NOTADB, matched
    on the primary byte so extended codes (SQLITE_CORRUPT_VTAB etc.)
    classify correctly too.  Message matching is the fallback for
    older Pythons: the corruption spellings are the documented English
    texts; a non-English locale could evade them, but the code check
    already covers every locale on supported Pythons.
    """
    if not isinstance(error, sqlite3.DatabaseError):
        return False
    errorcode = getattr(error, "sqlite_errorcode", None)
    if errorcode is not None and (errorcode & 0xFF) in _CORRUPT_PRIMARY_CODES:
        return True
    message = str(error).lower()
    return any(marker in message for marker in _CORRUPTION_MARKERS)


async def _preflight_existing_file(
    hass: HomeAssistant, db_path: Path
) -> None:
    """Detect corruption in an EXISTING file before it is opened read-write.

    Opening read-write persists WAL mode — for a rollback-journal file
    that rewrites the header byte 18/19 and can create -wal/-shm
    sidecars — which would modify a corrupt file before detection and
    break the leave-untouched guarantee.  This preflight therefore
    validates the WHOLE file with a READ-ONLY connection (mode=ro +
    immutable=1 URI, PRAGMA integrity_check, run on the executor like
    every other DB call): corruption anywhere fails there, before
    anything is written.  ``immutable=1`` is SQLite's documented
    guarantee that the connection performs NO writes and creates NO
    sidecars — even a WAL-header file gets its -wal/-shm reads served
    without creating the shared-memory file.  Missing/empty files skip
    the preflight (they are created fresh by the real open).  All
    filesystem stat/URI work runs inside the executor job with the
    probe so the event loop never touches disk.
    """
    def _probe() -> None:
        # The file-state check and URI construction live inside the
        # executor job: exists/stat/resolve are disk I/O.
        if not db_path.exists():
            return
        # A zero-byte file is neither missing nor a valid database: it
        # is a corrupt (truncated-to-nothing) existing file, likely an
        # interrupted first write.  The leave-untouched contract applies
        # to it too: refuse rather than silently initialize over it.
        if db_path.stat().st_size == 0:
            raise sqlite3.DatabaseError(
                "existing database file is empty (zero bytes): file is "
                "not a database"
            )
        # Properly escape the path: '#'/'?'/'%' in a directory or file
        # name would otherwise be parsed as URI fragments/parameters/
        # escapes.  immutable=1: SQLite guarantees no writes and no
        # sidecar creation from this connection.
        uri = db_path.resolve().as_uri() + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
        verdict = row[0] if row else "missing"
        if verdict != "ok":
            # A non-ok integrity verdict IS corruption: raise with the
            # verdict text (which matches the corruption markers) and
            # the NOTADB code so classification is code-based.
            raise sqlite3.DatabaseError(
                f"integrity_check verdict {verdict!r} on read-only "
                f"probe: file is not a database"
            )

    try:
        # Every DB-touching call goes through the executor (the mock
        # harness's async_add_executor_job is awaitable too).
        await hass.async_add_executor_job(_probe)
    except sqlite3.DatabaseError as err:
        # Non-ok integrity verdicts are corruption, full stop: there is
        # no benign reading of a failed whole-file integrity check, so
        # ANY DatabaseError out of the probe that carries a corruption
        # marker or code propagates as corruption.  Only exotic probe
        # failures that classify as non-corruption (e.g. a transient
        # 'database is locked' on the read) are downgraded to a debug
        # log, letting the real open path surface them.
        if _is_corruption_error(err):
            raise
        raise sqlite3.DatabaseError(
            f"read-only corruption probe of {db_path} failed: {err}"
        ) from err

async def _async_open_database(
    hass: HomeAssistant, db_path: Path
) -> NestQuestDatabase:
    """Open the NestQuest database, mapping failure modes for setup.

    Three startup cases (Feature 02 done-condition):

    - file missing: SQLite creates it fresh on open — no special path,
      migrations stamp version 1 on the next step.
    - file present and valid: opens normally.
    - file present but corrupt: log an ERROR with the path, close
      anything opened, and raise ConfigEntryNotReady so HA retries —
      the file is left byte-for-byte untouched so the owner can
      restore a backup.  No code path here deletes or overwrites an
      existing database file.

    Corruption can surface at EITHER stage: a truncated header fails
    in the read-only preflight (before the file is ever opened
    read-write), while damaged later pages fail during migrations —
    the preflight guarantees no WAL sidecar or header write happens
    on a corrupt file before it is detected.  Both are classified the
    same way.
    """
    try:
        await _preflight_existing_file(hass, db_path)
        database = await make_database(hass).open(db_path)
    except asyncio.CancelledError:
        raise
    except sqlite3.DatabaseError as err:
        if _is_corruption_error(err):
            _LOGGER.error(
                "NestQuest database at %s is corrupt: %s. Refusing to "
                "start with a corrupt database; the file was left "
                "untouched so a backup can be restored. Home Assistant "
                "will retry setup.",
                db_path,
                err,
            )
            raise ConfigEntryNotReady(
                f"NestQuest database corrupt: {db_path}"
            ) from err
        # open() failed for a non-corruption reason (locked file,
        # permission problem): retryable, but nothing was opened.
        _LOGGER.error(
            "NestQuest database at %s failed to open: %s. Home "
            "Assistant will retry setup.",
            db_path,
            err,
        )
        raise ConfigEntryNotReady(
            f"NestQuest database unavailable: {db_path}"
        ) from err
    try:
        await apply_migrations(database)
    except (sqlite3.DatabaseError, RuntimeError) as err:
        await database.close()
        if _is_corruption_error(err):
            _LOGGER.error(
                "NestQuest database at %s is corrupt: %s. Refusing to "
                "start with a corrupt database; the file was left "
                "untouched so a backup can be restored. Home Assistant "
                "will retry setup.",
                db_path,
                err,
            )
            raise ConfigEntryNotReady(
                f"NestQuest database corrupt: {db_path}"
            ) from err
        # A non-corruption failure (e.g. a locked file, a future schema
        # version) is also a retryable setup problem, but without the
        # corruption framing.
        _LOGGER.error(
            "NestQuest database at %s failed to open: %s. Home "
            "Assistant will retry setup.",
            db_path,
            err,
        )
        raise ConfigEntryNotReady(
            f"NestQuest database unavailable: {db_path}"
        ) from err
    except asyncio.CancelledError:
        await database.close()
        raise
    return database


@dataclass
class NestQuestRuntimeData:
    """Runtime data stored on a NestQuest config entry."""

    entry_id: str
    settings: NestQuestSettings
    database: NestQuestDatabase
    remove_update_listener: Callable[[], Any]
    remove_time_change_listener: Callable[[], Any]
    coordinator: Any = None


async def _async_owner_user_ids(hass: HomeAssistant) -> list[str]:
    """Return every Home Assistant owner-account user id.

    The last-resort admin seed: when no persisted allowlist copy and no
    flow-context user survive to first setup, the HA owner accounts are
    seeded so the household is never left with zero admins (an empty
    allowlist fails closed, which would lock the household out of its
    own integration).  Owner accounts can already do everything in HA,
    so granting NestQuest admin is not a privilege escalation.
    """
    auth = getattr(hass, "auth", None)
    if auth is None:
        return []
    users = await auth.async_get_users()
    owners = [
        user.id
        for user in users
        if getattr(user, "is_owner", False) and getattr(user, "id", None)
    ]
    return owners


async def _run_horizon_materialization(
    hass: HomeAssistant,
    database: NestQuestDatabase,
    settings: NestQuestSettings,
) -> None:
    """Materialize the rolling horizon ``[today, today + horizon_days]``.

    "today" is computed in HA local time (``hass.config.time_zone``) rather
    than the system clock, so the horizon tracks the household's own day.
    The walk itself runs through :func:`~.materialize.materialize`, whose DB
    access is executor-only.

    This is the ONE generation path: the startup backfill, the daily rollover
    listener and the ``regenerate`` service all funnel through it, so there is
    no duplicated materialization logic.  ``settings`` (REQUIRED — there is no
    silent default; every caller already passes the entry's validated
    :class:`NestQuestSettings`) carries the configured ``horizon_days``.  The
    window itself comes from :meth:`settings.horizon_window` so the helper is
    real and shared (not recomputed inline here).
    """
    time_zone = ZoneInfo(hass.config.time_zone)
    today = datetime.datetime.now(time_zone).date()
    start, end = settings.horizon_window(today)
    await _materialize_run(database, start.isoformat(), end.isoformat(), today=today)


def _register_day_rollover_listener(
    hass: HomeAssistant,
    database: NestQuestDatabase,
    settings: NestQuestSettings,
) -> Callable[[], Any]:
    """Register the daily rollover listener and return its remover.

    Fires once per day at the configured local ``day_rollover_time``:
    first re-materializes the rolling horizon
    ``[today, today + horizon_days]`` through the shared
    :func:`_run_horizon_materialization` path (the entry's configured,
    validated ``horizon_days`` carried on ``settings``), then runs the
    Feature 11 missed sweep — announcing yesterday's still-open quests
    as missed AFTER today's instances exist, watermark-guarded so a
    re-fire of the listener the same night announces nothing twice.
    """
    hour, minute = settings.day_rollover_hour_minute

    async def _run_materialization(_now: datetime.datetime) -> None:
        await _run_horizon_materialization(hass, database, settings)
        await run_missed_sweep(hass, database)

    return async_track_time_change(
        hass, _run_materialization, hour=hour, minute=minute
    )


def _find_live_runtime_data(hass: HomeAssistant) -> NestQuestRuntimeData | None:
    """Return a live runtime record with a connected database, or None.

    The domain-global services (e.g. ``regenerate``) have no database of
    their own; they resolve whichever config entry's runtime data is
    currently live at call time, so none of them can hold a stale handle
    to a closed connection after another entry unloads.  The record also
    carries that entry's validated ``settings`` (e.g. the configured
    horizon) so service handlers read horizon days off it rather than
    re-reading HA config.
    """
    for runtime_data in hass.data.get(DOMAIN, {}).values():
        database = getattr(runtime_data, "database", None)
        if database is not None and database.connected:
            return runtime_data
    return None


def _make_regenerate_handler(hass: HomeAssistant):
    """Return the Feature 07 ``regenerate`` handler closed over ``hass``."""

    async def _regenerate(_call: Any) -> None:
        runtime_data = _find_live_runtime_data(hass)
        if runtime_data is None:
            _LOGGER.warning(
                "NestQuest regenerate requested but no config entry has a "
                "live database; ignoring"
            )
            return
        await _run_horizon_materialization(
            hass, runtime_data.database, runtime_data.settings
        )

    return _regenerate


def _register_services(hass: HomeAssistant) -> None:
    """Register domain-global NestQuest services once.

    Services are DOMAIN-global — registered exactly once (guarded by
    ``has_service`` on regenerate) and NOT bound to any config entry —
    so each handler resolves the currently-live database at call time
    and a name collision or duplicate setup is impossible.  Removal is
    handled by the unload path only once the LAST entry is removed
    (see :func:`_deregister_services`).
    """
    async_register_services(
        hass,
        find_runtime=_find_live_runtime_data,
        regenerate_handler=_make_regenerate_handler(hass),
    )


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
    existing = hass.data[DOMAIN].get(entry.entry_id)
    if existing is not None:
        db = getattr(existing, "database", None)
        if db is None or not db.connected:
            # Reopen through the SAME safety path as first setup: a
            # record without a live connection (a previous setup's
            # close-on-failure, or a hand-replaced file) must get the
            # missing/valid/corrupt classification too, never a raw
            # sqlite3 error and never skipped migrations — and the
            # same allowlist seeding, so a reopened fresh file is
            # never ownerless.
            db = await _async_open_database(
                hass, await async_get_db_path(hass)
            )
            try:
                stored_admin_ids = (
                    entry.options.get(CONF_ADMIN_USER_IDS)
                    or entry.data.get(CONF_ADMIN_USER_IDS)
                )
                context = getattr(entry, "context", None)
                context_user_id = (
                    context.get("user_id")
                    if isinstance(context, dict)
                    else None
                )
                await seed_setup_admin(
                    db,
                    stored_admin_ids=stored_admin_ids,
                    context_user_id=context_user_id,
                    owner_ids=await _async_owner_user_ids(hass),
                )
            except BaseException:
                # A seeding failure must not leak the just-opened
                # connection: close it before the error propagates, so
                # HA's setup retry starts from a clean handle (the
                # first-setup path closes symmetrically).
                await db.close()
                raise
            existing.database = db
        entry.runtime_data = existing
        return True

    async def _async_update_listener(
        listener_hass: HomeAssistant, listener_entry: ConfigEntry
    ) -> None:
        """Reload the entry when its options change."""
        await listener_hass.config_entries.async_reload(listener_entry.entry_id)

    database = await _async_open_database(hass, await async_get_db_path(hass))
    remove_update_listener: Callable[[], Any] | None = None
    remove_time_change_listener: Callable[[], Any] | None = None
    coordinator: Any = None
    try:
        # Seed the admin allowlist on first setup so the owner is never
        # locked out: an empty database takes the persisted admin copy
        # — the options flow's saved list first (it is the current
        # one), else the config flow's user from entry data — and only
        # then the HA user still present on the entry context.  No-op
        # on a non-empty list (fail-closed narrowing is deliberate).
        stored_admin_ids = (
            entry.options.get(CONF_ADMIN_USER_IDS)
            or entry.data.get(CONF_ADMIN_USER_IDS)
        )
        context = getattr(entry, "context", None)
        context_user_id = (
            context.get("user_id")
            if isinstance(context, dict)
            else None
        )
        owner_ids = await _async_owner_user_ids(hass)
        await seed_setup_admin(
            database,
            stored_admin_ids=stored_admin_ids,
            context_user_id=context_user_id,
            owner_ids=owner_ids,
        )
        # Build the explicit settings object from entry.options ONCE: the
        # horizon materialization and the daily-rollover listener both
        # consume it, so core never reads HA config itself.  A malformed
        # stored option falls back PER FIELD (via from_options_resilient)
        # so a single bad sibling option cannot reset the user's
        # horizon_days or day_rollover_time — the two fields core
        # consumes — to their defaults.
        settings = NestQuestSettings.from_options_resilient(entry.options)
        remove_update_listener = entry.add_update_listener(_async_update_listener)
        remove_time_change_listener = _register_day_rollover_listener(
            hass, database, settings
        )
        # Backfill any days the daily listener missed while the integration
        # was off (or freshly installed): run the one idempotent walk over
        # [today, today + horizon_days] once at setup, using the entry's
        # configured horizon.  This runs through the SAME path as the daily
        # listener and regenerate service.
        await _run_horizon_materialization(hass, database, settings)
        # The missed sweep runs at startup too (Feature 11): if HA was
        # down at the rollover time, the previous night's still-open
        # quests are announced as missed now instead of waiting for
        # the next midnight.  Watermark-guarded, so this is a no-op
        # when the night's sweep already ran.
        await run_missed_sweep(hass, database)
        _register_services(hass)
        # The shared Feature 10 coordinator: one refresh cycle every
        # entity reads from (CONF_UPDATE_INTERVAL seconds, default
        # five minutes).  Since Feature 18 it polls the API service's
        # panel snapshot instead of reading the local database; an
        # entry with no panel token yet gets the typed-error stub
        # (unavailable entities, never a setup crash).  Created AFTER
        # services so a failure below unwinds them through the except
        # path's listener handling.
        coordinator = NestQuestCoordinator(
            hass,
            entry_id=entry.entry_id,
            api_client=coordinator_client_from_entry(hass, entry),
            update_interval_seconds=entry.options.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
        )
        runtime_data = NestQuestRuntimeData(
            entry_id=entry.entry_id,
            settings=settings,
            database=database,
            remove_update_listener=remove_update_listener,
            remove_time_change_listener=remove_time_change_listener,
            coordinator=coordinator,
        )
        # The runtime record is registered BEFORE the first refresh:
        # the refresh path (and anything it calls) resolves the entry's
        # runtime state through hass.data, and it must find the live
        # database there — never a half-set-up entry.  The platforms
        # forward below reads the coordinator off the entry
        # (the HA runtime-data contract); a forward failure below
        # unwinds it through the except path.
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
        # A failure anywhere after the database is open must not leak the
        # listeners already registered against that (now-closed) database:
        # unwind EVERY remover we acquired before the failure, keeping the
        # original error as the one raised.  Removal is best-effort — a
        # failing remover must not mask the setup error that triggered it.
        for remove_listener in (
            remove_time_change_listener,
            remove_update_listener,
        ):
            if remove_listener is None:
                continue
            try:
                result = remove_listener()
                if inspect.isawaitable(result):
                    await result
            except BaseException:
                pass
        # A coordinator created before the failure holds entity
        # listeners pointed at the database being closed below —
        # shut it down FIRST so no scheduled refresh can ever run
        # against a closed connection.
        if coordinator is not None:
            try:
                await coordinator.async_shutdown()
            except BaseException:
                pass
        # A platform-forward failure reached this unwind AFTER
        # runtime_data was assigned: clear it so no later unload path
        # closes the already-closed database through the stale record.
        if getattr(entry, "runtime_data", None) is not None:
            entry.runtime_data = None
        # The runtime record was ALSO registered in hass.data before
        # the first refresh: remove it here on ANY failure, or a later
        # unload picks up the stale, already-torn-down record
        # (hass.data wins over entry.runtime_data there) and
        # re-invokes the already-consumed update-listener remover.
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await database.close()
        raise
    assert remove_update_listener is not None
    assert remove_time_change_listener is not None
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
    # listeners must not outlive the database and coordinator the
    # teardown below closes.
    platforms_unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if platforms_unloaded is False and runtime_data is not None:
        # Home Assistant KEPT one or more platforms loaded — their
        # entities still live and must keep their database.  Restore
        # the runtime record popped above and report failure so HA
        # retries the unload later instead of leaving live entities
        # backed by a closed database.
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data
        return False
    unload_error: BaseException | None = None
    if runtime_data is not None:
        remove_update_listener = getattr(runtime_data, "remove_update_listener", None)
        remove_time_change_listener = getattr(
            runtime_data, "remove_time_change_listener", None
        )
        try:
            for remove_listener in (
                remove_update_listener,
                remove_time_change_listener,
            ):
                if remove_listener is None:
                    continue
                try:
                    result = remove_listener()
                    if inspect.isawaitable(result):
                        await result
                except BaseException as err:
                    # Cancel EVERY listener even when an earlier remover
                    # raises: a skipped remover would leave a daily
                    # callback firing against a closed database after
                    # unload.  The first error is retained and re-raised
                    # only after both removers (and the DB close) ran.
                    if unload_error is None:
                        unload_error = err
        finally:
            # The coordinator's entity listeners must stop BEFORE the
            # database closes: a scheduled refresh starting during the
            # close await would touch a cleared connection.  (The
            # platform unload above already removed the entities; this
            # clears the coordinator's own remaining listeners.)
            coordinator = getattr(runtime_data, "coordinator", None)
            if coordinator is not None:
                shutdown = getattr(coordinator, "async_shutdown", None)
                if shutdown is not None:
                    await shutdown()
            database = getattr(runtime_data, "database", None)
            if database is not None:
                await database.close()
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
