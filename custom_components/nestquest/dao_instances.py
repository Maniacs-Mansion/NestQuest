"""Typed DAO layer for quest_instances and the append-only completion_events.

All SQL for these tables lives in this module per the feature
guardrails: callers get typed dataclasses back and never see raw rows
or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Append-only policy (Feature 08, D-005): ``completion_events`` is
strictly append-only.  This module is where that property is enforced
mechanically — the completion-events DAO below exposes NO update or
delete method at all; completions append, un-completions append a
separate reversal event, and instance state derives from the latest
event.  A package-wide guard test (bottom of the test module) keeps
mutation SQL for this table out of every other module.

Upsert semantics: ``QuestInstancesDao.upsert`` is idempotent on
(definition_id, due_date) — re-running materialization for a date
whose instance already exists updates nothing that matters
(child_id/due_time are refreshed only in the degenerate re-generation
case where they changed) and never duplicates a row.  The schema's
UNIQUE(definition_id, due_date) is the last line of defense.

``delete_future_uncompleted`` implements the Feature 06/07 rule that
reassignment and schedule edits regenerate future instances: it
removes only instances at or after the cutoff that have NO completion
event, inside one transaction, so an instance completed mid-call can
never be deleted.  Instances in the past are never touched (Feature 07
guardrail: never delete history), and no method here deletes a single
instance that has a completion event.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from .dao_children import _connection_lock
from .dao_rules import _validate_date
from .db import NestQuestDatabase

#: Timestamp policy for completion_events.occurred_at: strict UTC
#: ISO-8601 with explicit '+00:00' offset (module timestamp policy).
#: One accepted shape bounds lexicographic range queries correctly, so
#: the occurred-at scope does not guess at timestamp spellings.
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


def _validate_utc_timestamp(value: str, field: str) -> None:
    """Raise ValueError unless ``value`` is a strict UTC ISO-8601 stamp.

    Same strictness policy as _validate_date: parse with the exact
    format, then round-trip the parsed value against the input so
    non-padded or re-ordered shapes are rejected.  The round-trip
    strips the UTC offset (isoformat() omits it when the offset is
    zero), so the suffix is appended before comparing.
    """
    try:
        parsed = datetime.datetime.strptime(
            value, _UTC_TIMESTAMP_FORMAT
        )
    except (TypeError, ValueError):
        raise ValueError(
            f"{field} must be a UTC ISO-8601 timestamp "
            f"(YYYY-MM-DDTHH:MM:SS+00:00), got {value!r}"
        ) from None
    if parsed.isoformat() + "+00:00" != value:
        raise ValueError(
            f"{field} must be a strict UTC timestamp "
            f"(YYYY-MM-DDTHH:MM:SS+00:00), got {value!r}"
        )


def _next_day_start(date_str: str) -> str:
    """Return the UTC timestamp one second past ``date_str``'s last second.

    Gives range queries an exact half-open upper bound without
    fractional-second guessing.
    """
    day = datetime.date.fromisoformat(date_str)
    next_day = day + datetime.timedelta(days=1)
    return f"{next_day.isoformat()}T00:00:00+00:00"


@dataclass(frozen=True)
class QuestInstanceRecord:
    """One row of ``quest_instances``."""

    id: int
    definition_id: int
    child_id: int
    due_date: str
    due_time: str | None
    generated_at: str


@dataclass(frozen=True)
class CompletionEventRecord:
    """One row of ``completion_events`` (append-only table)."""

    id: int
    instance_id: int
    child_id: int
    event_type: str
    actor_source: str
    actor_user_id: str | None
    occurred_at: str
    was_on_time: bool | None


_INSTANCE_COLUMNS = (
    "id, definition_id, child_id, due_date, due_time, generated_at"
)
_EVENT_COLUMNS = (
    "id, instance_id, child_id, event_type, actor_source, actor_user_id, "
    "occurred_at, was_on_time"
)

#: The only event types the append path accepts; the schema CHECK is
#: the backstop, this is the DAO's typed front door.
EVENT_COMPLETED = "completed"
EVENT_UNCOMPLETED = "uncompleted"


def _instance_from_row(row: tuple) -> QuestInstanceRecord:
    return QuestInstanceRecord(
        id=row[0],
        definition_id=row[1],
        child_id=row[2],
        due_date=row[3],
        due_time=row[4],
        generated_at=row[5],
    )


def _event_from_row(row: tuple) -> CompletionEventRecord:
    return CompletionEventRecord(
        id=row[0],
        instance_id=row[1],
        child_id=row[2],
        event_type=row[3],
        actor_source=row[4],
        actor_user_id=row[5],
        occurred_at=row[6],
        was_on_time=None if row[7] is None else bool(row[7]),
    )


class QuestInstancesDao:
    """Typed async access to the ``quest_instances`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def upsert(
        self,
        definition_id: int,
        child_id: int,
        due_date: str,
        generated_at: str,
        *,
        due_time: str | None = None,
    ) -> QuestInstanceRecord:
        """Create the dated instance for (definition_id, due_date) idempotently.

        Running materialization twice for the same definition/date
        yields ONE row: the ON CONFLICT path refreshes the
        generation-time snapshot columns (child_id, due_time) and
        regenerates the stamp, but can never create a duplicate — the
        schema UNIQUE(definition_id, due_date) backs this up.

        Guardrails enforced here:

        - ``due_date`` must be TODAY or later: instances are never
          generated in the past (Feature 07).  The caller's
          materialization horizon is future-dated by definition.
        - An existing instance WITH a completion event is IMMUTABLE:
          the conflict path must not rewrite its snapshot columns
          (Feature 07/08).  The upsert refuses with ValueError in that
          case — silently no-oping would mask a materialization bug.

        The definition must exist (validated atomically under the
        connection lock so a concurrent definition deactivation or
        child deletion cannot slip between check and insert).
        """
        _validate_date(due_date, "due_date")
        # Fail fast on obviously-past dates BEFORE queuing on the
        # connection lock (a nice early error); the AUTHORITATIVE
        # check runs after the lock is acquired, because a caller can
        # wait on the lock across midnight — a date that was "today"
        # at call time may be "yesterday" by the time the INSERT runs.
        today = datetime.date.today().isoformat()
        if due_date < today:
            raise ValueError(
                f"instances are never generated in the past: due_date "
                f"{due_date!r} is before today {today!r}"
            )
        async with _connection_lock(self._database):
            async with self._database.transaction():
                # Re-read "today" under the lock: this is the date the
                # insert actually executes on, so the no-past rule
                # holds across midnight rollovers.
                today = datetime.date.today().isoformat()
                if due_date < today:
                    raise ValueError(
                        f"instances are never generated in the past: "
                        f"due_date {due_date!r} is before today "
                        f"{today!r}"
                    )
                definition = await self._database.fetch_one(
                    "SELECT child_id FROM quest_definitions WHERE id = ?",
                    (definition_id,),
                )
                if definition is None:
                    raise ValueError(
                        f"quest definition {definition_id} does not exist"
                    )
                if definition[0] != child_id:
                    raise ValueError(
                        f"quest definition {definition_id} is assigned to "
                        f"child {definition[0]}, not {child_id}; instance "
                        "must carry the definition's assignee"
                    )
                child = await self._database.fetch_one(
                    "SELECT 1 FROM children WHERE id = ?", (child_id,)
                )
                if child is None:
                    raise ValueError(f"child {child_id} does not exist")
                existing = await self._database.fetch_one(
                    "SELECT 1 FROM completion_events "
                    "WHERE instance_id = (SELECT id FROM quest_instances "
                    "WHERE definition_id = ? AND due_date = ?)",
                    (definition_id, due_date),
                )
                if existing is not None:
                    raise ValueError(
                        f"instance for (definition {definition_id}, "
                        f"due_date {due_date!r}) already has a completion "
                        "event and is immutable; it cannot be regenerated"
                    )
                await self._database.execute(
                    "INSERT INTO quest_instances (definition_id, child_id, "
                    "due_date, due_time, generated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (definition_id, due_date) DO UPDATE SET "
                    "child_id = excluded.child_id, "
                    "due_time = excluded.due_time, "
                    "generated_at = excluded.generated_at",
                    (
                        definition_id,
                        child_id,
                        due_date,
                        due_time,
                        generated_at,
                    ),
                )
                instance = await self.get(definition_id, due_date)
        assert instance is not None
        return instance

    async def get(
        self, definition_id: int, due_date: str
    ) -> QuestInstanceRecord | None:
        """Return the instance for (definition_id, due_date), or None."""
        row = await self._database.fetch_one(
            f"SELECT {_INSTANCE_COLUMNS} FROM quest_instances "
            "WHERE definition_id = ? AND due_date = ?",
            (definition_id, due_date),
        )
        return _instance_from_row(row) if row is not None else None

    async def get_by_id(self, instance_id: int) -> QuestInstanceRecord | None:
        """Return the instance with ``instance_id``, or None."""
        row = await self._database.fetch_one(
            f"SELECT {_INSTANCE_COLUMNS} FROM quest_instances WHERE id = ?",
            (instance_id,),
        )
        return _instance_from_row(row) if row is not None else None

    async def list_by_child_and_date(
        self, child_id: int, due_date: str
    ) -> list[QuestInstanceRecord]:
        """Return the child's instances due exactly on ``due_date``."""
        _validate_date(due_date, "due_date")
        rows = await self._database.fetch_all(
            f"SELECT {_INSTANCE_COLUMNS} FROM quest_instances "
            "WHERE child_id = ? AND due_date = ? ORDER BY id",
            (child_id, due_date),
        )
        return [_instance_from_row(row) for row in rows]

    async def list_by_date_range(
        self,
        child_id: int,
        range_start: str,
        range_end: str,
    ) -> list[QuestInstanceRecord]:
        """Return the child's instances with due_date in the closed range."""
        _validate_date(range_start, "range_start")
        _validate_date(range_end, "range_end")
        if range_end < range_start:
            raise ValueError(
                "range_end must be on or after range_start, got "
                f"{range_end!r} < {range_start!r}"
            )
        rows = await self._database.fetch_all(
            f"SELECT {_INSTANCE_COLUMNS} FROM quest_instances "
            "WHERE child_id = ? AND due_date >= ? AND due_date <= ? "
            "ORDER BY due_date, id",
            (child_id, range_start, range_end),
        )
        return [_instance_from_row(row) for row in rows]

    async def delete_future_uncompleted(
        self, definition_id: int, cutoff_date: str
    ) -> int:
        """Delete the definition's open instances at/after cutoff.

        Implements regeneration after a definition edit or reassignment
        (Features 06/07): only instances at or after the cutoff with NO
        completion event are removed, inside one transaction — an
        instance that gains a completion event mid-flight cannot be
        deleted.  The cutoff cannot be backdated below today: "future"
        is measured against TODAY (materialization regenerates the
        rolling horizon from now), so a caller cannot use this to
        rewrite past open instances either — the day-rollover missed
        sweep (Feature 11) handles past-due instances instead.  Any
        instance with a completion event is never touched, regardless
        of its date.  Returns the number deleted.
        """
        _validate_date(cutoff_date, "cutoff_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                # "today" is read under the lock: the DELETE actually
                # executes on this date, so a caller queued across
                # midnight cannot delete instances that became past
                # while it waited (backdating is clamped to the
                # execution date, not the call date).
                today = datetime.date.today().isoformat()
                effective_cutoff = max(cutoff_date, today)
                result = await self._database.execute(
                    "DELETE FROM quest_instances WHERE definition_id = ? "
                    "AND due_date >= ? AND NOT EXISTS ("
                    "  SELECT 1 FROM completion_events "
                    "  WHERE instance_id = quest_instances.id"
                    ")",
                    (definition_id, effective_cutoff),
                )
        return result.rowcount


class CompletionEventsDao:
    """Typed append-only access to the ``completion_events`` table.

    APPEND-ONLY BY CONSTRUCTION: this class exposes ``append`` and the
    three read methods below, and NOTHING else.  There is no update,
    no delete, no upsert — completions and un-completions both arrive
    through :meth:`append` as new rows, and history is immutable
    (Feature 08 done-condition: no code path updates or deletes an
    event).  The package-wide leak-guard test additionally fails if
    mutation SQL for this table ever appears in any module.
    """

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def append(
        self,
        instance_id: int,
        child_id: int,
        event_type: str,
        actor_source: str,
        occurred_at: str,
        was_on_time: bool | None,
        *,
        actor_user_id: str | None = None,
    ) -> CompletionEventRecord:
        """Append one completion or un-completion event.

        ``actor_source`` is 'user' (with ``actor_user_id`` set) or
        'panel' (no user id — the tapped child is ``child_id``); the
        actor-pair CHECK enforces this shape at the schema level.
        ``occurred_at`` must be the module's one strict UTC shape
        (YYYY-MM-DDTHH:MM:SS+00:00) so lexicographic range queries
        stay exact.  ``was_on_time`` is required (True/False) for
        completions; for un-completions it may be None or the reversed
        completion's flag (Feature 08 still deciding).  The instance
        and child must exist — validated atomically under the
        connection lock.
        """
        if event_type not in (EVENT_COMPLETED, EVENT_UNCOMPLETED):
            raise ValueError(
                f"event_type must be '{EVENT_COMPLETED}' or "
                f"'{EVENT_UNCOMPLETED}', got {event_type!r}"
            )
        if actor_source not in ("user", "panel"):
            raise ValueError(
                f"actor_source must be 'user' or 'panel', got "
                f"{actor_source!r}"
            )
        if actor_source == "user" and not actor_user_id:
            raise ValueError(
                "actor_source 'user' requires actor_user_id"
            )
        if actor_source == "panel" and actor_user_id is not None:
            raise ValueError(
                "actor_source 'panel' must not carry actor_user_id"
            )
        if was_on_time is not None and type(was_on_time) is not bool:
            raise ValueError(
                f"was_on_time must be True, False or None, got "
                f"{was_on_time!r}"
            )
        if event_type == EVENT_COMPLETED and was_on_time is None:
            raise ValueError(
                "a completed event requires was_on_time (True/False)"
            )
        _validate_utc_timestamp(occurred_at, "occurred_at")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                instance = await self._database.fetch_one(
                    "SELECT child_id FROM quest_instances WHERE id = ?",
                    (instance_id,),
                )
                if instance is None:
                    raise ValueError(
                        f"quest instance {instance_id} does not exist"
                    )
                if instance[0] != child_id:
                    raise ValueError(
                        f"quest instance {instance_id} belongs to child "
                        f"{instance[0]}, not {child_id}"
                    )
                child = await self._database.fetch_one(
                    "SELECT 1 FROM children WHERE id = ?", (child_id,)
                )
                if child is None:
                    raise ValueError(f"child {child_id} does not exist")
                result = await self._database.execute(
                    "INSERT INTO completion_events (instance_id, child_id, "
                    "event_type, actor_source, actor_user_id, occurred_at, "
                    "was_on_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        instance_id,
                        child_id,
                        event_type,
                        actor_source,
                        actor_user_id,
                        occurred_at,
                        None if was_on_time is None else int(was_on_time),
                    ),
                )
                event = await self._database.fetch_one(
                    f"SELECT {_EVENT_COLUMNS} FROM completion_events "
                    "WHERE id = ?",
                    (result.lastrowid,),
                )
        assert event is not None
        return _event_from_row(event)

    async def list_by_instance(
        self, instance_id: int
    ) -> list[CompletionEventRecord]:
        """Return every event for the instance, in append order."""
        rows = await self._database.fetch_all(
            f"SELECT {_EVENT_COLUMNS} FROM completion_events "
            "WHERE instance_id = ? ORDER BY id",
            (instance_id,),
        )
        return [_event_from_row(row) for row in rows]

    async def list_by_child_and_date_range(
        self,
        child_id: int,
        range_start: str,
        range_end: str,
        *,
        due_date_scope: bool = True,
    ) -> list[CompletionEventRecord]:
        """Return the child's events for instances due in the closed range.

        Scopes by the INSTANCE's due date (the day the task was owed),
        not the event's wall-clock timestamp: history reporting asks
        "what happened to the tasks due that day" (Feature 13).  Set
        ``due_date_scope=False`` to filter by ``occurred_at`` date
        instead.  Ordered by instance, then event id.
        """
        _validate_date(range_start, "range_start")
        _validate_date(range_end, "range_end")
        if range_end < range_start:
            raise ValueError(
                "range_end must be on or after range_start, got "
                f"{range_end!r} < {range_start!r}"
            )
        if due_date_scope:
            predicate = (
                "SELECT id FROM quest_instances WHERE child_id = ? "
                "AND due_date >= ? AND due_date <= ?"
            )
            parameters: list[object] = [child_id, range_start, range_end]
        else:
            # Occurred-at scope: occurred_at is validated to the one
            # accepted UTC shape at append time, so half-open day
            # bounds in that same shape are exact (no spelling drift).
            occurred_start = f"{range_start}T00:00:00+00:00"
            occurred_end = f"{range_end}T23:59:59+00:00"
            query = (
                f"SELECT {_EVENT_COLUMNS} FROM completion_events "
                "WHERE child_id = ? AND occurred_at >= ? "
                "AND occurred_at < ? ORDER BY instance_id, id"
            )
            rows = await self._database.fetch_all(
                query,
                [
                    child_id,
                    occurred_start,
                    _next_day_start(range_end),
                ],
            )
            return [_event_from_row(row) for row in rows]
        rows = await self._database.fetch_all(
            f"SELECT {_EVENT_COLUMNS} FROM completion_events "
            f"WHERE instance_id IN ({predicate}) "
            "ORDER BY instance_id, id",
            tuple(parameters),
        )
        return [_event_from_row(row) for row in rows]

    async def get_latest_for_instance(
        self, instance_id: int
    ) -> CompletionEventRecord | None:
        """Return the instance's most recent event, or None if untouched.

        Instance current state derives from this event (Feature 08):
        'completed' means done, 'uncompleted' as the latest means open
        again, None means never completed.
        """
        row = await self._database.fetch_one(
            f"SELECT {_EVENT_COLUMNS} FROM completion_events "
            "WHERE instance_id = ? ORDER BY id DESC LIMIT 1",
            (instance_id,),
        )
        return _event_from_row(row) if row is not None else None