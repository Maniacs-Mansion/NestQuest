"""Typed DAO layer for the presence_patterns and presence_overrides tables.

All SQL for these tables lives in this module per the feature
guardrails: callers get typed dataclasses back and never see raw rows
or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Semantics per the done-condition and Feature 05:

- A child has ZERO OR MORE presence patterns (schema 9 — no UNIQUE on
  ``child_id``); each is created, updated and deleted by its own id.
- A child with NO pattern row is present every day — the absence of a
  row is meaningful state, expressed by
  :meth:`PresencePatternsDao.list_by_child` returning an empty list,
  never by an empty pattern row.
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
class PresencePatternRecord:
    """One row of ``presence_patterns``."""

    id: int
    child_id: int
    name: str
    kind: str
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


_PATTERN_COLUMNS = (
    "id, child_id, name, kind, cycle_length_weeks, anchor_date, pattern"
)
_OVERRIDE_COLUMNS = (
    "id, child_id, start_date, end_date, is_present, note"
)


def _pattern_from_row(row: tuple) -> PresencePatternRecord:
    return PresencePatternRecord(
        id=row[0],
        child_id=row[1],
        name=row[2],
        kind=row[3],
        cycle_length_weeks=row[4],
        anchor_date=row[5],
        pattern=row[6],
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


class PresencePatternsDao:
    """Typed async access to the ``presence_patterns`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def create(
        self,
        child_id: int,
        name: str,
        kind: str,
        cycle_length_weeks: int,
        anchor_date: str,
        pattern: str,
    ) -> PresencePatternRecord:
        """Insert one pattern for the child and return it as stored.

        The child must exist (FK) — validated atomically under the
        connection lock so a deleted child cannot pass a stale check.
        ``kind``, the cycle length and the pattern shape (segment count
        = ``cycle_length_weeks``) are enforced by the schema CHECKs.
        """
        _validate_date(anchor_date, "anchor_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                child = await self._database.fetch_one(
                    "SELECT 1 FROM children WHERE id = ?", (child_id,)
                )
                if child is None:
                    raise ValueError(f"child {child_id} does not exist")
                result = await self._database.execute(
                    "INSERT INTO presence_patterns (child_id, name, kind, "
                    "cycle_length_weeks, anchor_date, pattern) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        child_id,
                        name,
                        kind,
                        cycle_length_weeks,
                        anchor_date,
                        pattern,
                    ),
                )
                record = await self.get(result.lastrowid)
        assert record is not None
        return record

    async def list_by_child(self, child_id: int) -> list[PresencePatternRecord]:
        """Return the child's patterns ordered by id; empty when none.

        An empty list is meaningful and UNAMBIGUOUS here: the child
        exists and has no pattern row, i.e. the child is present every
        day (Feature 05 guardrail).  An unknown child id raises
        ValueError instead of returning an empty list, because
        "nonexistent child" must never be silently read as "present
        every day".
        """
        child = await self._database.fetch_one(
            "SELECT 1 FROM children WHERE id = ?", (child_id,)
        )
        if child is None:
            raise ValueError(f"child {child_id} does not exist")
        rows = await self._database.fetch_all(
            f"SELECT {_PATTERN_COLUMNS} FROM presence_patterns "
            "WHERE child_id = ? ORDER BY id",
            (child_id,),
        )
        return [_pattern_from_row(row) for row in rows]

    async def get(self, pattern_id: int) -> PresencePatternRecord | None:
        """Return one pattern by id, or None when it does not exist."""
        row = await self._database.fetch_one(
            f"SELECT {_PATTERN_COLUMNS} FROM presence_patterns WHERE id = ?",
            (pattern_id,),
        )
        return _pattern_from_row(row) if row is not None else None

    async def update(
        self,
        pattern_id: int,
        name: str,
        kind: str,
        cycle_length_weeks: int,
        anchor_date: str,
        pattern: str,
    ) -> PresencePatternRecord | None:
        """Replace one pattern's fields; None when the id does not exist.

        Every column but ``id`` and ``child_id`` is rewritten — a
        pattern never moves to another child.  The schema CHECKs apply
        exactly as on :meth:`create`.
        """
        _validate_date(anchor_date, "anchor_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                result = await self._database.execute(
                    "UPDATE presence_patterns SET name = ?, kind = ?, "
                    "cycle_length_weeks = ?, anchor_date = ?, pattern = ? "
                    "WHERE id = ?",
                    (
                        name,
                        kind,
                        cycle_length_weeks,
                        anchor_date,
                        pattern,
                        pattern_id,
                    ),
                )
                if result.rowcount == 0:
                    return None
                record = await self.get(pattern_id)
        return record

    async def delete(self, pattern_id: int) -> bool:
        """Remove one pattern by id; True if a row was removed.

        Deleting a child's last pattern leaves it present every day (no
        row means no restriction).
        """
        result = await self._database.execute(
            "DELETE FROM presence_patterns WHERE id = ?",
            (pattern_id,),
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

        Overlap policy (Feature 05): an override for a child may not
        overlap another override of the SAME child — two different
        present/absent answers for one date are unresolvable.  The
        overlap check (inclusive boundaries) runs inside the same
        transaction as the INSERT, so a racing create cannot slip a
        conflicting override between the check and the write; a
        conflict raises ValueError naming the conflicting override's
        id and range.
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
                # Only a well-ordered range has overlap semantics:
                # inverted ranges fall through to the INSERT and hit
                # the schema's end>=start CHECK, preserving the
                # IntegrityError contract the matrix tests rely on.
                if end_date >= start_date:
                    conflicting = await self._database.fetch_one(
                        f"SELECT {_OVERRIDE_COLUMNS} "
                        "FROM presence_overrides "
                        "WHERE child_id = ? AND end_date >= ? "
                        "AND start_date <= ? ORDER BY id LIMIT 1",
                        (child_id, start_date, end_date),
                    )
                else:
                    conflicting = None
                if conflicting is not None:
                    conflict = _override_from_row(conflicting)
                    raise ValueError(
                        f"override for child {child_id} "
                        f"[{start_date}, {end_date}] overlaps existing "
                        f"override {conflict.id} "
                        f"[{conflict.start_date}, {conflict.end_date}] "
                        f"(is_present={conflict.is_present})"
                    )
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

    async def list_filtered(
        self,
        *,
        child_id: int | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PresenceOverrideRecord]:
        """Return the household's overrides, optionally narrowed.

        Every filter is optional and they combine: ``child_id`` keeps
        that child's overrides only (an unknown child raises ValueError
        rather than reading as "no overrides"); ``start`` keeps
        overrides ending on or after it and ``end`` keeps overrides
        starting on or before it, so both together select the overrides
        overlapping the closed range ``[start, end]`` (the
        :meth:`list_by_child_and_range` boundary rule).  Dates are
        strict YYYY-MM-DD and ``end`` must not precede ``start``.
        Ordered stably by start date, then child id, then id.
        """
        if start is not None:
            _validate_date(start, "start")
        if end is not None:
            _validate_date(end, "end")
        if start is not None and end is not None and end < start:
            raise ValueError(
                f"end must be on or after start, got {end!r} < {start!r}"
            )
        clauses: list[str] = []
        params: list[object] = []
        if child_id is not None:
            child = await self._database.fetch_one(
                "SELECT 1 FROM children WHERE id = ?", (child_id,)
            )
            if child is None:
                raise ValueError(f"child {child_id} does not exist")
            clauses.append("child_id = ?")
            params.append(child_id)
        if start is not None:
            clauses.append("end_date >= ?")
            params.append(start)
        if end is not None:
            clauses.append("start_date <= ?")
            params.append(end)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._database.fetch_all(
            f"SELECT {_OVERRIDE_COLUMNS} FROM presence_overrides{where} "
            "ORDER BY start_date, child_id, id",
            tuple(params),
        )
        return [_override_from_row(row) for row in rows]

    async def get(self, override_id: int) -> PresenceOverrideRecord | None:
        """Return one override by id, or None when it does not exist."""
        row = await self._database.fetch_one(
            f"SELECT {_OVERRIDE_COLUMNS} FROM presence_overrides "
            "WHERE id = ?",
            (override_id,),
        )
        return _override_from_row(row) if row is not None else None

    async def delete(self, override_id: int) -> bool:
        """Remove one override by id; True if a row was removed."""
        result = await self._database.execute(
            "DELETE FROM presence_overrides WHERE id = ?",
            (override_id,),
        )
        return result.rowcount > 0


async def read_snapshot_unlocked(
    database: NestQuestDatabase,
    child_ids: list[int],
    range_start: str,
    range_end: str,
) -> tuple[
    dict[int, list[PresencePatternRecord]],
    dict[int, list[PresenceOverrideRecord]],
]:
    """Read patterns and overrides for ``child_ids`` WITHOUT locking.

    MUST be called inside the connection lock and an open transaction, so
    the patterns and overrides returned here stay coherent with every
    other table the caller reads inside that same transaction (the
    materialization walk's single input snapshot does exactly that).  The
    date range comes already validated by the caller.

    Returns ``(patterns, overrides)``:

    - ``patterns`` maps ``child_id`` to its :class:`PresencePatternRecord`
      list (ordered by id) for every child that HAS a pattern row.  A
      child absent from the mapping has no pattern, i.e. is present
      every day (Feature 05).
    - ``overrides`` maps ``child_id`` to that child's overrides overlapping
      ``[range_start, range_end]`` (inclusive boundaries), ordered by start
      date; a child with no matching override is absent from the mapping.

    ``child_ids`` must name existing children (the caller derives them
    from a trusted snapshot, within the same transaction).
    """
    children = sorted(set(child_ids))
    if not children:
        return {}, {}
    placeholders = ",".join("?" for _ in children)
    pattern_rows = await database.fetch_all(
        f"SELECT {_PATTERN_COLUMNS} FROM presence_patterns "
        f"WHERE child_id IN ({placeholders}) ORDER BY id",
        tuple(children),
    )
    override_rows = await database.fetch_all(
        f"SELECT {_OVERRIDE_COLUMNS} FROM presence_overrides "
        f"WHERE child_id IN ({placeholders}) AND end_date >= ? "
        "AND start_date <= ? ORDER BY start_date",
        tuple(children) + (range_start, range_end),
    )
    patterns: dict[int, list[PresencePatternRecord]] = {}
    for row in pattern_rows:
        record = _pattern_from_row(row)
        patterns.setdefault(record.child_id, []).append(record)
    overrides: dict[int, list[PresenceOverrideRecord]] = {}
    for row in override_rows:
        record = _override_from_row(row)
        overrides.setdefault(record.child_id, []).append(record)
    return patterns, overrides