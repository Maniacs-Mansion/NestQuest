"""Tests for db.py, the async SQLite connection wrapper of NestQuest."""
from __future__ import annotations

import ast
import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import executor_for, make_hass

import custom_components.nestquest.core.db as db_module
from custom_components.nestquest.core.db import NestQuestDatabase


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> tuple[NestQuestDatabase, MagicMock]:
    hass = _make_hass_mock()
    database = NestQuestDatabase(hass.async_add_executor_job)
    _run(database.open(path))
    return database, hass


# ---------------------------------------------------------------------------
# open(): pragmas, executor delegation, idempotence
# ---------------------------------------------------------------------------


def test_open_enables_wal_journal_mode(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "wal.db")
    row = _run(database.fetch_one("PRAGMA journal_mode"))
    assert row is not None and str(row[0]).lower() == "wal"
    _run(database.close())


def test_open_enables_foreign_key_enforcement(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "fk.db")
    row = _run(database.fetch_one("PRAGMA foreign_keys"))
    assert row is not None and int(row[0]) == 1
    _run(database.close())


def test_open_delegates_connection_to_executor(tmp_path) -> None:
    hass = _make_hass_mock()
    database = NestQuestDatabase(hass.async_add_executor_job)
    _run(database.open(tmp_path / "exec.db"))
    first_call = hass.async_add_executor_job.call_args_list[0]
    assert callable(first_call.args[0])
    _run(database.close())


def test_open_twice_returns_same_wrapper_without_second_connect(tmp_path) -> None:
    path = tmp_path / "once.db"
    hass = _make_hass_mock()
    database = NestQuestDatabase(hass.async_add_executor_job)
    first = _run(database.open(path))
    second = _run(database.open(path))
    assert first is database
    assert second is database
    assert database.connected is True
    opens = [
        c
        for c in hass.async_add_executor_job.call_args_list
        if getattr(c.args[0], "__name__", "") == "_open"
    ]
    assert len(opens) == 1
    _run(database.close())


def test_open_accepts_str_path(tmp_path) -> None:
    database, _hass = _open_db(str(tmp_path / "str.db"))
    assert database.connected is True
    _run(database.close())


# ---------------------------------------------------------------------------
# Executor delegation: every sqlite3 call happens off the event loop
# ---------------------------------------------------------------------------


def test_every_method_routes_sqlite3_through_executor(tmp_path) -> None:
    """Each wrapper call must go via hass.async_add_executor_job."""
    database, hass = _open_db(tmp_path / "route.db")
    calls_before = hass.async_add_executor_job.await_count

    _run(database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    _run(database.execute("INSERT INTO t (name) VALUES (?)", ("a",)))
    _run(database.execute_many("INSERT INTO t (name) VALUES (?)", [("b",), ("c",)]))
    row = _run(database.fetch_one("SELECT name FROM t WHERE id = 1"))
    rows = _run(database.fetch_all("SELECT name FROM t ORDER BY id"))

    assert row == ("a",)
    assert rows == [("a",), ("b",), ("c",)]
    assert hass.async_add_executor_job.await_count == calls_before + 5
    _run(database.close())


async def test_every_wrapper_call_awaits_executor_job(tmp_path) -> None:
    """The executor surface is awaited per wrapper call on a live loop."""
    hass = _make_hass_mock()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "loop.db")

    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    await database.fetch_one("SELECT 1")
    await database.fetch_all("SELECT 1")
    await database.execute_many("INSERT INTO t (id) VALUES (?)", [(1,)])
    async with database.transaction():
        pass

    assert hass.async_add_executor_job.await_count == 7
    assert all(callable(c.args[0]) for c in hass.async_add_executor_job.call_args_list)
    await database.close()


