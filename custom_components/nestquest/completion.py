"""Business layer for the completion event log (Feature 08).

Sits between the Feature 09 service gate and the typed
:class:`~.dao_instances.CompletionEventsDao`: callers get actor-shape
validation and the UTC occurred-at stamp here, and never talk to the
DAO or SQL directly.  This module is the only Feature-08 caller of
:meth:`~.dao_instances.CompletionEventsDao.append`.  Completing an
instance (no-op if already done) is :func:`complete_instance`;
un-completing (no-op if already open) is :func:`uncomplete_instance`.
Instance current state is derived from the latest event via
:func:`instance_state` (``open`` / ``done`` / ``missed``); there is
no status column.  ``missed`` is derived for past-due open instances
(``due_date`` before HA-local ``today``) and is never stored as an
event_type.

Actor policy matches the schema CHECKs (D-008): ``actor_source`` is
``'user'`` or ``'panel'`` only — never ``'service'``.  ``'user'``
requires ``actor_user_id`` and forbids ``actor_child_id``; ``'panel'``
requires ``actor_child_id`` (the tapped profile) and forbids
``actor_user_id``.  Inverted shapes raise a field-naming ValueError
before any write.

``occurred_at`` is stamped UTC ISO-8601 at second precision with an
explicit ``+00:00`` offset, matching the DAO's one accepted shape so
lexicographic range queries stay exact.  ``was_on_time`` is required
(True/False) for completed events; un-completions may pass None.  There
is no permission check here (that is Feature 09).
"""
from __future__ import annotations

import asyncio
import datetime

from .dao_children import _CONNECTION_LOCKS, _connection_lock
from .dao_instances import (
    EVENT_COMPLETED,
    EVENT_UNCOMPLETED,
    CompletionEventRecord,
    CompletionEventsDao,
    QuestInstanceRecord,
    QuestInstancesDao,
)
from .db import NestQuestDatabase

#: Timestamp policy for completion_events.occurred_at: strict UTC
#: ISO-8601 with explicit '+00:00' offset (module timestamp policy).
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


