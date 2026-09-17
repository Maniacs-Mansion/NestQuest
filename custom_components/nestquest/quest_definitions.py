"""Business layer for creating quest definitions (Feature 06).

Sits between the Feature 09 service gate and the typed
:class:`~.dao_rules.QuestDefinitionsDao`: callers get validation and the
all-or-nothing create here, and never touch the DAO SQL directly.
:func:`create_quest_definition` is the create path; there is no
permission check here (that is Feature 09).

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

from .dao_children import ChildRecord
from .dao_rules import (
    QuestDefinitionRecord,
    QuestDefinitionWindowRecord,
    QuestDefinitionsDao,
    _validate_time,
    _validate_window,
    schedule_rule_from_storage,
    schedule_rule_to_storage,
)
from .db import NestQuestDatabase
from .recurrence import ScheduleRule


@dataclass(frozen=True)
class CreatedQuestDefinition:
    """The persisted result of :func:`create_quest_definition`.

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
    snapshot = await dao.create_with_rule_and_windows(
        name,
        storage,
        _now_stamp(),
        assignee_ids,
        window_specs,
        description=description_value,
        icon=icon_value,
    )
    decoded_rule = schedule_rule_from_storage(storage)
    return CreatedQuestDefinition(
        definition=snapshot.definition,
        rule=decoded_rule,
        assignees=snapshot.assignees,
        windows=snapshot.windows,
    )
