"""Explicit, Home-Assistant-free settings object for NestQuest core.

The integration reads its configuration off a Home Assistant config
entry (``entry.options``); the core package must not.  This module
bridges that split: it defines a frozen, validation-carrying
:class:`NestQuestSettings` dataclass that the integration constructs
from ``entry.options`` (via :meth:`NestQuestSettings.from_options`, or
:meth:`NestQuestSettings.from_options_resilient` for the per-field
fallback used at setup) and then passes into the core paths that
previously read HA config themselves — the rolling horizon
(``horizon_days``) and the daily rollover time (``day_rollover_time``),
plus the Feature 11 notification settings (notify target, the three
summary/reminder/report times, and the four independent enable toggles).

Nothing in this module imports ``homeassistant`` or touches a config
entry; ``from_options`` accepts any plain mapping keyed by the
:data:`~.const.CONF_*` names.  The validation semantics match the
options flow's: ``horizon_days`` must be a real integer >= 1 (bool
rejected), and ``day_rollover_time`` plus the three notification times
must be strict ``HH:MM`` 24-hour strings.  Construction therefore can
never yield a settings object whose horizon could shrink or explode the
materialized window, or whose rollover fires at an unparsable time.

The strict resolvers (:func:`_resolve_horizon_days`, :func:`_validate_hhmm`,
:func:`_resolve_bool`, :func:`_resolve_optional_str`) reject ``None``; the
``None``-as-absent mapping lives ONLY in :meth:`from_options` /
:meth:`from_options_resilient` (via :func:`_option_value`), so a hand-built
:class:`NestQuestSettings` cannot smuggle a ``None`` past
:meth:`__post_init__`.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
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
    LOGGER,
    TIME_PATTERN,
)


def _option_value(
    opts: Mapping[str, Any], key: str, default: Any
) -> Any:
    """Return ``opts[key]`` when present and non-None, else ``default``.

    This is the SOLE place the ``None``-as-absent mapping lives: a stored
    ``None`` is treated the same as an absent key — the historical
    ``horizon_days`` path mapped a missing-or-None value to the default,
    and this keeps that forgiving semantics uniform across every field.
    The per-field resolvers (:func:`_resolve_horizon_days`,
    :func:`_validate_hhmm`, :func:`_resolve_bool`,
    :func:`_resolve_optional_str`) are STRICT — they reject ``None`` —
    so a partially-populated ``entry.options`` dict (or one migrated
    across versions) never raises just because a key carries ``None``,
    and a hand-built :class:`NestQuestSettings` cannot smuggle a
    ``None`` past :meth:`NestQuestSettings.__post_init__`.
    """
    if key not in opts:
        return default
    value = opts[key]
    return default if value is None else value


def _validate_hhmm(value: Any, *, field: str) -> str:
    """Validate a strict ``HH:MM`` string and return it; raise naming ``field``.

    Uses the shared :data:`~.const.TIME_PATTERN` (the same compiled
    regex the options flow applies), so a stored option and a freshly
    validated form submit parse the same way.  ``None`` (and any
    non-string) is rejected; the ``None``-as-absent mapping lives ONLY
    in :meth:`NestQuestSettings.from_options` (via :func:`_option_value`).
    """
    if not isinstance(value, str) or TIME_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field} must be a strict HH:MM string, got {value!r}"
        )
    return value


def _resolve_horizon_days(value: Any) -> int:
    """Validate a horizon value and return the resolved day count.

    A bool is rejected (SQLite binds ``True``/``False`` onto an int), a
    non-int is rejected, and a sub-1 value is rejected — so a malformed
    option can never shrink or explode the materialized horizon.
    ``None`` is rejected here too; the ``None``-as-absent mapping lives
    ONLY in :meth:`NestQuestSettings.from_options` (via
    :func:`_option_value`), so a hand-built
    :class:`NestQuestSettings(horizon_days=None)` raises in
    :meth:`NestQuestSettings.__post_init__` rather than silently
    constructing an object whose :meth:`NestQuestSettings.horizon_window`
    would later raise ``TypeError`` on ``timedelta(days=None)``.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"horizon_days must be a positive integer, got {value!r}"
        )
    return value


def _resolve_bool(value: Any) -> bool:
    """Return a real bool; a non-bool (including ``None``) is rejected.

    voluptuous ``bool`` would coerce strings, so the options flow uses a
    strict-bool validator and this mirrors it.  The ``None``-as-absent
    mapping lives ONLY in :meth:`NestQuestSettings.from_options` (via
    :func:`_option_value`).
    """
    if not isinstance(value, bool):
        raise ValueError(f"expected a boolean, got {value!r}")
    return value


