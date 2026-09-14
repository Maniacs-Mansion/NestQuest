"""Typed DAO layer for the schedule_rules and task_definitions tables.

All SQL for ``schedule_rules`` and ``task_definitions`` lives in this
module per the feature guardrails: callers get typed dataclasses back
and never see raw rows or SQL.  Every method is async and runs through
:class:`~.db.NestQuestDatabase`, so each statement executes on the HA
executor and the event loop never blocks.

Guardrail mapping:

- ``schedule_rules`` deletion is delete-if-unreferenced: a rule still
  referenced by any task definition is rejected (the done-condition),
  not cascaded.
- ``task_definitions`` has no delete path at all: definitions are
  deactivated, never hard-deleted, and history must survive.
- ``set_assignee`` changes future instances only — the DAO writes the
  definition row and nothing else; reassignment never rewrites
  existing instances or completion history (Feature 06 guardrail).
- Validation of rule well-formedness and child activeness lives partly
  in the schema CHECKs (rule-type coherence) and partly in
  :meth:`TaskDefinitionsDao.create` (active child, rule existence);
  no permission checks here, that is the Feature 09 gate's job.

Concurrency: ``delete_rule_if_unreferenced`` performs its reference
check and DELETE inside one transaction under the connection-scoped
lock shared with :mod:`.dao_children`, so a definition referencing the
rule cannot appear between check and delete on this connection.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dao_children import _connection_lock
from .db import NestQuestDatabase


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
class TaskDefinitionRecord:
    """One row of ``task_definitions``."""

    id: int
    title: str
    description: str | None
    icon: str | None
    child_id: int
    schedule_rule_id: int
    due_time: str | None
    is_active: bool
    created_at: str


_RULE_COLUMNS = (
    "id, rule_type, interval, weekday_set, day_of_month, nth_weekday, "
    "month, start_date, end_date"
)
_DEFINITION_COLUMNS = (
    "id, title, description, icon, child_id, schedule_rule_id, due_time, "
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


def _definition_from_row(row: tuple) -> TaskDefinitionRecord:
    return TaskDefinitionRecord(
        id=row[0],
        title=row[1],
        description=row[2],
        icon=row[3],
        child_id=row[4],
        schedule_rule_id=row[5],
        due_time=row[6],
        is_active=bool(row[7]),
        created_at=row[8],
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
        CHECKs and surfaces as :class:`sqlite3.IntegrityError`.
        """
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
        rule_type: str | None = None,
        interval: int | None = None,
        weekday_set: str | None = None,
        day_of_month: int | None = None,
        nth_weekday: int | None = None,
        month: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """Update the given fields; returns rows updated (0 if absent).

        Only non-None arguments are written.  Editing a rule that a
        definition references changes future materializations only —
        this method touches no instances (Feature 06/07 separation).
        """
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
            if value is not None:
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
                    "SELECT 1 FROM task_definitions "
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


class TaskDefinitionsDao:
    """Typed async access to the ``task_definitions`` table.

    No delete method exists: definitions are deactivated via
    :meth:`set_active`, never hard-deleted, so completion history keeps
    its references (feature guardrail).
    """

    def __init__(self, database: NestQuestDatabase) -> None:
        self._database = database

    async def create(
        self,
        title: str,
        child_id: int,
        schedule_rule_id: int,
        created_at: str,
        *,
        description: str | None = None,
        icon: str | None = None,
        due_time: str | None = None,
        is_active: bool = True,
    ) -> TaskDefinitionRecord:
        """Insert one definition and return the record as stored.

        Validates the assignment target before saving: the child must
        exist and be active, and the rule must exist.  The schema
        foreign keys would reject unknown ids anyway, but an INACTIVE
        child would pass them — that check must happen here.
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
        rule = await self._database.fetch_one(
            "SELECT 1 FROM schedule_rules WHERE id = ?",
            (schedule_rule_id,),
        )
        if rule is None:
            raise ValueError(f"schedule rule {schedule_rule_id} does not exist")
        result = await self._database.execute(
            "INSERT INTO task_definitions (title, description, icon, "
            "child_id, schedule_rule_id, due_time, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                description,
                icon,
                child_id,
                schedule_rule_id,
                due_time,
                int(is_active),
                created_at,
            ),
        )
        definition = await self.get(result.lastrowid)
        assert definition is not None
        return definition

    async def get(self, definition_id: int) -> TaskDefinitionRecord | None:
        """Return the definition with ``definition_id``, or None."""
        row = await self._database.fetch_one(
            f"SELECT {_DEFINITION_COLUMNS} FROM task_definitions "
            "WHERE id = ?",
            (definition_id,),
        )
        return _definition_from_row(row) if row is not None else None

    async def list_by_child(self, child_id: int) -> list[TaskDefinitionRecord]:
        """Return all definitions assigned to ``child_id``, newest first."""
        rows = await self._database.fetch_all(
            f"SELECT {_DEFINITION_COLUMNS} FROM task_definitions "
            "WHERE child_id = ? ORDER BY id DESC",
            (child_id,),
        )
        return [_definition_from_row(row) for row in rows]

    async def list_active(self) -> list[TaskDefinitionRecord]:
        """Return all active definitions, oldest first (stable order)."""
        rows = await self._database.fetch_all(
            f"SELECT {_DEFINITION_COLUMNS} FROM task_definitions "
            "WHERE is_active = 1 ORDER BY id"
        )
        return [_definition_from_row(row) for row in rows]

    async def update(
        self,
        definition_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        due_time: str | None = None,
    ) -> int:
        """Update the given fields; returns rows updated (0 if absent).

        Assignment and activation are deliberately NOT settable here:
        they have their own explicit operations (:meth:`set_assignee`,
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
            if value is not None:
                assignments.append(f"{column} = ?")
                parameters.append(value)
        if not assignments:
            return 0
        parameters.append(definition_id)
        result = await self._database.execute(
            f"UPDATE task_definitions SET {', '.join(assignments)} "
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
            "UPDATE task_definitions SET is_active = ? WHERE id = ?",
            (int(is_active), definition_id),
        )
        return result.rowcount

    async def set_assignee(
        self, definition_id: int, child_id: int
    ) -> int:
        """Reassign the definition to ``child_id``; rows updated (0 if absent).

        Validates the new assignee like :meth:`create` (existing and
        active).  Changes future instances only: already-generated
        instances and completion history are never rewritten here.
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
        result = await self._database.execute(
            "UPDATE task_definitions SET child_id = ? WHERE id = ?",
            (child_id, definition_id),
        )
        return result.rowcount