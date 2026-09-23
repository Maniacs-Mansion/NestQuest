"""Read-only history layer for the admin plane (Admin spec §5, task 2d2dda53).

Assembles the History screen's event rows over the append-only
completion log: a query over a CLOSED date range ``[start_date,
end_date]`` for one of three filters —

- ``all`` — every completion event (completed AND uncompleted) whose
  instance is due in the range;
- ``reversals`` — the uncompleted events only;
- ``missed`` — the DERIVED missed instances in the range.

Range semantics (Feature 13's rule, kept): the range scopes by the
INSTANCE's ``due_date`` — the day the task was owed — not the event's
wall-clock ``occurred_at``, because history reporting asks "what
happened to the tasks due that day".  ``missed`` is derived, never
stored: rows come from :func:`~.completion.list_missed_for_child`
(past-due open instances, the same ``_derived_state`` rule the
coordinator uses), and nothing is ever appended for them.

Row shape: the Admin spec §5 event-row fields, fixed and documented in
:data:`CSV_COLUMNS` — ``occurred_at``, ``event_type``,
``child_name``, ``child_id``, ``quest_title``, ``instance_id``,
``window``, ``due_date``, ``due_time``, ``actor``, ``was_on_time``.
Derived missed rows carry ``event_type`` ``'missed'`` (never a stored
event_type), no ``occurred_at`` (there is no event), ``was_on_time``
``None`` and the spec's ``nightly sweep`` actor.  A stored event's
``actor`` follows the spec's meta shape: the ``actor_user_id`` string
for a user event (``joshua``), ``panel (Child)`` naming the tapped
profile for a panel event.

Validation policy (module-level, shared by both the JSON query and the
CSV export): the filter must be one of :data:`FILTERS` and the range
must be two strict ``YYYY-MM-DD`` dates with ``end >= start``;
violations raise ``ValueError`` naming the offending field
(``filter`` / ``start`` / ``end``) BEFORE any read.  The whole
household read runs under the task-reentrant connection lock so every
row of one answer is one snapshot — the same discipline
:mod:`.completion` gives its read-decide-write paths.

:func:`rows_to_csv` serializes rows with the :mod:`csv` module (proper
quoting, one stable header row) and :func:`export_history_csv` runs
query + serialization as ONE call, so the CSV export can never drift
from the JSON query's filtered range.  No permission check lives here
(that is the admin router's single ``require_admin`` dependency).
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import dataclass

from .completion import _reentrant_connection_lock, list_missed_for_child
from .dao_children import ChildRecord, ChildrenDao
from .dao_instances import (
    EVENT_UNCOMPLETED,
    CompletionEventRecord,
    CompletionEventsDao,
    QuestInstanceRecord,
    QuestInstancesDao,
)
from .dao_rules import QuestDefinitionsDao, _validate_date
from .db import NestQuestDatabase

#: The ``all`` filter: every completion event in the range.
FILTER_ALL = "all"

#: The ``reversals`` filter: uncompleted events only.
FILTER_REVERSALS = "reversals"

#: The ``missed`` filter: derived missed instances in the range.
FILTER_MISSED = "missed"

#: The filters the query accepts, in the Admin spec's chip order.
FILTERS = (FILTER_ALL, FILTER_REVERSALS, FILTER_MISSED)

#: The ``event_type`` a derived missed row reports.  ``missed`` is a
#: DERIVED state, never a stored event_type (Feature 08).
EVENT_MISSED = "missed"

#: The actor a derived missed row reports (Admin spec §5 meta:
#: ``missed · nightly sweep``).
ACTOR_NIGHTLY_SWEEP = "nightly sweep"

#: The CSV column set, in header order — the Admin spec §5 event-row
#: fields.  The header row is exactly this tuple, always, so a consumer
#: can key on column names.
CSV_COLUMNS = (
    "occurred_at",
    "event_type",
    "child_name",
    "child_id",
    "quest_title",
    "instance_id",
    "window",
    "due_date",
    "due_time",
    "actor",
    "was_on_time",
)


@dataclass(frozen=True)
class HistoryRow:
    """One history row: a stored event or a derived missed instance.

    The fields are :data:`CSV_COLUMNS` in order.  For a derived missed
    row ``occurred_at`` is ``None`` (no event exists) and ``was_on_time``
    is ``None``; for a stored event ``event_type`` is
    ``'completed'``/``'uncompleted'`` and the fields come from the event
    joined with its instance, child and definition.
    """

    occurred_at: str | None
    event_type: str
    child_name: str
    child_id: int
    quest_title: str
    instance_id: int
    window: str
    due_date: str
    due_time: str | None
    actor: str
    was_on_time: bool | None


def _validate_filter(filter_name: str) -> str:
    """Return the filter, or raise ValueError naming the field."""
    if filter_name not in FILTERS:
        raise ValueError(
            f"filter must be one of {', '.join(repr(f) for f in FILTERS)}, "
            f"got {filter_name!r}"
        )
    return filter_name


def _validate_range(start_date: str, end_date: str) -> tuple[str, str]:
    """Validate the closed range and return it, else raise naming the field.

    Both bounds must be strict ``YYYY-MM-DD`` dates (the shared
    :func:`~.dao_rules._validate_date`, so non-padded or re-ordered
    shapes are rejected and a non-string raises naming the field) and
    ``end`` must be on or after ``start``.
    """
    _validate_date(start_date, "start")
    _validate_date(end_date, "end")
    if end_date < start_date:
        raise ValueError(
            f"end must be on or after start, got {end_date!r} < "
            f"{start_date!r}"
        )
    return start_date, end_date


def _resolve_today(today: datetime.date | None) -> datetime.date:
    """Return the threaded HA-local date, or the host calendar date."""
    if today is None:
        return datetime.date.today()
    return today


def _event_actor(
    event: CompletionEventRecord, actor_child: ChildRecord | None
) -> str:
    """Return the spec-meta actor string for one stored event.

    A user event reports the ``actor_user_id`` string (the spec's
    ``uncompleted · joshua (admin)`` shape); a panel event reports
    ``panel (Child)`` naming the tapped profile.  The tapped child is
    never hard-deleted, so the lookup below is a belt-and-braces
    fallback to the stored id, never a silent rewrite of policy.
    """
    if event.actor_source == "user":
        return event.actor_user_id or ""
    if actor_child is not None:
        return f"panel ({actor_child.display_name})"
    return f"panel ({event.actor_child_id})"


def _event_row(
    event: CompletionEventRecord,
    instance: QuestInstanceRecord,
    child: ChildRecord,
    quest_title: str,
    actor_child: ChildRecord | None,
) -> HistoryRow:
    """Join one stored event with its instance, child and definition."""
    return HistoryRow(
        occurred_at=event.occurred_at,
        event_type=event.event_type,
        child_name=child.display_name,
        child_id=event.child_id,
        quest_title=quest_title,
        instance_id=event.instance_id,
        window=instance.window,
        due_date=instance.due_date,
        due_time=instance.due_time,
        actor=_event_actor(event, actor_child),
        was_on_time=event.was_on_time,
    )


def _missed_row(
    instance: QuestInstanceRecord,
    child: ChildRecord,
    quest_title: str,
) -> HistoryRow:
    """Build the derived row for one past-due open instance."""
    return HistoryRow(
        occurred_at=None,
        event_type=EVENT_MISSED,
        child_name=child.display_name,
        child_id=instance.child_id,
        quest_title=quest_title,
        instance_id=instance.id,
        window=instance.window,
        due_date=instance.due_date,
        due_time=instance.due_time,
        actor=ACTOR_NIGHTLY_SWEEP,
        was_on_time=None,
    )


def _csv_values(row: HistoryRow) -> list[str]:
    """Return one CSV row's cell values in :data:`CSV_COLUMNS` order.

    ``None`` cells serialize as empty (a missed row has no
    ``occurred_at``); ``was_on_time`` serializes as ``true``/``false``
    when the event carries the flag and empty when it does not.
    """
    return [
        row.occurred_at or "",
        row.event_type,
        row.child_name,
        str(row.child_id),
        row.quest_title,
        str(row.instance_id),
        row.window,
        row.due_date,
        row.due_time or "",
        row.actor,
        "" if row.was_on_time is None else str(row.was_on_time).lower(),
    ]


def rows_to_csv(rows: list[HistoryRow]) -> str:
    """Serialize history rows to CSV text with the documented header.

    The FIRST row is always :data:`CSV_COLUMNS`, so the header is
    stable and deterministic; the :mod:`csv` module handles quoting
    (titles or names containing commas or quotes are quoted per RFC
    4180) and CRLF line endings.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(_csv_values(row))
    return buffer.getvalue()


