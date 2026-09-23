"""Business layer for creating and editing quest definitions (Feature 06).

Sits between the Feature 09 service gate and the typed
:class:`~.dao_rules.QuestDefinitionsDao`: callers get validation and the
all-or-nothing create/edit here, and never touch the DAO SQL directly.
:func:`create_quest_definition` is the create path,
:func:`edit_quest_definition` the edit path, :func:`assign_child` and
:func:`unassign_child` the assignment paths, and
:func:`set_quest_definition_active` the deactivate/reactivate path.
There is no permission check here (that is Feature 09).

Validation policy mirrors :mod:`.children`:

- ``title`` is required and trimmed; empty or whitespace-only raises
  ValueError.
- ``rule`` must be an already-validated :class:`~.recurrence.ScheduleRule`
  (its constructor is total — rule validation is NOT re-implemented
  here).
- ``assignee_child_ids`` must be a non-empty list (strictly a ``list``);
  every id is a plain int (bools and floats rejected, since SQLite would
  bind them onto a real child) and must reference an existing ACTIVE
  child (the DAO enforces the active/exists check inside the same
  transaction).  Duplicate ids are rejected here, before the composite
  primary key could surface them as an :class:`sqlite3.IntegrityError`.
- ``windows`` must be a non-empty list (strictly a ``list``); each entry
  is a window name from :data:`~.const.QUEST_WINDOWS` — either a bare
  name (no due time) or a ``(name, due_time)`` pair whose due time is a
  strict 24-hour HH:MM string.  Duplicate window names are rejected
  here, before the composite primary key could surface them as an
  :class:`sqlite3.IntegrityError`.

The rule, definition, assignees and windows are persisted in ONE
transaction (the DAO's :meth:`~.dao_rules.QuestDefinitionsDao.create_with_rule_and_windows`),
so a rejected or failed create persists nothing.  The definition-level
``due_time`` column is superseded by per-window due times (D-008) and is
never set here.  ``created_at`` is stamped UTC ISO-8601 at second
precision, matching :mod:`.children`.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from .dao_children import ChildRecord, _connection_lock
from .dao_rules import (
    QuestDefinitionRecord,
    QuestDefinitionSnapshot,
    QuestDefinitionWindowRecord,
    QuestDefinitionsDao,
    ScheduleRuleStorage,
    ScheduleRulesDao,
    _UNSET,
    _validate_date,
    _validate_time,
    _validate_window,
    schedule_rule_from_storage,
    schedule_rule_storage_from_record,
    schedule_rule_to_storage,
)
from .db import NestQuestDatabase
from .materialize import regenerate_for_definition
from .recurrence import ScheduleRule, occurs_on


@dataclass(frozen=True)
class CreatedQuestDefinition:
    """The persisted result of a create, edit or activation change.

    ``definition`` is the stored row; ``rule`` is the schedule rule
    decoded back through the storage mapping; ``assignees`` and
    ``windows`` are the definition's linked child records and window
    declarations, read through the DAO.
    """

    definition: QuestDefinitionRecord
    rule: ScheduleRule
    assignees: list[ChildRecord]
    windows: list[QuestDefinitionWindowRecord]


def _now_stamp() -> str:
    """Return the module's strict UTC second-precision stamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _validate_text(
    value: object, field: str, *, required: bool = False
) -> str | None:
    """Validate a free-text field and return it trimmed.

    ``None`` raises when ``required`` and otherwise returns None.  A
    non-string value is rejected; an empty result is rejected for
    required fields.
    """
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {value!r}")
    trimmed = value.strip()
    if required and not trimmed:
        raise ValueError(f"{field} is required")
    return trimmed


def _validate_assignee_ids(value: object) -> list[int]:
    """Return the assignee ids as plain ints, or raise naming the field.

    The argument must be a non-empty list — strictly a ``list``: tuples
    and other sequences are rejected.  Each entry must be a real int
    (bools and floats rejected) so SQLite cannot bind ``True`` onto
    child 1 or a float onto a neighbouring profile.
    """
    if type(value) is not list:
        raise ValueError(
            f"assignee_child_ids must be a list, got {type(value).__name__}"
        )
    if not value:
        raise ValueError("assignee_child_ids must not be empty")
    ids: list[int] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise ValueError(
                "assignee_child_ids must contain integer child ids, "
                f"got {entry!r}"
            )
        ids.append(entry)
    if len(set(ids)) != len(ids):
        raise ValueError(
            "assignee_child_ids must not contain duplicate child ids"
        )
    return ids


