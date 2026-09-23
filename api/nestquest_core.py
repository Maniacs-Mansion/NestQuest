"""Transitional coupling: import ``core`` without importing Home Assistant.

The NestQuest domain ``core`` package (Feature 15) is bundled INSIDE the
Home Assistant integration at ``custom_components/nestquest/core/``.
Importing it the obvious way — ``import custom_components.nestquest.core``
— would execute ``custom_components/nestquest/__init__.py``, which
imports ``homeassistant``.  Home Assistant is NOT installed in the API
service's runtime, so that import raises ``ModuleNotFoundError`` and the
API cannot start.

``core`` itself is a clean, Home-Assistant-free package: its
``__init__.py`` is a bare docstring and every internal import is
relative (``from .db import ...``).  It can therefore be imported by
file location as a standalone package.

This module loads ``core`` with :func:`importlib.util.spec_from_file_location`
— registering it under the distinct top-level name ``nestquest_core``
with ``submodule_search_locations`` set to the bundled ``core``
directory — so its relative imports resolve against that directory
without touching ``sys.path``.  No generic top-level name (``db``,
``const``, ``schema``, ...) is published, so nothing here can silently
shadow a future dependency, and the integration's HA-coupled
``__init__.py`` is never executed: ``custom_components.nestquest`` is
never imported.

Usage::

    from api.nestquest_core import core_db, core_migrations
    # core_db.NestQuestDatabase, core_migrations.apply_migrations, ...

This is a TRANSITIONAL coupling.  Feature 18 (task 430f7f98) converts
the integration into a thin API client and moves ``core`` out of the
integration bundle; once that lands, this bootstrap helper goes away and
the API imports ``core`` as an ordinary installed dependency.

NOTE on the pytest process: the suite's ``conftest.py`` stubs the
parent integration package and imports ``custom_components.nestquest.core.*``
BEFORE any API test runs, so two copies of the core package coexist in
the pytest process — the one registered here as ``nestquest_core.*``
(loaded by file location) and the conftest-stubbed
``custom_components.nestquest.core.*``.  Later tasks must NOT compare
class or exception identity across these two copies: a
``nestquest_core.db.NestQuestDatabase`` is a DIFFERENT class object from
``custom_components.nestquest.core.db.NestQuestDatabase`` even though
they share source.  Operate on a single copy within any one code path.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

#: The repository root (this file is ``<root>/api/nestquest_core.py``).
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent

#: The bundled ``core`` package directory, inside the HA integration.
_CORE_DIR: Path = _REPO_ROOT / "custom_components" / "nestquest" / "core"

#: The ``core`` package's ``__init__.py`` — a bare docstring, so loading
#: it by file location executes no imports of its own.
_CORE_INIT: Path = _CORE_DIR / "__init__.py"

#: The distinct top-level name under which the bundled ``core`` package
#: is registered in ``sys.modules``.  A distinctive name (rather than the
#: generic ``core``) avoids publishing shadow-able top-level names and
#: keeps the bundled copy separate from the conftest-stubbed
#: ``custom_components.nestquest.core`` present in the pytest process.
_CORE_MODULE_NAME = "nestquest_core"


def _load_core() -> ModuleType:
    """Load the bundled ``core`` package by file location and return it.

    Registers the package under :data:`_CORE_MODULE_NAME` in
    ``sys.modules`` with ``submodule_search_locations`` pointing at the
    bundled directory, so its relative imports (``from .db import ...``)
    resolve to ``nestquest_core.<submodule>`` against that directory
    without mutating ``sys.path``.  Idempotent: a second call returns
    the already-registered module.
    """
    existing = sys.modules.get(_CORE_MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        _CORE_MODULE_NAME,
        _CORE_INIT,
        submodule_search_locations=[str(_CORE_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load core from {_CORE_INIT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_CORE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


#: The bundled core package, loaded by file location and registered as
#: ``nestquest_core`` in ``sys.modules``.  Held here so callers import the
#: submodules through it (``nestquest_core.db``, ``nestquest_core.migrations``)
#: the same relative way the integration does.
core: ModuleType = _load_core()

#: Re-exported for convenience; route handlers import these names from
#: here rather than reaching into the core package directly.
core_db = importlib.import_module(f"{_CORE_MODULE_NAME}.db")
core_migrations = importlib.import_module(f"{_CORE_MODULE_NAME}.migrations")

#: The panel snapshot builder and its payload shaper
#: (``core.snapshot.build_snapshot`` / ``instance_payload``) — the pure
#: assembly the panel routes call.
core_snapshot = importlib.import_module(f"{_CORE_MODULE_NAME}.snapshot")

#: The explicit settings object (``core.settings.NestQuestSettings``)
#: the snapshot builder's ``settings`` parameter takes.
core_settings = importlib.import_module(f"{_CORE_MODULE_NAME}.settings")

__all__ = [
    "core",
    "core_db",
    "core_migrations",
    "core_snapshot",
    "core_settings",
]
