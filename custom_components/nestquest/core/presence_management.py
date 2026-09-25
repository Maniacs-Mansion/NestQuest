"""Business layer for presence writes (Feature 09, API admin plane).

Sits between the write callers (the Feature 09 HA service handlers and
the API admin plane's presence routes) and the typed presence DAOs plus
the pure presence model: callers get the model validation, the create /
update / delete operations and the regeneration side effect here, and
never touch the DAO or SQL directly.  This is the ONE implementation of
these business rules — every caller constructs the same
:class:`~.presence.PresencePattern` / :class:`~.presence.PresenceOverride`
models (whose constructors are total, so no re-validation happens in a
handler) and gets the same post-write
:func:`~.materialize.regenerate_for_child`, so a child's future quest
instances track its changed presence no matter which plane issued the
write.  Like the model it is Home-Assistant-free: ``today`` is a plain
calendar date threaded through to the regeneration, defaulting to the
host clock there.

Pattern policy (schema 9): a child has ZERO OR MORE presence patterns,
each created, edited and deleted by its own id.  Patterns and overrides
are deletable by design (children are not — the children layer owns
that guardrail).  An unknown pattern or override id raises ValueError
prefixed ``pattern_id:`` / ``override_id:`` so a caller can distinguish
"unknown id" from a rejected argument the same way the
quest-definitions layer prefixes ``definition_id:``.

The admin plane's presence READS go through here too
(:func:`list_presence_patterns`, :func:`list_presence_overrides`), so a
reader never touches the DAO directly either.
"""
from __future__ import annotations

import datetime

from .dao_children import ChildrenDao
from .dao_presence import (
    PresenceOverrideRecord,
    PresenceOverridesDao,
    PresencePatternRecord,
    PresencePatternsDao,
)
from .dao_rules import _UNSET
from .db import NestQuestDatabase
from .materialize import count_removed_by_override, regenerate_for_child
from .presence import PresenceOverride, PresencePattern


def _validate_override_id(value: object) -> int:
    """Reject non-int override ids (bools would silently address id 1)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"override_id must be an integer, got {value!r}")
    return value


def _validate_pattern_id(value: object) -> int:
    """Reject non-int pattern ids (bools would silently address id 1)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"pattern_id must be an integer, got {value!r}")
    return value


async def _get_pattern_or_raise(
    dao: PresencePatternsDao, pattern_id: object
) -> PresencePatternRecord:
    """Return the stored pattern; an unknown id raises ``pattern_id:``."""
    record = await dao.get(_validate_pattern_id(pattern_id))
    if record is None:
        raise ValueError(
            f"pattern_id: presence pattern {pattern_id} does not exist"
        )
    return record


def decode_pattern_record(record: PresencePatternRecord) -> PresencePattern:
    """Decode one stored pattern row back through the model."""
    return PresencePattern.decode(
        record.child_id,
        record.name,
        record.kind,
        record.anchor_date,
        record.pattern,
    )


