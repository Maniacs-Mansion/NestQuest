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

from .const import QUEST_WINDOWS
from .dao_children import ChildRecord, _child_from_row, _connection_lock
from .dao_children import _CHILD_COLUMNS
from .db import NestQuestDatabase
from .recurrence import RuleType, RuleValidationError, ScheduleRule

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


_TIME_FORMAT = "%H:%M"


def _validate_time(value: str, field: str) -> None:
    """Raise ValueError unless ``value`` is a strict 24-hour HH:MM.

    Same strictness policy as _validate_date: parse with the exact
    format, then round-trip so '9:30' (non-padded) is rejected.  Time
    shapes are caller-side policy (the schema stores TEXT): windows'
    optional ``due_time`` and definition ``due_time`` both use this.
    """
    try:
        parsed = datetime.datetime.strptime(value, _TIME_FORMAT).time()
    except (TypeError, ValueError):
        raise ValueError(
            f"{field} must be a 24-hour HH:MM time, got {value!r}"
        ) from None
    if parsed.strftime(_TIME_FORMAT) != value:
        raise ValueError(
            f"{field} must be a strict HH:MM time, got {value!r}"
        )


def _validate_window(window: str) -> None:
    """Raise ValueError unless ``window`` is a ``const`` window name."""
    if window not in QUEST_WINDOWS:
        raise ValueError(
            f"window must be one of {', '.join(QUEST_WINDOWS)}, "
            f"got {window!r}"
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
class ScheduleRuleStorage:
    """The eight value columns a ScheduleRule maps to (no id column).

    ``id`` is assigned by the database on insert, so the model<->storage
    mapping concerns only the value columns.  ``nth_weekday_weekday`` is
    deliberately absent here: for MONTHLY_WEEKDAY its value is folded
    into ``weekday_set`` as that column's single CSV element.
    """

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


@dataclass(frozen=True)
class QuestDefinitionWindowRecord:
    """One row of ``quest_definition_windows``."""

    definition_id: int
    window: str
    due_time: str | None


@dataclass(frozen=True)
class QuestDefinitionSnapshot:
    """A definition plus its assignees and windows, read atomically.

    Returned by :meth:`QuestDefinitionsDao.create_with_rule_and_windows`
    with the assignees and windows read inside the SAME transaction that
    inserted them, so the snapshot is a consistent creation-time view —
    a concurrent assignee or window mutation cannot change it between
    the write and the read.
    """

    definition: QuestDefinitionRecord
    assignees: list[ChildRecord]
    windows: list[QuestDefinitionWindowRecord]


_RULE_COLUMNS = (
    "id, rule_type, interval, weekday_set, day_of_month, nth_weekday, "
    "month, start_date, end_date"
)
_DEFINITION_COLUMNS = (
    "id, title, description, icon, schedule_rule_id, due_time, "
    "is_active, created_at"
)
_WINDOW_COLUMNS = "definition_id, window, due_time"


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


def _window_from_row(row: tuple) -> QuestDefinitionWindowRecord:
    return QuestDefinitionWindowRecord(
        definition_id=row[0],
        window=row[1],
        due_time=row[2],
    )


#: Storage columns that are forbidden for each rule type.  A populated
#: forbidden column means the row's shape is invalid and must raise on
#: read, never be silently dropped.  ``weekday_set`` is absent for
#: DAILY/MONTHLY_DAY/YEARLY; MONTHLY_WEEKDAY is the only shape allowed a
#: non-NULL ``nth_weekday``; YEARLY is the only shape allowed ``month``.
_FORBIDDEN_STORAGE_FIELDS: dict[str, tuple[RuleType, ...]] = {
    "weekday_set": (RuleType.DAILY, RuleType.MONTHLY_DAY, RuleType.YEARLY),
    "day_of_month": (
        RuleType.DAILY,
        RuleType.WEEKLY,
        RuleType.CUSTOM_DAYS,
        RuleType.MONTHLY_WEEKDAY,
    ),
    "nth_weekday": (
        RuleType.DAILY,
        RuleType.WEEKLY,
        RuleType.CUSTOM_DAYS,
        RuleType.MONTHLY_DAY,
        RuleType.YEARLY,
    ),
    "month": (
        RuleType.DAILY,
        RuleType.WEEKLY,
        RuleType.CUSTOM_DAYS,
        RuleType.MONTHLY_DAY,
        RuleType.MONTHLY_WEEKDAY,
    ),
}


def schedule_rule_to_storage(rule: ScheduleRule) -> ScheduleRuleStorage:
    """Map a validated ScheduleRule onto its storage columns.

    ``rule_type`` stores as ``RuleType.storage_value`` (MONTHLY_DAY and
    MONTHLY_WEEKDAY both store ``'monthly'``); ``weekday_set`` stores as
    a sorted CSV list.  MONTHLY_WEEKDAY folds its model-only
    ``nth_weekday_weekday`` into ``weekday_set`` as that list's single
    element; every other type leaves the column as its own set
    (WEEKLY/CUSTOM_DAYS) or NULL.
    """
    shape = rule.rule_type
    if shape is RuleType.MONTHLY_WEEKDAY:
        weekday_set = str(rule.nth_weekday_weekday)
    elif shape is RuleType.WEEKLY or shape is RuleType.CUSTOM_DAYS:
        weekday_set = ",".join(str(w) for w in sorted(rule.weekday_set))
    else:
        weekday_set = None
    return ScheduleRuleStorage(
        rule_type=shape.storage_value,
        interval=rule.interval,
        weekday_set=weekday_set,
        day_of_month=rule.day_of_month,
        nth_weekday=rule.nth_weekday,
        month=rule.month,
        start_date=rule.start_date,
        end_date=rule.end_date,
    )


def schedule_rule_from_storage(storage: ScheduleRuleStorage) -> ScheduleRule:
    """Reconstruct a ScheduleRule from storage columns.

    Disambiguates MONTHLY_DAY from MONTHLY_WEEKDAY by which field is
    populated, and raises RuleValidationError rather than silently
    mis-decoding an ambiguous or invalid shape.
    """
    rule_type = storage.rule_type
    if rule_type == "daily":
        shape = RuleType.DAILY
    elif rule_type == "weekly":
        shape = RuleType.WEEKLY
    elif rule_type == "monthly":
        shape = _disambiguate_monthly(storage)
    elif rule_type == "yearly":
        shape = RuleType.YEARLY
    elif rule_type == "custom":
        shape = RuleType.CUSTOM_DAYS
    else:
        raise RuleValidationError(
            f"unknown storage rule_type {rule_type!r}"
        )

    _reject_forbidden_storage_fields(storage, shape)

    weekday_set = None
    nth_weekday_weekday = None
    if shape is RuleType.WEEKLY or shape is RuleType.CUSTOM_DAYS:
        weekday_set = _weekdays_from_csv(storage.weekday_set)
    elif shape is RuleType.MONTHLY_WEEKDAY:
        nth_weekday_weekday = _single_weekday_from_csv(storage.weekday_set)

    return ScheduleRule(
        rule_type=shape,
        interval=storage.interval,
        weekday_set=weekday_set,
        day_of_month=storage.day_of_month,
        nth_weekday=storage.nth_weekday,
        nth_weekday_weekday=nth_weekday_weekday,
        month=storage.month,
        start_date=storage.start_date,
        end_date=storage.end_date,
    )


def schedule_rule_storage_from_record(
    record: ScheduleRuleRecord,
) -> ScheduleRuleStorage:
    """Copy a rule row's value columns into a storage mapping.

    ``ScheduleRuleRecord`` is the read shape (it carries ``id``);
    :func:`schedule_rule_from_storage` consumes the value-only
    :class:`ScheduleRuleStorage` shape, so callers re-reading a stored
    rule convert through this helper.
    """
    return ScheduleRuleStorage(
        rule_type=record.rule_type,
        interval=record.interval,
        weekday_set=record.weekday_set,
        day_of_month=record.day_of_month,
        nth_weekday=record.nth_weekday,
        month=record.month,
        start_date=record.start_date,
        end_date=record.end_date,
    )


def _reject_forbidden_storage_fields(
    storage: ScheduleRuleStorage, shape: RuleType
) -> None:
    """Raise unless every populated column is permitted for ``shape``.

    The model constructor rejects a forbidden ``day_of_month``,
    ``nth_weekday``, or ``month``, but ``weekday_set`` never reaches it
    (it is folded for MONTHLY_WEEKDAY and dropped otherwise), so a daily
    row carrying ``weekday_set="0"`` would otherwise decode as a valid
    daily rule and silently lose the stored data.  This validates every
    shape column explicitly so a populated-forbidden column raises
    instead of being discarded.
    """
    for field, forbidden_shapes in _FORBIDDEN_STORAGE_FIELDS.items():
        value = getattr(storage, field)
        if value is not None and shape in forbidden_shapes:
            raise RuleValidationError(
                f"{shape.value} storage rows must not set {field}, "
                f"got {value!r}"
            )


def _disambiguate_monthly(storage: ScheduleRuleStorage) -> RuleType:
    """Resolve the shared 'monthly' storage value to a model type.

    MONTHLY_DAY names ``day_of_month`` only; MONTHLY_WEEKDAY names
    ``nth_weekday`` only.  Neither, or both, is ambiguous and raises.
    """
    day_of_month = storage.day_of_month
    nth_weekday = storage.nth_weekday
    if day_of_month is not None and nth_weekday is None:
        return RuleType.MONTHLY_DAY
    if nth_weekday is not None and day_of_month is None:
        return RuleType.MONTHLY_WEEKDAY
    raise RuleValidationError(
        "storage rule_type 'monthly' is ambiguous: must name exactly one "
        "of day_of_month or nth_weekday, got "
        f"day_of_month={day_of_month!r}, nth_weekday={nth_weekday!r}"
    )


def _weekdays_from_csv(value: str | None) -> frozenset[int]:
    """Parse a weekday CSV column into a frozenset of ints.

    ``None`` and ``""`` both yield an empty frozenset (the caller decides
    whether empty is legal); a non-integer token raises
    RuleValidationError rather than leaking a raw ValueError.
    """
    if value is None or value == "":
        return frozenset()
    try:
        entries = [int(token) for token in value.split(",")]
    except ValueError:
        raise RuleValidationError(
            f"weekday_set must be a CSV of integers, got {value!r}"
        ) from None
    return frozenset(entries)


def _single_weekday_from_csv(value: str | None) -> int:
    """The one weekday a MONTHLY_WEEKDAY stores in weekday_set.

    Parses the CSV into tokens FIRST and requires exactly one token,
    so a duplicate pair like ``"1,1"`` is rejected rather than silently
    canonicalized to a single weekday on re-storage.  An empty or
    multi-element column raises RuleValidationError.
    """
    if value is None or value == "":
        raise RuleValidationError(
            "MONTHLY_WEEKDAY storage weekday_set must hold exactly one "
            f"weekday, got {value!r}"
        )
    tokens = value.split(",")
    if len(tokens) != 1:
        raise RuleValidationError(
            "MONTHLY_WEEKDAY storage weekday_set must hold exactly one "
            f"weekday, got {value!r}"
        )
    try:
        return int(tokens[0])
    except ValueError:
        raise RuleValidationError(
            "MONTHLY_WEEKDAY storage weekday_set must be an integer, "
            f"got {value!r}"
        ) from None


async def _insert_rule_row(
    database: NestQuestDatabase, storage: ScheduleRuleStorage
) -> int:
    """Insert one ``schedule_rules`` row and return its new id.

    Runs inside the caller's transaction (no lock or transaction of its
    own) so a multi-table write can persist the rule together with the
    rows that reference it.  The caller is responsible for validating
    the storage fields — :meth:`ScheduleRulesDao.create` validates the
    date shape, and :meth:`QuestDefinitionsDao.create_with_rule_and_windows`
    receives storage already mapped from a validated
    :class:`~.recurrence.ScheduleRule`.
    """
    result = await database.execute(
        "INSERT INTO schedule_rules (rule_type, interval, weekday_set, "
        "day_of_month, nth_weekday, month, start_date, end_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            storage.rule_type,
            storage.interval,
            storage.weekday_set,
            storage.day_of_month,
            storage.nth_weekday,
            storage.month,
            storage.start_date,
            storage.end_date,
        ),
    )
    return result.lastrowid


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
        rule_id = await _insert_rule_row(
            self._database,
            ScheduleRuleStorage(
                rule_type=rule_type,
                interval=interval,
                weekday_set=weekday_set,
                day_of_month=day_of_month,
                nth_weekday=nth_weekday,
                month=month,
                start_date=start_date,
                end_date=end_date,
            ),
        )
        rule = await self.get(rule_id)
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

    async def create_with_rule_and_windows(
        self,
        title: str,
        schedule_rule: ScheduleRuleStorage,
        created_at: str,
        assignee_child_ids: list[int],
        windows: list[tuple[str, str | None]],
        *,
        description: str | None = None,
        icon: str | None = None,
    ) -> QuestDefinitionSnapshot:
        """Insert a rule, definition, assignees and windows atomically.

        The whole write — the schedule rule row, the definition row,
        every assignee link and every window declaration — runs inside
        ONE transaction under the connection lock, so a validation or
        write failure rolls the lot back together (all-or-nothing): the
        caller can never observe a definition with a missing rule,
        assignee or window, and a rejected create leaves no partial
        rows.

        Returns a :class:`QuestDefinitionSnapshot` whose assignees and
        windows are read back inside the same transaction, so the
        returned view cannot be raced by a concurrent assignee/window
        mutation after the write.

        The rule arrives as pre-validated storage fields (mapped from a
        :class:`~.recurrence.ScheduleRule` via
        :func:`schedule_rule_to_storage`); its dates are re-validated
        here so a hand-built storage can never persist a malformed date.
        The definition-level ``due_time`` column is deliberately left
        NULL — per-window due times supersede it (D-008).  Assignees are
        validated as existing-and-active at insert time, and windows are
        validated for name and strict HH:MM due time, matching
        :meth:`upsert_window`.
        """
        _validate_date(schedule_rule.start_date, "start_date")
        if schedule_rule.end_date is not None:
            _validate_date(schedule_rule.end_date, "end_date")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                for child_id in assignee_child_ids:
                    await self._validate_assignable_child(child_id)
                rule_id = await _insert_rule_row(self._database, schedule_rule)
                result = await self._database.execute(
                    "INSERT INTO quest_definitions (title, description, "
                    "icon, schedule_rule_id, due_time, is_active, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, description, icon, rule_id, None, 1, created_at),
                )
                definition_id = result.lastrowid
                for child_id in assignee_child_ids:
                    await self._database.execute(
                        "INSERT INTO quest_definition_assignees "
                        "(definition_id, child_id) VALUES (?, ?)",
                        (definition_id, child_id),
                    )
                for window, due_time in windows:
                    _validate_window(window)
                    if due_time is not None:
                        _validate_time(due_time, "due_time")
                    await self._database.execute(
                        "INSERT INTO quest_definition_windows "
                        "(definition_id, window, due_time) VALUES (?, ?, ?)",
                        (definition_id, window, due_time),
                    )
                definition = await self.get(definition_id)
                assignees = await self.list_assignees(definition_id)
                window_records = await self.list_windows(definition_id)
        assert definition is not None
        return QuestDefinitionSnapshot(
            definition=definition,
            assignees=assignees,
            windows=window_records,
        )

    async def edit_definition(
        self,
        definition_id: int,
        *,
        title: str | None | object = _UNSET,
        description: str | None | object = _UNSET,
        icon: str | None | object = _UNSET,
        rule: ScheduleRuleStorage | object = _UNSET,
        windows: list[tuple[str, str | None]] | object = _UNSET,
    ) -> QuestDefinitionSnapshot:
        """Edit a definition's metadata, rule and windows atomically.

        Mirrors :meth:`create_with_rule_and_windows`: everything runs
        inside ONE transaction under the connection lock, and the
        returned snapshot's assignees and windows are read back inside
        that transaction.  Arguments default to the module sentinel
        ``_UNSET`` meaning "leave this field alone"; ``None`` writes SQL
        NULL so optional metadata (description, icon) can be cleared.

        - ``title``/``description``/``icon`` update the definition row
          in place; the definition-level ``due_time`` column is never
          written (per-window due times supersede it, D-008).
        - ``rule`` (a pre-validated :class:`ScheduleRuleStorage`)
          overwrites the referenced ``schedule_rules`` row in place: the
          definition keeps its ``schedule_rule_id``, so no new or
          orphaned rule row appears.
        - ``windows`` REPLACES the whole window set: the current rows
          are deleted and the given set re-inserted, so missing windows
          are added, changed due times updated and removed windows
          dropped.

        Assignment is deliberately not settable here (multi-assignee is
        managed by :meth:`add_assignee`/:meth:`remove_assignee`), and
        activation is untouched.  Raises ValueError when the definition
        does not exist.  Edits change future instances only: no
        ``quest_instances`` or ``completion_events`` row is touched.
        """
        async with _connection_lock(self._database):
            async with self._database.transaction():
                definition = await self.get(definition_id)
                if definition is None:
                    raise ValueError(
                        f"quest definition {definition_id} does not exist"
                    )
                assignments: list[str] = []
                parameters: list[object] = []
                for column, value in (
                    ("title", title),
                    ("description", description),
                    ("icon", icon),
                ):
                    if value is not _UNSET:
                        assignments.append(f"{column} = ?")
                        parameters.append(value)
                if assignments:
                    parameters.append(definition_id)
                    await self._database.execute(
                        f"UPDATE quest_definitions SET "
                        f"{', '.join(assignments)} WHERE id = ?",
                        tuple(parameters),
                    )
                if rule is not _UNSET:
                    await ScheduleRulesDao(self._database).update(
                        definition.schedule_rule_id,
                        rule_type=rule.rule_type,
                        interval=rule.interval,
                        weekday_set=rule.weekday_set,
                        day_of_month=rule.day_of_month,
                        nth_weekday=rule.nth_weekday,
                        month=rule.month,
                        start_date=rule.start_date,
                        end_date=rule.end_date,
                    )
                if windows is not _UNSET:
                    await self._database.execute(
                        "DELETE FROM quest_definition_windows "
                        "WHERE definition_id = ?",
                        (definition_id,),
                    )
                    for window, due_time in windows:
                        _validate_window(window)
                        if due_time is not None:
                            _validate_time(due_time, "due_time")
                        await self._database.execute(
                            "INSERT INTO quest_definition_windows "
                            "(definition_id, window, due_time) "
                            "VALUES (?, ?, ?)",
                            (definition_id, window, due_time),
                        )
                updated = await self.get(definition_id)
                assignees = await self.list_assignees(definition_id)
                window_records = await self.list_windows(definition_id)
        assert updated is not None
        return QuestDefinitionSnapshot(
            definition=updated,
            assignees=assignees,
            windows=window_records,
        )

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

    async def upsert_window(
        self,
        definition_id: int,
        window: str,
        *,
        due_time: str | None = None,
    ) -> QuestDefinitionWindowRecord:
        """Declare (or re-declare) ``window`` on the definition.

        The composite primary key makes the write idempotent per
        (definition, window): re-declaring updates ``due_time`` in
        place instead of duplicating.  The window name must be one of
        ``const.QUEST_WINDOWS`` (the schema CHECK backs this up) and a
        provided ``due_time`` must be strict 24-hour HH:MM.  The
        definition must exist — validated under the connection lock so
        the verdict cannot go stale before the write.
        """
        _validate_window(window)
        if due_time is not None:
            _validate_time(due_time, "due_time")
        async with _connection_lock(self._database):
            async with self._database.transaction():
                definition = await self._database.fetch_one(
                    "SELECT 1 FROM quest_definitions WHERE id = ?",
                    (definition_id,),
                )
                if definition is None:
                    raise ValueError(
                        f"quest definition {definition_id} does not exist"
                    )
                await self._database.execute(
                    "INSERT INTO quest_definition_windows "
                    "(definition_id, window, due_time) VALUES (?, ?, ?) "
                    "ON CONFLICT (definition_id, window) DO UPDATE SET "
                    "due_time = excluded.due_time",
                    (definition_id, window, due_time),
                )
                row = await self._database.fetch_one(
                    f"SELECT {_WINDOW_COLUMNS} "
                    "FROM quest_definition_windows "
                    "WHERE definition_id = ? AND window = ?",
                    (definition_id, window),
                )
        assert row is not None
        return _window_from_row(row)

    async def list_windows(
        self, definition_id: int
    ) -> list[QuestDefinitionWindowRecord]:
        """Return the definition's windows in ``const`` order.

        Ordered by the canonical window sequence (morning, afternoon,
        evening) rather than insertion order, so callers always render
        the Quest Log's three columns consistently.  A definition with
        no windows returns [].
        """
        rows = await self._database.fetch_all(
            f"SELECT {_WINDOW_COLUMNS} FROM quest_definition_windows "
            "WHERE definition_id = ?",
            (definition_id,),
        )
        by_name = {row[1]: _window_from_row(row) for row in rows}
        return [
            by_name[name]
            for name in QUEST_WINDOWS
            if name in by_name
        ]

    async def remove_window(
        self, definition_id: int, window: str
    ) -> bool:
        """Remove the window declaration; True when a row was removed.

        Future materialization stops producing instances for this
        (definition, window); existing instances and completion history
        are never touched here (Feature 06 guardrail).
        """
        _validate_window(window)
        async with _connection_lock(self._database):
            result = await self._database.execute(
                "DELETE FROM quest_definition_windows "
                "WHERE definition_id = ? AND window = ?",
                (definition_id, window),
            )
        return result.rowcount > 0

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