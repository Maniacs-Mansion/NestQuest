"""Typed DAO layer for the schedule_rules, quest_definitions and
quest_definition_assignees tables.

All SQL for ``schedule_rules``, ``quest_definitions`` and
``quest_definition_assignees`` lives in this module per the feature
guardrails: callers get typed dataclasses back and never see raw rows
or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Guardrail mapping:

- ``schedule_rules`` deletion is delete-if-unreferenced: a rule still
  referenced by any quest definition is rejected (the done-condition),
  not cascaded.
- ``quest_definitions`` has no delete path at all: definitions are
  deactivated, never hard-deleted, and history must survive.
- Assignment is multi-assignee (D-008): :meth:`add_assignee` and
  :meth:`remove_assignee` change future instances only — the DAO writes
  the assignee table and nothing else; assignment edits never rewrite
  existing instances or completion history (Feature 06 guardrail).
- Validation of rule well-formedness and child activeness lives partly
  in the schema CHECKs (rule-type coherence) and partly in
  :meth:`QuestDefinitionsDao.create` (rule existence) and
  :meth:`QuestDefinitionsDao.add_assignee` (active child); no
  permission checks here, that is the Feature 09 gate's job.

Concurrency: ``delete_rule_if_unreferenced`` and the assignee
mutations perform their checks and writes inside one transaction under
the connection-scoped lock shared with :mod:`.dao_children`, so a
definition referencing the rule (or an assignee appearing) cannot slip
in between check and write on this connection.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from .dao_children import ChildRecord, _child_from_row, _connection_lock
from .dao_children import _CHILD_COLUMNS
from .db import NestQuestDatabase

#: Sentinel distinguishing "argument omitted" from "explicit SQL NULL"
#: in update methods: passing ``None`` must mean clearing a nullable
#: column, not skipping it.
_UNSET = object()

#: Date-shape policy: schedule-rule dates are ISO YYYY-MM-DD.  The
#: schema's lexical end>=start CHECK cannot prove a value is a real
#: calendar date, so the DAO validates the shape it accepts.
_DATE_FORMAT = "%Y-%m-%d"


def _validate_date(value: str, field: str) -> None:
    """Raise ValueError unless ``value`` is a YYYY-MM-DD calendar date.

    ``datetime.date.fromisoformat`` accepts ISO dates but is lenient on
    some builds (e.g. '2026-9-4'); strptime with an exact format is
    strict, and strptime round-trips the parsed value to reject zero
    padding ('2026-9-4' parses but its isoformat differs).
    """
    try:
        parsed = datetime.datetime.strptime(value, _DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise ValueError(
            f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}"
        ) from None
    if parsed.isoformat() != value:
        raise ValueError(
            f"{field} must be a strict YYYY-MM-DD date, got {value!r}"
        )


@dataclass(frozen=True)
class ScheduleRuleRecord:
    """One row of ``schedule_rules``."""

    id: int
    rule_type: str
    interval: int
    weekday_set: str | None
    day_of_month: int | None
    nth_weekday: int | None
    month: int | None
    start_date: str
    end_date: str | None


@dataclass(frozen=True)
class QuestDefinitionRecord:
    """One row of ``quest_definitions`` (without its assignees)."""

    id: int
    title: str
    description: str | None
    icon: str | None
    schedule_rule_id: int
    due_time: str | None
    is_active: bool
    created_at: str


_RULE_COLUMNS = (
    "id, rule_type, interval, weekday_set, day_of_month, nth_weekday, "
    "month, start_date, end_date"
)
_DEFINITION_COLUMNS = (
    "id, title, description, icon, schedule_rule_id, due_time, "
    "is_active, created_at"
)


def _rule_from_row(row: tuple) -> ScheduleRuleRecord:
    return ScheduleRuleRecord(
        id=row[0],
        rule_type=row[1],
        interval=row[2],
        weekday_set=row[3],
        day_of_month=row[4],
        nth_weekday=row[5],
        month=row[6],
        start_date=row[7],
        end_date=row[8],
    )


def _definition_from_row(row: tuple) -> QuestDefinitionRecord:
    return QuestDefinitionRecord(
        id=row[0],
        title=row[1],
        description=row[2],
        icon=row[3],
        schedule_rule_id=row[4],
        due_time=row[5],
        is_active=bool(row[6]),
        created_at=row[7],
    )


class ScheduleRulesDao:
    """Typed async access to the ``schedule_rules`` table."""

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def create(
        self,
        rule_type: str,
        start_date: str,
        *,
        interval: int = 1,
        weekday_set: str | None = None,
        day_of_month: int | None = None,
        nth_weekday: int | None = None,
        month: int | None = None,
        end_date: str | None = None,
    ) -> ScheduleRuleRecord:
        """Insert one rule and return the record as stored.

        Rule-type coherence (a weekly rule needs ``weekday_set``, a
        yearly rule needs ``month``, etc.) is enforced by the schema
        CHECKs and surfaces as :class:`sqlite3.IntegrityError`.  Date
        shape (strict YYYY-MM-DD) is validated here because the
        schema's lexical end>=start CHECK cannot prove a real calendar
        date.
        """
        _validate_date(start_date, "start_date")
        if end_date is not None:
            _validate_date(end_date, "end_date")
        result = await self._database.execute(
            "INSERT INTO schedule_rules (rule_type, interval, weekday_set, "
            "day_of_month, nth_weekday, month, start_date, end_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule_type,
                interval,
                weekday_set,
                day_of_month,
                nth_weekday,
                month,
                start_date,
                end_date,
            ),
        )
        rule = await self.get(result.lastrowid)
        assert rule is not None
        return rule

    async def get(self, rule_id: int) -> ScheduleRuleRecord | None:
        """Return the rule with ``rule_id``, or None."""
        row = await self._database.fetch_one(
            f"SELECT {_RULE_COLUMNS} FROM schedule_rules WHERE id = ?",
            (rule_id,),
        )
        return _rule_from_row(row) if row is not None else None

    async def update(
        self,
        rule_id: int,
        *,
        rule_type: str | None | object = _UNSET,
        interval: int | None | object = _UNSET,
        weekday_set: str | None | object = _UNSET,
        day_of_month: int | None | object = _UNSET,
        nth_weekday: int | None | object = _UNSET,
        month: int | None | object = _UNSET,
        start_date: str | None | object = _UNSET,
        end_date: str | None | object = _UNSET,
    ) -> int:
        """Update the given fields; returns rows updated (0 if absent).

        Arguments default to the module sentinel ``_UNSET`` meaning
        "leave this column alone"; passing ``None`` explicitly writes
        SQL NULL, so callers can reopen an ended rule (``end_date``
        back to NULL) or clear nullable shape fields.  Passing
        ``None``/a new value for a date field validates its shape.
        Editing a rule that a definition references changes future
        materializations only — this method touches no instances
        (Feature 06/07 separation).
        """
        date_args = (
            ("start_date", start_date),
            ("end_date", end_date),
        )
        for field, value in date_args:
            if value is not _UNSET and value is not None:
                _validate_date(value, field)
        assignments: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("rule_type", rule_type),
            ("interval", interval),
            ("weekday_set", weekday_set),
            ("day_of_month", day_of_month),
            ("nth_weekday", nth_weekday),
            ("month", month),
            ("start_date", start_date),
            ("end_date", end_date),
        ):
            if value is not _UNSET:
                assignments.append(f"{column} = ?")
                parameters.append(value)
        if not assignments:
            return 0
        parameters.append(rule_id)
        result = await self._database.execute(
            f"UPDATE schedule_rules SET {', '.join(assignments)} "
            "WHERE id = ?",
            tuple(parameters),
        )
        return result.rowcount

    async def delete_if_unreferenced(self, rule_id: int) -> bool:
        """Delete the rule only if no definition references it.

        Returns True if the rule was deleted, False if it is still
        referenced (or does not exist — distinguish via :meth:`get`).
        The reference check and the DELETE run inside one transaction
        under the connection lock, so a definition cannot start
        referencing the rule between the check and the delete.
        """
        async with _connection_lock(self._database):
            async with self._database.transaction():
                row = await self._database.fetch_one(
                    "SELECT 1 FROM quest_definitions "
                    "WHERE schedule_rule_id = ? LIMIT 1",
                    (rule_id,),
                )
                if row is not None:
                    return False
                result = await self._database.execute(
                    "DELETE FROM schedule_rules WHERE id = ?",
                    (rule_id,),
                )
                return result.rowcount > 0


class QuestDefinitionsDao:
    """Typed async access to ``quest_definitions`` and its assignees.

    No delete method exists: definitions are deactivated via
    :meth:`set_active`, never hard-deleted, so completion history keeps
    its references (feature guardrail).  Assignment is multi-assignee
    (D-008): the definition row carries no child; assignees live in
    ``quest_definition_assignees`` and are managed explicitly so the
    operations stay separately loggable and permission-gateable.
    """

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def create(
        self,
        title: str,
        schedule_rule_id: int,
        created_at: str,
        *,
        description: str | None = None,
        icon: str | None = None,
        due_time: str | None = None,
        is_active: bool = True,
        assignee_child_ids: list[int] | None = None,
    ) -> QuestDefinitionRecord:
        """Insert one definition and return the record as stored.

        Validates the schedule rule as part of the same serialized
        transaction as the insert: the rule must exist AT INSERT TIME —
        a rule deleted concurrently cannot slip between the check and
        the INSERT.  ``assignee_child_ids`` (each child must exist and
        be active) is applied in the same transaction, so a definition
        can never be observed with a stale or missing assignee set; an
        empty list or None creates an unassigned definition, which
        callers may fill via :meth:`add_assignee`.
        """
        async with _connection_lock(self._database):
            async with self._database.transaction():
                await self._validate_rule_exists(schedule_rule_id)
                for child_id in assignee_child_ids or []:
                    await self._validate_assignable_child(child_id)
                result = await self._database.execute(
                    "INSERT INTO quest_definitions (title, description, "
                    "icon, schedule_rule_id, due_time, is_active, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        title,
                        description,
                        icon,
                        schedule_rule_id,
                        due_time,
                        int(is_active),
                        created_at,
                    ),
                )
                definition_id = result.lastrowid
                for child_id in assignee_child_ids or []:
                    await self._database.execute(
                        "INSERT INTO quest_definition_assignees "
                        "(definition_id, child_id) VALUES (?, ?)",
                        (definition_id, child_id),
                    )
                definition = await self.get(definition_id)
        assert definition is not None
        return definition

    async def _validate_rule_exists(self, schedule_rule_id: int) -> None:
        """Raise ValueError unless the rule exists.

        MUST be called inside the connection lock so the verdict cannot
        go stale before the caller's INSERT commits.
        """
        rule = await self._database.fetch_one(
            "SELECT 1 FROM schedule_rules WHERE id = ?",
            (schedule_rule_id,),
        )
        if rule is None:
            raise ValueError(
                f"schedule rule {schedule_rule_id} does not exist"
            )

    async def get(self, definition_id: int) -> QuestDefinitionRecord | None:
        """Return the definition with ``definition_id``, or None."""
        row = await self._database.fetch_one(
            f"SELECT {_DEFINITION_COLUMNS} FROM quest_definitions "
            "WHERE id = ?",
            (definition_id,),
        )
        return _definition_from_row(row) if row is not None else None

    async def list_by_child(self, child_id: int) -> list[QuestDefinitionRecord]:
        """Return all definitions assigned to ``child_id``, newest first.

        Assignment is read through ``quest_definition_assignees``
        (D-008): a definition appears once per child regardless of how
        many assignees share it.
        """
        rows = await self._database.fetch_all(
            f"SELECT {_DEFINITION_COLUMNS} FROM quest_definitions "
            "WHERE id IN (SELECT definition_id "
            "FROM quest_definition_assignees WHERE child_id = ?) "
            "ORDER BY id DESC",
            (child_id,),
        )
        return [_definition_from_row(row) for row in rows]

    async def list_active(self) -> list[QuestDefinitionRecord]:
        """Return all active definitions, oldest first (stable order)."""
        rows = await self._database.fetch_all(
            f"SELECT {_DEFINITION_COLUMNS} FROM quest_definitions "
            "WHERE is_active = 1 ORDER BY id"
        )
        return [_definition_from_row(row) for row in rows]

    async def update(
        self,
        definition_id: int,
        *,
        title: str | None | object = _UNSET,
        description: str | None | object = _UNSET,
        icon: str | None | object = _UNSET,
        due_time: str | None | object = _UNSET,
    ) -> int:
        """Update the given fields; returns rows updated (0 if absent).

        Arguments default to the module sentinel ``_UNSET`` meaning
        "leave this column alone"; passing ``None`` explicitly writes
        SQL NULL, so callers can remove optional metadata
        (description, icon, due_time).  Assignment and activation are
        deliberately NOT settable here: they have their own explicit
        operations (:meth:`add_assignee`, :meth:`remove_assignee`,
        :meth:`set_active`) so they stay separately loggable and
        permission-gateable.
        """
        assignments: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("title", title),
            ("description", description),
            ("icon", icon),
            ("due_time", due_time),
        ):
            if value is not _UNSET:
                assignments.append(f"{column} = ?")
                parameters.append(value)
        if not assignments:
            return 0
        parameters.append(definition_id)
        result = await self._database.execute(
            f"UPDATE quest_definitions SET {', '.join(assignments)} "
            "WHERE id = ?",
            tuple(parameters),
        )
        return result.rowcount

    async def set_active(self, definition_id: int, is_active: bool) -> int:
        """Deactivate/reactivate; returns rows updated (0 if absent).

        Deactivating stops future instance generation but leaves
        existing instances and completion history untouched.
        """
        result = await self._database.execute(
            "UPDATE quest_definitions SET is_active = ? WHERE id = ?",
            (int(is_active), definition_id),
        )
        return result.rowcount

    async def add_assignee(
        self, definition_id: int, child_id: int
    ) -> None:
        """Assign ``child_id`` to the definition (idempotent).

        Validates the assignee inside the same serialized transaction
        as the INSERT (existing and active AT ASSIGNMENT TIME), so a
        child deactivated concurrently cannot become an assignee.
        Assigning an already-assigned child is a no-op, mirroring the
        composite primary key's storage-level guarantee.  Changes
        future instances only: already-generated instances and
        completion history are never rewritten here.
        """
        async with _connection_lock(self._database):
            async with self._database.transaction():
                await self._validate_assignable_child(child_id)
                definition = await self._database.fetch_one(
                    "SELECT 1 FROM quest_definitions WHERE id = ?",
                    (definition_id,),
                )
                if definition is None:
                    raise ValueError(
                        f"quest definition {definition_id} does not exist"
                    )
                await self._database.execute(
                    "INSERT INTO quest_definition_assignees "
                    "(definition_id, child_id) VALUES (?, ?) "
                    "ON CONFLICT (definition_id, child_id) DO NOTHING",
                    (definition_id, child_id),
                )

    async def remove_assignee(
        self, definition_id: int, child_id: int
    ) -> bool:
        """Remove the assignee link; True when a row was removed.

        Future materialization stops for this (definition, child) pair;
        existing instances and completion history are never touched
        here (Feature 06 guardrail).
        """
        async with _connection_lock(self._database):
            result = await self._database.execute(
                "DELETE FROM quest_definition_assignees "
                "WHERE definition_id = ? AND child_id = ?",
                (definition_id, child_id),
            )
        return result.rowcount > 0

    async def list_assignees(self, definition_id: int) -> list[ChildRecord]:
        """Return the definition's assignees as child records.

        Ordered by the children table's stable display order
        (``sort_order``, then id) so callers render a deterministic
        roster.  A definition with no assignees returns [].
        """
        rows = await self._database.fetch_all(
            f"SELECT {_CHILD_COLUMNS} FROM children "
            "WHERE id IN (SELECT child_id "
            "FROM quest_definition_assignees WHERE definition_id = ?) "
            "ORDER BY sort_order, id",
            (definition_id,),
        )
        return [_child_from_row(row) for row in rows]

    async def _validate_assignable_child(self, child_id: int) -> None:
        """Raise ValueError unless the child exists and is active.

        MUST be called inside the connection lock so the verdict cannot
        go stale before the caller's INSERT commits.
        """
        child = await self._database.fetch_one(
            "SELECT is_active FROM children WHERE id = ?", (child_id,)
        )
        if child is None:
            raise ValueError(f"child {child_id} does not exist")
        if not child[0]:
            raise ValueError(
                f"child {child_id} is inactive and cannot be assigned"
            )