"""The materialization walk (Feature 07 core).

:func:`materialize` turns the schedule rules + custody presence of the
active quest definitions into concrete ``quest_instances`` rows over a
date range.  It is the pure walk over definitions x dates x assignees x
windows; HA scheduling (day-rollover triggers) is a separate later
task and lives elsewhere.

The walk is deterministic and idempotent:

- All inputs — the active definitions with their rules, assignees and
  windows, AND the assignee children's presence schedules and scoped
  overrides — are read inside ONE locked transaction (see
  :func:`~.dao_rules.load_materialization_input`), so the walk sees a
  single coherent snapshot rather than a definition state from one
  instant and a presence state from another.
- Presence is snapshotted into an immutable
  :class:`~.presence.PresenceEngine` from that same coherent read.
- For each date in the range, each definition whose decoded rule
  :func:`~.recurrence.occurs_on` on that date, each assignee who is
  ``is_present`` on that date and each declared window, one instance is
  written through :class:`~.dao_instances.QuestInstancesDao.upsert_if_valid`
  with a ``generated_at`` stamp shared by the whole batch (one coherent
  time per run).

A config change that lands AFTER the snapshot is read but BEFORE a
tuple's write (an assignment removed, a definition or child deactivated,
a window removed) makes that tuple SKIP rather than abort the batch:
:meth:`~.dao_instances.QuestInstancesDao.upsert_if_valid` re-validates
every materialization precondition (active definition, active child,
live assignment, declared window, and its CURRENT ``due_time``) inside
the SAME transaction as the INSERT, so the check and the write cannot be
split by a racing config edit.

The upsert is idempotent on (definition_id, child_id, due_date,
window), so re-running the materialization over the same range never
duplicates a row; a tuple whose instance is already completed is SKIPPED
(never rewritten, never raised) by
:meth:`~.dao_instances.QuestInstancesDao.upsert_if_valid`.
"""
from __future__ import annotations

import datetime

from .const import DEFAULT_HORIZON_DAYS
from .dao_instances import QuestInstancesDao
from .dao_rules import (
    _validate_date,
    load_materialization_input,
    schedule_rule_from_storage,
    schedule_rule_storage_from_record,
)
from .db import NestQuestDatabase
from .presence import PresenceEngine, PresenceOverride, PresenceSchedule
from .recurrence import ScheduleRule, occurs_on


def _now_stamp() -> str:
    """Return the batch's shared UTC second-precision generation stamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _decode_rule(snapshot) -> ScheduleRule:
    """Decode a snapshot's rule record back into a ScheduleRule.

    The record carried by the snapshot is the one the definition
    referenced at read time, so decoding it here (rather than re-reading
    through ``ScheduleRulesDao``) preserves the coherence the snapshot
    guarantees.
    """
    return schedule_rule_from_storage(
        schedule_rule_storage_from_record(snapshot.rule)
    )


def _build_engine(
    schedules_records,
    overrides_records,
) -> PresenceEngine:
    """Convert raw presence records into an immutable PresenceEngine."""
    schedules: dict[int, PresenceSchedule] = {}
    for child_id, record in schedules_records.items():
        schedules[child_id] = PresenceSchedule.decode(
            child_id, record.anchor_date, record.pattern
        )
    overrides: dict[int, list[PresenceOverride]] = {}
    for child_id, records in overrides_records.items():
        overrides[child_id] = [
            PresenceOverride(
                record.child_id,
                record.start_date,
                record.end_date,
                record.is_present,
                record.note,
            )
            for record in records
        ]
    return PresenceEngine(schedules, overrides)


async def materialize(
    database: NestQuestDatabase,
    start_date: str,
    end_date: str,
) -> int:
    """Generate quest instances for the closed range [start_date, end_date].

    ``start_date`` and ``end_date`` must be strict ISO calendar dates
    (YYYY-MM-DD) with ``end_date`` on or after ``start_date``; anything
    else raises ValueError naming the offending field.  Returns the number
    of instances upserted for the range (idempotent — a re-run refreshes
    the same rows, never duplicates them).

    All inputs are read in ONE locked transaction; each tuple's write then
    goes through the atomic :meth:`~.dao_instances.QuestInstancesDao.upsert_if_valid`,
    which re-validates the tuple and its current ``due_time`` in the same
    transaction as the INSERT, so a config change that arrives mid-batch
    skips the affected tuples rather than aborting the batch or leaving a
    partial result.
    """
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    if end_date < start_date:
        raise ValueError(
            f"end_date must be on or after start_date, got "
            f"{end_date!r} < {start_date!r}"
        )

    snapshots, schedules_records, overrides_records = await (
        load_materialization_input(database, start_date, end_date)
    )
    engine = _build_engine(schedules_records, overrides_records)

    definitions = [
        (snapshot.definition.id, _decode_rule(snapshot),
         snapshot.assignees, snapshot.windows)
        for snapshot in snapshots
    ]

    generated_at = _now_stamp()
    instances = QuestInstancesDao(database)

    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

    count = 0
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        for definition_id, rule, assignees, windows in definitions:
            if not occurs_on(rule, cursor):
                continue
            for child in assignees:
                if not engine.is_present(child.id, cursor):
                    continue
                for window in windows:
                    written = await instances.upsert_if_valid(
                        definition_id,
                        child.id,
                        iso,
                        generated_at,
                        window=window.window,
                        due_time=window.due_time,
                    )
                    if written is not None:
                        count += 1
        cursor += datetime.timedelta(days=1)
    return count


async def regenerate_for_definition(
    database: NestQuestDatabase,
    definition_id: int,
) -> int:
    """Regenerate a definition's future instances after a config change.

    The Feature 06 edit/assignment/activation paths call this after a
    successful write so future instances track the new state: the
    definition's open instances at or after today are deleted (never a
    completed instance, never the past) via
    :meth:`~.dao_instances.QuestInstancesDao.delete_future_uncompleted`,
    then the materialization walk re-runs over the rolling horizon
    ``[today, today + DEFAULT_HORIZON_DAYS]`` so the (changed) rule,
    assignee set and windows re-materialize against today's state.

    "today" is computed the same way the walk computes it —
    ``datetime.date.today()`` — so the delete cutoff and the
    re-materialization range share one anchor, and the walk's
    ``upsert_if_valid`` no-past guard never rejects the regenerated
    range.  Returns the number of instances the re-materialization
    upserted across the whole snapshot (idempotent — other active
    definitions' tuples refresh in place, never duplicate).
    """
    today = datetime.date.today()
    start_date = today.isoformat()
    end_date = (today + datetime.timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat()

    instances = QuestInstancesDao(database)
    await instances.delete_future_uncompleted(definition_id, start_date)
    return await materialize(database, start_date, end_date)