def _now_stamp() -> str:
    """Return the module's strict UTC second-precision stamp."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        _UTC_TIMESTAMP_FORMAT
    )


def _stamp_occurred_at(now: datetime.datetime | None) -> str:
    """Return a DAO-accepted UTC stamp for ``now``, or the current time."""
    if now is None:
        return _now_stamp()
    if not isinstance(now, datetime.datetime):
        raise ValueError(f"now must be a datetime, got {now!r}")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(datetime.timezone.utc).strftime(
        _UTC_TIMESTAMP_FORMAT
    )


def _completion_moment(
    now: datetime.datetime | None,
    today: datetime.date | None,
) -> tuple[datetime.date, datetime.time | None]:
    """Return the HA-local completion date and optional wall-clock time.

    ``today`` is the HA-local calendar date when threaded (Feature 07
    style).  ``now`` is a timezone-aware HA-local datetime; its wall
    clock is used as-is and is never converted to UTC.  When ``today``
    is omitted the date comes from ``now``.  When both are omitted the
    host calendar date is the Feature 07 fallback — never the UTC
    clock.  Time-of-day is None unless ``now`` is supplied; comparing
    against ``due_time`` requires ``now``.
    """
    if now is not None:
        if not isinstance(now, datetime.datetime):
            raise ValueError(f"now must be a datetime, got {now!r}")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
    if today is not None:
        completion_date = today
    elif now is not None:
        completion_date = now.date()
    else:
        completion_date = datetime.date.today()
    if now is None:
        return completion_date, None
    return completion_date, now.time()


def _resolve_today(today: datetime.date | None) -> datetime.date:
    """Return the threaded HA-local date, or the host calendar date."""
    if today is None:
        return datetime.date.today()
    return today


def _derived_state(
    instance: QuestInstanceRecord,
    latest: CompletionEventRecord | None,
    today: datetime.date,
) -> str:
    """Return ``open``, ``done``, or ``missed`` from event plus due date.

    A latest completed event is ``done`` even when past due.  No events
    or a latest uncompleted event is ``open``, or ``missed`` when
    ``due_date`` is before ``today``.  ``missed`` is never an event_type.
    """
    if latest is None or latest.event_type == EVENT_UNCOMPLETED:
        due_date = datetime.date.fromisoformat(instance.due_date)
        if due_date < today:
            return "missed"
        return "open"
    if latest.event_type == EVENT_COMPLETED:
        return "done"
    raise ValueError(
        f"event_type must be '{EVENT_COMPLETED}' or "
        f"'{EVENT_UNCOMPLETED}', got {latest.event_type!r}"
    )


def _was_on_time(
    instance: QuestInstanceRecord,
    now: datetime.datetime | None,
    today: datetime.date | None,
) -> bool:
    """Return whether the completion moment is on time for ``instance``.

    On ``due_date`` before ``due_time`` is on time; on ``due_date``
    after ``due_time``, or any later date, is late.  With no
    ``due_time``, on time if the completion date equals ``due_date``
    (or is earlier); late if after ``due_date``.  Same-day
    ``due_time`` comparison requires ``now``; UTC time-of-day is never
    substituted.
    """
    completion_date, completion_time = _completion_moment(now, today)
    due_date = datetime.date.fromisoformat(instance.due_date)
    if completion_date < due_date:
        return True
    if completion_date > due_date:
        return False
    if instance.due_time is None:
        return True
    if completion_time is None:
        raise ValueError("now is required to compare due_time")
    due_time = datetime.datetime.strptime(instance.due_time, "%H:%M").time()
    return completion_time <= due_time


class _TaskReentrantLock:
    """Shared connection lock the owning task may re-enter."""

    def __init__(self, inner: asyncio.Lock) -> None:
        self._inner = inner
        self._task: asyncio.Task | None = None
        self._depth = 0

    def locked(self) -> bool:
        return self._inner.locked()

    async def acquire(self) -> bool:
        task = asyncio.current_task()
        if self._task is task:
            self._depth += 1
            return True
        await self._inner.acquire()
        self._task = task
        self._depth = 1
        return True

    def release(self) -> None:
        if self._task is not asyncio.current_task():
            raise RuntimeError("lock released by a non-owner")
        self._depth -= 1
        if self._depth == 0:
            self._task = None
            self._inner.release()

    async def __aenter__(self) -> _TaskReentrantLock:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()


def _reentrant_connection_lock(database) -> _TaskReentrantLock:
    """Return the shared connection lock, made task-reentrant.

    ``CompletionEventsDao.append`` also acquires this lock, so
    check+append in :func:`complete_instance` and
    :func:`uncomplete_instance` must re-enter on the same task.  The
    wrapper is stored in the shared dict so the DAO sees the same
    object.
    """
    loop = asyncio.get_running_loop()
    key = (id(database), id(loop))
    lock = _CONNECTION_LOCKS.get(key)
    if isinstance(lock, _TaskReentrantLock):
        return lock
    wrapped = _TaskReentrantLock(
        lock if lock is not None else asyncio.Lock()
    )
    _CONNECTION_LOCKS[key] = wrapped
    return wrapped


def _validate_int_id(value: object, field: str) -> int:
    """Reject non-int ids (bools included) before any lookup."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer, got {value!r}")
    return value


def _validate_event_type(value: object) -> str:
    """Return a schema-legal event type, or raise naming the field."""
    if value not in (EVENT_COMPLETED, EVENT_UNCOMPLETED):
        raise ValueError(
            f"event_type must be '{EVENT_COMPLETED}' or "
            f"'{EVENT_UNCOMPLETED}', got {value!r}"
        )
    return value


def _validate_actor(
    actor_source: object,
    actor_user_id: object,
    actor_child_id: object,
) -> tuple[str, str | None, int | None]:
    """Return a schema-legal actor triple, or raise naming the field.

    ``'user'`` requires a non-empty ``actor_user_id`` string and forbids
    ``actor_child_id``.  ``'panel'`` requires an integer
    ``actor_child_id`` and forbids ``actor_user_id``.  Any other
    ``actor_source`` (including ``'service'``) is rejected.
    """
    if actor_source not in ("user", "panel"):
        raise ValueError(
            f"actor_source must be 'user' or 'panel', got {actor_source!r}"
        )
    if actor_source == "user":
        if not isinstance(actor_user_id, str) or not actor_user_id.strip():
            raise ValueError("actor_source 'user' requires actor_user_id")
        if actor_child_id is not None:
            raise ValueError(
                "actor_source 'user' must not carry actor_child_id"
            )
        return "user", actor_user_id.strip(), None
    if actor_user_id is not None:
        raise ValueError("actor_source 'panel' must not carry actor_user_id")
    if actor_child_id is None:
        raise ValueError(
            "actor_source 'panel' requires actor_child_id"
        )
    return (
        "panel",
        None,
        _validate_int_id(actor_child_id, "actor_child_id"),
    )


