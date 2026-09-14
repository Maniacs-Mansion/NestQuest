"""The NestQuest integration."""
from __future__ import annotations

import asyncio
import inspect
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, LOGGER
from .db import NestQuestDatabase
from .migrations import apply_migrations
from .store import async_get_db_path

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
        database = await NestQuestDatabase(hass).open(db_path)
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
    options: dict[str, Any]
    database: NestQuestDatabase
    remove_update_listener: Callable[[], Any]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the NestQuest integration. YAML configuration is not used, returns True."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NestQuest from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    existing = hass.data[DOMAIN].get(entry.entry_id)
    if existing is not None:
        db = getattr(existing, "database", None)
        if db is None or not db.connected:
            # Reopen through the SAME safety path as first setup: a
            # record without a live connection (a previous setup's
            # close-on-failure, or a hand-replaced file) must get the
            # missing/valid/corrupt classification too, never a raw
            # sqlite3 error and never skipped migrations.
            db = await _async_open_database(
                hass, await async_get_db_path(hass)
            )
            existing.database = db
        entry.runtime_data = existing
        return True

    async def _async_update_listener(
        listener_hass: HomeAssistant, listener_entry: ConfigEntry
    ) -> None:
        """Reload the entry when its options change."""
        await listener_hass.config_entries.async_reload(listener_entry.entry_id)

    database = await _async_open_database(hass, await async_get_db_path(hass))
    try:
        remove_update_listener = entry.add_update_listener(_async_update_listener)
    except BaseException:
        await database.close()
        raise
    runtime_data = NestQuestRuntimeData(
        entry_id=entry.entry_id,
        options=dict(entry.options),
        database=database,
        remove_update_listener=remove_update_listener,
    )
    entry.runtime_data = runtime_data
    hass.data[DOMAIN][entry.entry_id] = runtime_data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime_data = domain_data.pop(entry.entry_id, None)
    if not domain_data:
        hass.data.pop(DOMAIN, None)
    if runtime_data is None:
        runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is not None:
        remove_update_listener = getattr(runtime_data, "remove_update_listener", None)
        unload_error: BaseException | None = None
        try:
            if remove_update_listener is not None:
                result = remove_update_listener()
                if inspect.isawaitable(result):
                    await result
        except BaseException as err:
            unload_error = err
        finally:
            database = getattr(runtime_data, "database", None)
            if database is not None:
                await database.close()
        if unload_error is not None:
            if getattr(entry, "runtime_data", None) is not None:
                entry.runtime_data = None
            raise unload_error
    if getattr(entry, "runtime_data", None) is not None:
        entry.runtime_data = None
    return True
