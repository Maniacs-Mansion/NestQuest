"""The presence and custody model (Feature 05).

PURE module: no Home Assistant imports, no database access, no
timezone logic — it operates on plain calendar dates only (feature
guardrail).  The later engine (cycle position, ``is_present``,
overrides, previews) builds directly on this model.

A :class:`PresencePattern` answers "on which weekdays of which cycle
week does this rule apply to this child?" for an N-week repeating
custody rule, and its ``kind`` says what the rule claims on those
days: ``home`` (the child is at this house) or ``away``.  A child
carries ZERO OR MORE patterns (schema 9), e.g. "away every Thursday
and Friday" plus "away every other weekend"; a child with NO pattern
is present every day (that default, and how patterns combine, lives in
the engine, not here).

Pattern encoding: the model's canonical serialization is the SAME
pipe-separated CSV the database stores (see schema.py's
``presence_patterns.pattern``): segment ``i`` (week index ``i``) is a
comma-separated list of the weekdays the pattern covers, 0 = Monday ..
6 = Sunday, e.g. ``'0,2,4|1,3'`` = Mon/Wed/Fri in week 0, Tue/Thu in
week 1.  An empty segment means the pattern covers no day of that
week.  Encoding sorts each segment's weekdays and uses the exact
segment order, so ``decode(encode(pattern))`` round-trips losslessly
and two patterns with equal weekday sets produce equal strings.

Anchor-date policy: ``anchor_date`` pins the cycle.  Cycle position is
computed from anchor-date arithmetic ONLY — never ISO week numbers or
week parity (D-004): 53-week years silently invert parity on January
1st.  The arithmetic lives in the engine task; this module validates
that the anchor is a strict calendar date.

Validation policy: construction is total — every reject happens in
``__init__`` so no invalid pattern can ever exist:
- ``name`` must be a string that is not blank; it is stored trimmed.
- ``kind`` must be ``'home'`` or ``'away'``.
- ``cycle_length_weeks`` must be an integer 1..4.  The 4 cap matches
  the database CHECK (schema.py) and keeps anchor arithmetic and the
  encoded pattern human-readable; revisit both together if a longer
  cycle is ever needed.
- ``pattern`` must cover week indices 0..cycle_length_weeks-1 exactly
  (no gaps, no extra weeks) with sets of integers 0..6 (bools
  rejected: True would silently mean Monday).
- ``anchor_date`` must be a strict ISO YYYY-MM-DD calendar date (or a
  ``datetime.date``).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from types import MappingProxyType

#: The schema's documented cap for cycle_length_weeks (schema.py keeps
#: the pattern human-readable and the anchor arithmetic small).
MAX_CYCLE_LENGTH_WEEKS = 4

#: The pattern kinds the schema's CHECK allows: what a covering
#: pattern claims about the child on that date.
PATTERN_KINDS = ("home", "away")

_DATE_FORMAT = "%Y-%m-%d"


def _parse_date(value: object, field_name: str) -> datetime.date:
    """Accept a datetime.date or a strict YYYY-MM-DD string.

    ``datetime.datetime`` is rejected explicitly: it SUBCLASSES
    datetime.date, so a bare isinstance check would store a value with
    a time component and every later calendar-date comparison (e.g.
    ``PresenceOverride.covers``) would raise TypeError.
    """
    if isinstance(value, datetime.datetime):
        raise ValueError(
            f"{field_name} must be a plain calendar date, not a "
            f"datetime with a time component: {value!r}"
        )
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a datetime.date or an ISO date string, "
            f"got {value!r}"
        )
    try:
        parsed = datetime.datetime.strptime(value, _DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be an ISO date (YYYY-MM-DD), got {value!r}"
        ) from None
    if parsed.isoformat() != value:
        raise ValueError(
            f"{field_name} must be a strict YYYY-MM-DD date, got {value!r}"
        )
    return parsed


def _validate_week_index(week: object, cycle_length_weeks: int) -> int:
    """Reject non-int week indices (bools included) and out-of-cycle."""
    if isinstance(week, bool) or not isinstance(week, int):
        raise ValueError(
            f"pattern week index must be an integer, got {week!r}"
        )
    if not 0 <= week < cycle_length_weeks:
        raise ValueError(
            f"pattern week index must be in 0..{cycle_length_weeks - 1}, "
            f"got {week}"
        )
    return week


def _validate_weekday_set(week: int, weekdays: object) -> frozenset[int]:
    """Validate one week's present-weekday set."""
    if isinstance(weekdays, (str, bytes)) or weekdays is None:
        raise ValueError(
            f"pattern[{week}] must be an iterable of weekday ints 0..6, "
            f"got {weekdays!r}"
        )
    try:
        members = list(weekdays)
    except TypeError:
        raise ValueError(
            f"pattern[{week}] must be an iterable of weekday ints 0..6, "
            f"got {weekdays!r}"
        ) from None
    for member in members:
        if isinstance(member, bool) or not isinstance(member, int):
            raise ValueError(
                f"pattern[{week}] weekday must be an int 0..6, got {member!r}"
            )
        if not 0 <= member <= 6:
            raise ValueError(
                f"pattern[{week}] weekday must be in 0..6 (Monday=0), "
                f"got {member}"
            )
    return frozenset(members)


