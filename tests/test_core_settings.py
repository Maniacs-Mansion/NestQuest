"""Tests for core/settings.py: the explicit, HA-free settings object.

Covers three contracts from task 4dd8f870:

- ``NestQuestSettings.from_options`` applies defaults when keys are
  absent and rejects invalid horizon/rollover values.
- An AST scan asserts no module under
  ``custom_components/nestquest/core/`` imports ``homeassistant``,
  accesses a ``hass.config`` / config-entry attribute, or reads
  config-entry options.  (Docstring mentions are allowed.)
- A settings object constructed with NON-default ``horizon_days`` and
  ``day_rollover_time`` drives a materialization whose resulting window
  matches the non-default horizon.
"""
from __future__ import annotations

import ast
import datetime
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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


def test_horizon_window_default_today() -> None:
    """horizon_window returns [today, today + horizon_days] when today is omitted."""
    s = NestQuestSettings(horizon_days=7)
    start, end = s.horizon_window()
    today = datetime.date.today()
    assert start == today
    assert end == today + datetime.timedelta(days=7)


def test_horizon_window_pinned_today() -> None:
    """A pinned today is honored so the window is deterministic."""
    s = NestQuestSettings(horizon_days=5)
    pinned = datetime.date(2026, 3, 1)
    start, end = s.horizon_window(pinned)
    assert start == pinned
    assert end == pinned + datetime.timedelta(days=5)


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


def _attribute_chain(node: ast.Attribute) -> list[str]:
    """Flatten an attribute access chain into dotted-name parts (leaf first)."""
    parts: list[str] = [node.attr]
    cur: ast.expr = node.value
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return parts


def _dotted_attr(node: ast.Attribute) -> str:
    """Return the dotted name of an attribute chain, root first."""
    return ".".join(reversed(_attribute_chain(node)))


def _scan_module_for_ha_config(path: Path) -> list[str]:
    """Return a list of offender strings for HA-coupling in ``path``.

    Flags:
    - any ``import homeassistant`` / ``from homeassistant ...``;
    - any attribute access whose chain reaches ``hass.config`` or any
      ``.options``/``.data`` access on a name literally named ``entry``
      (a config-entry attribute read), EXCEPT inside a docstring-only
      module (no runtime access) — but since AST only sees code, not
      docstrings, docstring mentions are structurally exempt.
    - any call to ``.options.get(...)`` / ``.data.get(...)`` on a name
      literally named ``entry`` (a config-entry options/data read).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_homeassistant(alias.name):
                    offenders.append(
                        f"{path.name}:{node.lineno} homeassistant import: "
                        f"import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if _is_homeassistant(base):
                offenders.append(
                    f"{path.name}:{node.lineno} homeassistant import: from {base}"
                )
            for alias in node.names:
                combined = (
                    f"{base}.{alias.name}" if base else alias.name
                )
                if _is_homeassistant(combined):
                    offenders.append(
                        f"{path.name}:{node.lineno} homeassistant import: "
                        f"from {base} import {alias.name}"
                    )
        elif isinstance(node, ast.Attribute):
            dotted = _dotted_attr(node)
            # hass.config.<anything> — a HA config read.
            if dotted == "hass.config" or dotted.startswith("hass.config."):
                offenders.append(
                    f"{path.name}:{node.lineno} hass.config access: {dotted}"
                )
            # entry.options / entry.data — a config-entry attribute read.
            # Only flag the leaf attribute itself (not every sub-expression),
            # and only when the root name is literally 'entry'.
            root = _attribute_chain(node)[-1]
            if root == "entry" and node.attr in {"options", "data"}:
                offenders.append(
                    f"{path.name}:{node.lineno} config-entry attribute read: "
                    f"{dotted}"
                )

    return offenders


def test_core_modules_have_no_ha_config_reads() -> None:
    """No core module imports homeassistant or reads HA config / entry options.

    Docstring mentions are allowed: AST only sees code, and the offenders
    this scan flags (imports, attribute accesses) never appear in a
    docstring.  The existing docstring references to ``hass.config`` in
    ``core/events.py`` and ``core/store.py`` therefore pass.
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


def test_settings_module_lives_under_core() -> None:
    """settings.py is part of the core package (not the integration root)."""
    assert (CORE_PKG / "settings.py").is_file()
    # And it is importable as a core submodule.
    import custom_components.nestquest.core.settings as mod

    assert hasattr(mod, "NestQuestSettings")
    assert inspect.isclass(mod.NestQuestSettings)


def test_settings_module_has_no_ha_imports() -> None:
    """settings.py specifically carries no homeassistant import."""
    offenders = _scan_module_for_ha_config(CORE_PKG / "settings.py")
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# Materialization over a non-default horizon.
# ---------------------------------------------------------------------------


def _make_hass_mock():
    from unittest.mock import AsyncMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(
        side_effect=(lambda fn, *a, **k: fn(*a, **k))
    )
    return hass


async def _prepare(path):
    from custom_components.nestquest.core.db import NestQuestDatabase
    from custom_components.nestquest.core.migrations import apply_migrations

    database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
    await database.open(path)
    await apply_migrations(database)
    return database


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def test_materialize_over_non_default_horizon(tmp_path) -> None:
    """A settings object with a non-default horizon drives the matching window.

    Constructs NestQuestSettings with horizon_days=3 and day_rollover_time
    '03:30' (both non-default), builds the window via horizon_window, and
    drives materialize over it; asserts the resulting instance rows land
    exactly on the [today, today+3] window and NOT beyond it.
    """
    import asyncio

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

    async def _main():
        database = await _prepare(tmp_path / "nq.db")
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

    asyncio.new_event_loop().run_until_complete(_main())