async def query_history(
    database: NestQuestDatabase,
    filter_name: str,
    start_date: str,
    end_date: str,
    *,
    today: datetime.date | None = None,
) -> list[HistoryRow]:
    """Return the history rows for ``filter_name`` over the closed range.

    Validates the filter and the strict ``YYYY-MM-DD`` range (raising
    ``ValueError`` naming ``filter`` / ``start`` / ``end``) BEFORE any
    read, then builds the rows:

    - ``all`` / ``reversals``: every child's events whose instances are
      due in the range (:meth:`~.dao_instances.CompletionEventsDao.list_by_child_and_date_range`,
      the Feature 13 due-date scope), ``reversals`` keeping only the
      ``uncompleted`` rows.
    - ``missed``: :func:`~.completion.list_missed_for_child` per child —
      the SAME derived-state rule the coordinator uses, never a new one,
      and never a stored event.

    Rows are ordered deterministically by ``due_date``, then instance,
    then event id (the per-instance append order, so a completion and
    its reversal keep their order).  ``today`` pins the HA-local date
    the missed derivation compares due dates against (the host calendar
    date when omitted).  The whole read runs under the task-reentrant
    connection lock — :func:`list_missed_for_child` re-enters it — so
    one answer is one snapshot.
    """
    filter_name = _validate_filter(filter_name)
    start_date, end_date = _validate_range(start_date, end_date)
    today_date = _resolve_today(today)

    keyed: list[tuple[tuple[str, int, int], HistoryRow]] = []
    async with _reentrant_connection_lock(database):
        children = await ChildrenDao(database).list_all()
        children_by_id = {child.id: child for child in children}
        instances = QuestInstancesDao(database)
        definitions = QuestDefinitionsDao(database)
        events = CompletionEventsDao(database)
        titles: dict[int, str] = {}

        if filter_name == FILTER_MISSED:
            for child in children:
                for instance in await list_missed_for_child(
                    database, child.id, start_date, end_date, today=today_date
                ):
                    if instance.definition_id not in titles:
                        definition = await definitions.get(
                            instance.definition_id
                        )
                        assert definition is not None, (
                            "a materialized instance's definition exists"
                        )
                        titles[instance.definition_id] = definition.title
                    keyed.append(
                        (
                            (instance.due_date, instance.id, 0),
                            _missed_row(
                                instance,
                                child,
                                titles[instance.definition_id],
                            ),
                        )
                    )
            keyed.sort(key=lambda pair: pair[0])
            return [row for _, row in keyed]

        for child in children:
            for event in await events.list_by_child_and_date_range(
                child.id, start_date, end_date
            ):
                if filter_name == FILTER_REVERSALS and (
                    event.event_type != EVENT_UNCOMPLETED
                ):
                    continue
                instance = await instances.get_by_id(event.instance_id)
                assert instance is not None, (
                    "an event's instance is never deleted (append-only "
                    "history keeps its references)"
                )
                actor_child = (
                    children_by_id.get(event.actor_child_id)
                    if event.actor_child_id is not None
                    else None
                )
                if instance.definition_id not in titles:
                    definition = await definitions.get(instance.definition_id)
                    assert definition is not None, (
                        "a materialized instance's definition exists"
                    )
                    titles[instance.definition_id] = definition.title
                keyed.append(
                    (
                        (instance.due_date, instance.id, event.id),
                        _event_row(
                            event,
                            instance,
                            child,
                            titles[instance.definition_id],
                            actor_child,
                        ),
                    )
                )
        keyed.sort(key=lambda pair: pair[0])
        return [row for _, row in keyed]


async def export_history_csv(
    database: NestQuestDatabase,
    filter_name: str,
    start_date: str,
    end_date: str,
    *,
    today: datetime.date | None = None,
) -> str:
    """Return the filtered history as CSV text, header row included.

    ONE query + serialization call so the CSV export carries exactly
    the JSON query's filtered range and order — the same
    :func:`query_history` validation, rows and :func:`rows_to_csv`
    serializer, never a second implementation.
    """
    rows = await query_history(
        database, filter_name, start_date, end_date, today=today
    )
    return rows_to_csv(rows)


__all__ = [
    "ACTOR_NIGHTLY_SWEEP",
    "CSV_COLUMNS",
    "EVENT_MISSED",
    "EVENT_UNCOMPLETED",
    "FILTERS",
    "FILTER_ALL",
    "FILTER_MISSED",
    "FILTER_REVERSALS",
    "HistoryRow",
    "export_history_csv",
    "query_history",
    "rows_to_csv",
]