async def test_public_methods_return_only_plain_data(tmp_path) -> None:
    """execute/execute_many return plain dataclasses, never sqlite3 objects."""
    hass = _make_hass_mock()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "plain.db")
    result = await database.execute(
        "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"
    )
    assert not isinstance(result, (sqlite3.Connection, sqlite3.Cursor))
    insert = await database.execute("INSERT INTO t (name) VALUES (?)", ("a",))
    assert not isinstance(insert, (sqlite3.Connection, sqlite3.Cursor))
    assert insert.rowcount == 1
    assert insert.lastrowid == 1
    many = await database.execute_many(
        "INSERT INTO t (name) VALUES (?)", [("b",), ("c",)]
    )
    assert not isinstance(many, (sqlite3.Connection, sqlite3.Cursor))
    assert many.rowcount == 2
    row = await database.fetch_one("SELECT name FROM t WHERE id = 1")
    assert row == ("a",)
    rows = await database.fetch_all("SELECT name FROM t ORDER BY id")
    assert rows == [("a",), ("b",), ("c",)]
    for value in (*rows, row):
        assert not isinstance(value, sqlite3.Cursor)
    await database.close()


async def test_no_sqlite3_call_on_event_loop_with_real_executor(tmp_path) -> None:
    """With the conftest hass (real run_in_executor), queries still succeed."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "real.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert await database.fetch_one("SELECT 1") == (1,)
    await database.close()


async def test_real_executor_never_touches_loop_thread(tmp_path, monkeypatch) -> None:
    """Every real sqlite3 call must run on a non-event-loop thread.

    sqlite3.connect is instrumented so a proxy wraps the connection and
    every cursor it hands out; each proxied call records the thread it ran
    on.  A recorded thread id equal to the event-loop thread would mean a
    sqlite3 call crossed the executor boundary.
    """
    loop_thread = threading.get_ident()
    recorded: list[int] = []
    guard = threading.Lock()

    def _note() -> None:
        with guard:
            recorded.append(threading.get_ident())

    class _Proxy:
        """Generic proxy recording the thread of every attribute call."""

        def __init__(self, target: Any) -> None:
            object.__setattr__(self, "_target", target)

        def __getattr__(self, name: str):
            attr = getattr(object.__getattribute__(self, "_target"), name)
            if not callable(attr):
                return attr

            def _wrapped(*args, **kwargs):
                _note()
                result = attr(*args, **kwargs)
                if isinstance(result, sqlite3.Cursor):
                    return _Proxy(result)
                return result

            return _wrapped

    real_connect = sqlite3.connect
    connect_threads: list[int] = []

    def _traced_connect(*args, **kwargs):
        _note()
        connect_threads.append(threading.get_ident())
        return _Proxy(real_connect(*args, **kwargs))

    monkeypatch.setattr(db_module.sqlite3, "connect", _traced_connect)

    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "threads.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    await database.execute("INSERT INTO t (id) VALUES (?)", (1,))
    await database.execute_many("INSERT INTO t (id) VALUES (?)", [(2,), (3,)])
    assert await database.fetch_one("SELECT id FROM t WHERE id = 1") == (1,)
    assert await database.fetch_all("SELECT id FROM t") == [(1,), (2,), (3,)]
    async with database.transaction():
        await database.execute("INSERT INTO t (id) VALUES (?)", (4,))
    await database.close()

    assert recorded, "expected at least one recorded sqlite3 call"
    assert len(connect_threads) == 1, (
        f"expected exactly one traced sqlite3.connect, got {len(connect_threads)}"
    )
    assert loop_thread not in recorded, (
        f"sqlite3 call ran on the event-loop thread {loop_thread}; "
        f"recorded threads: {sorted(set(recorded))}"
    )


# ---------------------------------------------------------------------------
# Source scan: sqlite3.* only inside executor-delegated functions
# ---------------------------------------------------------------------------


def _iter_with_scope(node, chain):
    """Yield (node, enclosing-function chain), depth-first."""
    for child in ast.iter_child_nodes(node):
        yield child, chain
        next_chain = chain + (child,) if isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) else chain
        yield from _iter_with_scope(child, next_chain)


def test_db_sqlite3_calls_only_inside_executor_delegated_functions() -> None:
    """Every sqlite3.* call in db.py sits inside an executor-delegating function.

    A function is executor-delegating when it (or, for nested closures, any of
    its enclosing functions) passes work to the wrapper's ``self._executor``
    callable (the Home-Assistant-free contract that mirrors
    ``hass.async_add_executor_job``).
    """
    source = Path(db_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(db_module.__file__))

    delegated = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "_executor"
            for sub in ast.walk(node)
        )
    }
    assert delegated, "expected executor-delegated functions in db.py"

    violations = []
    for node, chain in _iter_with_scope(tree, ()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sqlite3"
            and not any(f.name in delegated for f in chain)
        ):
            violations.append((node.lineno, node.func.attr))
    assert violations == [], (
        f"Direct sqlite3 calls outside executor-delegated functions: {violations}"
    )


def test_package_wide_sqlite3_scan_excludes_only_db_module() -> None:
    """The package-wide store scan exempts exactly the db module."""
    pkg_dir = Path(db_module.__file__).parent
    scanned = [p.name for p in pkg_dir.glob("*.py") if p.name != "db.py"]
    assert scanned, "expected other package modules to be scanned"
    assert "db.py" not in scanned


# ---------------------------------------------------------------------------
# close(): idempotence and post-close errors
# ---------------------------------------------------------------------------


def test_close_is_idempotent(tmp_path) -> None:
    database, hass = _open_db(tmp_path / "idem.db")
    _run(database.close())
    assert database.connected is False
    _run(database.close())
    assert database.connected is False
    assert hass.async_add_executor_job.await_count == 2
    assert database.rowcount == -1
    assert database.lastrowid is None


def test_operations_after_close_raise_clear_error(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "closed.db")
    _run(database.close())

    async def _txn():
        async with database.transaction():
            pass

    with pytest.raises(RuntimeError, match="closed"):
        _run(database.execute("SELECT 1"))
    with pytest.raises(RuntimeError, match="closed"):
        _run(database.fetch_one("SELECT 1"))
    with pytest.raises(RuntimeError, match="closed"):
        _run(database.fetch_all("SELECT 1"))
    with pytest.raises(RuntimeError, match="closed"):
        _run(database.execute_many("SELECT 1", []))
    with pytest.raises(RuntimeError, match="closed"):
        _run(_txn())


# ---------------------------------------------------------------------------
# Transactions: commit on success, rollback on exception
# ---------------------------------------------------------------------------


def test_transaction_commits_on_success(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "commit.db")
    _run(database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))

    async def _block():
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))

    _run(_block())
    assert _run(database.fetch_all("SELECT name FROM t")) == [("kept",)]
    _run(database.close())


def test_transaction_rolls_back_on_exception(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "rollback.db")
    _run(database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    _run(database.execute("INSERT INTO t (name) VALUES (?)", ("before",)))

    async def _block():
        with pytest.raises(ValueError, match="boom"):
            async with database.transaction():
                await database.execute(
                    "INSERT INTO t (name) VALUES (?)", ("dropped",)
                )
                raise ValueError("boom")

    _run(_block())
    assert _run(database.fetch_all("SELECT name FROM t")) == [("before",)]
    _run(database.close())


async def test_commit_failure_rolls_back_and_next_transaction_works(
    tmp_path,
) -> None:
    """A COMMIT failure rolls back and leaves the wrapper reusable.

    With PRAGMA defer_foreign_keys=ON a violating insert succeeds inside
    the transaction and the foreign-key violation only surfaces at COMMIT.
    The commit error must propagate, the real connection must end up
    outside any transaction, and the next transaction() plus statement
    must run cleanly.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "deferred.db")
    await database.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    await database.execute(
        "CREATE TABLE child ("
        "id INTEGER PRIMARY KEY, "
        "parent_id INTEGER NOT NULL REFERENCES parent(id))"
    )

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        async with database.transaction():
            await database.execute("PRAGMA defer_foreign_keys=ON")
            await database.execute(
                "INSERT INTO child (parent_id) VALUES (?)", (999,)
            )

    assert database._in_transaction is False
    assert database._tx_task is None
    assert database._conn is not None
    assert database._conn.in_transaction is False
    assert await database.fetch_all("SELECT COUNT(*) FROM child") == [(0,)]

    async with database.transaction():
        await database.execute("INSERT INTO parent (id) VALUES (?)", (1,))
        await database.execute(
            "INSERT INTO child (parent_id) VALUES (?)", (1,)
        )
    assert await database.fetch_all("SELECT COUNT(*) FROM child") == [(1,)]
    await database.close()


