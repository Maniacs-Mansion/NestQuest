"""The ScheduleRule model: rule types, validation, and serialization.

A :class:`ScheduleRule` describes WHEN a recurring chore fires — a pure
data structure with no Home Assistant and no database imports.  The
evaluation engine (:mod:`.recurrence`, Feature 04) consumes it;
the DAO layer (Feature 02) serializes its dict form into the
``schedule_rules`` table.

Type model: one enum per rule family.  ``MONTHLY_DAY`` ("the 15th of
every month") and ``MONTHLY_WEEKDAY`` ("the second Tuesday of every
month") are distinct types rather than one monthly type with optional
fields, so every field combination a rule can carry is decided by the
rule type alone and validation is total: a rule either constructs, or
raises :class:`RuleValidationError` naming the offending fields.

Validation policy (fail fast at construction — the schema's CHECK
constraints are a second line of defense, but invalid rules must never
reach storage):

- ``interval`` >= 1 for every rule.
- ``weekday_set`` is required for WEEKLY and CUSTOM_DAYS, forbidden
  elsewhere; each element must be 0 (Monday) .. 6 (Sunday).
- ``day_of_month`` 1..31 is required for MONTHLY_DAY.
- ``nth_weekday`` in -1..5 (1 = first, 5 = last-possible, -1 = last)
  and a weekday 0..6 are required for MONTHLY_WEEKDAY.
- ``month`` 1..12 is required for YEARLY.
- ``start_date`` is a strict ISO date; ``end_date`` is optional and,
  when present, must be on or after ``start_date``.
- ``due_time`` is optional and must be HH:MM 24-hour.

Month-end policy (documented for Feature 04): a MONTHLY_DAY rule for
the 31st does NOT fire in a 30-day month, and a YEARLY rule for
February 29th does NOT fire in a non-leap year — the engine skips
instead of clamping to month end, because clamping silently moves
"the 31st" to "the 30th" and double-fires tasks.  ``weekday_in_month``
(True = Nth weekday, False = Nth-from-last for negative n) resolves
the MONTHLY_WEEKDAY position.
"""
from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass, field

#: Date-shape policy: strict YYYY-MM-DD, matching the DAO layers.
_DATE_FORMAT = "%Y-%m-%d"


