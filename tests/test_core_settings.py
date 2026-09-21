"""Tests for core/settings.py: the explicit, HA-free settings object.

Covers the contracts from task 4dd8f870 plus the review fixes:

- ``NestQuestSettings.from_options`` applies defaults when keys are
  absent and rejects invalid horizon/rollover values; ``from_options``
  is strict (raises), while ``from_options_resilient`` falls back PER
  FIELD so a malformed sibling cannot reset horizon_days/rollover.
- An AST scan asserts no module under
  ``custom_components/nestquest/core/`` imports ``homeassistant``,
  names ``hass``/``config_entry``, reads a ``.config``/``.options``/
  ``.data`` attribute, or dynamically reads them via ``getattr``/
  ``hasattr``.  (Docstring mentions are allowed.)  A negative-control
  test feeds the scanner each bypass shape and asserts it flags them.
- A settings object constructed with NON-default ``horizon_days`` and
  ``day_rollover_time`` drives a materialization whose resulting window
  matches the non-default horizon — via BOTH the core ``materialize``
  path and the INTEGRATION path (``_run_horizon_materialization`` +
  ``_register_day_rollover_listener``).
"""
from __future__ import annotations

import ast
import datetime
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.nestquest.const import (
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
from custom_components.nestquest.core.settings import NestQuestSettings


# ---------------------------------------------------------------------------
# from_options: defaults + validation.
# ---------------------------------------------------------------------------


def test_from_options_none_yields_all_defaults() -> None:
    """A None mapping yields a settings object with every default applied."""
    s = NestQuestSettings.from_options(None)
    assert s.horizon_days == DEFAULT_HORIZON_DAYS
    assert s.day_rollover_time == DEFAULT_DAY_ROLLOVER_TIME
    assert s.notify_target == ""
    assert s.morning_summary_time == DEFAULT_MORNING_SUMMARY_TIME
    assert s.afternoon_reminder_time == DEFAULT_AFTERNOON_REMINDER_TIME
    assert s.end_of_day_report_time == DEFAULT_END_OF_DAY_REPORT_TIME
    assert s.morning_summary_enabled is DEFAULT_AUTOMATION_ENABLED
    assert s.afternoon_reminder_enabled is DEFAULT_AUTOMATION_ENABLED
    assert s.end_of_day_report_enabled is DEFAULT_AUTOMATION_ENABLED
    assert s.celebration_enabled is DEFAULT_AUTOMATION_ENABLED


def test_from_options_empty_mapping_yields_all_defaults() -> None:
    """An empty mapping also yields every default (the fresh-install case)."""
    s = NestQuestSettings.from_options({})
    assert s.horizon_days == DEFAULT_HORIZON_DAYS
    assert s.day_rollover_time == DEFAULT_DAY_ROLLOVER_TIME


def test_from_options_reads_keys() -> None:
    """Each CONF_* key is read into the matching field."""
    opts = {
        CONF_HORIZON_DAYS: 21,
        CONF_DAY_ROLLOVER_TIME: "03:30",
        CONF_NOTIFY_TARGET: "notify.mobile_app_x",
        CONF_MORNING_SUMMARY_TIME: "07:15",
        CONF_AFTERNOON_REMINDER_TIME: "14:45",
        CONF_END_OF_DAY_REPORT_TIME: "21:30",
        CONF_MORNING_SUMMARY_ENABLED: False,
        CONF_AFTERNOON_REMINDER_ENABLED: False,
        CONF_END_OF_DAY_REPORT_ENABLED: False,
        CONF_CELEBRATION_ENABLED: False,
    }
    s = NestQuestSettings.from_options(opts)
    assert s.horizon_days == 21
    assert s.day_rollover_time == "03:30"
    assert s.notify_target == "notify.mobile_app_x"
    assert s.morning_summary_time == "07:15"
    assert s.afternoon_reminder_time == "14:45"
    assert s.end_of_day_report_time == "21:30"
    assert s.morning_summary_enabled is False
    assert s.afternoon_reminder_enabled is False
    assert s.end_of_day_report_enabled is False
    assert s.celebration_enabled is False


def test_from_options_does_not_mutate_caller_mapping() -> None:
    """from_options consumes the mapping read-only."""
    opts: dict[str, Any] = {CONF_HORIZON_DAYS: 9}
    snapshot = dict(opts)
    _ = NestQuestSettings.from_options(opts)
    assert opts == snapshot


@pytest.mark.parametrize(
    "value",
    [True, False, "5", 0, -3, 1.5],
)
def test_from_options_rejects_invalid_horizon(value: Any) -> None:
    """A malformed horizon_days is rejected.

    A key that is ABSENT (or present-but-None) falls back to the
    default — see :func:`test_from_options_horizon_absent_falls_back_to_default`
    and the None case below; any other invalid value raises, matching
    the options flow's strict validation.
    """
    with pytest.raises(ValueError, match="horizon_days"):
        NestQuestSettings.from_options({CONF_HORIZON_DAYS: value})


def test_from_options_horizon_absent_falls_back_to_default() -> None:
    """An absent (or None) horizon_days key falls back to the default."""
    assert NestQuestSettings.from_options({}).horizon_days == DEFAULT_HORIZON_DAYS
    assert (
        NestQuestSettings.from_options(
            {CONF_HORIZON_DAYS: None}
        ).horizon_days
        == DEFAULT_HORIZON_DAYS
    )


@pytest.mark.parametrize(
    "value",
    ["25:00", "00:60", "24:00", "9:5", "abc", "07:00:00", 700, ""],
)
def test_from_options_rejects_invalid_rollover(value: Any) -> None:
    """A malformed day_rollover_time is rejected.

    A key that is ABSENT (or present-but-None) falls back to the
    default — a present-but-empty-string or non-HH:MM value raises,
    matching the options flow's strict validation.
    """
    with pytest.raises(ValueError):
        NestQuestSettings.from_options({CONF_DAY_ROLLOVER_TIME: value})


def test_from_options_rollover_absent_falls_back_to_default() -> None:
    """An absent (or None) day_rollover_time key falls back to the default."""
    assert (
        NestQuestSettings.from_options({}).day_rollover_time
        == DEFAULT_DAY_ROLLOVER_TIME
    )
    assert (
        NestQuestSettings.from_options(
            {CONF_DAY_ROLLOVER_TIME: None}
        ).day_rollover_time
        == DEFAULT_DAY_ROLLOVER_TIME
    )


@pytest.mark.parametrize(
    "key",
    [
        CONF_MORNING_SUMMARY_TIME,
        CONF_AFTERNOON_REMINDER_TIME,
        CONF_END_OF_DAY_REPORT_TIME,
    ],
)
def test_from_options_rejects_invalid_notification_time(key: str) -> None:
    """The three notification times are validated as strict HH:MM."""
    with pytest.raises(ValueError):
        NestQuestSettings.from_options({key: "25:99"})


@pytest.mark.parametrize(
    "key",
    [
        CONF_MORNING_SUMMARY_ENABLED,
        CONF_AFTERNOON_REMINDER_ENABLED,
        CONF_END_OF_DAY_REPORT_ENABLED,
        CONF_CELEBRATION_ENABLED,
    ],
)
def test_from_options_rejects_non_bool_toggle(key: str) -> None:
    """Each toggle must be a real bool (no string coercion)."""
    with pytest.raises(ValueError):
        NestQuestSettings.from_options({key: "yes"})


def test_from_options_rejects_non_string_notify_target() -> None:
    """notify_target must be a string (or absent)."""
    with pytest.raises(ValueError):
        NestQuestSettings.from_options({CONF_NOTIFY_TARGET: 123})


def test_from_options_strips_notify_target() -> None:
    """A padded notify target is stripped; empty stays empty."""
    s = NestQuestSettings.from_options({CONF_NOTIFY_TARGET: "  notify.x  "})
    assert s.notify_target == "notify.x"
    s_empty = NestQuestSettings.from_options({CONF_NOTIFY_TARGET: "   "})
    assert s_empty.notify_target == ""


# ---------------------------------------------------------------------------
# from_options_resilient: per-field fallback (P2-1).
# ---------------------------------------------------------------------------


def test_from_options_resilient_none_yields_all_defaults() -> None:
    """A None mapping yields the all-defaults settings (no warnings)."""
    s = NestQuestSettings.from_options_resilient(None)
    assert s.horizon_days == DEFAULT_HORIZON_DAYS
    assert s.day_rollover_time == DEFAULT_DAY_ROLLOVER_TIME


def test_from_options_resilient_reads_valid_keys() -> None:
    """Valid keys are read exactly as from_options would read them."""
    s = NestQuestSettings.from_options_resilient(
        {CONF_HORIZON_DAYS: 3, CONF_DAY_ROLLOVER_TIME: "03:30"}
    )
    assert s.horizon_days == 3
    assert s.day_rollover_time == "03:30"


def test_from_options_resilient_keeps_horizon_when_sibling_is_bad(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed SIBLING field cannot reset horizon_days or day_rollover_time.

    The old all-or-nothing fallback reset EVERY field when from_options
    raised for ANY field: ``{horizon_days: 3, morning_summary_time:
    '25:00'}`` yielded horizon 14 (was 3).  The resilient builder falls
    back PER FIELD, so horizon_days=3 and day_rollover_time='03:30'
    survive a malformed morning_summary_time, and the bad field alone
    falls back to its default with a warning naming it.
    """
    s = NestQuestSettings.from_options_resilient(
        {
            CONF_HORIZON_DAYS: 3,
            CONF_DAY_ROLLOVER_TIME: "03:30",
            CONF_MORNING_SUMMARY_TIME: "25:00",
        }
    )
    assert s.horizon_days == 3
    assert s.day_rollover_time == "03:30"
    # The malformed sibling fell back to its default.
    assert s.morning_summary_time == DEFAULT_MORNING_SUMMARY_TIME
    # A warning was logged naming the bad field.
    assert any(
        "morning_summary_time" in record.getMessage()
        and record.levelname == "WARNING"
        for record in caplog.records
    )


def test_from_options_resilient_bad_horizon_falls_back_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed horizon_days itself falls back to the default + warning."""
    s = NestQuestSettings.from_options_resilient({CONF_HORIZON_DAYS: True})
    assert s.horizon_days == DEFAULT_HORIZON_DAYS
    assert any(
        "horizon_days" in record.getMessage() and record.levelname == "WARNING"
        for record in caplog.records
    )


def test_from_options_resilient_bad_rollover_falls_back_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed day_rollover_time falls back to the default + warning."""
    s = NestQuestSettings.from_options_resilient(
        {CONF_DAY_ROLLOVER_TIME: "99:99"}
    )
    assert s.day_rollover_time == DEFAULT_DAY_ROLLOVER_TIME
    assert any(
        "day_rollover_time" in record.getMessage()
        and record.levelname == "WARNING"
        for record in caplog.records
    )


def test_from_options_resilient_none_value_is_not_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A None value maps to the default silently (it is absent, not malformed)."""
    s = NestQuestSettings.from_options_resilient(
        {CONF_HORIZON_DAYS: None, CONF_MORNING_SUMMARY_TIME: None}
    )
    assert s.horizon_days == DEFAULT_HORIZON_DAYS
    assert s.morning_summary_time == DEFAULT_MORNING_SUMMARY_TIME
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


# ---------------------------------------------------------------------------
# Construction + frozenness.
# ---------------------------------------------------------------------------


def test_direct_construction_validates() -> None:
    """Hand-built instances validate the same way from_options does."""
    with pytest.raises(ValueError):
        NestQuestSettings(horizon_days=0)
    with pytest.raises(ValueError):
        NestQuestSettings(day_rollover_time="bad")
    with pytest.raises(ValueError):
        NestQuestSettings(morning_summary_enabled="yes")


@pytest.mark.parametrize(
    "field,kwargs",
    [
        ("horizon_days", {"horizon_days": None}),
        ("day_rollover_time", {"day_rollover_time": None}),
        ("notify_target", {"notify_target": None}),
        ("morning_summary_time", {"morning_summary_time": None}),
        ("afternoon_reminder_time", {"afternoon_reminder_time": None}),
        ("end_of_day_report_time", {"end_of_day_report_time": None}),
        ("morning_summary_enabled", {"morning_summary_enabled": None}),
        ("afternoon_reminder_enabled", {"afternoon_reminder_enabled": None}),
        ("end_of_day_report_enabled", {"end_of_day_report_enabled": None}),
        ("celebration_enabled", {"celebration_enabled": None}),
    ],
)
def test_direct_construction_rejects_none(field: str, kwargs: dict[str, Any]) -> None:
    """__post_init__ is STRICT: None is rejected for every field.

    P2-5: the None->default mapping lives ONLY in from_options (via
    _option_value).  A hand-built NestQuestSettings(field=None) must raise
    in __post_init__ rather than constructing and later blowing up
    horizon_window (timedelta(days=None) -> TypeError) or the rollover
    listener.
    """
    with pytest.raises(ValueError):
        NestQuestSettings(**kwargs)


@pytest.mark.parametrize("value", [True, False, "5", 1.5])
def test_direct_construction_rejects_non_int_horizon(value: Any) -> None:
    """A bool or non-int horizon is rejected at construction (not bool-as-int)."""
    with pytest.raises(ValueError, match="horizon_days"):
        NestQuestSettings(horizon_days=value)



def test_settings_is_frozen() -> None:
    """The dataclass is frozen so a stale settings object cannot be mutated."""
    s = NestQuestSettings()
    with pytest.raises(FrozenInstanceError):
        s.horizon_days = 99  # type: ignore[misc]


def test_day_rollover_hour_minute() -> None:
    """day_rollover_hour_minute returns the parsed (hour, minute)."""
    s = NestQuestSettings(day_rollover_time="03:30")
    assert s.day_rollover_hour_minute == (3, 30)
    assert NestQuestSettings().day_rollover_hour_minute == (0, 0)


# ---------------------------------------------------------------------------
# horizon_window.
# ---------------------------------------------------------------------------


def test_horizon_window_pinned_today() -> None:
    """A pinned today is honored so the window is deterministic.

    ``today`` is REQUIRED (no host-clock default) — see
    :meth:`NestQuestSettings.horizon_window`.
    """
    s = NestQuestSettings(horizon_days=5)
    pinned = datetime.date(2026, 3, 1)
    start, end = s.horizon_window(pinned)
    assert start == pinned
    assert end == pinned + datetime.timedelta(days=5)


def test_horizon_window_requires_today() -> None:
    """horizon_window has no default today: omitting it raises TypeError."""
    s = NestQuestSettings(horizon_days=5)
    with pytest.raises(TypeError):
        s.horizon_window()  # type: ignore[call-arg]


def test_horizon_window_non_default_horizon() -> None:
    """A non-default horizon_days widens the window accordingly."""
    pinned = datetime.date(2026, 3, 1)
    short = NestQuestSettings(horizon_days=3).horizon_window(pinned)
    long_ = NestQuestSettings(horizon_days=30).horizon_window(pinned)
    assert short[1] == pinned + datetime.timedelta(days=3)
    assert long_[1] == pinned + datetime.timedelta(days=30)
    assert (long_[1] - short[1]).days == 27


# ---------------------------------------------------------------------------
# AST: no HA config reads under core/.
# ---------------------------------------------------------------------------

CORE_PKG = Path(
    __import__(
        "custom_components.nestquest.core", fromlist=["__file__"]
    ).__file__
).parent


def _is_homeassistant(module: str) -> bool:
    return module == "homeassistant" or module.startswith("homeassistant.")


#: HA-specific identifiers with no legitimate core use.  ``entry`` is
#: deliberately NOT in this set: core uses ``entry`` as a domain loop
#: variable (iterating weekday_set entries in recurrence/presence/
#: quest_definitions), so forbidding the bare name would false-positive.
#: The config-entry attribute reads the bare-name check misses are
#: caught by _CONFIG_ATTRS and _FORBIDDEN_ATTRS below.
_FORBIDDEN_NAMES = frozenset({"hass", "config_entry"})

#: Attribute names that signal a HA object reference (self.hass,
#: self.entry, obj.config_entry).  No core module currently uses any of
#: these as an attribute, so flagging them is false-positive-free.
_FORBIDDEN_ATTRS = frozenset({"hass", "entry", "config_entry"})

#: Config-entry attribute reads — the shapes ``hass.config``,
#: ``config_entry.options``, ``self.entry.options``, ``runtime.options``,
#: ``entry.data``.  Flagging the attribute ANYWHERE (regardless of root)
#: is what catches ``runtime.options``, which the old root-only check
#: missed.  No core module currently reads any of these attributes.
_CONFIG_ATTRS = frozenset({"config", "options", "data"})

#: Dynamic config-entry reads via getattr/hasattr with a string argument.
_GETATTR_FUNCS = frozenset({"getattr", "hasattr"})


def _scan_source_for_ha_config(
    source: str, *, name: str = "<snippet>"
) -> list[str]:
    """Return offender strings for HA-coupling in ``source``.

    Flags (each closes a bypass the old root-only ``hass``/``entry``
    chain check missed):

    - any ``import homeassistant`` / ``from homeassistant ...``;
    - any ``Name``/``arg`` whose id is ``hass`` or ``config_entry``
      (HA-specific identifiers with no legitimate core use);
    - any attribute access whose ``attr`` is ``hass``/``entry``/
      ``config_entry`` (catches ``self.hass``, ``self.entry``,
      ``obj.config_entry`` — root names the old check could not see);
    - any attribute access whose ``attr`` is ``config``/``options``/
      ``data`` (catches ``hass.config``, ``config_entry.options``,
      ``self.entry.options``, ``runtime.options`` regardless of root);
    - any ``getattr``/``hasattr`` call whose string argument is
      ``'config'``/``'options'``/``'data'`` (catches the dynamic read
      ``getattr(hass, 'config')`` the static attribute check cannot see).

    Docstring mentions are structurally exempt: AST only sees code, and
    none of these node shapes appear inside a string literal.  The
    existing docstring references to ``hass.config`` in ``core/events.py``
    and ``core/store.py`` therefore pass.
    """
    tree = ast.parse(source, filename=name)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_homeassistant(alias.name):
                    offenders.append(
                        f"{name}:{node.lineno} homeassistant import: "
                        f"import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if _is_homeassistant(base):
                offenders.append(
                    f"{name}:{node.lineno} homeassistant import: from {base}"
                )
            for alias in node.names:
                combined = f"{base}.{alias.name}" if base else alias.name
                if _is_homeassistant(combined):
                    offenders.append(
                        f"{name}:{node.lineno} homeassistant import: "
                        f"from {base} import {alias.name}"
                    )
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                offenders.append(
                    f"{name}:{node.lineno} forbidden identifier: {node.id!r}"
                )
        elif isinstance(node, ast.arg):
            if node.arg in _FORBIDDEN_NAMES:
                offenders.append(
                    f"{name}:{node.lineno} forbidden parameter: {node.arg!r}"
                )
        elif isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_ATTRS:
                offenders.append(
                    f"{name}:{node.lineno} forbidden attribute: .{node.attr}"
                )
            if node.attr in _CONFIG_ATTRS:
                offenders.append(
                    f"{name}:{node.lineno} config-entry attribute read: "
                    f".{node.attr}"
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _GETATTR_FUNCS:
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value in _CONFIG_ATTRS
                    ):
                        offenders.append(
                            f"{name}:{node.lineno} {func.id}() dynamic "
                            f"config-entry read: {arg.value!r}"
                        )

    return offenders


def _scan_module_for_ha_config(path: Path) -> list[str]:
    """Scan a core module file for HA-coupling (file-backed scan)."""
    return _scan_source_for_ha_config(
        path.read_text(encoding="utf-8"), name=path.name
    )


def test_core_modules_have_no_ha_config_reads() -> None:
    """No core module imports homeassistant or reads HA config / entry options.

    The scan forbids the HA-specific identifiers ``hass``/``config_entry``,
    the HA-object attributes ``.hass``/``.entry``/``.config_entry``, the
    config-entry attribute reads ``.config``/``.options``/``.data``, and
    dynamic ``getattr``/``hasattr`` reads of them — so a chain rooted at
    ``self`` or ``runtime`` (which the old root-only check missed) is now
    caught.  Docstring mentions pass: AST only sees code.
    """
    py_files = sorted(CORE_PKG.rglob("*.py"))
    assert py_files, "core package not found"
    all_offenders: list[str] = []
    for py_file in py_files:
        all_offenders.extend(_scan_module_for_ha_config(py_file))
    assert all_offenders == [], (
        "core package reads HA config / entry options:\n"
        + "\n".join(all_offenders)
    )


def test_ast_scan_flags_each_bypass_shape() -> None:
    """Negative control: the scanner flags each bypass shape the old check missed.

    The old scan only flagged chains rooted at a literal name ``hass``/
    ``entry``.  Each snippet below is a shape it missed; the new scanner
    must flag every one.
    """
    snippets: dict[str, str] = {
        "self.hass.config": "x = self.hass.config\n",
        "config_entry.options": "x = config_entry.options\n",
        "self.entry.options": "x = self.entry.options\n",
        "getattr(hass,'config')": "x = getattr(hass, 'config')\n",
        "runtime.options": "x = runtime.options\n",
        "hasattr(obj,'data')": "x = hasattr(obj, 'data')\n",
    }
    for label, src in snippets.items():
        offenders = _scan_source_for_ha_config(src, name=label)
        assert offenders, f"scanner missed {label!r}: {src!r}"


def test_ast_scan_allows_legitimate_entry_loop_var() -> None:
    """A bare ``entry`` loop variable (a domain concept) is NOT flagged.

    ``entry`` is used in core as a loop variable over weekday_set entries
    (recurrence.py, presence.py, quest_definitions.py) — not a HA config
    entry.  Forbidding the bare name would false-positive on those, so
    only ``hass``/``config_entry`` are forbidden as bare names; the
    config-entry reads via ``entry.options``/``entry.data`` are caught by
    the ``_CONFIG_ATTRS`` attribute check instead.
    """
    offenders = _scan_source_for_ha_config(
        "for entry in items:\n    pass\n", name="loop"
    )
    assert offenders == [], offenders


def test_ast_scan_allows_clean_core_shape() -> None:
    """A clean snippet with no HA coupling is not flagged (no false positives)."""
    src = "opts = {'a': 1}\nx = opts.get('a')\nfor entry in items:\n    pass\n"
    offenders = _scan_source_for_ha_config(src, name="clean")
    assert offenders == [], offenders


def test_settings_module_lives_under_core() -> None:
    """settings.py is part of the core package (not the integration root)."""
    assert (CORE_PKG / "settings.py").is_file()
    # And it is importable as a core submodule.
    import custom_components.nestquest.core.settings as mod

    assert hasattr(mod, "NestQuestSettings")
    assert isinstance(mod.NestQuestSettings, type)


def test_settings_module_has_no_ha_imports() -> None:
    """settings.py specifically carries no homeassistant import or config read."""
    offenders = _scan_module_for_ha_config(CORE_PKG / "settings.py")
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# Materialization over a non-default horizon: core path + integration path.
# ---------------------------------------------------------------------------


async def _prepare(path, executor):
    """Open and migrate a database backed by ``executor`` (executor-only DB access)."""
    from custom_components.nestquest.core.db import NestQuestDatabase
    from custom_components.nestquest.core.migrations import apply_migrations

    database = NestQuestDatabase(executor)
    await database.open(path)
    await apply_migrations(database)
    return database


async def test_materialize_over_non_default_horizon(hass, tmp_path) -> None:
    """A settings object with a non-default horizon drives the matching window.

    Constructs NestQuestSettings with horizon_days=3 and day_rollover_time
    '03:30' (both non-default), builds the window via horizon_window, and
    drives the CORE ``materialize`` over it; asserts the resulting instance
    rows land exactly on the [today, today+3] window and NOT beyond it.
    """
    from custom_components.nestquest.core.dao_children import ChildrenDao
    from custom_components.nestquest.core.dao_instances import (
        QuestInstancesDao,
    )
    from custom_components.nestquest.core.materialize import materialize
    from custom_components.nestquest.core.quest_definitions import (
        create_quest_definition,
    )
    from custom_components.nestquest.core.recurrence import (
        RuleType,
        ScheduleRule,
    )

    database = await _prepare(tmp_path / "nq.db", hass.async_add_executor_job)
    try:
        settings = NestQuestSettings(
            horizon_days=3, day_rollover_time="03:30"
        )
        assert settings.horizon_days == 3
        assert settings.day_rollover_time == "03:30"

        today = datetime.date(2026, 3, 1)
        start, end = settings.horizon_window(today)
        assert start == today
        assert end == today + datetime.timedelta(days=3)

        NOW = "2026-03-01T12:00:00+00:00"
        child = await ChildrenDao(database).create("Ada", NOW)
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(
                rule_type=RuleType.DAILY, start_date=today.isoformat()
            ),
            [child.id],
            ["morning"],
        )

        count = await materialize(
            database,
            start.isoformat(),
            end.isoformat(),
            today=today,
        )
        # 4 days (today..today+3 inclusive), one instance per day.
        assert count == 4

        records = await QuestInstancesDao(database).list_by_date_range(
            child.id, start.isoformat(), end.isoformat()
        )
        dates = sorted({r.due_date for r in records})
        assert dates == [
            (today + datetime.timedelta(days=i)).isoformat()
            for i in range(4)
        ]

        # Beyond the configured horizon: no instances.
        beyond = (end + datetime.timedelta(days=1)).isoformat()
        far = (end + datetime.timedelta(days=10)).isoformat()
        assert await QuestInstancesDao(database).list_by_date_range(
            child.id, beyond, far
        ) == []
    finally:
        await database.close()


def _freeze_nestquest_clock(
    monkeypatch, instant: datetime.datetime
) -> None:
    """Freeze the integration's ``datetime`` clock to a fixed aware instant.

    Only ``custom_components.nestquest``'s ``datetime`` binding is patched,
    so ``_run_horizon_materialization``'s ``datetime.datetime.now`` reads
    this instant (localized to ``hass.config.time_zone``) while the test
    harness and core keep the real clock.  Mirrors the helper in
    test_timezones.py.
    """
    import custom_components.nestquest as nestquest

    frozen = instant.astimezone(datetime.timezone.utc)

    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    fake_module = SimpleNamespace(
        datetime=_FrozenDatetime,
        timedelta=datetime.timedelta,
        date=datetime.date,
    )
    monkeypatch.setattr(nestquest, "datetime", fake_module)


async def test_integration_path_threads_settings(
    hass, tmp_path, monkeypatch
) -> None:
    """The integration path threads ``settings`` through horizon_window + rollover.

    P2-3: ``_run_horizon_materialization`` now calls
    ``settings.horizon_window(today)`` (so the helper is real and shared,
    not recomputed inline), and ``_register_day_rollover_listener``
    registers at ``settings.day_rollover_hour_minute``.  This runs the
    INTEGRATION path with ``horizon_days=3`` and
    ``day_rollover_time='03:30'`` and asserts the resulting instance
    window matches [today, today+3] AND the registered hour/minute are 3/30
    — a test the requirement-level core-only check could not fail.
    """
    import custom_components.nestquest as nestquest
    from custom_components.nestquest.core.dao_children import ChildrenDao
    from custom_components.nestquest.core.dao_instances import (
        QuestInstancesDao,
    )
    from custom_components.nestquest.core.quest_definitions import (
        create_quest_definition,
    )
    from custom_components.nestquest.core.recurrence import (
        RuleType,
        ScheduleRule,
    )

    # Freeze the integration clock so "today" is deterministic (the
    # hass fixture's config.time_zone is UTC, so 2026-03-01 12:00 UTC
    # localizes to 2026-03-01).
    _freeze_nestquest_clock(
        monkeypatch, datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.timezone.utc)
    )

    database = await _prepare(tmp_path / "nq.db", hass.async_add_executor_job)
    try:
        settings = NestQuestSettings(horizon_days=3, day_rollover_time="03:30")
        today = datetime.date(2026, 3, 1)

        NOW = "2026-03-01T12:00:00+00:00"
        child = await ChildrenDao(database).create("Ada", NOW)
        await create_quest_definition(
            database,
            "Daily chore",
            ScheduleRule(
                rule_type=RuleType.DAILY, start_date=today.isoformat()
            ),
            [child.id],
            ["morning"],
        )

        # Integration path: the window comes from settings.horizon_window.
        await nestquest._run_horizon_materialization(hass, database, settings)

        end = today + datetime.timedelta(days=3)
        records = await QuestInstancesDao(database).list_by_date_range(
            child.id, today.isoformat(), end.isoformat()
        )
        dates = sorted({r.due_date for r in records})
        assert dates == [
            (today + datetime.timedelta(days=i)).isoformat()
            for i in range(4)
        ]
        beyond = (end + datetime.timedelta(days=1)).isoformat()
        far = (end + datetime.timedelta(days=10)).isoformat()
        assert await QuestInstancesDao(database).list_by_date_range(
            child.id, beyond, far
        ) == []

        # The rollover listener registers at the configured hour/minute.
        remove = nestquest._register_day_rollover_listener(
            hass, database, settings
        )
        try:
            reg = hass.time_change.registrations[-1]
            assert reg["hour"] == 3
            assert reg["minute"] == 30
        finally:
            remove()
    finally:
        await database.close()
