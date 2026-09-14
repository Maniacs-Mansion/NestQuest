"""Async SQLite connection wrapper for the NestQuest integration."""
from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant


@dataclass(frozen=True)
class ExecutionResult:
    """Plain-data outcome of one statement.

    ``rowcount`` and ``lastrowid`` mirror the corresponding
    :class:`sqlite3.Cursor` attributes; both are captured on the executor
    thread so no sqlite3 object ever crosses back to the event loop.
    """

    rowcount: int
    lastrowid: int | None


class NestQuestDatabase:
    """Async wrapper around a single SQLite connection.

    Every sqlite3 call is delegated to the Home Assistant executor through
    ``hass.async_add_executor_job`` so the event loop is never blocked, and
    only plain Python data (row tuples and :class:`ExecutionResult`) is
    returned to the event loop.

    Every operation is serialized through one asyncio.Lock per wrapper.  A
    ``transaction()`` holds that lock for its whole BEGIN..COMMIT span, so
    interleaved coroutines cannot corrupt the transaction and concurrent
    BEGINs are impossible; statements issued while a transaction is open
    queue until it completes.  Concurrent transactions on one wrapper are
    not supported: a second ``transaction()`` entered while one is active
    raises :class:`RuntimeError`.  ``close()`` serializes on the same lock
    and is idempotent.

    Every connection-affecting executor job (connect, pragmas, statements,
    transaction lifecycle and close) is awaited through the settlement
    helper :meth:`_await_settled`: if the awaiting task is cancelled while
    a job is in flight, the job still settles on the worker thread before
    the cancellation propagates, so the wrapper lock is never released
    while the executor thread is mid-job.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the wrapper around a Home Assistant instance."""
        self._hass = hass
        self._conn: sqlite3.Connection | None = None
        self._rowcount: int = -1
        self._lastrowid: int | None = None
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._in_transaction = False
        self._tx_task: asyncio.Task | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Return the per-wrapper lock, (re)bound to the running loop.

        HA drives every wrapper call from one event loop, so the lock is
        created once and reused; re-binding only when the running loop
        differs keeps the wrapper usable from plain synchronous drivers
        that run each call on a fresh loop.
        """
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @property
    def connected(self) -> bool:
        """Return True while the underlying connection is open."""
        return self._conn is not None

    @property
    def rowcount(self) -> int:
        """Row count of the most recent statement, or -1 when unset."""
        return self._rowcount

    @property
    def lastrowid(self) -> int | None:
        """Row id of the most recent insert, or None when unset."""
        return self._lastrowid

    @asynccontextmanager
    async def _serialized(self) -> AsyncIterator[None]:
        """Hold the wrapper lock unless the caller owns the active transaction.

        A transaction holds the lock for its whole BEGIN..COMMIT span;
        statements issued by the transaction's own task are already
        serialized by it and must not re-acquire the non-reentrant lock.
        Any other task queues on the lock until the transaction ends.
        """
        if (
            self._in_transaction
            and self._tx_task is not None
            and asyncio.current_task() is self._tx_task
        ):
            yield
            return
        async with self._get_lock():
            yield

    async def open(self, path: Path | str) -> NestQuestDatabase:
        """Open the SQLite file with WAL journal mode and foreign keys on."""
        if self._conn is not None:
            return self
        async with self._get_lock():
            if self._conn is not None:
                return self

            def _open() -> sqlite3.Connection:
                conn = sqlite3.connect(
                    path, check_same_thread=False, isolation_level=None
                )
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
                except BaseException:
                    conn.close()
                    raise
                return conn

            self._conn = await self._await_settled(
                self._hass.async_add_executor_job(_open)
            )
        return self

    async def execute(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> ExecutionResult:
        """Run one statement in the executor and return its plain result."""
        async with self._serialized():
            conn = self._require_conn()

            def _execute() -> ExecutionResult:
                cursor = conn.execute(sql, parameters)
                return ExecutionResult(cursor.rowcount, cursor.lastrowid)

            result = await self._await_settled(
                self._hass.async_add_executor_job(_execute)
            )
            self._rowcount = result.rowcount
            self._lastrowid = result.lastrowid
            return result

    async def execute_many(
        self, sql: str, parameters: Sequence[Sequence[Any]]
    ) -> ExecutionResult:
        """Run executemany in the executor and return its plain result."""
        async with self._serialized():
            conn = self._require_conn()

            def _execute_many() -> ExecutionResult:
                cursor = conn.executemany(sql, parameters)
                return ExecutionResult(cursor.rowcount, cursor.lastrowid)

            result = await self._await_settled(
                self._hass.async_add_executor_job(_execute_many)
            )
            self._rowcount = result.rowcount
            self._lastrowid = result.lastrowid
            return result

    async def fetch_one(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> tuple | None:
        """Run a query in the executor and return its first row, or None."""
        async with self._serialized():
            conn = self._require_conn()

            def _fetch_one() -> tuple[tuple | None, int, int | None]:
                cursor = conn.execute(sql, parameters)
                return cursor.fetchone(), cursor.rowcount, cursor.lastrowid

            row, rowcount, lastrowid = await self._await_settled(
                self._hass.async_add_executor_job(_fetch_one)
            )
            self._rowcount = rowcount
            self._lastrowid = lastrowid
            return row

    async def fetch_all(
        self, sql: str, parameters: Sequence[Any] = ()
    ) -> list[tuple]:
        """Run a query in the executor and return all of its rows."""
        async with self._serialized():
            conn = self._require_conn()

            def _fetch_all() -> tuple[list[tuple], int, int | None]:
                cursor = conn.execute(sql, parameters)
                return cursor.fetchall(), cursor.rowcount, cursor.lastrowid

            rows, rowcount, lastrowid = await self._await_settled(
                self._hass.async_add_executor_job(_fetch_all)
            )
            self._rowcount = rowcount
            self._lastrowid = lastrowid
            return rows

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Run a block inside BEGIN/COMMIT, rolling back on any exception.

        The wrapper lock is held for the entire BEGIN..COMMIT span, so no
        other statement can interleave inside the transaction.  Entering a
        second transaction while one is active raises RuntimeError.  A
        failing COMMIT (e.g. a deferred foreign-key violation) also triggers
        a ROLLBACK before the commit error propagates, so the real
        connection is never left inside a stray transaction.

        The lifecycle is cancellation-safe.  Transaction ownership and the
        wrapper lock are only released after the executor work has fully
        settled, even when the owning task is cancelled mid-flight: if a
        cancelled BEGIN or COMMIT still completes on the worker thread,
        the corresponding ROLLBACK is shielded and awaited before any state
        is cleared.  A lifecycle statement that fails plus a failing
        follow-up cleanup surface both errors in an ExceptionGroup.
        """
        if self._in_transaction:
            raise RuntimeError(
                "A NestQuest transaction is already active on this "
                "connection; concurrent transactions are not supported"
            )
        async with self._get_lock():
            conn = self._require_conn()
            self._in_transaction = True
            self._tx_task = asyncio.current_task()
            try:

                def _begin() -> None:
                    conn.execute("BEGIN")

                await self._settle_lifecycle(
                    conn,
                    self._hass.async_add_executor_job(_begin),
                    "BEGIN did not settle cleanly and the follow-up "
                    "cleanup also raised; the transaction may need manual "
                    "cleanup",
                )
                try:
                    yield
                except BaseException:

                    def _rollback() -> None:
                        conn.execute("ROLLBACK")

                    await self._settle_lifecycle(
                        conn,
                        self._hass.async_add_executor_job(_rollback),
                        "ROLLBACK failed and the follow-up cleanup also "
                        "raised; the transaction may need manual cleanup",
                    )
                    raise

                def _commit() -> None:
                    conn.execute("COMMIT")

                await self._settle_lifecycle(
                    conn,
                    self._hass.async_add_executor_job(_commit),
                    "COMMIT failed and the follow-up cleanup also raised; "
                    "the transaction may need manual cleanup",
                )
            finally:
                self._in_transaction = False
                self._tx_task = None

    async def _settle_lifecycle(
        self, conn: sqlite3.Connection, job: Awaitable[Any], message: str
    ) -> None:
        """Run one BEGIN/ROLLBACK/COMMIT job, then force the connection clean.

        The job always settles first (see :meth:`_await_settled`), so a
        cancelled statement that the worker thread completed anyway is
        never abandoned mid-flight.  If the job raised, a follow-up
        ROLLBACK — itself settled — guarantees the connection ends outside
        any SQLite transaction before the error propagates.  When both the
        job and the cleanup raise, both errors are preserved in an
        ExceptionGroup instead of the original being lost.
        """
        try:
            await self._await_settled(job)
        except BaseException as settle_error:
            errors: list[BaseException] = [settle_error]
            try:
                await self._ensure_no_stray_transaction(conn)
            except BaseException as cleanup_error:
                errors.append(cleanup_error)
            if len(errors) == 2:
                raise BaseExceptionGroup(message, errors) from settle_error
            raise

    async def _ensure_no_stray_transaction(
        self, conn: sqlite3.Connection
    ) -> None:
        """Force the connection out of any transaction via ROLLBACK.

        Runs after a failed or cancelled lifecycle statement.  The worker
        thread may still be finishing (or may already have completed) the
        very statement whose await was cancelled, so both the check and
        the ROLLBACK settle in the executor before the caller releases
        transaction ownership.
        """

        def _cleanup() -> bool:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            return conn.in_transaction

        stray = await self._await_settled(
            self._hass.async_add_executor_job(_cleanup)
        )
        if stray:
            raise RuntimeError(
                "The SQLite connection is still inside a transaction after "
                "cleanup; the transaction may need manual cleanup"
            )

    async def _await_settled(self, job: Awaitable[Any]) -> Any:
        """Await ``job``, letting it settle even if this task is cancelled.

        Cancellation is observed, not swallowed: it is re-raised only once
        the job has fully settled, so the caller can finalize against a
        known connection state instead of abandoning in-flight work.  The
        job is wrapped in a task because a bare coroutine dies un-awaited
        once its await is cancelled.  A second cancellation during
        settlement is absorbed the same way; if the job itself fails after
        a cancellation, both errors surface in an ExceptionGroup.
        """
        cancelled = False
        inner = asyncio.ensure_future(job)
        while not inner.done():
            try:
                await asyncio.shield(inner)
            except asyncio.CancelledError:
                cancelled = True
        try:
            result = inner.result()
        except BaseException as job_error:
            if cancelled:
                raise BaseExceptionGroup(
                    "executor job failed while settling after cancellation",
                    [asyncio.CancelledError(), job_error],
                ) from job_error
            raise
        if cancelled:
            raise asyncio.CancelledError()
        return result

    async def close(self) -> None:
        """Close the connection in the executor; safe to call repeatedly.

        Serialized on the wrapper lock, so an in-flight operation or open
        transaction always completes before the connection is closed.
        """
        if (
            self._in_transaction
            and self._tx_task is not None
            and asyncio.current_task() is self._tx_task
        ):
            raise RuntimeError(
                "Cannot close the NestQuest database from inside its own "
                "transaction; exit the transaction first"
            )
        async with self._get_lock():
            conn, self._conn = self._conn, None
            self._rowcount, self._lastrowid = -1, None
            if conn is None:
                return

            def _close() -> None:
                conn.close()

            await self._await_settled(self._hass.async_add_executor_job(_close))

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(
                "The NestQuest database connection is closed; call open() first"
            )
        return self._conn