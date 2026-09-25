"""The materialization walk (Feature 07 core).

:func:`materialize` turns the schedule rules + custody presence of the
active quest definitions into concrete ``quest_instances`` rows over a
date range.  It is the pure walk over definitions x dates x assignees x
windows; HA scheduling (day-rollover triggers) is a separate later
task and lives elsewhere.

The walk is deterministic and idempotent:

- All inputs — the active definitions with their rules, assignees and
  windows, AND the assignee children's presence patterns and scoped
  overrides — are read inside ONE locked transaction (see
  :func:`~.dao_rules.load_materialization_input`), so the walk sees a
  single coherent snapshot rather than a definition state from one
  instant and a presence state from another.
- Presence is snapshotted into an immutable
  :class:`~.presence.PresenceEngine` from that same coherent read.
- For each date in the range, each definition whose decoded rule
  :func:`~.recurrence.occurs_on` on that date, each assignee who is
  ``is_present`` on that date (or every assignee, when the definition's
  ``skip_on_away`` is off) and each declared window, one instance is
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
creating, updating and deleting a presence pattern
(:mod:`.presence_management`'s ``create_presence_pattern`` /
``update_presence_pattern`` / ``delete_presence_pattern``),
``create_presence_override``, and ``delete_presence_override``.  A
pattern delete changes presence state too, so it must regenerate just
like the others.  This hook
is documented, not yet wired: no presence business layer exists yet, and
the presence DAO (``dao_presence.py``) must stay free of business rules
— never call :func:`regenerate_for_child` from inside the DAO layer.
"""
from __future__ import annotations

import datetime
from typing import NamedTuple

from .const import DEFAULT_HORIZON_DAYS
from .dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
    _resolve_today,
)
from .dao_rules import (
    _validate_date,
    load_materialization_input,
    schedule_rule_from_storage,
    schedule_rule_storage_from_record,
)
from .db import NestQuestDatabase
from .presence import PresenceEngine, PresenceOverride, PresencePattern
from .recurrence import ScheduleRule, occurs_on