def _validate_name(value: object) -> str:
    """Reject non-string and blank pattern names; return it trimmed."""
    if not isinstance(value, str):
        raise ValueError(f"name must be a string, got {value!r}")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("name must not be empty")
    return trimmed


def _validate_kind(value: object) -> str:
    """Reject any kind other than the schema's ``home`` / ``away``."""
    if not isinstance(value, str) or value not in PATTERN_KINDS:
        raise ValueError(
            f"kind must be one of {', '.join(PATTERN_KINDS)}, got {value!r}"
        )
    return value


def _validate_cycle_length(value: object) -> int:
    """Reject non-int and out-of-range cycle lengths (bools included)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"cycle_length_weeks must be an integer, got {value!r}"
        )
    if not 1 <= value <= MAX_CYCLE_LENGTH_WEEKS:
        raise ValueError(
            f"cycle_length_weeks must be between 1 and "
            f"{MAX_CYCLE_LENGTH_WEEKS}, got {value}"
        )
    return value


def _validate_child_id(value: object) -> int:
    """Reject non-int child ids (bools would silently address child 1)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"child_id must be an integer, got {value!r}")
    return value


@dataclass(frozen=True, init=False)
class PresencePattern:
    """One of a child's N-week repeating presence rules.

    ``pattern`` maps each week index of the cycle (``0`` .. ``n-1``)
    to the set of weekdays the rule covers (ints, Monday=0); ``kind``
    is what the rule claims on a covered date (``home`` or ``away``).
    A week with an empty set covers no day of that week.  How several
    patterns combine is the engine's job (:class:`PresenceEngine`).
    """

    child_id: int
    name: str
    kind: str
    cycle_length_weeks: int
    anchor_date: datetime.date
    pattern: MappingProxyType  # week index -> frozenset of weekdays

    def __init__(
        self,
        child_id: int,
        name: str,
        kind: str,
        cycle_length_weeks: int,
        anchor_date: object,
        pattern: dict[int, object],
    ) -> None:
        object.__setattr__(self, "child_id", _validate_child_id(child_id))
        object.__setattr__(self, "name", _validate_name(name))
        object.__setattr__(self, "kind", _validate_kind(kind))
        cycle = _validate_cycle_length(cycle_length_weeks)
        object.__setattr__(self, "cycle_length_weeks", cycle)
        object.__setattr__(
            self, "anchor_date", _parse_date(anchor_date, "anchor_date")
        )
        if not isinstance(pattern, dict):
            raise ValueError(
                "pattern must map week index to a set of covered "
                f"weekdays, got {pattern!r}"
            )
        normalised: dict[int, frozenset[int]] = {}
        for week, weekdays in pattern.items():
            index = _validate_week_index(week, cycle)
            normalised[index] = _validate_weekday_set(index, weekdays)
        missing = [
            week for week in range(cycle) if week not in normalised
        ]
        if missing:
            raise ValueError(
                f"pattern must cover week indices 0..{cycle - 1}; "
                f"missing {missing}"
            )
        # Frozen must mean frozen: a bare dict would let callers inject
        # unvalidated weekdays (or drop required weeks) AFTER
        # construction, bypassing total validation.  The mapping
        # proxy exposes the validated contents read-only; the
        # per-week sets are already frozensets.
        object.__setattr__(self, "pattern", MappingProxyType(normalised))

    def encode(self) -> str:
        """Serialize to the database's pipe-separated CSV shape.

        Segments appear in week order; each segment is the week's
        covered weekdays as a sorted comma-separated list (an empty set
        encodes as an empty segment).  Two patterns with equal weekday
        sets encode identically.
        """
        segments = [
            ",".join(str(day) for day in sorted(self.pattern[week]))
            for week in range(self.cycle_length_weeks)
        ]
        return "|".join(segments)

    @classmethod
    def decode(
        cls,
        child_id: int,
        name: str,
        kind: str,
        anchor_date: object,
        encoded: str,
    ) -> "PresencePattern":
        """Build a pattern from its encoded weekday sets.

        The cycle length is derived from the segment count, mirroring
        the database's segment-count CHECK.  Decoding is strict: wrong
        shapes, non-numeric or out-of-range weekdays are rejected —
        the database CHECKs make such rows unrepresentable, and this
        is the same contract on the model side.  A segment count above
        the documented cycle cap is rejected by the ordinary
        construction validation.
        """
        if not isinstance(encoded, str):
            raise ValueError(
                f"encoded pattern must be a string, got {encoded!r}"
            )
        segments = encoded.split("|")
        pattern: dict[int, set[int]] = {}
        for week, segment in enumerate(segments):
            weekdays: set[int] = set()
            if segment:
                for part in segment.split(","):
                    if len(part) != 1 or part not in "0123456":
                        raise ValueError(
                            f"encoded segment {week} carries an invalid "
                            f"weekday {part!r} (single digits 0-6 only)"
                        )
                    weekdays.add(int(part))
            pattern[week] = weekdays
        return cls(child_id, name, kind, len(segments), anchor_date, pattern)

    def covers(self, date: datetime.date) -> bool:
        """Return True when ``date``'s weekday is in its cycle week's set.

        The cycle week comes from :func:`cycle_week_index` — anchor-date
        arithmetic only, never ISO week numbers or parity (D-004).
        """
        return date.weekday() in self.pattern[cycle_week_index(self, date)]


