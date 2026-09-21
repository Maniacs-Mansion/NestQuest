"""Invariant: the bundled core package is self-contained.

Every module under ``custom_components/nestquest/core/`` must be free of
Home Assistant and must not climb out of the core package: no
``homeassistant`` import, no relative import with level > 1, no absolute
import of ``custom_components.nestquest.<something other than core>``,
and no bare ``import core`` / ``from core``.  This guards the
storage-layer extraction (task d0b691d8) from regressing into a
HA-coupled or integration-coupled bundle.
"""
from __future__ import annotations

import ast
from pathlib import Path

CORE_PKG = Path(
    __import__(
        "custom_components.nestquest.core", fromlist=["__file__"]
    ).__file__
).parent


def _module_chain(base: str, name: str) -> str:
    """Combined dotted path for ``from <base> import <name>``."""
    return f"{base}.{name}" if base else name


def _is_homeassistant(module: str) -> bool:
    return module == "homeassistant" or module.startswith("homeassistant.")


def _climbs_out_of_core(module: str) -> bool:
    """An absolute path that reaches the integration package but not core."""
    if module == "custom_components.nestquest":
        return True
    if module.startswith("custom_components.nestquest."):
        rest = module[len("custom_components.nestquest."):]
        head = rest.split(".", 1)[0]
        return head != "core"
    return False


def _is_bare_core(module: str) -> bool:
    """A bare ``core`` / ``core.*`` absolute reference (not the bundle)."""
    return module == "core" or module.startswith("core.")


def _scan(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if _is_homeassistant(mod):
                    offenders.append(
                        f"{path.name}:{node.lineno} homeassistant import: import {mod}"
                    )
                if _is_bare_core(mod):
                    offenders.append(
                        f"{path.name}:{node.lineno} bare core import: import {mod}"
                    )
                if _climbs_out_of_core(mod):
                    offenders.append(
                        f"{path.name}:{node.lineno} climbs out of core: import {mod}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 1:
                offenders.append(
                    f"{path.name}:{node.lineno} relative import climbs out "
                    f"of core (level {node.level})"
                )
                continue
            if node.level:
                # relative level 1 stays inside core; nothing to check.
                continue
            base = node.module or ""
            if _is_homeassistant(base):
                offenders.append(
                    f"{path.name}:{node.lineno} homeassistant import: from {base}"
                )
            if _is_bare_core(base):
                offenders.append(
                    f"{path.name}:{node.lineno} bare core import: from {base}"
                )
            if _climbs_out_of_core(base):
                offenders.append(
                    f"{path.name}:{node.lineno} climbs out of core: from {base}"
                )
            for alias in node.names:
                combined = _module_chain(base, alias.name)
                if _is_homeassistant(combined):
                    offenders.append(
                        f"{path.name}:{node.lineno} homeassistant import: "
                        f"from {base} import {alias.name}"
                    )
                if _is_bare_core(combined):
                    offenders.append(
                        f"{path.name}:{node.lineno} bare core import: "
                        f"from {base} import {alias.name}"
                    )
                if _climbs_out_of_core(combined):
                    offenders.append(
                        f"{path.name}:{node.lineno} climbs out of core: "
                        f"from {base} import {alias.name}"
                    )
    return offenders


def test_core_package_is_self_contained() -> None:
    """No core module imports homeassistant or climbs out of the core package."""
    py_files = sorted(CORE_PKG.rglob("*.py"))
    assert py_files, "core package not found under custom_components/nestquest/core"
    all_offenders: list[str] = []
    for py_file in py_files:
        all_offenders.extend(_scan(py_file))
    assert all_offenders == [], (
        "core package isolation violated:\n" + "\n".join(all_offenders)
    )