def _now_stamp() -> str:
    """Return the batch's shared UTC second-precision generation stamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _resolve_horizon_days(horizon_days: int | None) -> int:
    """Validate a regeneration horizon and return the resolved day count.

    ``None`` resolves to :data:`~.const.DEFAULT_HORIZON_DAYS`.  A bool
    (SQLite would happily bind ``True``/``False`` onto an int), a non-int,
    or a value below 1 raises ValueError naming the field — the validation
    runs BEFORE any future-instance delete so a malformed horizon can never
    delete rows it then fails to rebuild.  A negative horizon would
    otherwise delete first and only then be rejected by
    :func:`materialize`'s inverted-range check; ``0``/``False`` would
    silently shrink the window to a single day.
    """
    if horizon_days is None:
        return DEFAULT_HORIZON_DAYS
    if (
        isinstance(horizon_days, bool)
        or not isinstance(horizon_days, int)
        or horizon_days < 1
    ):
        raise ValueError(
            f"horizon_days must be a positive integer, got {horizon_days!r}"
        )
    return horizon_days


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
    patterns_records,
    overrides_records,
    *,
    extra_overrides: tuple[PresenceOverride, ...] = (),
) -> PresenceEngine:
    """Convert raw presence records into an immutable PresenceEngine.

    ``extra_overrides`` layers already-validated, NOT-yet-stored
    overrides on top of the stored ones — the consequence preview's
    proposed override (:func:`count_removed_by_override`).
    """
    patterns: dict[int, list[PresencePattern]] = {}
    for child_id, records in patterns_records.items():
        patterns[child_id] = [
            PresencePattern.decode(
                record.child_id,
                record.name,
                record.kind,
                record.anchor_date,
                record.pattern,
            )
            for record in records
        ]
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
    for override in extra_overrides:
        overrides.setdefault(override.child_id, []).append(override)
    return PresenceEngine(patterns, overrides)


class GeneratedTuple(NamedTuple):
    """One instance the walk WOULD write: its upsert key plus due time."""

    definition_id: int
    child_id: int
    due_date: str
    window: str
    due_time: str | None


def _generation_preview(
    snapshots,
    engine: PresenceEngine,
    start: datetime.date,
    end: datetime.date,
    *,
    child_filter: set[int] | None = None,
) -> list[GeneratedTuple]:
    """Return the tuples the walk would write over ``[start, end]``.

    The pure, read-only half of :func:`materialize`: for each date, each
    definition whose decoded rule :func:`~.recurrence.occurs_on` it,
    each assignee in ``child_filter`` (every assignee when None) who is
    ``is_present`` on it — or every assignee when the definition's
    ``skip_on_away`` is off — and each declared window, one tuple, in
    the walk's write order.  :func:`materialize` writes exactly these
    tuples and :func:`count_removed_by_override` compares two of these
    previews, so the write and the consequence preview can never
    diverge.  No database access.
    """
    definitions = [
        (snapshot.definition.id, _decode_rule(snapshot),
         snapshot.assignees, snapshot.windows,
         snapshot.definition.skip_on_away)
        for snapshot in snapshots
    ]
    generated: list[GeneratedTuple] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        for (
            definition_id, rule, assignees, windows, skip_on_away
        ) in definitions:
            if not occurs_on(rule, cursor):
                continue
            for child in assignees:
                if child_filter is not None and child.id not in child_filter:
                    continue
                if skip_on_away and not engine.is_present(child.id, cursor):
                    continue
                for window in windows:
                    generated.append(
                        GeneratedTuple(
                            definition_id,
                            child.id,
                            iso,
                            window.window,
                            window.due_time,
                        )
                    )
        cursor += datetime.timedelta(days=1)
    return generated


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

    snapshots, patterns_records, overrides_records = await (
        load_materialization_input(database, start_date, end_date)
    )
    engine = _build_engine(patterns_records, overrides_records)
    child_filter = None if child_ids is None else set(child_ids)

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
    for generated in _generation_preview(
        snapshots, engine, start, end, child_filter=child_filter
    ):
        written = await instances.upsert_if_valid(
            generated.definition_id,
            generated.child_id,
            generated.due_date,
            generated_at,
            window=generated.window,
            due_time=generated.due_time,
            today=today,
        )
        if written is not None:
            count += 1
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
    A bool, non-int, or sub-1 value raises ValueError BEFORE any delete.
    Returns the number of instances the re-materialization
    upserted across the whole snapshot (idempotent — other active
    definitions' tuples refresh in place, never duplicate).
    """
    horizon = _resolve_horizon_days(horizon_days)
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
# instances track a child's changed presence: create_presence_pattern,
# update_presence_pattern, delete_presence_pattern,
# create_presence_override, and delete_presence_override.  A pattern
# delete changes presence state too, so it must regenerate just like
# the others.  It is deliberately NOT
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
    presence-state write — create_presence_pattern,
    update_presence_pattern, delete_presence_pattern,
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
    :data:`~.const.DEFAULT_HORIZON_DAYS`.  A bool, non-int, or sub-1 value
    raises ValueError BEFORE any delete.  Returns the number of instances
    the re-materialization upserted for the child across the whole
    snapshot.
    """
    if isinstance(child_id, bool) or not isinstance(child_id, int):
        raise ValueError(f"child_id must be an integer, got {child_id!r}")

    horizon = _resolve_horizon_days(horizon_days)
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


async def count_removed_by_override(
    database: NestQuestDatabase,
    override: PresenceOverride,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> int:
    """Count the upcoming instances saving ``override`` would remove.

    Read-only: nothing is written.  The window is the part of the
    override's range inside the rolling horizon ``[today, today +
    horizon_days]`` that :func:`regenerate_for_child` rebuilds after the
    override is saved (outside the range the two presence answers agree,
    so nothing there can change).  The materialization input is read
    ONCE (:func:`~.dao_rules.load_materialization_input`) and
    :func:`_generation_preview` runs twice over it for the override's
    child — with the stored presence, and with ``override`` layered on
    top (:func:`_build_engine`'s ``extra_overrides``).  The count is the
    tuples the first preview generates and the second does not, MINUS
    every (definition, date, window) whose stored instance already has a
    completion event (D-005: regeneration never deletes those).  A
    definition with ``skip_on_away`` off generates regardless of
    presence, so it contributes nothing; a present override only ever
    ADDS tuples, so it counts 0.

    An override overlapping a stored one (which the create path refuses)
    resolves through the engine's latest-start-wins rule.  ``today`` and
    ``horizon_days`` resolve exactly as :func:`regenerate_for_child`
    resolves them; a malformed horizon raises ValueError.
    """
    horizon = _resolve_horizon_days(horizon_days)
    today_date = _resolve_today(today)
    start = max(today_date, override.start_date)
    end = min(
        today_date + datetime.timedelta(days=horizon), override.end_date
    )
    if end < start:
        return 0
    start_date, end_date = start.isoformat(), end.isoformat()
    child_id = override.child_id

    snapshots, patterns_records, overrides_records = await (
        load_materialization_input(database, start_date, end_date)
    )
    current = _generation_preview(
        snapshots,
        _build_engine(patterns_records, overrides_records),
        start,
        end,
        child_filter={child_id},
    )
    proposed = set(
        _generation_preview(
            snapshots,
            _build_engine(
                patterns_records,
                overrides_records,
                extra_overrides=(override,),
            ),
            start,
            end,
            child_filter={child_id},
        )
    )
    removed = [generated for generated in current if generated not in proposed]
    if not removed:
        return 0

    stored = await QuestInstancesDao(database).list_by_date_range(
        child_id, start_date, end_date
    )
    touched = {
        event.instance_id
        for event in await CompletionEventsDao(
            database
        ).list_by_child_and_date_range(child_id, start_date, end_date)
    }
    completed = {
        (instance.definition_id, instance.due_date, instance.window)
        for instance in stored
        if instance.id in touched
    }
    return sum(
        1
        for generated in removed
        if (generated.definition_id, generated.due_date, generated.window)
        not in completed
    )