async def test_cancel_during_open_closes_abandoned_connection(tmp_path) -> None:
    """NQ-PR12-010: cancel during open() must close the settled connection.

    The _open executor job is gated: the open task is cancelled while the
    connect is still in flight, then the worker is allowed to complete it
    anyway.  The settled connection must never be adopted, must be closed
    through a settled executor-backed close before the cancellation
    propagates, and a follow-up open() must succeed cleanly.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(executor_for(hass))

    open_started = asyncio.Event()
    release_open = asyncio.Event()
    jobs: list[str] = []
    captured: dict[str, Any] = {}
    real_add = hass.async_add_executor_job

    async def _gated_add_executor_job(fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        jobs.append(name)
        if name == "_open":
            open_started.set()
            await release_open.wait()
        result = await real_add(fn, *args, **kwargs)
        if name == "_open":
            captured["conn"] = result
        return result

    hass.async_add_executor_job = _gated_add_executor_job

    open_task = asyncio.create_task(database.open(tmp_path / "cancel-open.db"))
    await open_started.wait()
    open_task.cancel()
    await asyncio.sleep(0.05)
    assert database._conn is None, (
        "the cancelled open adopted a connection that was still settling"
    )
    release_open.set()
    with pytest.raises(asyncio.CancelledError):
        await open_task

    assert database.connected is False
    assert "_close_abandoned" in jobs, (
        "the abandoned connection was not closed via an executor job"
    )
    conn = captured.get("conn")
    assert conn is not None

    def _probe() -> str:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return "closed"
        return "open"

    assert await real_add(_probe) == "closed"

    hass.async_add_executor_job = real_add
    await database.open(tmp_path / "cancel-open.db")
    assert database.connected is True
    assert await database.fetch_one("SELECT 1") == (1,)
    await database.close()


async def test_cancel_during_begin_settles_then_rolls_back(tmp_path) -> None:
    """NQ-PR12-007: cancel during BEGIN must not leak a stray transaction.

    The BEGIN executor job is gated: the transaction task is cancelled
    while BEGIN is still in flight, then the worker is allowed to
    complete it anyway.  The wrapper must keep transaction ownership
    until the submitted work settles, roll the completed BEGIN back,
    clear its state, and stay usable for the next transaction.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(executor_for(hass))
    await database.open(tmp_path / "cancel-begin.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    await database.execute("INSERT INTO t (name) VALUES (?)", ("before",))

    begin_started = asyncio.Event()
    release_begin = asyncio.Event()
    real_add = hass.async_add_executor_job

    async def _gated_add_executor_job(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "_begin":
            begin_started.set()
            await release_begin.wait()
        return await real_add(fn, *args, **kwargs)

    hass.async_add_executor_job = _gated_add_executor_job

    async def _txn() -> None:
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))

    txn_task = asyncio.create_task(_txn())
    await begin_started.wait()
    txn_task.cancel()
    await asyncio.sleep(0.05)
    assert database._in_transaction is True, (
        "ownership was released while the cancelled BEGIN was still in flight"
    )
    release_begin.set()
    with pytest.raises(asyncio.CancelledError):
        await txn_task

    assert database._in_transaction is False
    assert database._tx_task is None
    assert database._conn is not None
    assert database._conn.in_transaction is False

    hass.async_add_executor_job = real_add
    assert await database.fetch_all("SELECT name FROM t ORDER BY id") == [
        ("before",)
    ]
    async with database.transaction():
        await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))
    assert await database.fetch_all("SELECT name FROM t ORDER BY id") == [
        ("before",),
        ("kept",),
    ]
    await database.close()