async def create_presence_pattern(
    database: NestQuestDatabase,
    child_id: int,
    name: str,
    kind: str,
    cycle_length_weeks: int,
    anchor_date: object,
    pattern: dict[int, object],
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> PresencePatternRecord:
    """Add one repeating presence pattern to a child.

    The :class:`~.presence.PresencePattern` model validates at
    construction — a non-blank name, ``kind`` ``home``/``away``, cycle
    length 1..4, a strict calendar anchor date, and a pattern covering
    week indices 0..n-1 with weekday sets — so no invalid pattern
    reaches the DAO.  The encoded pattern is inserted beside the
    child's other patterns, then :func:`~.materialize.regenerate_for_child`
    re-materializes the child's future instances against the new
    presence.  ``today``/``horizon_days`` thread through to that
    regeneration; raising ValueError names what to fix (an unknown
    child reads ``child N does not exist``).

    Returns the STORED record WITH its ``id`` — the handle
    :func:`update_presence_pattern` and :func:`delete_presence_pattern`
    take.
    """
    model = PresencePattern(
        child_id, name, kind, cycle_length_weeks, anchor_date, pattern
    )
    record = await PresencePatternsDao(database).create(
        model.child_id,
        model.name,
        model.kind,
        model.cycle_length_weeks,
        model.anchor_date.isoformat(),
        model.encode(),
    )
    await regenerate_for_child(
        database, model.child_id, today=today, horizon_days=horizon_days
    )
    return record


async def update_presence_pattern(
    database: NestQuestDatabase,
    pattern_id: int,
    *,
    name: str | object = _UNSET,
    kind: str | object = _UNSET,
    cycle_length_weeks: int | object = _UNSET,
    anchor_date: object = _UNSET,
    pattern: dict[int, object] | object = _UNSET,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> PresencePatternRecord:
    """Edit one presence pattern; only supplied fields change.

    The pattern is looked up FIRST (an unknown id raises ValueError
    prefixed ``pattern_id:``), the supplied fields are laid over the
    stored ones and the WHOLE result is rebuilt through the
    :class:`~.presence.PresencePattern` model — so a partial edit is
    validated exactly as a create is (changing ``cycle_length_weeks``
    without a matching ``pattern`` is rejected), and an explicit None
    is rejected rather than ignored.  The pattern stays with its child;
    the child's future instances are regenerated afterwards.
    """
    dao = PresencePatternsDao(database)
    stored = decode_pattern_record(await _get_pattern_or_raise(dao, pattern_id))
    model = PresencePattern(
        stored.child_id,
        stored.name if name is _UNSET else name,
        stored.kind if kind is _UNSET else kind,
        (
            stored.cycle_length_weeks
            if cycle_length_weeks is _UNSET
            else cycle_length_weeks
        ),
        stored.anchor_date if anchor_date is _UNSET else anchor_date,
        dict(stored.pattern) if pattern is _UNSET else pattern,
    )
    record = await dao.update(
        pattern_id,
        model.name,
        model.kind,
        model.cycle_length_weeks,
        model.anchor_date.isoformat(),
        model.encode(),
    )
    if record is None:
        raise ValueError(
            f"pattern_id: presence pattern {pattern_id} does not exist"
        )
    await regenerate_for_child(
        database, model.child_id, today=today, horizon_days=horizon_days
    )
    return record


async def delete_presence_pattern(
    database: NestQuestDatabase,
    pattern_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> PresencePatternRecord:
    """Delete one presence pattern by id and return it as it was stored.

    The pattern is looked up FIRST and an unknown id raises ValueError
    prefixed ``pattern_id:`` BEFORE any delete, so a mistyped id can
    never be silently swallowed by a no-op.  The deletion is followed
    by :func:`~.materialize.regenerate_for_child` for the pattern's own
    child — the id decides the child, never a caller-supplied one.
    """
    dao = PresencePatternsDao(database)
    record = await _get_pattern_or_raise(dao, pattern_id)
    await dao.delete(record.id)
    await regenerate_for_child(
        database, record.child_id, today=today, horizon_days=horizon_days
    )
    return record


async def create_presence_override(
    database: NestQuestDatabase,
    child_id: int,
    start_date: object,
    end_date: object,
    is_present: bool,
    note: str | None = None,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> PresenceOverrideRecord:
    """Create one date-range presence override and return it as stored.

    The :class:`~.presence.PresenceOverride` model validates at
    construction — strict calendar dates, ``end_date`` on or after
    ``start_date``, a real ``is_present`` bool, a string-or-None note —
    then the DAO insert applies the same-child no-overlap policy (a
    conflicting range raises ValueError naming the existing override)
    and :func:`~.materialize.regenerate_for_child` re-materializes the
    child's future instances against the override's presence answer.
    An unknown child reads ``child N does not exist``.

    Returns the stored record WITH its ``id`` — the handle a later
    :func:`delete_presence_override` takes.
    """
    override = PresenceOverride(
        child_id, start_date, end_date, is_present, note=note
    )
    record = await PresenceOverridesDao(database).create(
        override.child_id,
        override.start_date.isoformat(),
        override.end_date.isoformat(),
        override.is_present,
        note=override.note,
    )
    await regenerate_for_child(
        database, override.child_id, today=today, horizon_days=horizon_days
    )
    return record


async def preview_presence_override_consequence(
    database: NestQuestDatabase,
    child_id: int,
    start_date: object,
    end_date: object,
    is_present: bool,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> int:
    """Return how many upcoming instances saving this override removes.

    The admin override editor's live consequence warning, computed
    BEFORE anything is saved: the arguments build the SAME
    :class:`~.presence.PresenceOverride` :func:`create_presence_override`
    builds (so a malformed or inverted range, or a non-bool
    ``is_present``, raises the same ValueError), then
    :func:`~.materialize.count_removed_by_override` compares what the
    materialization walk generates for the child with and without it.
    Nothing is written.  An unknown child reads ``child N does not
    exist``; an INACTIVE child has no instances to remove (the walk's
    write path never materializes one), so it counts 0.
    ``today``/``horizon_days`` resolve as the post-save regeneration
    resolves them.
    """
    override = PresenceOverride(child_id, start_date, end_date, is_present)
    child = await ChildrenDao(database).get(override.child_id)
    if child is None:
        raise ValueError(f"child {override.child_id} does not exist")
    if not child.is_active:
        return 0
    return await count_removed_by_override(
        database, override, today=today, horizon_days=horizon_days
    )


async def list_presence_patterns(
    database: NestQuestDatabase, child_id: int
) -> list[PresencePatternRecord]:
    """Return the child's presence patterns ordered by id.

    An empty list means the child exists and has no pattern — present
    every day (Feature 05).  An unknown child raises ValueError
    (``child N does not exist``) rather than reading as present.
    """
    return await PresencePatternsDao(database).list_by_child(child_id)


async def list_presence_overrides(
    database: NestQuestDatabase,
    *,
    child_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[PresenceOverrideRecord]:
    """Return the household's presence overrides, optionally filtered.

    ``child_id`` narrows to one child (unknown: ``child N does not
    exist``); ``start``/``end`` keep the overrides overlapping that
    closed range (strict YYYY-MM-DD, ``end >= start``).  Ordered by
    start date, then child id, then id.
    """
    return await PresenceOverridesDao(database).list_filtered(
        child_id=child_id, start=start, end=end
    )


async def delete_presence_override(
    database: NestQuestDatabase,
    override_id: int,
    *,
    today: datetime.date | None = None,
    horizon_days: int | None = None,
) -> PresenceOverrideRecord:
    """Delete one presence override by id and return it as it was stored.

    The override is looked up FIRST and an unknown id raises ValueError
    prefixed ``override_id:`` (naming the id) BEFORE any delete, so a
    mistyped id can never be silently swallowed by a no-op.  The
    deletion is followed by :func:`~.materialize.regenerate_for_child`
    for the override's own child — the id decides the child, never a
    caller-supplied one.  ``today``/``horizon_days`` thread through to
    that regeneration.
    """
    _validate_override_id(override_id)
    dao = PresenceOverridesDao(database)
    override = await dao.get(override_id)
    if override is None:
        raise ValueError(
            f"override_id: presence override {override_id} does not exist"
        )
    await dao.delete(override_id)
    await regenerate_for_child(
        database, override.child_id, today=today, horizon_days=horizon_days
    )
    return override