def _validate_was_on_time(
    event_type: str, was_on_time: object
) -> bool | None:
    """Return a real bool or None; completed events require True/False."""
    if was_on_time is not None and type(was_on_time) is not bool:
        raise ValueError(
            f"was_on_time must be True, False or None, got {was_on_time!r}"
        )
    if event_type == EVENT_COMPLETED and was_on_time is None:
        raise ValueError(
            "a completed event requires was_on_time (True/False)"
        )
    return was_on_time


async def append_event(
    database: NestQuestDatabase,
    instance_id: int,
    child_id: int,
    event_type: str,
    *,
    actor_source: str,
    actor_user_id: str | None = None,
    actor_child_id: int | None = None,
    was_on_time: bool | None = None,
    now: datetime.datetime | None = None,
) -> CompletionEventRecord:
    """Append one completion or un-completion event and return the row.

    Validates actor shapes and the completed-event on-time requirement
    before calling :meth:`CompletionEventsDao.append`.  ``occurred_at``
    is stamped here (UTC ``+00:00``); pass ``now`` to pin the clock.
    """
    instance_id = _validate_int_id(instance_id, "instance_id")
    child_id = _validate_int_id(child_id, "child_id")
    event_type = _validate_event_type(event_type)
    actor_source, actor_user_id, actor_child_id = _validate_actor(
        actor_source, actor_user_id, actor_child_id
    )
    was_on_time = _validate_was_on_time(event_type, was_on_time)
    occurred_at = _stamp_occurred_at(now)
    return await CompletionEventsDao(database).append(
        instance_id,
        child_id,
        event_type,
        actor_source,
        occurred_at,
        was_on_time,
        actor_user_id=actor_user_id,
        actor_child_id=actor_child_id,
    )


async def instance_state(
    database: NestQuestDatabase,
    instance_id: int,
    *,
    today: datetime.date | None = None,
) -> str:
    """Return ``open``, ``done``, or ``missed`` from the latest event.

    No events, or a latest event of uncompleted, is ``open`` unless
    ``due_date`` is before ``today`` (HA-local, threaded), in which
    case it is ``missed``.  A latest event of completed is ``done``
    even when past due.  ``missed`` is never stored as an event_type.
    Unknown ``instance_id`` raises ValueError naming the field.
    Existence and the latest event are read inside the connection lock
    so the answer is one snapshot.
    """
    instance_id = _validate_int_id(instance_id, "instance_id")
    today_date = _resolve_today(today)
    async with _connection_lock(database):
        instance = await QuestInstancesDao(database).get_by_id(instance_id)
        if instance is None:
            raise ValueError(
                f"instance_id: quest instance {instance_id} does not exist"
            )
        latest = await CompletionEventsDao(database).get_latest_for_instance(
            instance_id
        )
    return _derived_state(instance, latest, today_date)


