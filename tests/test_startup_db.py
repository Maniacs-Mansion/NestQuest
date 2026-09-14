"""Tests for startup handling of missing, valid, and corrupt databases."""
from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_config_entry
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.nestquest import (
    _async_open_database,
    _is_corruption_error,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import (
    VERSION_TABLE,
    apply_migrations,
)
from tests.test_lifecycle import _wire


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> NestQuestDatabase:
    database = NestQuestDatabase(_make_hass_mock())
    _run(database.open(path))
    return database


async def _avalid_database(path) -> None:
    """Create a valid, migrated NestQuest database file (async, on the
    running loop, for use inside pytest-asyncio tests)."""
    database = NestQuestDatabase(_make_hass_mock())
    await database.open(path)
    try:
        await apply_migrations(database)
    finally:
        await database.close()


def _valid_database(path) -> None:
    """Create a valid, migrated NestQuest database file at ``path``."""
    database = _open_db(path)
    try:
        _run(apply_migrations(database))
    finally:
        _run(database.close())


def _truncated_database(path) -> None:
    """Create a deliberately truncated (corrupt) database file.

    A valid database is written, closed, then cut short mid-header:
    opening it reports 'file is not a database' — exactly what an
    interrupted write or failing disk leaves behind.
    """
    _valid_database(path)
    data = path.read_bytes()
    assert len(data) > 64, "valid database must exist before truncation"
    path.write_bytes(data[: len(data) // 2])


# ---------------------------------------------------------------------------
# Corruption classification
# ---------------------------------------------------------------------------


def test_is_corruption_error_matches_sqlite_spellings() -> None:
    assert _is_corruption_error(
        sqlite3.DatabaseError("file is not a database")
    )
    assert _is_corruption_error(
        sqlite3.DatabaseError("file is not a database".upper())
    )
    assert _is_corruption_error(
        sqlite3.DatabaseError("file is encrypted or malformed")
    )
    assert _is_corruption_error(
        sqlite3.OperationalError("file is not a database")
    )


def test_is_corruption_error_rejects_other_failures() -> None:
    assert not _is_corruption_error(
        sqlite3.OperationalError("database is locked")
    )
    assert not _is_corruption_error(
        sqlite3.IntegrityError("NOT NULL constraint failed")
    )
    assert not _is_corruption_error(RuntimeError("boom"))
    assert not _is_corruption_error(ValueError("nope"))


# ---------------------------------------------------------------------------
# Startup: three cases through _async_open_database
# ---------------------------------------------------------------------------


def test_missing_file_opens_fresh(tmp_path) -> None:
    db_path = tmp_path / "nestquest.db"
    assert not db_path.exists()
    database = _run(_async_open_database(_make_hass_mock(), db_path))
    try:
        # The file was created fresh and migrations stamped version 1.
        assert db_path.exists()
        row = _run(
            database.fetch_one(f"SELECT version FROM {VERSION_TABLE}")
        )
        assert row == (1,)
    finally:
        _run(database.close())


def test_valid_file_opens_and_migrations_noop(tmp_path) -> None:
    db_path = tmp_path / "nestquest.db"
    _valid_database(db_path)
    digest_before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    database = _run(_async_open_database(_make_hass_mock(), db_path))
    try:
        row = _run(
            database.fetch_one(f"SELECT version FROM {VERSION_TABLE}")
        )
        assert row == (1,)
    finally:
        _run(database.close())
    # Opening a valid file must not rewrite it (the no-op path).
    assert (
        hashlib.sha256(db_path.read_bytes()).hexdigest() == digest_before
    )


def test_corrupt_file_raises_not_ready_and_leaves_file_untouched(
    tmp_path, caplog
) -> None:
    db_path = tmp_path / "nestquest.db"
    _truncated_database(db_path)
    corrupt_bytes = db_path.read_bytes()
    digest = hashlib.sha256(corrupt_bytes).hexdigest()

    with pytest.raises(ConfigEntryNotReady) as excinfo:
        _run(_async_open_database(_make_hass_mock(), db_path))

    # The file is byte-identical: the owner can restore/inspect it.
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == digest
    assert len(db_path.read_bytes()) == len(corrupt_bytes)
    # The original error is preserved and the log names the path.
    assert isinstance(excinfo.value.__cause__, sqlite3.DatabaseError)
    assert any(
        "corrupt" in record.getMessage().lower()
        and str(db_path) in record.getMessage()
        for record in caplog.records
        if record.levelname == "ERROR"
    ), "the error log must name the corrupt path"


def test_corrupt_file_raises_not_ready_never_raw_error(tmp_path) -> None:
    """The corrupt case must surface as ConfigEntryNotReady, not crash
    setup with a raw sqlite3.DatabaseError — and it must ALWAYS raise
    (returning normally would mean corruption was silently accepted)."""
    db_path = tmp_path / "nestquest.db"
    _truncated_database(db_path)
    with pytest.raises(ConfigEntryNotReady) as excinfo:
        _run(_async_open_database(_make_hass_mock(), db_path))
    assert isinstance(excinfo.value.__cause__, sqlite3.DatabaseError)


def test_migration_stage_corruption_leaves_db_and_sidecars_untouched(
    tmp_path,
) -> None:
    """A valid header with a corrupt LATER page is detected during
    migrations, AFTER the read-write open has switched the file to WAL.
    The leave-untouched guarantee must still hold byte-for-byte for
    the main file AND no WAL/SHM sidecars may be left behind for the
    owner to clean up.

    The fixture is deliberately a ROLLBACK-JOURNAL file (created with
    plain sqlite3, default journal_mode=delete, NOT via the wrapper):
    that is the case where the WAL transition actually rewrites the
    header — a WAL-mode fixture would mask the write under test.
    """
    db_path = tmp_path / "nestquest.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute(
            "CREATE TABLE filler (id INTEGER PRIMARY KEY, "
            "payload TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO filler (payload) VALUES (?)",
            [(f"row-{index}" * 8,) for index in range(200)],
        )
        conn.commit()
    finally:
        conn.close()
    data = bytearray(db_path.read_bytes())
    assert conn.execute is not None
    assert len(data) > 4200, "fixture must span more than one page"
    # Corrupt a page well past the 100-byte header (offset 4096, the
    # second page region): the header itself stays valid, so the
    # read-write open succeeds and only the integrity probe/migrations
    # discover damage.
    for offset in range(4096, 4128):
        data[offset] = 0xFF
    db_path.write_bytes(bytes(data))
    corrupt_bytes = db_path.read_bytes()
    digest = hashlib.sha256(corrupt_bytes).hexdigest()

    with pytest.raises(ConfigEntryNotReady) as excinfo:
        _run(_async_open_database(_make_hass_mock(), db_path))
    assert isinstance(excinfo.value.__cause__, sqlite3.DatabaseError)

    # The main file is byte-identical to the corrupt state we handed in.
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == digest
    # No WAL/SHM sidecars left behind (WAL mode was never persisted,
    # or they were cleaned up on close).
    assert not (tmp_path / "nestquest.db-wal").exists()
    assert not (tmp_path / "nestquest.db-shm").exists()


def test_open_failure_closes_connection_when_opened(
    tmp_path, monkeypatch
) -> None:
    """A failure DURING MIGRATIONS closes the opened connection; a
    failure inside open() itself has nothing to close (the wrapper
    never adopted a connection), so close must not be called there.
    """
    db_path = tmp_path / "nestquest.db"
    _truncated_database(db_path)

    close_calls: list[bool] = []
    original_close = NestQuestDatabase.close

    async def _spy_close(self):
        close_calls.append(True)
        return await original_close(self)

    monkeypatch.setattr(NestQuestDatabase, "close", _spy_close)
    with pytest.raises(ConfigEntryNotReady):
        _run(_async_open_database(_make_hass_mock(), db_path))
    # Corruption hit at PRAGMA time inside open(): no connection was
    # adopted, so there is nothing to close and close() must NOT have
    # been called (calling close on a never-opened wrapper would be
    # harmless but the helper deliberately skips it).
    assert close_calls == []

    # Contrast: a failure DURING migrations (file opens fine) closes.
    close_calls.clear()
    valid_path = tmp_path / "migrations-fail.db"
    _valid_database(valid_path)
    # _valid_database's own close went through the spy; only the
    # failure path's close counts from here.
    close_calls.clear()
    from custom_components.nestquest import migrations as migrations_mod
    from custom_components.nestquest.db import NestQuestDatabase as _DB

    async def _failing(database, migrations=None):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(migrations_mod, "apply_migrations", _failing)
    monkeypatch.setattr(
        "custom_components.nestquest.apply_migrations", _failing
    )
    with pytest.raises(ConfigEntryNotReady) as excinfo:
        _run(_async_open_database(_make_hass_mock(), valid_path))
    # Exactly one close: the migrations-failure cleanup path.  (The
    # spy also sees the wrapper's own idempotent close if it were
    # double-called — it must not be.)
    assert close_calls == [True], (
        "an open connection must be closed before the error propagates"
    )
    assert isinstance(excinfo.value.__cause__, sqlite3.DatabaseError)


# ---------------------------------------------------------------------------
# Startup through async_setup_entry (the real wiring)
# ---------------------------------------------------------------------------


def _make_setup(hass, registry):
    def _setup(entry):
        return async_setup_entry(hass, entry)

    return _setup


async def _setup_entry(hass, entry, registry) -> object:
    entry = _wire(entry, registry)
    await async_setup_entry(hass, entry)
    return entry


async def test_setup_with_corrupt_file_raises_not_ready(
    hass, make_entry, monkeypatch, tmp_path, caplog
) -> None:
    from custom_components.nestquest.store import async_get_db_path

    db_path = await async_get_db_path(hass)
    await _avalid_database(db_path)
    data = db_path.read_bytes()
    assert len(data) > 64
    db_path.write_bytes(data[: len(data) // 2])
    corrupt_bytes = db_path.read_bytes()

    entry = make_entry()
    with pytest.raises(ConfigEntryNotReady):
        await _setup_entry(hass, entry, hass.registry)
    # File untouched, no runtime data stored.
    assert db_path.read_bytes() == corrupt_bytes
    assert hass.data["nestquest"].get(entry.entry_id) is None


async def test_setup_with_missing_file_creates_and_loads(
    hass, make_entry
) -> None:
    entry = await _setup_entry(hass, make_entry(), hass.registry)
    database = entry.runtime_data.database
    try:
        row = await database.fetch_one(
            f"SELECT version FROM {VERSION_TABLE}"
        )
        assert row == (1,)
    finally:
        await database.close()
    assert await async_unload_entry(hass, entry) is True


async def test_setup_with_valid_file_preserves_rows(
    hass, make_entry
) -> None:
    entry_a = await _setup_entry(hass, make_entry(), hass.registry)
    database_a = entry_a.runtime_data.database
    await database_a.execute(
        "INSERT INTO children (display_name, created_at) VALUES (?, ?)",
        ("Ada", "2026-09-14T12:00:00+00:00"),
    )
    # Unload pops the runtime record AND closes the connection; a
    # fresh setup for the same entry_id then reopens the file.
    assert await async_unload_entry(hass, entry_a) is True

    entry_b = await _setup_entry(hass, make_entry(), hass.registry)
    database_b = entry_b.runtime_data.database
    assert database_b is not database_a
    try:
        row = await database_b.fetch_one("SELECT COUNT(*) FROM children")
        assert row == (1,)
    finally:
        await database_b.close()
    assert await async_unload_entry(hass, entry_b) is True


# ---------------------------------------------------------------------------
# No code path deletes or overwrites an existing database file
# ---------------------------------------------------------------------------


def test_package_never_unlinks_or_truncates_db_files() -> None:
    """Guardrail: no code path may delete or overwrite an existing
    database file.  Scans the package for unlink/rmtree/write on the
    DB filename constant or *.db patterns.
    """
    import re
    from pathlib import Path

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent
    pattern = re.compile(
        r"(unlink|rmtree|write_bytes|write_text|open\s*\(\s*[^)]*['\"]w)"
        r"[^\n]*(nestquest\.db|\.db['\"])|"
        r"(nestquest\.db|\.db['\"])[^\n]*"
        r"(unlink|rmtree|write_bytes|write_text)",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for py in sorted(package.glob("*.py")):
        if pattern.search(py.read_text()):
            offenders.append(py.name)
    assert offenders == [], (
        f"code paths that could delete/overwrite the database: {offenders}"
    )