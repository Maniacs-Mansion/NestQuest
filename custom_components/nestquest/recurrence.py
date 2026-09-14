"""The ScheduleRule model: rule types, validation, and serialization.

A :class:`ScheduleRule` describes WHEN a recurring chore fires — a pure
frozen dataclass with no Home Assistant and no database imports.  The
evaluation engine (Feature 04) consumes it; the DAO layer (Feature 02)
serializes its dict form into the ``schedule_rules`` table.

Type model: one enum member per recurrence shape.  ``MONTHLY_DAY``
("the 15th of every month") and ``MONTHLY_WEEKDAY`` ("the second
Tuesday of every month") are distinct types rather than one monthly
type with optional fields, so validation is total: a rule either
constructs, or raises :class:`RuleValidationError` naming the offending
field.  Every type carries ONLY the fields its shape needs; carrying
any other shape's field is a construction error.

Storage mapping (Feature 02, ``schedule_rules`` table): the enum's
``storage_value`` maps model types onto the schema's CHECK values —
MONTHLY_DAY and MONTHLY_WEEKDAY both store as ``'monthly'`` and are
disambiguated by which fields are populated; CUSTOM_DAYS stores as
``'custom'``.  ``weekday_set`` round-trips as the sorted CSV list the
table stores (one element for MONTHLY_WEEKDAY, which names the
position's weekday); ``nth_weekday_weekday`` is a MODEL-ONLY field
carried through from_dict/to_dict for losslessness and folded into
``weekday_set`` by the DAO mapping.  ``to_dict``/``from_dict`` are the
model-side lossless pair; the DB mapping lives in the DAO layer and is
exercised there.

Validation policy (fail fast at construction — the schema's CHECK
constraints are a second line of defense, but invalid rules must never
reach storage):

- ``interval`` >= 1 for every rule.
- ``weekday_set`` is required for WEEKLY and CUSTOM_DAYS, forbidden
  elsewhere; entries are 0 (Monday) .. 6 (Sunday), no booleans.
- ``day_of_month`` 1..31 is required for MONTHLY_DAY.
- ``nth_weekday`` 1..5 or -1 (0 is meaningless as a position and is
  rejected) with a weekday 0..6 for MONTHLY_WEEKDAY.
- ``month`` 1..12 is required for YEARLY.
- ``start_date`` is a strict ISO date; ``end_date`` is optional and,
  when present, on or after ``start_date``.

Month-end policy (documented for Feature 04): a MONTHLY_DAY rule for
the 31st does NOT fire in a 30-day month, and a YEARLY rule for
February 29th does NOT fire in a non-leap year — the engine skips
instead of clamping to month end, because clamping silently moves
"the 31st" to "the 30th" and double-fires tasks.
"""
from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass, field

#: Date-shape policy: strict YYYY-MM-DD, matching the DAO layers.
_DATE_FORMAT = "%Y-%m-%d"

#: Weekday-name policy: 0 = Monday .. 6 = Sunday (ISO order).