async def test_cancel_during_commit_settles_then_propagates_cancellation(
    tmp_path,
) -> None:
    """NQ-PR12-007: cancel during COMMIT must not mask the cancellation.

    COMMIT is gated; the task is cancelled while it is in flight and the
    worker then completes it anyway.  The cancellation must propagate as
    CancelledError (not be converted by a doomed ROLLBACK of an already
    committed transaction), the connection must end outside any
    transaction, and the wrapper must stay usable.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(executor_for(hass))
    await database.open(tmp_path / "cancel-commit.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

    commit_started = asyncio.Event()
    release_commit = asyncio.Event()
    real_add = hass.async_add_executor_job

    async def _gated_add_executor_job(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "_commit":
            commit_started.set()
            await release_commit.wait()
        return await real_add(fn, *args, **kwargs)

    hass.async_add_executor_job = _gated_add_executor_job

    async def _txn() -> None:
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))

    txn_task = asyncio.create_task(_txn())
    await commit_started.wait()
    txn_task.cancel()
    await asyncio.sleep(0.05)
    assert database._in_transaction is True, (
        "ownership was released while the cancelled COMMIT was still in flight"
    )
    release_commit.set()
    with pytest.raises(asyncio.CancelledError):
        await txn_task

    assert database._in_transaction is False
    assert database._tx_task is None
    assert database._conn is not None
    assert database._conn.in_transaction is False

    hass.async_add_executor_job = real_add
    assert await database.fetch_all("SELECT name FROM t") == [("kept",)]
    async with database.transaction():
        await database.execute("INSERT INTO t (name) VALUES (?)", ("again",))
    assert await database.fetch_all("SELECT name FROM t ORDER BY id") == [
        ("kept",),
        ("again",),
    ]
    await database.close()


async def test_cancel_during_in_transaction_execute_settles_then_rolls_back(
    tmp_path,
) -> None:
    """NQ-PR12-009: cancel during an in-transaction statement must not race ROLLBACK.

    The in-transaction INSERT executor job is gated: the transaction task
    is cancelled while the statement is still in flight, then the worker
    is allowed to complete it anyway.  The ROLLBACK must only run after
    the statement has settled — while the statement is in flight the
    transaction is still open — and the cancelled statement's write must
    not persist.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(executor_for(hass))
    await database.open(tmp_path / "cancel-execute.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    await database.execute("INSERT INTO t (name) VALUES (?)", ("before",))

    insert_started = asyncio.Event()
    release_insert = asyncio.Event()
    real_add = hass.async_add_executor_job

    async def _gated_add_executor_job(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "_execute":
            insert_started.set()
            await release_insert.wait()
        return await real_add(fn, *args, **kwargs)

    hass.async_add_executor_job = _gated_add_executor_job

    async def _txn() -> None:
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("lost",))

    txn_task = asyncio.create_task(_txn())
    await insert_started.wait()
    txn_task.cancel()
    await asyncio.sleep(0.05)
    assert database._in_transaction is True, (
        "ownership was released while the cancelled statement was in flight"
    )
    assert database._conn is not None
    assert database._conn.in_transaction is True, (
        "ROLLBACK ran before the cancelled statement settled"
    )
    release_insert.set()
    with pytest.raises(asyncio.CancelledError):
        await txn_task

    assert database._in_transaction is False
    assert database._tx_task is None
    assert database._conn is not None
    assert database._conn.in_transaction is False

    hass.async_add_executor_job = real_add
    assert await database.fetch_all("SELECT name FROM t ORDER BY id") == [
        ("before",)
    ]
    async with database.transaction():
        await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))
    assert await database.fetch_all("SELECT name FROM t ORDER BY id") == [
        ("before",),
        ("kept",),
    ]
    await database.close()