@dataclass(frozen=True, init=False)
class PresenceOverride:
    """A date-specific present/absent flag beating any pattern.

    Covers a single date (``end_date == start_date``) or an inclusive
    range.  A concrete range is the storage shape
    (``presence_overrides.end_date`` is NOT NULL), so the model
    requires both bounds and validates start <= end.  Construction and
    validation live here so the engine can trust every instance.
    """

    child_id: int
    start_date: datetime.date
    end_date: datetime.date
    is_present: bool
    note: str | None

    def __init__(
        self,
        child_id: int,
        start_date: object,
        end_date: object,
        is_present: bool,
        note: str | None = None,
    ) -> None:
        object.__setattr__(self, "child_id", _validate_child_id(child_id))
        start = _parse_date(start_date, "start_date")
        end = _parse_date(end_date, "end_date")
        if end < start:
            raise ValueError(
                f"end_date must be on or after start_date, got "
                f"{end.isoformat()} < {start.isoformat()}"
            )
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)
        if not isinstance(is_present, bool):
            raise ValueError(
                f"is_present must be a real bool, got {is_present!r}"
            )
        object.__setattr__(self, "is_present", is_present)
        if note is not None and not isinstance(note, str):
            raise ValueError(f"note must be a string or None, got {note!r}")
        object.__setattr__(self, "note", note)

    def covers(self, date: datetime.date) -> bool:
        """Return True when the override applies to ``date``."""
        return self.start_date <= date <= self.end_date