class RuleType(enum.Enum):
    """The six recurrence shapes the engine supports.

    ``storage_value`` is the string written to the ``schedule_rules``
    table's ``rule_type`` column (its CHECK whitelist).  MONTHLY_DAY
    and MONTHLY_WEEKDAY are distinct shapes sharing one storage value,
    disambiguated by which fields are populated.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY_DAY = "monthly_day"
    MONTHLY_WEEKDAY = "monthly_weekday"
    YEARLY = "yearly"
    CUSTOM_DAYS = "custom_days"

    @property
    def storage_value(self) -> str:
        """The schema-level rule_type string this model type maps to."""
        return {
            RuleType.DAILY: "daily",
            RuleType.WEEKLY: "weekly",
            RuleType.MONTHLY_DAY: "monthly",
            RuleType.MONTHLY_WEEKDAY: "monthly",
            RuleType.YEARLY: "yearly",
            RuleType.CUSTOM_DAYS: "custom",
        }[self]


class RuleValidationError(ValueError):
    """Raised when a ScheduleRule field combination is invalid."""


def _validate_date(value: str, field_name: str) -> None:
    """Raise unless ``value`` is a strict YYYY-MM-DD calendar date."""
    try:
        parsed = datetime.datetime.strptime(value, _DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise RuleValidationError(
            f"{field_name} must be an ISO date (YYYY-MM-DD), got {value!r}"
        ) from None
    if parsed.isoformat() != value:
        raise RuleValidationError(
            f"{field_name} must be a strict YYYY-MM-DD date, got {value!r}"
        )


def _validate_weekday_set(weekday_set) -> frozenset[int]:
    """Return a normalized frozenset or raise with a clear message.

    Sequence entries are validated BEFORE set() coercion: a list like
    [0, False] must not collapse the boolean into 0, and unhashable
    entries must raise RuleValidationError, never a raw TypeError.
    """
    if isinstance(weekday_set, (list, tuple)):
        for entry in weekday_set:
            # _is_plain_int: bool and int subclasses (potentially
            # unhashable) are rejected before set() coercion.
            if not _is_plain_int(entry):
                raise RuleValidationError(
                    f"weekday_set entries must be plain integers, got "
                    f"{entry!r}"
                )
        weekday_set = set(weekday_set)
    if not isinstance(weekday_set, (set, frozenset)):
        raise RuleValidationError(
            f"weekday_set must be a set of weekday integers, got "
            f"{type(weekday_set).__name__}"
        )
    if not weekday_set:
        raise RuleValidationError(
            "weekday_set must not be empty for weekly/custom rules"
        )
    for entry in weekday_set:
        if not _is_plain_int(entry):
            raise RuleValidationError(
                f"weekday_set entries must be plain integers, got "
                f"{entry!r}"
            )
        if not 0 <= entry <= 6:
            raise RuleValidationError(
                f"weekday_set entries must be 0 (Monday)..6 (Sunday), "
                f"got {entry!r}"
            )
    return frozenset(weekday_set)


def _is_plain_int(value) -> bool:
    """True only for real ints: bool excluded AND int subclasses too
    (an unhashable int subclass would break the frozen-hashable model)."""
    return type(value) is int


def _validate_monthly_weekday(nth_weekday, weekday) -> None:
    """Validate the MONTHLY_WEEKDAY position fields."""
    if nth_weekday is None or not _is_plain_int(nth_weekday):
        raise RuleValidationError(
            "nth_weekday must be an integer for monthly_weekday rules, "
            f"got {nth_weekday!r}"
        )
    if not (-1 <= nth_weekday <= 5) or nth_weekday == 0:
        raise RuleValidationError(
            f"nth_weekday must be -1 (last) or 1..5, got {nth_weekday!r}"
        )
    if weekday is None or not _is_plain_int(weekday) or not 0 <= weekday <= 6:
        raise RuleValidationError(
            f"monthly_weekday rules require a weekday 0 (Monday)..6 "
            f"(Sunday), got {weekday!r}"
        )





@dataclass(frozen=True)
class ScheduleRule:
    """An immutable, validated recurrence rule (see module docstring).

    Construct with keyword arguments; invalid combinations raise
    :class:`RuleValidationError` at construction time.  Fields map
    one-to-one onto the ``schedule_rules`` table columns, with
    ``nth_weekday_weekday`` as the model-only weekday companion to
    ``nth_weekday`` (serialized inside ``weekday_set`` at the DAO
    boundary).
    """

    rule_type: RuleType
    interval: int = 1
    weekday_set: frozenset[int] | None = None
    day_of_month: int | None = None
    nth_weekday: int | None = None
    nth_weekday_weekday: int | None = None
    month: int | None = None
    start_date: str = "1970-01-01"
    end_date: str | None = None

    def __post_init__(self) -> None:
        # Normalize a string rule_type into the enum; anything else
        # that is not already a RuleType is rejected.
        if isinstance(self.rule_type, str):
            # EXACT model names only: no whitespace stripping, no storage
            # aliases.  The DAO maps storage strings to model fields when
            # reading rows; the model boundary stays unambiguous.
            candidates = {rt.name.lower(): rt for rt in RuleType}
            if self.rule_type in candidates:
                object.__setattr__(
                    self, "rule_type", candidates[self.rule_type]
                )
            else:
                raise RuleValidationError(
                    f"rule_type must be a RuleType or one of "
                    f"{sorted(candidates)}, got {self.rule_type!r}"
                )
        if not isinstance(self.rule_type, RuleType):
            raise RuleValidationError(
                f"rule_type must be a RuleType or one of its string "
                f"values, got {self.rule_type!r}"
            )
        if not _is_plain_int(self.interval):
            raise RuleValidationError(
                f"interval must be an integer >= 1, got {self.interval!r}"
            )
        if self.interval < 1:
            raise RuleValidationError(
                f"interval must be >= 1, got {self.interval!r}"
            )

        _validate_date(self.start_date, "start_date")
        if self.end_date is not None:
            _validate_date(self.end_date, "end_date")
            if self.end_date < self.start_date:
                raise RuleValidationError(
                    f"end_date {self.end_date!r} must be on or after "
                    f"start_date {self.start_date!r}"
                )

        # Type-exclusive field policy, enforced for every type: build
        # the dict of present fields, then reject every field the shape
        # must not carry (weekday_set present is detectable via None vs
        # set even after normalization below).
        shape = self.rule_type
        if shape is RuleType.DAILY:
            forbidden_fields = (
                "weekday_set",
                "day_of_month",
                "nth_weekday",
                "nth_weekday_weekday",
                "month",
            )
        elif shape is RuleType.WEEKLY:
            forbidden_fields = (
                "day_of_month",
                "nth_weekday",
                "nth_weekday_weekday",
                "month",
            )
        elif shape is RuleType.CUSTOM_DAYS:
            forbidden_fields = (
                "day_of_month",
                "nth_weekday",
                "nth_weekday_weekday",
                "month",
            )
        elif shape is RuleType.MONTHLY_DAY:
            forbidden_fields = ("weekday_set", "nth_weekday",
                                "nth_weekday_weekday", "month")
        elif shape is RuleType.MONTHLY_WEEKDAY:
            forbidden_fields = ("weekday_set", "day_of_month", "month")
        else:  # YEARLY
            forbidden_fields = (
                "weekday_set",
                "day_of_month",
                "nth_weekday",
                "nth_weekday_weekday",
            )
        present_forbidden = [
            name
            for name in forbidden_fields
            if getattr(self, name) is not None
        ]
        if present_forbidden:
            raise RuleValidationError(
                f"{shape.value} rules must not set "
                f"{', '.join(sorted(present_forbidden))}"
            )

        # Required fields per shape.
        if shape is RuleType.WEEKLY or shape is RuleType.CUSTOM_DAYS:
            normalized = _validate_weekday_set(self.weekday_set)
            object.__setattr__(self, "weekday_set", normalized)
        elif shape is RuleType.MONTHLY_DAY:
            if self.day_of_month is None or not _is_plain_int(
                self.day_of_month
            ):
                raise RuleValidationError(
                    "monthly_day rules require day_of_month (1..31)"
                )
            if not 1 <= self.day_of_month <= 31:
                raise RuleValidationError(
                    f"day_of_month must be 1..31, got {self.day_of_month!r}"
                )
        elif shape is RuleType.MONTHLY_WEEKDAY:
            _validate_monthly_weekday(
                self.nth_weekday, self.nth_weekday_weekday
            )
        elif shape is RuleType.YEARLY:
            if self.month is None or not _is_plain_int(self.month):
                raise RuleValidationError(
                    "yearly rules require month (1..12)"
                )
            if not 1 <= self.month <= 12:
                raise RuleValidationError(
                    f"month must be 1..12, got {self.month!r}"
                )

    def to_dict(self) -> dict:
        """Return the lossless dict form (model-side storage shape).

        ``weekday_set`` serializes as a sorted list; MONTHLY_WEEKDAY's
        weekday travels inside it (appended) plus
        ``nth_weekday_weekday`` so the pair round-trips without
        ambiguity at the model layer.
        """
        return {
            "rule_type": self.rule_type.name.lower(),  # model name
            "interval": self.interval,
            "weekday_set": (
                sorted(self.weekday_set) if self.weekday_set is not None
                else None
            ),
            "day_of_month": self.day_of_month,
            "nth_weekday": self.nth_weekday,
            "nth_weekday_weekday": self.nth_weekday_weekday,
            "month": self.month,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleRule":
        """Rebuild a rule from :meth:`to_dict` output.

        Raises :class:`RuleValidationError` on unknown keys, missing
        keys, or invalid combinations — never a raw TypeError.
        """
        if not isinstance(data, dict):
            raise RuleValidationError(
                f"rule data must be a dict, got {type(data).__name__}"
            )
        allowed = {
            "rule_type",
            "interval",
            "weekday_set",
            "day_of_month",
            "nth_weekday",
            "nth_weekday_weekday",
            "month",
            "start_date",
            "end_date",
        }
        unknown = [key for key in data if key not in allowed]
        if unknown:
            raise RuleValidationError(
                f"unknown rule fields: {sorted(unknown, key=repr)}"
            )
        if "rule_type" not in data:
            raise RuleValidationError("missing required rule field: rule_type")
        weekday_set = data.get("weekday_set")
        if isinstance(weekday_set, (list, tuple)):
            # Validate entries as plain ints BEFORE set() coercion, so a
            # list like [0, False] cannot collapse False into 0 and an
            # unhashable/int-subclass entry cannot leak a raw TypeError.
            for entry in weekday_set:
                if not _is_plain_int(entry):
                    raise RuleValidationError(
                        f"weekday_set entries must be plain integers, got "
                        f"{entry!r}"
                    )
            weekday_set = set(weekday_set)
        return cls(
            rule_type=data["rule_type"],
            interval=data.get("interval", 1),
            weekday_set=weekday_set,
            day_of_month=data.get("day_of_month"),
            nth_weekday=data.get("nth_weekday"),
            nth_weekday_weekday=data.get("nth_weekday_weekday"),
            month=data.get("month"),
            start_date=data.get("start_date", "1970-01-01"),
            end_date=data.get("end_date"),
        )


# ---------------------------------------------------------------------------
# Evaluation engine (Feature 04): pure date arithmetic on ScheduleRule
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime.date:
    """Parse a strict ISO date already validated by the model."""
    return datetime.datetime.strptime(value, _DATE_FORMAT).date()


def _anchor_offset(rule: ScheduleRule, target: datetime.date) -> int:
    """Day offset from the rule's anchor date to ``target``.

    The anchor for DAILY/WEEKLY-interval arithmetic is start_date: the
    first day the rule CAN fire.  A negative offset means the target
    precedes the rule's window entirely.
    """
    return (target - _parse_date(rule.start_date)).days


def _within_window(rule: ScheduleRule, target: datetime.date) -> bool:
    """True when ``target`` is inside the rule's [start, end] window."""
    if target < _parse_date(rule.start_date):
        return False
    if rule.end_date is not None and target > _parse_date(rule.end_date):
        return False
    return True


