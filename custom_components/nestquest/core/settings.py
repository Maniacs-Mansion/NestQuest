"""Explicit, Home-Assistant-free settings object for NestQuest core.

The integration reads its configuration off a Home Assistant config
entry (``entry.options``); the core package must not.  This module
bridges that split: it defines a frozen, validation-carrying
:class:`NestQuestSettings` dataclass that the integration constructs
from ``entry.options`` (via :meth:`NestQuestSettings.from_options`) and
then passes into the core paths that previously read HA config
themselves — the rolling horizon (``horizon_days``) and the daily
rollover time (``day_rollover_time``), plus the Feature 11 notification
settings (notify target, the three summary/reminder/report times, and
the four independent enable toggles).

Nothing in this module imports ``homeassistant`` or touches a config
entry; ``from_options`` accepts any plain mapping keyed by the
:data:`~.const.CONF_*` names.  The validation semantics match the
options flow's: ``horizon_days`` must be a real integer >= 1 (bool
rejected), and ``day_rollover_time`` plus the three notification times
must be strict ``HH:MM`` 24-hour strings.  Construction therefore can
never yield a settings object whose horizon could shrink or explode the
materialized window, or whose rollover fires at an unparsable time.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .const import (
    CONF_AFTERNOON_REMINDER_ENABLED,
    CONF_AFTERNOON_REMINDER_TIME,
    CONF_CELEBRATION_ENABLED,
    CONF_DAY_ROLLOVER_TIME,
    CONF_END_OF_DAY_REPORT_ENABLED,
    CONF_END_OF_DAY_REPORT_TIME,
    CONF_HORIZON_DAYS,
    CONF_MORNING_SUMMARY_ENABLED,
    CONF_MORNING_SUMMARY_TIME,
    CONF_NOTIFY_TARGET,
    DEFAULT_AFTERNOON_REMINDER_TIME,
    DEFAULT_AUTOMATION_ENABLED,
    DEFAULT_DAY_ROLLOVER_TIME,
    DEFAULT_END_OF_DAY_REPORT_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_MORNING_SUMMARY_TIME,
)

#: Strict 24-hour ``HH:MM`` pattern — matches the options flow's
#: ``_TIME_PATTERN`` verbatim so a stored option and a freshly-validated
#: form submit parse the same way.
_HHMM_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def _option_value(
    opts: Mapping[str, Any], key: str, default: Any
) -> Any:
    """Return ``opts[key]`` when present and non-None, else ``default``.

    A stored ``None`` is treated the same as an absent key — the
    historical ``horizon_days`` path mapped a missing-or-None value to
    the default, and this keeps that forgiving semantics uniform across
    every field: a partially-populated ``entry.options`` dict (or one
    migrated across versions) never raises just because a key carries
    ``None``.
    """
    if key not in opts:
        return default
    value = opts[key]
    return default if value is None else value


def _parse_hhmm(value: str) -> tuple[int, int]:
    """Return ``(hour, minute)`` for a strict ``HH:MM`` string.

    Raises :class:`ValueError` for anything that is not a string or does
    not match :data:`_HHMM_PATTERN` — the same rule the options flow
    applies, surfaced here so a malformed mapping cannot construct a
    settings object with an unparsable time.
    """
    if not isinstance(value, str) or _HHMM_PATTERN.fullmatch(value) is None:
        raise ValueError(f"expected a strict HH:MM string, got {value!r}")
    hour_str, _, minute_str = value.partition(":")
    return int(hour_str), int(minute_str)


def _resolve_horizon_days(value: Any) -> int:
    """Validate a horizon value and return the resolved day count.

    Mirrors :func:`~.materialize._resolve_horizon_days`: a bool is
    rejected (SQLite binds ``True``/``False`` onto an int), a non-int
    is rejected, and a sub-1 value is rejected — so a malformed option
    can never shrink or explode the materialized horizon.  ``None``
    resolves to :data:`~.const.DEFAULT_HORIZON_DAYS`.
    """
    if value is None:
        return DEFAULT_HORIZON_DAYS
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"horizon_days must be a positive integer, got {value!r}"
        )
    return value


def _resolve_bool(value: Any, *, default: bool) -> bool:
    """Return a real bool, falling back to ``default`` when ``value`` is None.

    A non-bool, non-None value is rejected — voluptuous ``bool`` would
    coerce strings, so the options flow uses ``_strict_bool`` and this
    mirrors it.
    """
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"expected a boolean, got {value!r}")
    return value


def _resolve_optional_str(value: Any) -> str:
    """Return a stripped notify target string; empty means "not configured".

    A non-str value is rejected.  An empty (or whitespace-only) value
    is kept as the empty string — the shipped default, meaning no
    notifications are configured yet — rather than raising, mirroring
    the options flow's empty-target acceptance.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"notify_target must be a string, got {value!r}")
    return value.strip()


