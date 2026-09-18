"""Business layer for the completion event log (Feature 08).

Sits between the Feature 09 service gate and the typed
:class:`~.dao_instances.CompletionEventsDao`: callers get actor-shape
validation and the UTC occurred-at stamp here, and never talk to the
DAO or SQL directly.  This module is the only Feature-08 caller of
:meth:`~.dao_instances.CompletionEventsDao.append`.  Completing and
un-completing an instance (no-op-if-already-done) arrive in later
tasks.  Instance current state is derived from the latest event via
:func:`instance_state` (``open`` / ``done``); there is no status
column.

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

import datetime

from .dao_children import _connection_lock
from .dao_instances import (
    EVENT_COMPLETED,
    EVENT_UNCOMPLETED,
    CompletionEventRecord,
    CompletionEventsDao,
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
) -> str:
    """Return ``open`` or ``done`` from the instance's latest event.

    No events, or a latest event of uncompleted, is ``open``.  A latest
    event of completed is ``done``.  Unknown ``instance_id`` raises
    ValueError naming the field.  Existence and the latest event are
    read inside the connection lock so the answer is one snapshot.
    """
    instance_id = _validate_int_id(instance_id, "instance_id")
    async with _connection_lock(database):
        instance = await QuestInstancesDao(database).get_by_id(instance_id)
        if instance is None:
            raise ValueError(
                f"instance_id: quest instance {instance_id} does not exist"
            )
        latest = await CompletionEventsDao(database).get_latest_for_instance(
            instance_id
        )
    if latest is None or latest.event_type == EVENT_UNCOMPLETED:
        return "open"
    if latest.event_type == EVENT_COMPLETED:
        return "done"
    raise ValueError(
        f"event_type must be '{EVENT_COMPLETED}' or "
        f"'{EVENT_UNCOMPLETED}', got {latest.event_type!r}"
    )