def occurs_on(rule: ScheduleRule, target: datetime.date) -> bool:
    """Return True when ``rule`` fires on ``target``.

    Pure function: no I/O, no timezone awareness, no mutation.  Dates
    are plain calendar dates (Feature 04 guardrail); the caller decides
    the timezone that produced them.
    """
    # Dispatch FIRST: an unimplemented shape must raise loudly even for
    # dates outside the window, never silently evaluate to False.
    shape = rule.rule_type
    if shape is not RuleType.DAILY:
        raise NotImplementedError(
            f"occurs_on for {shape} lands with its own engine task "
            "(Features 04 task sequence)"
        )
    if not _within_window(rule, target):
        return False
    offset = (target - _parse_date(rule.start_date)).days
    return offset % rule.interval == 0


def occurrences_between(
    rule: ScheduleRule, start: str, end: str
) -> list[str]:
    """Return every date string in [start, end] the rule fires on.

    Inclusive on both ends.  Raises RuleValidationError on malformed or
    inverted bounds; a window entirely outside [rule.start_date,
    rule.end_date] yields an empty list.
    """
    if rule.rule_type is not RuleType.DAILY:
        raise NotImplementedError(
            f"occurrences_between for {rule.rule_type} lands with its own "
            "engine task (Features 04 task sequence)"
        )
    _validate_date(start, "start")
    _validate_date(end, "end")
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if end_date < start_date:
        raise RuleValidationError(
            f"end {end!r} must be on or after start {start!r}"
        )
    rule_start = _parse_date(rule.start_date)
    if end_date < rule_start:
        return []
    # Clamp the walk to the rule's own window and the queried range.
    effective_start = max(start_date, rule_start)
    effective_end = end_date
    if rule.end_date is not None:
        effective_end = min(effective_end, _parse_date(rule.end_date))
    results: list[str] = []
    cursor = effective_start
    while cursor <= effective_end:
        if occurs_on(rule, cursor):
            results.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    return results
