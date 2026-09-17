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

Regeneration: a config or presence change must rebuild future instances
so they track the new state.  :func:`regenerate_for_definition` covers
definition edits / reassignment (Features 06/07); :func:`regenerate_for_child`
covers a single child's presence change (Feature 09).  Both delete the
affected open instances at or after today — never a completed instance,
never the past — and re-run the walk over the rolling horizon
``[today, today + horizon_days]`` (``horizon_days`` defaults to
``DEFAULT_HORIZON_DAYS``).

HOOK (Feature 09 presence services): the presence business layer that
lands in Feature 09 MUST call :func:`regenerate_for_child` after EVERY
presence-state write so a child's future instances track its presence:
``set_presence_pattern`` (including clearing/setting an empty pattern),
deleting/clearing the presence schedule
(:meth:`~.dao_presence.PresenceSchedulesDao.delete`),
``create_presence_override``, and ``delete_presence_override``.  A
schedule delete changes presence state too (the child becomes
always-present), so it must regenerate just like the others.  This hook
is documented, not yet wired: no presence business layer exists yet, and
the presence DAO (``dao_presence.py``) must stay free of business rules
— never call :func:`regenerate_for_child` from inside the DAO layer.
"""
from __future__ import annotations

import datetime

from .const import DEFAULT_HORIZON_DAYS
from .dao_instances import QuestInstancesDao, _resolve_today
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
    *,
    child_ids: list[int] | None = None,
    today: datetime.date | None = None,
) -> int:
    """Generate quest instances for the closed range [start_date, end_date].

    ``start_date`` and ``end_date`` must be strict ISO calendar dates
    (YYYY-MM-DD) with ``end_date`` on or after ``start_date``; anything
    else raises ValueError naming the offending field.  Returns the number
    of instances upserted for the range (idempotent — a re-run refreshes
    the same rows, never duplicates them).

    ``child_ids`` optionally scopes the walk to exactly those children:
    assignees outside the list are never written, so a caller that only
    wants one child's instances rebuilt (e.g. :func:`regenerate_for_child`
    after a presence change) cannot touch any unrelated child's rows.
    When omitted (or None) the walk covers every assignee as before.

    ``today`` optionally pins the resolved HA-local date the walk's
    no-past guard compares against; it is threaded into every
    :meth:`~.dao_instances.QuestInstancesDao.upsert_if_valid` write.  When
    omitted the host clock (``datetime.date.today``) is used, which is the
    historical default.  A caller that computed the horizon in Home
    Assistant's configured time zone MUST pass that same date here so a
    time zone behind the host around midnight is not rejected as "past".

    ``start_date`` is clamped up to the resolved "today" (the same
    ``today`` anchor threaded into the no-past guard), so a caller that
    passes a ``start_date`` already in the past never yields a
    past-dated instance: the walk simply begins on today and skips every
    earlier date.  A range entirely in the past therefore produces zero
    instances rather than an error, and the DAO's no-past guard remains
    the authoritative backstop under the lock.

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
    child_filter = None if child_ids is None else set(child_ids)

    definitions = [
        (snapshot.definition.id, _decode_rule(snapshot),
         snapshot.assignees, snapshot.windows)
        for snapshot in snapshots
    ]

    generated_at = _now_stamp()
    instances = QuestInstancesDao(database)

    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

    # Clamp a past start up to today (the HA-local anchor when the caller
    # pinned one, else the host clock) so the walk can never emit a
    # past-dated instance; the DAO's no-past guard remains the backstop.
    # A range entirely in the past therefore yields zero instances.
    today_date = _resolve_today(today)
    start = max(start, today_date)

    count = 0
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        for definition_id, rule, assignees, windows in definitions:
            if not occurs_on(rule, cursor):
                continue
            for child in assignees:
                if child_filter is not None and child.id not in child_filter:
                    continue
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
                        today=today,
                    )
                    if written is not None:
                        count += 1
        cursor += datetime.timedelta(days=1)
    return count