def _resolve_optional_str(value: Any) -> str:
    """Return a stripped notify target string; a non-str is rejected.

    A padded or whitespace-only value is STRIPPED to its trim — the
    shipped default is the empty string, meaning "no notifications are
    configured yet".  This is intentionally MORE LENIENT than the options
    flow, which REJECTS a target that differs from its own trim (so a
    padded value never persists): the integration tolerates a stored
    padded value (e.g. one migrated from an older schema) by normalizing
    it rather than crashing setup.  The ``None``-as-absent mapping lives
    ONLY in :meth:`NestQuestSettings.from_options` (via
    :func:`_option_value`).
    """
    if not isinstance(value, str):
        raise ValueError(f"notify_target must be a string, got {value!r}")
    return value.strip()


@dataclass(frozen=True)
class NestQuestSettings:
    """Explicit, HA-free configuration carried into core paths.

    The integration builds this once from ``entry.options`` (via
    :meth:`from_options`, or :meth:`from_options_resilient` for the
    per-field fallback used at setup) and threads it into the horizon
    materialization and the daily-rollover scheduling.  Core never
    reads HA config itself; callers pass the resolved horizon and
    rollover time in.

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
        # Validate STRICTLY at construction so a hand-built instance
        # cannot carry an invalid value: the same rules from_options
        # applies, but WITHOUT the None->default mapping (that lives
        # only in from_options via _option_value).  A None horizon, time,
        # toggle, or notify target raises here rather than later blowing
        # up horizon_window or the rollover listener.
        _resolve_horizon_days(self.horizon_days)
        _validate_hhmm(self.day_rollover_time, field="day_rollover_time")
        if not isinstance(self.notify_target, str):
            raise ValueError(
                f"notify_target must be a string, got {self.notify_target!r}"
            )
        _validate_hhmm(self.morning_summary_time, field="morning_summary_time")
        _validate_hhmm(
            self.afternoon_reminder_time, field="afternoon_reminder_time"
        )
        _validate_hhmm(
            self.end_of_day_report_time, field="end_of_day_report_time"
        )
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
        # The string is validated at construction, so a plain partition
        # is safe and avoids re-running the regex on every access.
        hour_str, _, minute_str = self.day_rollover_time.partition(":")
        return int(hour_str), int(minute_str)

    def horizon_window(
        self, today: datetime.date
    ) -> tuple[datetime.date, datetime.date]:
        """Return the rolling horizon window ``[today, today + horizon_days]``.

        ``today`` is REQUIRED (there is no host-clock default): the
        integration passes the HA-local ``hass.config.time_zone`` date so
        the horizon tracks the household's own day, and a silent
        host-clock fallback would be a wrong-day footgun (a test or a
        caller that forgets to pass ``today`` would otherwise materialize
        against the machine's calendar, not the household's).  The
        returned window is closed/inclusive — the same shape
        :func:`~.materialize.materialize` walks.
        """
        end = today + datetime.timedelta(days=self.horizon_days)
        return today, end

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any] | None = None
    ) -> "NestQuestSettings":
        """Build settings from a CONF_*-keyed mapping (e.g. ``entry.options``).

        Reads the same keys the options flow persists, applying the
        matching defaults when a key is absent OR ``None`` (via
        :func:`_option_value`, the SOLE place the ``None``-as-absent
        mapping lives) and validating STRICTLY: ``horizon_days`` is a
        positive int (bool rejected), the four times are strict
        ``HH:MM``, the four toggles are real booleans, and
        ``notify_target`` is a string (stripped).  A malformed value
        RAISES — the integration uses :meth:`from_options_resilient` at
        setup to fall back per field instead of crashing.  A ``None``
        mapping yields the all-defaults settings — useful for tests and
        for a fresh install whose options dict is empty.

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
            day_rollover_time=_validate_hhmm(
                _option_value(
                    opts, CONF_DAY_ROLLOVER_TIME, DEFAULT_DAY_ROLLOVER_TIME
                ),
                field="day_rollover_time",
            ),
            notify_target=_resolve_optional_str(
                _option_value(opts, CONF_NOTIFY_TARGET, "")
            ),
            morning_summary_time=_validate_hhmm(
                _option_value(
                    opts,
                    CONF_MORNING_SUMMARY_TIME,
                    DEFAULT_MORNING_SUMMARY_TIME,
                ),
                field="morning_summary_time",
            ),
            afternoon_reminder_time=_validate_hhmm(
                _option_value(
                    opts,
                    CONF_AFTERNOON_REMINDER_TIME,
                    DEFAULT_AFTERNOON_REMINDER_TIME,
                ),
                field="afternoon_reminder_time",
            ),
            end_of_day_report_time=_validate_hhmm(
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
                )
            ),
            afternoon_reminder_enabled=_resolve_bool(
                _option_value(
                    opts,
                    CONF_AFTERNOON_REMINDER_ENABLED,
                    DEFAULT_AUTOMATION_ENABLED,
                )
            ),
            end_of_day_report_enabled=_resolve_bool(
                _option_value(
                    opts,
                    CONF_END_OF_DAY_REPORT_ENABLED,
                    DEFAULT_AUTOMATION_ENABLED,
                )
            ),
            celebration_enabled=_resolve_bool(
                _option_value(
                    opts, CONF_CELEBRATION_ENABLED, DEFAULT_AUTOMATION_ENABLED
                )
            ),
        )

    @classmethod
    def from_options_resilient(
        cls, options: Mapping[str, Any] | None = None
    ) -> "NestQuestSettings":
        """Build settings, falling back PER FIELD on a malformed value.

        Unlike :meth:`from_options` (which raises on the first invalid
        field), this resolves EACH field in its own try/except: a
        malformed value logs a :data:`~.const.LOGGER` warning naming the
        field and falls back to that field's default.  The integration
        uses this at setup so a single bad sibling option (e.g. a
        migrated ``morning_summary_time`` of ``'25:00'``) cannot
        silently reset the user's ``horizon_days`` or
        ``day_rollover_time`` — the two fields core actually consumes.

        An absent or ``None`` key maps to the default via
        :func:`_option_value` WITHOUT a warning (that is the normal
        missing-key path); only a present, non-``None``, invalid value
        triggers a warning and a per-field fallback.
        """
        opts: Mapping[str, Any] = (
            MappingProxyType({}) if options is None else MappingProxyType(options)
        )
        resolved: dict[str, Any] = {}

        def _resolve(
            field: str, key: str, default: Any, fn: Callable[[Any], Any]
        ) -> None:
            raw = _option_value(opts, key, default)
            try:
                resolved[field] = fn(raw)
            except ValueError as err:
                LOGGER.warning(
                    "NestQuest option %s is invalid (%s); falling back "
                    "to the default %r",
                    field,
                    err,
                    default,
                )
                resolved[field] = default

        _resolve(
            "horizon_days",
            CONF_HORIZON_DAYS,
            DEFAULT_HORIZON_DAYS,
            _resolve_horizon_days,
        )
        _resolve(
            "day_rollover_time",
            CONF_DAY_ROLLOVER_TIME,
            DEFAULT_DAY_ROLLOVER_TIME,
            lambda v: _validate_hhmm(v, field="day_rollover_time"),
        )
        _resolve(
            "notify_target",
            CONF_NOTIFY_TARGET,
            "",
            _resolve_optional_str,
        )
        _resolve(
            "morning_summary_time",
            CONF_MORNING_SUMMARY_TIME,
            DEFAULT_MORNING_SUMMARY_TIME,
            lambda v: _validate_hhmm(v, field="morning_summary_time"),
        )
        _resolve(
            "afternoon_reminder_time",
            CONF_AFTERNOON_REMINDER_TIME,
            DEFAULT_AFTERNOON_REMINDER_TIME,
            lambda v: _validate_hhmm(v, field="afternoon_reminder_time"),
        )
        _resolve(
            "end_of_day_report_time",
            CONF_END_OF_DAY_REPORT_TIME,
            DEFAULT_END_OF_DAY_REPORT_TIME,
            lambda v: _validate_hhmm(v, field="end_of_day_report_time"),
        )
        _resolve(
            "morning_summary_enabled",
            CONF_MORNING_SUMMARY_ENABLED,
            DEFAULT_AUTOMATION_ENABLED,
            _resolve_bool,
        )
        _resolve(
            "afternoon_reminder_enabled",
            CONF_AFTERNOON_REMINDER_ENABLED,
            DEFAULT_AUTOMATION_ENABLED,
            _resolve_bool,
        )
        _resolve(
            "end_of_day_report_enabled",
            CONF_END_OF_DAY_REPORT_ENABLED,
            DEFAULT_AUTOMATION_ENABLED,
            _resolve_bool,
        )
        _resolve(
            "celebration_enabled",
            CONF_CELEBRATION_ENABLED,
            DEFAULT_AUTOMATION_ENABLED,
            _resolve_bool,
        )
        return cls(**resolved)