async def test_commit_and_rollback_failures_are_both_preserved(tmp_path) -> None:
    """NQ-PR12-008: both errors survive when COMMIT and ROLLBACK both fail.

    The COMMIT executor call is forced to fail, and the follow-up
    cleanup ROLLBACK is forced to fail as well.  The raised error must
    keep both original exceptions inspectable instead of discarding the
    commit failure behind the rollback failure.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(executor_for(hass))
    await database.open(tmp_path / "both-fail.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    commit_failure = sqlite3.OperationalError("commit exploded")
    rollback_failure = sqlite3.OperationalError("rollback exploded")
    real_add = hass.async_add_executor_job

    async def _failing_add_executor_job(fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        if name == "_commit":
            raise commit_failure
        if name == "_cleanup":
            raise rollback_failure
        return await real_add(fn, *args, **kwargs)

    hass.async_add_executor_job = _failing_add_executor_job

    with pytest.raises(BaseExceptionGroup) as exc_info:
        async with database.transaction():
            pass

    assert commit_failure in exc_info.value.exceptions
    assert rollback_failure in exc_info.value.exceptions
    assert database._in_transaction is False
    assert database._tx_task is None
    await database.close()


async def test_transaction_persists_across_connections(tmp_path) -> None:
    """A committed transaction is visible to a brand-new connection."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "persist.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    async with database.transaction():
        await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))
    await database.close()

    other = NestQuestDatabase(hass.async_add_executor_job)
    await other.open(tmp_path / "persist.db")
    assert await other.fetch_all("SELECT name FROM t") == [("kept",)]
    await other.close()


