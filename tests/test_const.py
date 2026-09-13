"""Tests for const.py of NestQuest."""
from __future__ import annotations

import ast
from datetime import datetime
import logging
from pathlib import Path

from custom_components.nestquest import const


def test_domain() -> None:
    """Verify DOMAIN is defined and equals 'nestquest'."""
    assert hasattr(const, "DOMAIN")
    assert const.DOMAIN == "nestquest"
    assert isinstance(const.DOMAIN, str)


def test_logger() -> None:
    """Verify LOGGER_NAME and LOGGER are defined with correct types and values."""
    assert hasattr(const, "LOGGER_NAME")
    assert const.LOGGER_NAME == "custom_components.nestquest"
    assert isinstance(const.LOGGER_NAME, str)

    assert hasattr(const, "LOGGER")
    assert isinstance(const.LOGGER, logging.Logger)
    assert const.LOGGER.name == "custom_components.nestquest"


def test_platforms() -> None:
    """Verify PLATFORMS is defined as an empty list."""
    assert hasattr(const, "PLATFORMS")
    assert isinstance(const.PLATFORMS, list)
    assert const.PLATFORMS == []


def test_sqlite_db_filename() -> None:
    """Verify SQLITE_DB_FILENAME is defined and equals 'nestquest.db'."""
    assert hasattr(const, "SQLITE_DB_FILENAME")
    assert const.SQLITE_DB_FILENAME == "nestquest.db"
    assert isinstance(const.SQLITE_DB_FILENAME, str)


def test_horizon_days_config() -> None:
    """Verify CONF_HORIZON_DAYS and DEFAULT_HORIZON_DAYS are valid."""
    assert hasattr(const, "CONF_HORIZON_DAYS")
    assert const.CONF_HORIZON_DAYS == "horizon_days"
    assert hasattr(const, "DEFAULT_HORIZON_DAYS")
    assert isinstance(const.DEFAULT_HORIZON_DAYS, int)
    assert const.DEFAULT_HORIZON_DAYS == 14
    assert const.DEFAULT_HORIZON_DAYS > 0


def test_day_rollover_time_config() -> None:
    """Verify CONF_DAY_ROLLOVER_TIME and DEFAULT_DAY_ROLLOVER_TIME are valid."""
    assert hasattr(const, "CONF_DAY_ROLLOVER_TIME")
    assert const.CONF_DAY_ROLLOVER_TIME == "day_rollover_time"
    assert hasattr(const, "DEFAULT_DAY_ROLLOVER_TIME")
    assert isinstance(const.DEFAULT_DAY_ROLLOVER_TIME, str)
    assert const.DEFAULT_DAY_ROLLOVER_TIME == "00:00"
    # Validate time format HH:MM
    parsed = datetime.strptime(const.DEFAULT_DAY_ROLLOVER_TIME, "%H:%M")
    assert parsed.hour == 0 and parsed.minute == 0


def test_panel_idle_timeout_config() -> None:
    """Verify CONF_PANEL_IDLE_TIMEOUT and DEFAULT_PANEL_IDLE_TIMEOUT are valid."""
    assert hasattr(const, "CONF_PANEL_IDLE_TIMEOUT")
    assert const.CONF_PANEL_IDLE_TIMEOUT == "panel_idle_timeout"
    assert hasattr(const, "DEFAULT_PANEL_IDLE_TIMEOUT")
    assert isinstance(const.DEFAULT_PANEL_IDLE_TIMEOUT, int)
    assert const.DEFAULT_PANEL_IDLE_TIMEOUT == 300
    assert const.DEFAULT_PANEL_IDLE_TIMEOUT > 0


def test_no_hardcoded_domain_or_db_filename_in_modules() -> None:
    """Ensure no module other than const.py hardcodes DOMAIN string or SQLITE_DB_FILENAME."""
    pkg_dir = Path(const.__file__).parent
    py_files = [f for f in pkg_dir.glob("*.py") if f.name != "const.py"]

    assert len(py_files) > 0, "No python modules found in package to check"

    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value != "nestquest.db", (
                    f"Found hard-coded database filename '{node.value}' in {py_file.name}:{node.lineno}"
                )
                if node.value == "nestquest":
                    raise AssertionError(
                        f"Found hard-coded domain string '{node.value}' in {py_file.name}:{node.lineno}"
                    )