def _normalize_windows(
    value: object,
) -> list[tuple[str, str | None]]:
    """Normalize the windows argument to ``(name, due_time)`` pairs.

    The outer argument must be a non-empty list — strictly a ``list``:
    tuples and other sequences are rejected, while each individual entry
    may still be a ``(window, due_time)`` tuple.  A bare window name
    (due time None) is also accepted.  The name must be a
    :data:`~.const.QUEST_WINDOWS` spelling and a present due time must be
    a strict 24-hour HH:MM, both validated up front so a malformed
    window is rejected before any write.
    """
    if type(value) is not list:
        raise ValueError(
            f"windows must be a list, got {type(value).__name__}"
        )
    if not value:
        raise ValueError("windows must not be empty")
    normalized: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if isinstance(entry, str):
            name: object = entry
            due_time: object = None
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            name, due_time = entry[0], entry[1]
        else:
            raise ValueError(
                f"windows[{index}] must be a window name or a "
                f"(name, due_time) pair, got {entry!r}"
            )
        _validate_window(name)
        if due_time is not None:
            _validate_time(due_time, "due_time")
        if name in seen:
            raise ValueError(
                f"windows must not contain duplicate window {name!r}"
            )
        seen.add(name)
        normalized.append((name, due_time))
    return normalized


def _validate_definition_id(value: object) -> int:
    """Reject non-int definition ids (bools included) before any lookup.

    SQLite binds Python bools as integers, so ``True`` would silently
    address definition 1 and a float would round — malformed service
    input must never mutate the wrong definition.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"definition_id must be an integer, got {value!r}")
    return value


def _validate_child_id(value: object) -> int:
    """Reject non-int child ids (bools included) before any lookup.

    SQLite binds Python bools as integers, so ``True`` would silently
    address child 1 and a float would round — malformed service input
    must never mutate the wrong profile.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"child_id must be an integer, got {value!r}")
    return value


async def create_quest_definition(
    database: NestQuestDatabase,
    title: str,
    rule: ScheduleRule,
    assignee_child_ids: list[int],
    windows: list[str | tuple[str, str | None]],
    *,
    description: str | None = None,
    icon: str | None = None,
) -> CreatedQuestDefinition:
    """Create a quest definition (rule + assignees + windows) atomically.

    Validates the arguments up front, then persists the schedule rule,
    the definition, its assignees and its windows in one transaction via
    the DAO.  Returns the stored definition together with its decoded
    rule, assignees and windows — all read back inside that same
    transaction, so the returned bundle is a consistent creation
    snapshot.  Raises ValueError on any rejected argument; a rejected or
    failed create persists nothing.
    """
    name = _validate_text(title, "title", required=True)
    assert name is not None
    if not isinstance(rule, ScheduleRule):
        raise ValueError(f"rule must be a ScheduleRule, got {rule!r}")
    assignee_ids = _validate_assignee_ids(assignee_child_ids)
    window_specs = _normalize_windows(windows)
    description_value = _validate_text(description, "description")
    icon_value = _validate_text(icon, "icon")

    storage = schedule_rule_to_storage(rule)
    dao = QuestDefinitionsDao(database)
    try:
        snapshot = await dao.create_with_rule_and_windows(
            name,
            storage,
            _now_stamp(),
            assignee_ids,
            window_specs,
            description=description_value,
            icon=icon_value,
        )
    except ValueError as error:
        # The DAO's assignee check names only the child; re-raise so the
        # public contract names the field the caller actually passed.
        message = str(error)
        if message.startswith("child "):
            raise ValueError(
                f"assignee_child_ids: {message}"
            ) from error
        raise
    decoded_rule = schedule_rule_from_storage(storage)
    return CreatedQuestDefinition(
        definition=snapshot.definition,
        rule=decoded_rule,
        assignees=snapshot.assignees,
        windows=snapshot.windows,
    )