# ---------------------------------------------------------------------------
# Serialization: one lock per wrapper, no cross-commit interleaving
# ---------------------------------------------------------------------------


async def test_concurrent_writers_do_not_interleave_commits(tmp_path) -> None:
    """Real-executor proof: nothing commits inside another transaction's span.

    A transaction runner repeatedly counts rows, inserts, and counts again
    inside BEGIN..COMMIT; the count must grow by exactly one, proving no
    other writer committed in between even though several writer tasks fire
    statements concurrently on real executor threads.  Statements issued
    while a transaction is open queue behind it on the wrapper lock.
    """
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "serial.db")
    await database.execute("CREATE TABLE t (kind TEXT, seq INTEGER)")
    tx_rounds, writers, writer_rounds = 6, 5, 8
    total = tx_rounds + writers * writer_rounds

    async def _tx_runner() -> None:
        for rnd in range(tx_rounds):
            async with database.transaction():
                rows = await database.fetch_all("SELECT COUNT(*) FROM t")
                seen = rows[0][0] if rows else -1
                await database.execute(
                    "INSERT INTO t (kind, seq) VALUES (?, ?)", ("tx", rnd)
                )
                rows = await database.fetch_all("SELECT COUNT(*) FROM t")
                grown = rows[0][0] if rows else -1
                if grown != seen + 1:
                    raise AssertionError(
                        f"interleaved commit: count {seen} -> {grown} "
                        f"in tx round {rnd}"
                    )

    async def _writer(worker: int) -> None:
        for rnd in range(writer_rounds):
            await database.execute(
                "INSERT INTO t (kind, seq) VALUES (?, ?)", ("w", worker)
            )

    await asyncio.gather(
        _tx_runner(), *(_writer(w) for w in range(writers))
    )

    rows = await database.fetch_all("SELECT COUNT(*) FROM t")
    assert rows[0][0] == total, f"expected {total} rows, got {rows[0][0]}"
    await database.close()


async def test_transaction_span_excludes_concurrent_transaction(tmp_path) -> None:
    """A second transaction caller is rejected with a clear error."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "reject.db")
    await database.execute("CREATE TABLE t (id INTEGER)")

    started = asyncio.Event()

    async def _first() -> None:
        async with database.transaction():
            started.set()
            await asyncio.sleep(0.05)

    first = asyncio.create_task(_first())
    await started.wait()
    with pytest.raises(RuntimeError, match="transaction"):
        async with database.transaction():
            pass
    await first
    await database.execute("INSERT INTO t (id) VALUES (?)", (1,))
    assert await database.fetch_one("SELECT id FROM t") == (1,)
    await database.close()


async def test_transaction_blocks_other_statements_until_commit(tmp_path) -> None:
    """A statement issued during an open transaction queues behind it."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "block.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

    order: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def _txn() -> None:
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("in_tx",))
            order.append("tx-start")
            started.set()
            await release.wait()
            order.append("tx-end")

    async def _outsider() -> None:
        await started.wait()
        await database.execute("INSERT INTO t (name) VALUES (?)", ("after",))
        order.append("outside")

    txn_task = asyncio.create_task(_txn())
    await started.wait()
    outsider_task = asyncio.create_task(_outsider())
    await asyncio.sleep(0.05)
    assert order == ["tx-start"], f"outsider ran inside transaction: {order}"
    release.set()
    await asyncio.gather(txn_task, outsider_task)
    assert order == ["tx-start", "tx-end", "outside"]
    rows = await database.fetch_all("SELECT name FROM t ORDER BY id")
    assert rows == [("in_tx",), ("after",)]
    await database.close()


