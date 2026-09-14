"""Typed DAO layer for the presence_schedules and presence_overrides tables.

All SQL for these tables lives in this module per the feature
guardrails: callers get typed dataclasses back and never see raw rows
or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Semantics per the done-condition and Feature 05:

- A child has AT MOST ONE presence schedule (schema UNIQUE); upserting
  by child updates the existing row rather than raising.
- A child with NO schedule row is present every day — the absence of a
  row is meaningful state, expressed by :meth:`PresenceSchedulesDao.get_by_child`
  returning None, never by an empty pattern row.
- Overrides beat the pattern for their date range (that resolution is
  the presence engine's job, Feature 05); the DAO only stores and
  lists them.  A single-day override stores the same date as both
  start and end (schema CHECK requires end >= start).

Date arguments are validated as strict YYYY-MM-DD per the same policy
the rules DAO applies: the schema's lexical CHECKs cannot prove
calendar validity.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dao_children import _connection_lock
from .dao_rules import _UNSET, _validate_date
from .db import NestQuestDatabase


@dataclass(frozen=True)
class PresenceScheduleRecord:
    """One row of ``presence_schedules``."""

    id: int
    child_id: int
    cycle_length_weeks: int
    anchor_date: str
    pattern: str


@dataclass(frozen=True)
class PresenceOverrideRecord:
    """One row of ``presence_overrides``."""

    id: int
    child_id: int
    start_date: str
    end_date: str
    is_present: bool
    note: str | None


_SCHEDULE_COLUMNS = (
    "id, child_id, cycle_length_weeks, anchor_date, pattern"
)
_OVERRIDE_COLUMNS = (
    "id, child_id, start_date, end_date, is_present, note"
)


def _schedule_from_row(row: tuple) -> PresenceScheduleRecord:
    return PresenceScheduleRecord(
        id=row[0],
        child_id=row[1],
        cycle_length_weeks=row[2],
        anchor_date=row[3],
        pattern=row[4],
    )


def _override_from_row(row: tuple) -> PresenceOverrideRecord:
    return PresenceOverrideRecord(
        id=row[0],
        child_id=row[1],
        start_date=row[2],
        end_date=row[3],
        is_present=bool(row[4]),
        note=row[5],
    )


class PresenceSchedulesDao:
    """Typed async access to the ``presence_schedules`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def upsert_by_child(
        self,
        child_id: int,
        cycle_length_weeks: int,
        anchor_date: str,
        pattern: str,
    ) -> PresenceScheduleRecord:
        """Set the child's presence schedule, replacing any existing one.

        Upsert semantics are the done-condition: a second schedule for
        the same child updates the existing row rather than raising.
        Runs under the connection lock so a concurrent upsert/delete
        for the same child serializes instead of colliding on the
        schema's UNIQUE(child_id).  Pattern validity (segment shape,
        segment count = cycle_length_weeks) is enforced by the schema
        CHECKs; the child must exist (FK) — validated atomically here
        so a deleted child cannot pass a stale check.
        """
        _validate_date(anchor_date, "anchor_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                child = await self._database.fetch_one(
                    "SELECT 1 FROM children WHERE id = ?", (child_id,)
                )
                if child is None:
                    raise ValueError(f"child {child_id} does not exist")
                await self._database.execute(
                    "INSERT INTO presence_schedules (child_id, "
                    "cycle_length_weeks, anchor_date, pattern) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (child_id) DO UPDATE SET "
                    "cycle_length_weeks = excluded.cycle_length_weeks, "
                    "anchor_date = excluded.anchor_date, "
                    "pattern = excluded.pattern",
                    (child_id, cycle_length_weeks, anchor_date, pattern),
                )
                schedule = await self.get_by_child(child_id)
        assert schedule is not None
        return schedule

    async def get_by_child(
        self, child_id: int
    ) -> PresenceScheduleRecord | None:
        """Return the child's schedule, or None when the child has none.

        None is meaningful and UNAMBIGUOUS here: the child exists and
        has no schedule row, i.e. the child is present every day
        (Feature 05 guardrail).  An unknown child id raises ValueError
        instead of returning None, because "nonexistent child" must
        never be silently read as "present every day".
        """
        child = await self._database.fetch_one(
            "SELECT 1 FROM children WHERE id = ?", (child_id,)
        )
        if child is None:
            raise ValueError(f"child {child_id} does not exist")
        row = await self._database.fetch_one(
            f"SELECT {_SCHEDULE_COLUMNS} FROM presence_schedules "
            "WHERE child_id = ?",
            (child_id,),
        )
        return _schedule_from_row(row) if row is not None else None

    async def delete(self, child_id: int) -> bool:
        """Remove the child's schedule; True if a row was removed.

        After deletion the child is present every day (no row means
        no restriction).  Deleting a schedule the child never had
        returns False.
        """
        result = await self._database.execute(
            "DELETE FROM presence_schedules WHERE child_id = ?",
            (child_id,),
        )
        return result.rowcount > 0


class PresenceOverridesDao:
    """Typed async access to the ``presence_overrides`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def create(
        self,
        child_id: int,
        start_date: str,
        end_date: str,
        is_present: bool,
        *,
        note: str | None = None,
    ) -> PresenceOverrideRecord:
        """Insert one override and return the record as stored.

        The child must exist (validated atomically under the
        connection lock).  Date shape is validated strictly, and the
        schema CHECK rejects end < start.
        """
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                child = await self._database.fetch_one(
                    "SELECT 1 FROM children WHERE id = ?", (child_id,)
                )
                if child is None:
                    raise ValueError(f"child {child_id} does not exist")
                result = await self._database.execute(
                    "INSERT INTO presence_overrides (child_id, "
                    "start_date, end_date, is_present, note) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (child_id, start_date, end_date, int(is_present), note),
                )
                override = await self._database.fetch_one(
                    f"SELECT {_OVERRIDE_COLUMNS} FROM presence_overrides "
                    "WHERE id = ?",
                    (result.lastrowid,),
                )
        assert override is not None
        return _override_from_row(override)

    async def list_by_child_and_range(
        self,
        child_id: int,
        range_start: str,
        range_end: str,
    ) -> list[PresenceOverrideRecord]:
        """Return the child's overrides overlapping [range_start, range_end].

        An override overlaps the range when it ends on or after the
        range starts and starts on or before the range ends (inclusive
        boundary dates, matching the storage model where overrides are
        closed date ranges).  Ordered by start date.
        """
        _validate_date(range_start, "range_start")
        _validate_date(range_end, "range_end")
        if range_end < range_start:
            raise ValueError(
                "range_end must be on or after range_start, got "
                f"{range_end!r} < {range_start!r}"
            )
        rows = await self._database.fetch_all(
            f"SELECT {_OVERRIDE_COLUMNS} FROM presence_overrides "
            "WHERE child_id = ? AND end_date >= ? AND start_date <= ? "
            "ORDER BY start_date",
            (child_id, range_start, range_end),
        )
        return [_override_from_row(row) for row in rows]

    async def delete(self, override_id: int) -> bool:
        """Remove one override by id; True if a row was removed."""
        result = await self._database.execute(
            "DELETE FROM presence_overrides WHERE id = ?",
            (override_id,),
        )
        return result.rowcount > 0