def cycle_week_index(
    pattern: PresencePattern, target_date: object
) -> int:
    """Return the cycle week index ``target_date`` falls in.

    Anchor-date arithmetic ONLY (D-004): ``((target_date -
    anchor_date).days // 7) % cycle_length_weeks``.  Python's floor
    division makes dates BEFORE the anchor behave correctly — they
    walk the cycle backwards (day -1 is the last week of the cycle,
    day -8 wraps one further) instead of inverting, which is exactly
    what ISO week parity does wrong in 53-week years.  The modulo of
    a negative in Python is non-negative, so the index is always a
    valid week index.
    """
    target = _parse_date(target_date, "target_date")
    days = (target - pattern.anchor_date).days
    return (days // 7) % pattern.cycle_length_weeks


#: Search cap for :meth:`PresenceEngine.next_present_dates`: two full
#: years of daily checks.  A child absent every day (an away pattern
#: covering every weekday) would otherwise loop forever; the cap bounds
#: the scan and surfaces the situation as an error instead.
MAX_PREVIEW_SCAN_DAYS = 366 * 2


class PresenceEngine:
    """Answers "is this child at this house on this date?".

    Pure and side-effect-free: built from an immutable snapshot of the
    children's patterns (``child_id -> list of PresencePattern``), it
    never touches the database — callers build a snapshot from the DAO
    layer and pass it in.  A child with NO pattern is present every day
    (the third household child's case).  Evaluation order, first match
    wins — see :meth:`is_present`.  Pattern coverage is anchor-date
    arithmetic (:func:`cycle_week_index`, never ISO week parity).
    """

    def __init__(
        self,
        patterns: dict[int, list[PresencePattern]],
        overrides: dict[int, list[PresenceOverride]] | None = None,
    ) -> None:
        if not isinstance(patterns, dict):
            raise ValueError(
                "patterns must map child_id to a list of PresencePattern, "
                f"got {patterns!r}"
            )
        for child_id, entries in patterns.items():
            # Validate the KEY as a model child id too: True and 1.0
            # compare equal to 1, so {True: [pattern(1)]} would be
            # accepted and then behave differently on lookup.
            _validate_child_id(child_id)
            if not isinstance(entries, list):
                raise ValueError(
                    f"patterns[{child_id!r}] must be a list of "
                    f"PresencePattern, got {entries!r}"
                )
            for entry in entries:
                if not isinstance(entry, PresencePattern):
                    raise ValueError(
                        f"patterns[{child_id!r}] entries must be "
                        f"PresencePattern, got {entry!r}"
                    )
                if entry.child_id != child_id:
                    raise ValueError(
                        f"patterns is keyed {child_id!r} but holds a "
                        f"pattern of child {entry.child_id}"
                    )
        if overrides is None:
            overrides = {}
        if not isinstance(overrides, dict):
            raise ValueError(
                "overrides must map child_id to a list of "
                f"PresenceOverride, got {overrides!r}"
            )
        for child_id, entries in overrides.items():
            _validate_child_id(child_id)
            if not isinstance(entries, list):
                raise ValueError(
                    f"overrides[{child_id!r}] must be a list of "
                    f"PresenceOverride, got {entries!r}"
                )
            for entry in entries:
                if not isinstance(entry, PresenceOverride):
                    raise ValueError(
                        f"overrides[{child_id!r}] entries must be "
                        f"PresenceOverride, got {entry!r}"
                    )
                if entry.child_id != child_id:
                    raise ValueError(
                        f"overrides is keyed {child_id!r} but holds an "
                        f"override of child {entry.child_id}"
                    )
        # Read-only snapshot: reassignment is refused and no mutator
        # exists, so a built engine answers consistently for its
        # lifetime.  The patterns and overrides lists are copied to
        # immutable tuples — a shallow mapping copy alone would leave
        # caller-owned lists reachable, and mutating one later would
        # change is_present results.
        object.__setattr__(
            self,
            "_patterns",
            MappingProxyType(
                {child_id: tuple(entries) for child_id, entries in patterns.items()}
            ),
        )
        object.__setattr__(
            self,
            "_overrides",
            MappingProxyType(
                {child_id: tuple(entries) for child_id, entries in overrides.items()}
            ),
        )

    def is_present(self, child_id: object, date: object) -> bool:
        """Return whether ``child_id`` is present on ``date``.

        Ordered, first match wins:

        1. An override covering the date — its flag IS the answer,
           including for a child with no pattern at all.  The DAO layer
           guarantees a child's overrides never overlap; if a snapshot
           still carries two covering the same date, the one with the
           LATEST start date wins (deterministic, and matches "the most
           specific swap wins").
        2. Any ``away`` pattern covering the date — absent.
        3. Any ``home`` pattern covering the date — present.
        4. Otherwise: absent when the child has at least one ``home``
           pattern (a home pattern lists the days the child IS here, so
           an uncovered date is a day away — the retired single-schedule
           semantics, which migration 9 carries across as ``home``
           patterns unchanged), else present (no pattern, or ``away``
           patterns only: the household default).
        """
        if isinstance(child_id, bool) or not isinstance(child_id, int):
            raise ValueError(f"child_id must be an integer, got {child_id!r}")
        target = _parse_date(date, "date")
        entries = self._overrides.get(child_id) or []
        covering = [
            entry for entry in entries if entry.covers(target)
        ]
        if covering:
            winner = max(covering, key=lambda entry: entry.start_date)
            return winner.is_present
        patterns = self._patterns.get(child_id) or ()
        if any(
            pattern.kind == "away" and pattern.covers(target)
            for pattern in patterns
        ):
            return False
        homes = [pattern for pattern in patterns if pattern.kind == "home"]
        if any(pattern.covers(target) for pattern in homes):
            return True
        return not homes

    def next_present_dates(
        self,
        child_id: object,
        start_date: object,
        count: int,
    ) -> list[datetime.date]:
        """Return the next ``count`` dates the child is present.

        Walks forward from ``start_date`` (INCLUSIVE — a parent
        previewing "starting Monday" expects Monday itself when the
        child is present) checking :meth:`is_present` for every day,
        so overrides and the patterns are honoured identically.  The
        admin Schedule tab renders this preview so a parent can confirm
        a custody pattern is right before saving it.

        A child absent every scanned day raises ValueError after the
        two-year search cap — an always-absent child would otherwise
        loop forever.  ``count`` must be a positive integer.
        """
        _validate_child_id(child_id)
        start = _parse_date(start_date, "start_date")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(f"count must be an integer, got {count!r}")
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        found: list[datetime.date] = []
        day = start
        for _ in range(MAX_PREVIEW_SCAN_DAYS):
            if self.is_present(child_id, day):
                found.append(day)
                if len(found) == count:
                    return found
            day += datetime.timedelta(days=1)
        raise ValueError(
            f"child {child_id} is not present on any of the "
            f"{MAX_PREVIEW_SCAN_DAYS} days from {start.isoformat()}; "
            f"{count} present day(s) cannot be previewed"
        )

    def __setattr__(self, name: object, value: object) -> None:
        raise AttributeError(
            "PresenceEngine is an immutable snapshot; build a new engine "
            "instead of mutating this one"
        )