async def edit_quest_definition(
    database: NestQuestDatabase,
    definition_id: int,
    *,
    title: str | object = _UNSET,
    description: str | None | object = _UNSET,
    icon: str | None | object = _UNSET,
    rule: ScheduleRule | object = _UNSET,
    windows: list[str | tuple[str, str | None]] | object = _UNSET,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> CreatedQuestDefinition:
    """Edit a quest definition's metadata, rule and windows atomically.

    Arguments default to the sentinel ``_UNSET`` meaning "leave this
    field alone".  A provided ``title`` is validated like create's
    (required and trimmed); ``description`` and ``icon`` are optional
    and may be cleared by passing ``None`` explicitly.  A provided
    ``rule`` must be an already-validated :class:`~.recurrence.ScheduleRule`
    and REPLACES the definition's schedule rule IN PLACE — the existing
    ``schedule_rules`` row is updated, never orphaned or duplicated.  A
    provided ``windows`` list REPLACES the whole window set (each entry
    a ``const.QUEST_WINDOWS`` name, optionally with a strict HH:MM due
    time), matching create's non-empty contract.  Assignment is NOT
    settable here.  Raises ValueError when the definition does not
    exist or any argument is rejected.

    Returns the updated definition together with its decoded rule,
    assignees and windows — all read back inside the DAO's transaction,
    so the returned bundle is a consistent edit snapshot.  Edits change
    future instances only; no ``quest_instances`` or
    ``completion_events`` row is touched.

    ``today`` optionally pins the caller-resolved HA-local date the
    regeneration's no-past guard and horizon are anchored to (threaded
    into :func:`~.materialize.regenerate_for_definition`); it is a plain
    ``datetime.date`` with no HA import here — the Feature 09 service
    supplies the hass-derived value.  When omitted, regeneration falls
    back to the host clock, same as before.  ``horizon_days`` sizes the
    regeneration's re-materialization window the same way (threaded into
    :func:`~.materialize.regenerate_for_definition`); it defaults to
    :data:`~.const.DEFAULT_HORIZON_DAYS` when omitted.
    """
    _validate_definition_id(definition_id)

    title_value: str | None | object = _UNSET
    if title is not _UNSET:
        name = _validate_text(title, "title", required=True)
        assert name is not None
        title_value = name

    description_value: str | None | object = _UNSET
    if description is not _UNSET:
        description_value = _validate_text(description, "description")

    icon_value: str | None | object = _UNSET
    if icon is not _UNSET:
        icon_value = _validate_text(icon, "icon")

    rule_storage: ScheduleRuleStorage | object = _UNSET
    if rule is not _UNSET:
        if not isinstance(rule, ScheduleRule):
            raise ValueError(f"rule must be a ScheduleRule, got {rule!r}")
        rule_storage = schedule_rule_to_storage(rule)

    window_specs: list[tuple[str, str | None]] | object = _UNSET
    if windows is not _UNSET:
        window_specs = _normalize_windows(windows)

    dao = QuestDefinitionsDao(database)
    try:
        snapshot = await dao.edit_definition(
            definition_id,
            title=title_value,
            description=description_value,
            icon=icon_value,
            rule=rule_storage,
            windows=window_specs,
        )
    except ValueError as error:
        # The DAO's missing-definition error names only the id; re-raise
        # so the public contract names the field the caller passed (matching
        # assign/unassign/deactivate).
        message = str(error)
        if message.startswith("quest definition "):
            raise ValueError(f"definition_id: {message}") from error
        raise

    decoded_rule = schedule_rule_from_storage(
        schedule_rule_storage_from_record(snapshot.rule)
    )

    await regenerate_for_definition(
        database, definition_id, today=today, horizon_days=horizon_days
    )

    return CreatedQuestDefinition(
        definition=snapshot.definition,
        rule=decoded_rule,
        assignees=snapshot.assignees,
        windows=snapshot.windows,
    )


async def assign_child(
    database: NestQuestDatabase,
    definition_id: int,
    child_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> list[ChildRecord]:
    """Assign ``child_id`` to the definition (idempotent).

    Validates that both ids are plain ints (bools and floats rejected)
    and that the child exists and is active — the DAO enforces the
    active/exists check inside its transaction, and also confirms the
    definition exists.  Assigning an already-assigned child is a no-op
    (no duplicate row).  Returns the definition's assignees read back
    inside the DAO's same transaction, a consistent post-assignment
    roster (a concurrent assign/unassign cannot race it after the
    write).  Raises ValueError on any rejected argument.  Only the
    ``quest_definition_assignees`` link is written; existing instances
    and completion history are never touched.

    ``today`` optionally pins the caller-resolved HA-local date threaded
    into the assignment's regeneration (see :func:`edit_quest_definition`).
    ``horizon_days`` optionally sizes the regeneration's re-materialization
    window the same way.
    """
    _validate_definition_id(definition_id)
    _validate_child_id(child_id)
    dao = QuestDefinitionsDao(database)
    try:
        assignees = await dao.add_assignee(definition_id, child_id)
    except ValueError as error:
        # The DAO names only the child/definition; re-raise so the
        # public contract names the field the caller actually passed.
        message = str(error)
        if message.startswith("child "):
            raise ValueError(f"child_id: {message}") from error
        if message.startswith("quest definition "):
            raise ValueError(f"definition_id: {message}") from error
        raise
    await regenerate_for_definition(
        database, definition_id, today=today, horizon_days=horizon_days
    )
    return assignees


async def unassign_child(
    database: NestQuestDatabase,
    definition_id: int,
    child_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> bool:
    """Unassign ``child_id`` from the definition; True when removed.

    Validates both ids are plain ints (bools and floats rejected) and
    that the definition exists, then removes the (definition, child)
    link.  Returns True when a row was removed and False when the child
    was not currently assigned.  Raises ValueError on a rejected
    argument.  Only the ``quest_definition_assignees`` link is written;
    existing instances and completion history are never touched.

    ``today`` optionally pins the caller-resolved HA-local date threaded
    into the unassignment's regeneration (see :func:`edit_quest_definition`).
    ``horizon_days`` optionally sizes the regeneration's re-materialization
    window the same way.
    """
    _validate_definition_id(definition_id)
    _validate_child_id(child_id)
    dao = QuestDefinitionsDao(database)
    definition = await dao.get(definition_id)
    if definition is None:
        raise ValueError(
            f"definition_id: quest definition {definition_id} does not exist"
        )
    removed = await dao.remove_assignee(definition_id, child_id)
    await regenerate_for_definition(
        database, definition_id, today=today, horizon_days=horizon_days
    )
    return removed


async def set_quest_definition_active(
    database: NestQuestDatabase,
    definition_id: int,
    is_active: bool,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> CreatedQuestDefinition:
    """Deactivate or reactivate a definition; returns the updated view.

    Flipping the flag is the only removal path (Feature 06 guardrail):
    a deactivated definition stops future instance generation but its
    row, schedule rule, assignees and windows all survive, and existing
    instances plus completion history are never touched.  Reactivation
    re-enables future generation; generating or removing instances is
    Feature 07 and does not happen here.

    ``definition_id`` must be a plain int (bools and floats rejected,
    since SQLite would bind ``True`` onto definition 1) and
    ``is_active`` must be a real bool — the DAO's ``int()`` would
    otherwise silently coerce strings and numerics ("1", 0) into a
    state the caller never asked for.  Raises ValueError naming the
    offending field when the id is malformed, ``is_active`` is not a
    bool, or the definition does not exist.

    Atomicity: the existence check, the UPDATE and the readback of the
    definition, its rule, assignees and windows all run inside the
    connection-scoped lock, so the returned bundle is a consistent
    snapshot that a concurrent mutation cannot race.

    ``today`` optionally pins the caller-resolved HA-local date threaded
    into the activation change's regeneration (see
    :func:`edit_quest_definition`).  ``horizon_days`` optionally sizes the
    regeneration's re-materialization window the same way.
    """
    _validate_definition_id(definition_id)
    if not isinstance(is_active, bool):
        raise ValueError(f"is_active must be a real bool, got {is_active!r}")
    async with _connection_lock(database):
        dao = QuestDefinitionsDao(database)
        if await dao.get(definition_id) is None:
            raise ValueError(
                f"definition_id: quest definition {definition_id} "
                "does not exist"
            )
        await dao.set_active(definition_id, is_active)
        updated = await dao.get(definition_id)
        assert updated is not None
        rule_record = await ScheduleRulesDao(database).get(
            updated.schedule_rule_id
        )
        assert rule_record is not None
        assignees = await dao.list_assignees(definition_id)
        windows = await dao.list_windows(definition_id)
    rule = schedule_rule_from_storage(
        schedule_rule_storage_from_record(rule_record)
    )
    await regenerate_for_definition(
        database, definition_id, today=today, horizon_days=horizon_days
    )
    return CreatedQuestDefinition(
        definition=updated,
        rule=rule,
        assignees=assignees,
        windows=windows,
    )


def _bundle_snapshot(
    snapshot: QuestDefinitionSnapshot,
) -> CreatedQuestDefinition:
    """Decode a DAO snapshot into the layer's rich view.

    The rule record carried by the snapshot is the one the definition
    referenced at read time, so decoding it here (rather than re-reading
    through :class:`~.dao_rules.ScheduleRulesDao`) preserves the
    coherence the DAO's locked snapshot guarantees: the rule, assignees
    and windows all come from one atomic read, never three separate ones.
    """
    rule = schedule_rule_from_storage(
        schedule_rule_storage_from_record(snapshot.rule)
    )
    return CreatedQuestDefinition(
        definition=snapshot.definition,
        rule=rule,
        assignees=snapshot.assignees,
        windows=snapshot.windows,
    )


async def list_active_definitions(
    database: NestQuestDatabase,
) -> list[CreatedQuestDefinition]:
    """Return every ACTIVE definition with its decoded rule and links.

    Ordered by rising definition id, matching the DAO's ``list_active``
    order, so callers get a stable, repeatable sequence.  Each entry is
    the same rich :class:`CreatedQuestDefinition` snapshot as the rest of
    the layer: the stored row plus its decoded
    :class:`~.recurrence.ScheduleRule`, assignees and windows.  The
    definitions and their links are read by the DAO inside one locked
    transaction, so each bundle is a coherent snapshot that a concurrent
    edit cannot interleave.
    """
    dao = QuestDefinitionsDao(database)
    snapshots = await dao.list_snapshots_active()
    return [_bundle_snapshot(snapshot) for snapshot in snapshots]


async def list_definitions_for_child(
    database: NestQuestDatabase,
    child_id: int,
) -> list[CreatedQuestDefinition]:
    """Return the definitions assigned to ``child_id`` (rich view).

    ``child_id`` must be a plain int (bools and floats rejected, since
    SQLite would bind ``True`` onto child 1).  Results are ordered by
    rising definition id, matching ``list_active_definitions`` and
    ``list_definitions_firing_on``.  Each entry is a
    :class:`CreatedQuestDefinition` snapshot bundling the definition with
    its decoded rule, assignees and windows, read atomically by the DAO.
    """
    _validate_child_id(child_id)
    dao = QuestDefinitionsDao(database)
    snapshots = await dao.list_snapshots_by_child(child_id)
    bundles = [_bundle_snapshot(snapshot) for snapshot in snapshots]
    return sorted(bundles, key=lambda bundle: bundle.definition.id)


async def list_definitions_firing_on(
    database: NestQuestDatabase,
    date: str,
) -> list[CreatedQuestDefinition]:
    """Return the ACTIVE definitions whose rule fires on ``date``.

    ``date`` must be a strict ISO calendar date (YYYY-MM-DD); a malformed
    value raises ValueError naming the field.  Each active definition's
    stored rule is decoded through the task-1 storage mapping and handed
    to the recurrence engine's :func:`~.recurrence.occurs_on`; only the
    definitions whose decoded rule fires on the date are returned, in
    rising definition-id order, each as the same rich
    :class:`CreatedQuestDefinition` snapshot as the rest of the layer.
    The definitions and their rules are read inside one locked
    transaction, so a bundle can never filter on one rule while
    presenting another state's windows.
    """
    _validate_date(date, "date")
    target = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    dao = QuestDefinitionsDao(database)
    snapshots = await dao.list_snapshots_active()
    bundles = [_bundle_snapshot(snapshot) for snapshot in snapshots]
    return [bundle for bundle in bundles if occurs_on(bundle.rule, target)]
