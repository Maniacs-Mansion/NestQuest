"""Tests for store.py of NestQuest."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from custom_components.nestquest import store
from custom_components.nestquest.const import SQLITE_DB_FILENAME


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass(config_dir: Path, execute: bool = True):
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(config_dir / SQLITE_DB_FILENAME))
    hass.async_add_executor_job = AsyncMock(
        side_effect=(lambda fn, *a: fn(*a)) if execute else None
    )
    return hass


def test_returns_absolute_path_from_config_path() -> None:
    hass = _make_hass(Path("/config"), execute=False)
    db_path = _run(store.async_get_db_path(hass))
    hass.config.path.assert_called_once_with(SQLITE_DB_FILENAME)
    assert db_path == Path("/config") / SQLITE_DB_FILENAME
    assert db_path.is_absolute()


def test_relative_config_path_is_normalized_to_absolute(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    hass = MagicMock()
    hass.config.path = MagicMock(return_value="relative-config/" + SQLITE_DB_FILENAME)
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    db_path = _run(store.async_get_db_path(hass))
    assert db_path.is_absolute()
    assert db_path.name == SQLITE_DB_FILENAME
    assert str(db_path).endswith("relative-config/" + SQLITE_DB_FILENAME)
    assert db_path.parent.is_dir()
    assert (tmp_path / "relative-config").is_dir()
    assert not db_path.exists()


def test_creates_missing_parent_directory(tmp_path) -> None:
    nested = tmp_path / "homeassistant" / "config"
    hass = _make_hass(nested)
    db_path = _run(store.async_get_db_path(hass))
    assert db_path.parent == nested
    assert nested.is_dir()
    assert db_path.parent.is_dir()
    assert not db_path.exists()


def test_two_calls_return_same_path(tmp_path) -> None:
    hass = _make_hass(tmp_path)
    first = _run(store.async_get_db_path(hass))
    second = _run(store.async_get_db_path(hass))
    assert first == second
    assert first.parent.is_dir()
    assert not first.exists()
    assert not second.exists()


def test_existing_directory_does_not_fail(tmp_path) -> None:
    nested = tmp_path / "config"
    nested.mkdir()
    hass = _make_hass(nested)
    db_path = _run(store.async_get_db_path(hass))
    assert db_path == nested / SQLITE_DB_FILENAME
    assert db_path.parent.is_dir()
    assert not db_path.exists()


def test_mkdir_runs_via_executor(tmp_path) -> None:
    nested = tmp_path / "deep" / "nested"
    hass = _make_hass(nested)
    db_path = _run(store.async_get_db_path(hass))
    assert nested.is_dir()
    hass.async_add_executor_job.assert_called_once()
    args, kwargs = hass.async_add_executor_job.call_args
    fn, fn_args = args[0], args[1:]
    assert callable(fn)
    assert fn is store._ensure_dir
    assert fn_args == (nested,)
    assert kwargs == {}
    assert db_path.parent == nested
    assert db_path.parent.is_dir()
    assert not db_path.exists()


def test_executor_helper_creates_directory(tmp_path) -> None:
    nested = tmp_path / "executor" / "made"
    store._ensure_dir(nested)
    assert nested.is_dir()
    store._ensure_dir(nested)
    assert nested.is_dir()


def test_no_sqlite3_import_outside_db_module() -> None:
    """sqlite3 is banned package-wide except two justified modules.

    db.py is the connection wrapper (all statement execution lives
    there).  __init__.py imports sqlite3 ONLY for its exception types
    to classify corruption on startup (done-condition: corrupt file ->
    ConfigEntryNotReady); it never opens a connection or executes
    SQL — that is asserted separately below.
    """
    pkg_dir = Path(store.__file__).parent
    py_files = list(pkg_dir.glob("*.py"))
    assert py_files
    allowed = {"db.py", "__init__.py"}
    for py_file in py_files:
        if py_file.name in allowed:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "sqlite3", (
                        f"Found sqlite3 import in {py_file.name}:{node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
                raise AssertionError(
                    f"Found sqlite3 import in {py_file.name}:{node.lineno}"
                )


def test_init_module_never_opens_or_executes_sqlite() -> None:
    """The __init__.py sqlite3 usage is limited to (a) exception typing
    for corruption classification and (b) the ONE read-only preflight
    connection (mode=ro URI, SELECT-only) that detects corruption in an
    existing file before the real read-write open.  No read-write
    connect, no cursor writes, no non-SELECT statements may appear.
    """
    import re
    from pathlib import Path

    init_path = (
        Path(store.__file__).parent / "__init__.py"
    ).read_text(encoding="utf-8")
    # The preflight connect must be the URI read-only form, and only
    # SELECT statements and the integrity_check PRAGMA may run there.
    assert "sqlite3.connect(uri, uri=True)" in init_path
    assert "?mode=ro" in init_path
    assert 'PRAGMA integrity_check' in init_path
    forbidden = re.compile(
        r"sqlite3\s*\.\s*connect(?!\(\s*uri\s*,)"
        r"|\bconn(ection)?\s*\.\s*execute\s*\(\s*[\"'](?!SELECT\s|PRAGMA\s+integrity_check)"
        r"|\bexecutemany\b|\bexecutescript\b",
        re.IGNORECASE,
    )
    assert forbidden.search(init_path) is None, (
        "__init__.py may use sqlite3 only for exception typing and the "
        "read-only corruption preflight (SELECT + integrity_check)"
    )


def test_no_file_creation_calls_in_store() -> None:
    source = Path(store.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(store.__file__))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                raise AssertionError(
                    f"Found open() call in store.py:{node.lineno}"
                )
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "touch"
            ):
                raise AssertionError(
                    f"Found touch() call in store.py:{node.lineno}"
                )
    assert "touch(" not in source
    assert "open(" not in source


def test_container_style_path_resolves() -> None:
    hass = _make_hass(Path("/config"), execute=False)
    assert _run(store.async_get_db_path(hass)) == Path("/config") / SQLITE_DB_FILENAME


def test_core_style_path_resolves(tmp_path) -> None:
    config_dir = tmp_path / ".homeassistant"
    hass = _make_hass(config_dir)
    assert _run(store.async_get_db_path(hass)) == config_dir / SQLITE_DB_FILENAME
    assert (config_dir / SQLITE_DB_FILENAME).parent.is_dir()