async def complete_instance(
    database: NestQuestDatabase,
    instance_id: int,
    *,
    actor_source: str,
    actor_user_id: str | None = None,
    actor_child_id: int | None = None,
    now: datetime.datetime | None = None,
    today: datetime.date | None = None,
) -> str:
    """Append a completed event unless the instance is already done.

    Returns the derived state ``done``.  An already-done instance is a
    no-op: nothing is appended.  Unknown ``instance_id`` raises
    ValueError naming the field.  Existence, latest-event, and the
    append run under one connection lock so a concurrent complete
    cannot double-append.

    ``was_on_time`` is computed from the HA-local completion moment
    (threaded ``now`` / ``today``) against the instance ``due_date``
    and optional ``due_time``.  ``now`` is the timezone-aware HA-local
    datetime; its wall clock is never converted to UTC.  Same-day
    ``due_time`` comparison requires ``now``.
    """
    instance_id = _validate_int_id(instance_id, "instance_id")
    actor_source, actor_user_id, actor_child_id = _validate_actor(
        actor_source, actor_user_id, actor_child_id
    )
    async with _reentrant_connection_lock(database):
        instance = await QuestInstancesDao(database).get_by_id(instance_id)
        if instance is None:
            raise ValueError(
                f"instance_id: quest instance {instance_id} does not exist"
            )
        latest = await CompletionEventsDao(database).get_latest_for_instance(
            instance_id
        )
        if latest is not None and latest.event_type == EVENT_COMPLETED:
            return "done"
        if latest is not None and latest.event_type != EVENT_UNCOMPLETED:
            raise ValueError(
                f"event_type must be '{EVENT_COMPLETED}' or "
                f"'{EVENT_UNCOMPLETED}', got {latest.event_type!r}"
            )
        await append_event(
            database,
            instance.id,
            instance.child_id,
            EVENT_COMPLETED,
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            actor_child_id=actor_child_id,
            was_on_time=_was_on_time(instance, now, today),
            now=now,
        )
    return "done"


async def uncomplete_instance(
    database: NestQuestDatabase,
    instance_id: int,
    *,
    actor_source: str,
    actor_user_id: str | None = None,
    actor_child_id: int | None = None,
    now: datetime.datetime | None = None,
    today: datetime.date | None = None,
) -> str:
    """Append an uncompleted event unless the instance is already open.

    Returns the derived state ``open``, or ``missed`` when the instance
    is past due (``due_date`` before HA-local ``today``).  An
    already-open instance is a no-op: nothing is appended.  Unknown
    ``instance_id`` raises ValueError naming the field.  Existence,
    latest-event, and the append run under one connection lock so a
    concurrent uncomplete cannot double-append.  The original completed
    row is not modified.
    """
    instance_id = _validate_int_id(instance_id, "instance_id")
    actor_source, actor_user_id, actor_child_id = _validate_actor(
        actor_source, actor_user_id, actor_child_id
    )
    today_date = _resolve_today(today)
    async with _reentrant_connection_lock(database):
        instance = await QuestInstancesDao(database).get_by_id(instance_id)
        if instance is None:
            raise ValueError(
                f"instance_id: quest instance {instance_id} does not exist"
            )
        latest = await CompletionEventsDao(database).get_latest_for_instance(
            instance_id
        )
        if latest is None or latest.event_type == EVENT_UNCOMPLETED:
            return _derived_state(instance, latest, today_date)
        if latest.event_type != EVENT_COMPLETED:
            raise ValueError(
                f"event_type must be '{EVENT_COMPLETED}' or "
                f"'{EVENT_UNCOMPLETED}', got {latest.event_type!r}"
            )
        latest = await append_event(
            database,
            instance.id,
            instance.child_id,
            EVENT_UNCOMPLETED,
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            actor_child_id=actor_child_id,
            was_on_time=None,
            now=now,
        )
    return _derived_state(instance, latest, today_date)


async def list_missed_for_child(
    database: NestQuestDatabase,
    child_id: int,
    range_start: str,
    range_end: str,
    *,
    today: datetime.date | None = None,
) -> list[QuestInstanceRecord]:
    """Return the child's missed instances due in the closed date range.

    Missed means the latest event state is open and ``due_date`` is
    before ``today`` (HA-local, threaded).  Uses
    :meth:`QuestInstancesDao.list_by_date_range` plus derived state.
    Never appends a missed event.  Instances and latest events are
    read inside the connection lock so the list is one snapshot.
    """
    child_id = _validate_int_id(child_id, "child_id")
    today_date = _resolve_today(today)
    async with _connection_lock(database):
        instances = await QuestInstancesDao(database).list_by_date_range(
            child_id, range_start, range_end
        )
        events = CompletionEventsDao(database)
        missed: list[QuestInstanceRecord] = []
        for instance in instances:
            latest = await events.get_latest_for_instance(instance.id)
            if _derived_state(instance, latest, today_date) == "missed":
                missed.append(instance)
    return missed