async def regenerate_for_definition(
    database: NestQuestDatabase,
    definition_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> int:
    """Regenerate a definition's future instances after a config change.

    The Feature 06 edit/assignment/activation paths call this after a
    successful write so future instances track the new state: the
    definition's open instances at or after today are deleted (never a
    completed instance, never the past) via
    :meth:`~.dao_instances.QuestInstancesDao.delete_future_uncompleted`,
    then the materialization walk re-runs over the rolling horizon
    ``[today, today + horizon_days]`` so the (changed) rule,
    assignee set and windows re-materialize against today's state.

    "today" is computed the same way the walk computes it —
    :func:`~.dao_instances._today` — so the delete cutoff and the
    re-materialization range share one anchor, and the walk's
    ``upsert_if_valid`` no-past guard never rejects the regenerated
    range.  ``today`` optionally pins a caller-resolved HA-local date
    (threaded into both the delete cutoff and the re-materialization)
    so a household time zone behind the host around midnight stays
    consistent.  ``horizon_days`` sizes the re-materialization window;
    when omitted it falls back to :data:`~.const.DEFAULT_HORIZON_DAYS`.
    Returns the number of instances the re-materialization
    upserted across the whole snapshot (idempotent — other active
    definitions' tuples refresh in place, never duplicate).
    """
    horizon = DEFAULT_HORIZON_DAYS if horizon_days is None else horizon_days
    today_date = _resolve_today(today)
    start_date = today_date.isoformat()
    end_date = (
        today_date + datetime.timedelta(days=horizon)
    ).isoformat()

    instances = QuestInstancesDao(database)
    await instances.delete_future_uncompleted(
        definition_id, start_date, today=today
    )
    return await materialize(database, start_date, end_date, today=today)


# HOOK (Feature 09 presence services): ``regenerate_for_child`` is the
# child-presence counterpart to ``regenerate_for_definition``.  The
# presence business layer that lands in Feature 09 MUST call
# ``regenerate_for_child`` after EVERY presence-state write, so future
# instances track a child's changed presence: set_presence_pattern
# (including clearing/setting an empty pattern), deleting/clearing the
# presence schedule (PresenceSchedulesDao.delete),
# create_presence_override, and delete_presence_override.  A schedule
# delete changes presence state too (the child becomes always-present),
# so it must regenerate just like the others.  It is deliberately NOT
# wired into ``dao_presence.py``: the DAO layer stays pure storage (no
# business rules), and no presence business layer exists yet to host the
# call — see the module docstring note above.
async def regenerate_for_child(
    database: NestQuestDatabase,
    child_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> int:
    """Regenerate a child's future instances after a presence change.

    The Feature 09 presence services call this after every
    presence-state write — set_presence_pattern (including clearing or
    setting an empty pattern), deleting/clearing the presence schedule
    (:meth:`~.dao_presence.PresenceSchedulesDao.delete`),
    create_presence_override, and delete_presence_override — so a
    child's future instances track its new presence: the child's open
    instances at or after today are deleted across ALL its definitions
    (never a completed instance, never the past) via
    :meth:`~.dao_instances.QuestInstancesDao.delete_future_uncompleted_for_child`,
    then the materialization walk re-runs over the rolling horizon
    ``[today, today + horizon_days]`` scoped to that child only,
    so the child's now-absent/present dates re-materialize against
    today's presence WITHOUT touching any other child's rows.

    ``child_id`` must be a plain int — bool and float are rejected
    (SQLite binds a bool as 0/1 and a float would round, so a malformed
    id must never mutate the wrong profile).

    "today" is computed the same way the walk computes it —
    :func:`~.dao_instances._today` — and the re-materialization range uses the
    delete's returned effective cutoff (see
    :meth:`~.dao_instances.QuestInstancesDao.delete_future_uncompleted_for_child`),
    so the delete cutoff and the re-materialization window share ONE
    execution-day anchor even when the call is queued across midnight.
    ``today`` optionally pins a caller-resolved HA-local date, threaded
    into the delete cutoff and the re-materialization for the same
    host-vs-HA time-zone consistency.  ``horizon_days`` sizes the
    re-materialization window; when omitted it falls back to
    :data:`~.const.DEFAULT_HORIZON_DAYS`.  Returns the number of instances
    the re-materialization upserted for the child across the whole
    snapshot.
    """
    if isinstance(child_id, bool) or not isinstance(child_id, int):
        raise ValueError(f"child_id must be an integer, got {child_id!r}")

    horizon = DEFAULT_HORIZON_DAYS if horizon_days is None else horizon_days
    today_date = _resolve_today(today)

    instances = QuestInstancesDao(database)
    # Use the delete's returned effective cutoff as the materialize anchor,
    # NOT the independently-computed "today" above.  If the call is queued
    # across midnight the delete clamps its cutoff to the execution-day;
    # materializing from the stale "today" (now yesterday) would trip the
    # walk's no-past guard and leave the child's future instances deleted
    # but not rebuilt.  One anchor for both keeps them consistent.
    _, effective_cutoff = await instances.delete_future_uncompleted_for_child(
        child_id, today_date.isoformat(), today=today
    )
    start = datetime.date.fromisoformat(effective_cutoff)
    end_date = (start + datetime.timedelta(days=horizon)).isoformat()
    return await materialize(
        database, start.isoformat(), end_date, child_ids=[child_id], today=today
    )