class RuleType(enum.Enum):
    """The six recurrence shapes the engine supports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY_DAY = "monthly_day"
    MONTHLY_WEEKDAY = "monthly_weekday"
    YEARLY = "yearly"
    CUSTOM_DAYS = "custom_days"


class RuleValidationError(ValueError):
    """Raised when a ScheduleRule field combination is invalid."""


def _validate_date(value: str, field: str) -> None:
    """Raise unless ``value`` is a strict YYYY-MM-DD calendar date."""
    try:
        parsed = datetime.datetime.strptime(value, _DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise RuleValidationError(
            f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}"
        ) from None
    if parsed.isoformat() != value:
        raise RuleValidationError(
            f"{field} must be a strict YYYY-MM-DD date, got {value!r}"
        )


def _validate_weekday_set(weekday_set) -> None:
    """Raise unless ``weekday_set`` is a non-empty 0-6 integer set."""
    if not isinstance(weekday_set, (set, frozenset)):
        raise RuleValidationError(
            "weekday_set must be a set of weekday integers, got "
            f"{type(weekday_set).__name__}"
        )
    if not weekday_set:
        raise RuleValidationError(
            "weekday_set must not be empty for weekly/custom rules"
        )
    for entry in weekday_set:
        if not isinstance(entry, int) or isinstance(entry, bool):
            raise RuleValidationError(
                f"weekday_set entries must be integers, got {entry!r}"
            )
        if not 0 <= entry <= 6:
            raise RuleValidationError(
                f"weekday_set entries must be 0 (Monday)..6 (Sunday), "
                f"got {entry!r}"
            )


def _validate_monthday_set(nth_weekday: int | None, weekday: int | None) -> None:
    """Validate the MONTHLY_WEEKDAY position fields."""
    if nth_weekday is None or not isinstance(nth_weekday, int) or (
        isinstance(nth_weekday, bool)
    ):
        raise RuleValidationError(
            "nth_weekday must be an integer -1..5 for monthly_weekday "
            f"rules, got {nth_weekday!r}"
        )
    if not (-1 <= nth_weekday <= 5) or nth_weekday == 0:
        raise RuleValidationError(
            f"nth_weekday must be -1 (last) or 1..5, got {nth_weekday!r}"
        )
    if weekday is None:
        raise RuleValidationError(
            "monthly_weekday rules require a weekday (0..6) naming the "
            "day of week"
        )
    if not isinstance(weekday, int) or isinstance(weekday, bool) or not (
        0 <= weekday <= 6
    ):
        raise RuleValidationError(
            f"weekday must be an integer 0 (Monday)..6 (Sunday), got "
            f"{weekday!r}"
        )


class ScheduleRule:
    """An immutable, validated recurrence rule.

    Construct with keyword arguments; invalid combinations raise
    :class:`RuleValidationError` at construction time.  The fields map
    one-to-one onto the ``schedule_rules`` table columns.
    """

    __slots__ = (
        "rule_type",
        "interval",
        "weekday_set",
        "day_of_month",
        "nth_weekday",
        "nth_weekday_weekday",
        "month",
        "start_date",
        "end_date",
    )

    def __init__(
        self,
        rule_type: RuleType | str,
        *,
        interval: int = 1,
        weekday_set: frozenset[int] | set[int] | None = None,
        day_of_month: int | None = None,
        nth_weekday: int | None = None,
        nth_weekday_weekday: int | None = None,
        month: int | None = None,
        start_date: str = "1970-01-01",
        end_date: str | None = None,
    ) -> None:
        if isinstance(rule_type, str):
            try:
                rule_type = RuleType(rule_type)
            except ValueError:
                raise RuleValidationError(
                    f"rule_type must be one of "
                    f"{[rt.value for rt in RuleType]}, got {rule_type!r}"
                ) from None
        if not isinstance(interval, int) or isinstance(interval, bool):
            raise RuleValidationError(
                f"interval must be an integer >= 1, got {interval!r}"
            )
        if interval < 1:
            raise RuleValidationError(
                f"interval must be >= 1, got {interval!r}"
            )

        _validate_date(start_date, "start_date")
        if end_date is not None:
            _validate_date(end_date, "end_date")
            if end_date < start_date:
                raise RuleValidationError(
                    f"end_date {end_date!r} must be on or after "
                    f"start_date {start_date!r}"
                )

        if rule_type is RuleType.WEEKLY:
            if weekday_set is None:
                raise RuleValidationError(
                    "weekly rules require weekday_set"
                )
            _validate_weekday_set(weekday_set)
            weekday_set = frozenset(weekday_set)
        elif rule_type is RuleType.CUSTOM_DAYS:
            if weekday_set is None:
                raise RuleValidationError(
                    "custom_days rules require weekday_set"
                )
            _validate_weekday_set(weekday_set)
            weekday_set = frozenset(weekday_set)
            if day_of_month is not None:
                raise RuleValidationError(
                    "custom_days rules must not set day_of_month"
                )
            if nth_weekday is not None:
                raise RuleValidationError(
                    "custom_days rules must not set nth_weekday"
                )
            if month is not None:
                raise RuleValidationError(
                    "custom_days rules must not set month"
                )
        elif rule_type is RuleType.MONTHLY_DAY:
            if day_of_month is None or not isinstance(day_of_month, int) or (
                isinstance(day_of_month, bool)
            ):
                raise RuleValidationError(
                    "monthly_day rules require day_of_month (1..31)"
                )
            if not 1 <= day_of_month <= 31:
                raise RuleValidationError(
                    f"day_of_month must be 1..31, got {day_of_month!r}"
                )
            if weekday_set is not None:
                raise RuleValidationError(
                    "monthly_day rules must not set weekday_set"
                )
            if nth_weekday is not None:
                raise RuleValidationError(
                    "monthly_day rules must not set nth_weekday"
                )
            if nth_weekday_weekday is not None:
                raise RuleValidationError(
                    "monthly_day rules must not set nth_weekday_weekday"
                )
        elif rule_type is RuleType.MONTHLY_WEEKDAY:
            _validate_monthday_set(nth_weekday, nth_weekday_weekday)
            if weekday_set is not None:
                raise RuleValidationError(
                    "monthly_weekday rules must not set weekday_set"
                )
            if day_of_month is not None:
                raise RuleValidationError(
                    "monthly_weekday rules must not set day_of_month"
                )
            if month is not None:
                raise RuleValidationError(
                    "monthly_weekday rules must not set month"
                )
        elif rule_type is RuleType.YEARLY:
            if month is None or not isinstance(month, int) or isinstance(
                month, bool
            ):
                raise RuleValidationError(
                    "yearly rules require month (1..12)"
                )
            if not 1 <= month <= 12:
                raise RuleValidationError(
                    f"month must be 1..12, got {month!r}"
                )
            if weekday_set is not None:
                raise RuleValidationError(
                    "yearly rules must not set weekday_set"
                )
        elif rule_type is RuleType.DAILY:
            if weekday_set is not None:
                raise RuleValidationError(
                    "daily rules must not set weekday_set"
                )
            if day_of_month is not None:
                raise RuleValidationError(
                    "daily rules must not set day_of_month"
                )
            if nth_weekday is not None:
                raise RuleValidationError(
                    "daily rules must not set nth_weekday"
                )
            if month is not None:
                raise RuleValidationError(
                    "daily rules must not set month"
                )

        object.__setattr__(self, "rule_type", rule_type)
        object.__setattr__(self, "interval", interval)
        object.__setattr__(self, "weekday_set", weekday_set)
        object.__setattr__(self, "day_of_month", day_of_month)
        object.__setattr__(self, "nth_weekday", nth_weekday)
        object.__setattr__(self, "nth_weekday_weekday", nth_weekday_weekday)
        object.__setattr__(self, "month", month)
        object.__setattr__(self, "start_date", start_date)
        object.__setattr__(self, "end_date", end_date)

    rule_type: RuleType
    interval: int
    weekday_set: frozenset[int] | None
    day_of_month: int | None
    nth_weekday: int | None
    nth_weekday_weekday: int | None
    month: int | None
    start_date: str
    end_date: str | None

    def __setattr__(self, name, value) -> None:
        raise AttributeError(
            "ScheduleRule is immutable; construct a new instance instead"
        )

    def __delattr__(self, name) -> None:
        raise AttributeError("ScheduleRule is immutable")

    def to_dict(self) -> dict:
        """Return the lossless dict form (also the DAO storage shape)."""
        return {
            "rule_type": self.rule_type.value,
            "interval": self.interval,
            "weekday_set": sorted(self.weekday_set) if self.weekday_set else None,
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

        Raises :class:`RuleValidationError` on unknown keys or invalid
        combinations, exactly like construction.
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
        unknown = set(data) - allowed
        if unknown:
            raise RuleValidationError(
                f"unknown rule fields: {sorted(unknown)}"
            )
        missing = {"rule_type"} - set(data)
        if missing:
            raise RuleValidationError(
                f"missing required rule fields: {sorted(missing)}"
            )
        weekday_set = data.get("weekday_set")
        if isinstance(weekday_set, list):
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

    def __eq__(self, other) -> bool:
        if not isinstance(other, ScheduleRule):
            return NotImplemented
        return all(
            getattr(self, slot) == getattr(other, slot)
            for slot in self.__slots__
        )

    def __hash__(self) -> int:
        return hash(
            tuple(
                (
                    frozenset(getattr(self, slot))
                    if isinstance(getattr(self, slot), frozenset)
                    else getattr(self, slot)
                )
                for slot in self.__slots__
            )
        )

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__
        )
        return f"ScheduleRule({fields})"