async def test_concurrent_transaction_is_rejected_with_clear_error(
    tmp_path,
) -> None:
    """A second concurrent transaction() gets a clear RuntimeError."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "concurrent-tx.db")
    await database.execute("CREATE TABLE t (id INTEGER)")

    started = asyncio.Event()

    async def _first() -> None:
        async with database.transaction():
            started.set()
            await asyncio.sleep(0.05)

    first = asyncio.create_task(_first())
    await started.wait()
    with pytest.raises(RuntimeError, match="transaction"):
        async with database.transaction():
            pass
    await first
    await database.close()


async def test_close_waits_for_in_flight_transaction(tmp_path) -> None:
    """close() serializes: an open transaction finishes before shutdown."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "closerace.db")
    await database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

    started = asyncio.Event()
    release = asyncio.Event()

    async def _txn() -> None:
        async with database.transaction():
            await database.execute("INSERT INTO t (name) VALUES (?)", ("kept",))
            started.set()
            await release.wait()

    txn_task = asyncio.create_task(_txn())
    await started.wait()
    close_task = asyncio.create_task(database.close())
    await asyncio.sleep(0.05)
    assert database.connected is True, "close() raced an open transaction"
    release.set()
    await asyncio.gather(txn_task, close_task)
    assert database.connected is False

    witness = NestQuestDatabase(hass.async_add_executor_job)
    await witness.open(tmp_path / "closerace.db")
    assert await witness.fetch_all("SELECT name FROM t") == [("kept",)]
    await witness.close()


async def test_close_during_transaction_from_same_task_is_rejected(
    tmp_path,
) -> None:
    """close() inside its own transaction body raises instead of deadlocking."""
    hass, _registry = make_hass()
    database = NestQuestDatabase(hass.async_add_executor_job)
    await database.open(tmp_path / "selfclose.db")
    await database.execute("CREATE TABLE t (id INTEGER)")
    with pytest.raises(RuntimeError, match="transaction"):
        async with database.transaction():
            await database.close()
    assert database.connected is True
    await database.close()


# ---------------------------------------------------------------------------
# rowcount / lastrowid surface
# ---------------------------------------------------------------------------


def test_rowcount_and_lastrowid_before_any_operation(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "unset.db")
    assert database.rowcount == -1
    assert database.lastrowid is None
    _run(database.close())


def test_execute_exposes_rowcount_and_lastrowid(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "counts.db")
    _run(database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    _run(database.execute("INSERT INTO t (name) VALUES (?)", ("x",)))
    assert database.rowcount == 1
    assert database.lastrowid == 1
    _run(database.execute("INSERT INTO t (name) VALUES (?)", ("y",)))
    assert database.rowcount == 1
    assert database.lastrowid == 2
    _run(database.close())


def test_execute_many_exposes_rowcount(tmp_path) -> None:
    database, _hass = _open_db(tmp_path / "many.db")
    _run(database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    _run(database.execute_many("INSERT INTO t (name) VALUES (?)", [("a",), ("b",)]))
    assert database.rowcount == 2
    _run(database.execute("INSERT INTO t (name) VALUES (?)", ("c",)))
    assert database.lastrowid == 3
    _run(database.close())


# ---------------------------------------------------------------------------