@dataclass(frozen=True)
class NestQuestSettings:
    """Explicit, HA-free configuration carried into core paths.

    The integration builds this once from ``entry.options`` (via
    :meth:`from_options`) and threads it into the horizon materialization
    and the daily-rollover scheduling.  Core never reads HA config
    itself; callers pass the resolved horizon and rollover time in.

    All fields are validated at construction; the dataclass is frozen so
    a stale settings object cannot be mutated in place after the
    integration hands it off.
    """

    horizon_days: int = DEFAULT_HORIZON_DAYS
    day_rollover_time: str = DEFAULT_DAY_ROLLOVER_TIME
    notify_target: str = ""
    morning_summary_time: str = DEFAULT_MORNING_SUMMARY_TIME
    afternoon_reminder_time: str = DEFAULT_AFTERNOON_REMINDER_TIME
    end_of_day_report_time: str = DEFAULT_END_OF_DAY_REPORT_TIME
    morning_summary_enabled: bool = DEFAULT_AUTOMATION_ENABLED
    afternoon_reminder_enabled: bool = DEFAULT_AUTOMATION_ENABLED
    end_of_day_report_enabled: bool = DEFAULT_AUTOMATION_ENABLED
    celebration_enabled: bool = DEFAULT_AUTOMATION_ENABLED

    def __post_init__(self) -> None:
        # Validate at construction so a hand-built instance cannot carry
        # an invalid value either: the same rules from_options applies.
        _resolve_horizon_days(self.horizon_days)
        _parse_hhmm(self.day_rollover_time)
        if not isinstance(self.notify_target, str):
            raise ValueError(
                f"notify_target must be a string, got {self.notify_target!r}"
            )
        _parse_hhmm(self.morning_summary_time)
        _parse_hhmm(self.afternoon_reminder_time)
        _parse_hhmm(self.end_of_day_report_time)
        for name in (
            "morning_summary_enabled",
            "afternoon_reminder_enabled",
            "end_of_day_report_enabled",
            "celebration_enabled",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise ValueError(
                    f"{name} must be a boolean, got {value!r}"
                )

    @property
    def day_rollover_hour_minute(self) -> tuple[int, int]:
        """The (hour, minute) the daily rollover fires at."""
        return _parse_hhmm(self.day_rollover_time)

    def horizon_window(
        self, today: datetime.date | None = None
    ) -> tuple[datetime.date, datetime.date]:
        """Return the rolling horizon window ``[today, today + horizon_days]``.

        ``today`` defaults to the host clock's date
        (:func:`datetime.date.today`), matching the historical materialize
        default.  The integration overrides this with the HA-local
        ``hass.config.time_zone`` date so the horizon tracks the
        household's own day.  The returned window is closed/inclusive —
        the same shape :func:`~.materialize.materialize` walks.
        """
        if today is None:
            today = datetime.date.today()
        end = today + datetime.timedelta(days=self.horizon_days)
        return today, end

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any] | None = None
    ) -> "NestQuestSettings":
        """Build settings from a CONF_*-keyed mapping (e.g. ``entry.options``).

        Reads the same keys the options flow persists, applying the
        matching defaults when a key is absent and validating the same
        way the options flow does: ``horizon_days`` is a positive int
        (bool rejected), the four times are strict ``HH:MM``, the four
        toggles are real booleans, and ``notify_target`` is a string.
        A ``None`` mapping yields the all-defaults settings — useful for
        tests and for a fresh install whose options dict is empty.

        ``options`` is consumed read-only via
        :class:`types.MappingProxyType`, so this method never mutates
        the caller's mapping.
        """
        opts: Mapping[str, Any] = (
            MappingProxyType({}) if options is None else MappingProxyType(options)
        )
        return cls(
            horizon_days=_resolve_horizon_days(
                _option_value(opts, CONF_HORIZON_DAYS, DEFAULT_HORIZON_DAYS)
            ),
            day_rollover_time=_parse_hhmm_str(
                _option_value(opts, CONF_DAY_ROLLOVER_TIME, DEFAULT_DAY_ROLLOVER_TIME),
                field="day_rollover_time",
            ),
            notify_target=_resolve_optional_str(
                _option_value(opts, CONF_NOTIFY_TARGET, "")
            ),
            morning_summary_time=_parse_hhmm_str(
                _option_value(
                    opts, CONF_MORNING_SUMMARY_TIME, DEFAULT_MORNING_SUMMARY_TIME
                ),
                field="morning_summary_time",
            ),
            afternoon_reminder_time=_parse_hhmm_str(
                _option_value(
                    opts,
                    CONF_AFTERNOON_REMINDER_TIME,
                    DEFAULT_AFTERNOON_REMINDER_TIME,
                ),
                field="afternoon_reminder_time",
            ),
            end_of_day_report_time=_parse_hhmm_str(
                _option_value(
                    opts,
                    CONF_END_OF_DAY_REPORT_TIME,
                    DEFAULT_END_OF_DAY_REPORT_TIME,
                ),
                field="end_of_day_report_time",
            ),
            morning_summary_enabled=_resolve_bool(
                _option_value(
                    opts, CONF_MORNING_SUMMARY_ENABLED, DEFAULT_AUTOMATION_ENABLED
                ),
                default=DEFAULT_AUTOMATION_ENABLED,
            ),
            afternoon_reminder_enabled=_resolve_bool(
                _option_value(
                    opts,
                    CONF_AFTERNOON_REMINDER_ENABLED,
                    DEFAULT_AUTOMATION_ENABLED,
                ),
                default=DEFAULT_AUTOMATION_ENABLED,
            ),
            end_of_day_report_enabled=_resolve_bool(
                _option_value(
                    opts,
                    CONF_END_OF_DAY_REPORT_ENABLED,
                    DEFAULT_AUTOMATION_ENABLED,
                ),
                default=DEFAULT_AUTOMATION_ENABLED,
            ),
            celebration_enabled=_resolve_bool(
                _option_value(
                    opts, CONF_CELEBRATION_ENABLED, DEFAULT_AUTOMATION_ENABLED
                ),
                default=DEFAULT_AUTOMATION_ENABLED,
            ),
        )


def _parse_hhmm_str(value: Any, *, field: str) -> str:
    """Return a validated ``HH:MM`` string, raising on a malformed value.

    A separate helper from :func:`_parse_hhmm` because :meth:`from_options`
    needs the original string kept (the dataclass stores strings, not
    tuples), but still wants the same strict validation.
    """
    if not isinstance(value, str) or _HHMM_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field} must be a strict HH:MM string, got {value!r}"
        )
    return value
