"""The presence and custody model (Feature 05).

PURE module: no Home Assistant imports, no database access, no
timezone logic — it operates on plain calendar dates only (feature
guardrail).  The later engine (cycle position, ``is_present``,
overrides, previews) builds directly on this model.

A :class:`PresenceSchedule` answers "on which weekdays of which cycle
week is this child at this house?" for an N-week repeating custody
pattern.  Two of the household's three children follow a two-week
rotation; a child with NO schedule row is present every day (that
default lives in the engine, not here).

Pattern encoding: the model's canonical serialization is the SAME
pipe-separated CSV the database stores (see schema.py's
``presence_schedules.pattern``): segment ``i`` (week index ``i``) is a
comma-separated list of present weekdays, 0 = Monday .. 6 = Sunday,
e.g. ``'0,2,4|1,3'`` = Mon/Wed/Fri in week 0, Tue/Thu in week 1.  An
empty segment means absent every day of that week.  Encoding sorts
each segment's weekdays and uses the exact segment order, so
``decode(encode(schedule))`` round-trips losslessly and two schedules
with equal patterns produce equal strings.

Anchor-date policy: ``anchor_date`` pins the cycle.  Cycle position is
computed from anchor-date arithmetic ONLY — never ISO week numbers or
week parity (D-004): 53-week years silently invert parity on January
1st.  The arithmetic lives in the engine task; this module validates
that the anchor is a strict calendar date.

Validation policy: construction is total — every reject happens in
``__init__`` so no invalid schedule can ever exist:
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
class PresenceSchedule:
    """One child's N-week repeating presence pattern.

    ``pattern`` maps each week index of the cycle (``0`` .. ``n-1``)
    to the set of present weekdays (ints, Monday=0).  A week with an
    empty set means the child is absent every day of that week — which
    is distinct from having no schedule at all (the engine treats a
    missing schedule as present every day).
    """

    child_id: int
    cycle_length_weeks: int
    anchor_date: datetime.date
    pattern: MappingProxyType  # week index -> frozenset of weekdays

    def __init__(
        self,
        child_id: int,
        cycle_length_weeks: int,
        anchor_date: object,
        pattern: dict[int, object],
    ) -> None:
        object.__setattr__(self, "child_id", _validate_child_id(child_id))
        cycle = _validate_cycle_length(cycle_length_weeks)
        object.__setattr__(self, "cycle_length_weeks", cycle)
        object.__setattr__(
            self, "anchor_date", _parse_date(anchor_date, "anchor_date")
        )
        if not isinstance(pattern, dict):
            raise ValueError(
                "pattern must map week index to a set of present "
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
        present weekdays as a sorted comma-separated list (an empty set
        encodes as an empty segment).  Two schedules with equal
        patterns encode identically.
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
        anchor_date: object,
        encoded: str,
    ) -> "PresenceSchedule":
        """Build a schedule from its encoded pattern.

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
        return cls(child_id, len(segments), anchor_date, pattern)


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
    schedule: PresenceSchedule, target_date: object
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
    days = (target - schedule.anchor_date).days
    return (days // 7) % schedule.cycle_length_weeks


class PresenceEngine:
    """Answers "is this child at this house on this date?".

    Pure and side-effect-free: built from an immutable snapshot of the
    children's schedules (``child_id -> PresenceSchedule``), it never
    touches the database — callers build a snapshot from the DAO layer
    and pass it in.  A child with NO schedule entry is present every
    day (the third household child's case); a child WITH a schedule is
    present exactly when the date's weekday is in that schedule's
    pattern for the date's cycle week index (anchor-date arithmetic —
    :func:`cycle_week_index`, never ISO week parity).
    """

    def __init__(self, schedules: dict[int, PresenceSchedule]) -> None:
        if not isinstance(schedules, dict):
            raise ValueError(
                f"schedules must map child_id to PresenceSchedule, got "
                f"{schedules!r}"
            )
        for child_id, schedule in schedules.items():
            if not isinstance(schedule, PresenceSchedule):
                raise ValueError(
                    f"schedules[{child_id!r}] must be a PresenceSchedule, "
                    f"got {schedule!r}"
                )
            if schedule.child_id != child_id:
                raise ValueError(
                    f"schedules is keyed {child_id!r} but holds the "
                    f"schedule of child {schedule.child_id}"
                )
        # Read-only snapshot: reassignment is refused and no mutator
        # exists, so a built engine answers consistently for its
        # lifetime.
        object.__setattr__(self, "_schedules", MappingProxyType(dict(schedules)))

    def is_present(self, child_id: object, date: object) -> bool:
        """Return whether ``child_id`` is present on ``date``."""
        if isinstance(child_id, bool) or not isinstance(child_id, int):
            raise ValueError(f"child_id must be an integer, got {child_id!r}")
        target = _parse_date(date, "date")
        schedule = self._schedules.get(child_id)
        if schedule is None:
            # No schedule at all: present every day (household default).
            return True
        week = cycle_week_index(schedule, target)
        return target.weekday() in schedule.pattern[week]

    def __setattr__(self, name: object, value: object) -> None:
        raise AttributeError(
            "PresenceEngine is an immutable snapshot; build a new engine "
            "instead of mutating this one"
        )
