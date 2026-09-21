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
relative (``from .db import ...``).  It can therefore be imported as a
top-level package if the integration directory is placed on
``sys.path``.  This module does exactly that, in ONE documented place,
so the coupling between the API and the bundled core is explicit and
testable rather than scattered across route handlers.

Usage::

    from api.nestquest_core import core_db, core_migrations
    # core_db.NestQuestDatabase, core_migrations.apply_migrations, ...

This is a TRANSITIONAL coupling.  Feature 18 (task 430f7f98) converts
the integration into a thin API client and moves ``core`` out of the
integration bundle; once that lands, this bootstrap helper goes away and
the API imports ``core`` as an ordinary installed dependency.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

#: The repository root (this file is ``<root>/api/nestquest_core.py``).
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent

#: The integration directory that contains the bundled ``core`` package.
#: Adding this to ``sys.path`` makes ``import core`` resolve to
#: ``custom_components/nestquest/core/`` WITHOUT executing the
#: integration's ``__init__.py`` (which would import ``homeassistant``).
_INTEGRATION_DIR: Path = _REPO_ROOT / "custom_components" / "nestquest"

_BOOTSTRAPPED = False


def bootstrap_core() -> None:
    """Make the bundled ``core`` package importable as a top-level package.

    Inserts the integration directory at the front of ``sys.path`` (once,
    idempotently).  After this call, ``import core`` resolves to the
    bundled ``custom_components/nestquest/core`` package, and its
    relative internal imports (``from .db import ...``) resolve against
    that same directory.  The integration's HA-coupled ``__init__.py`` is
    never executed: ``core`` is imported directly as a top-level package,
    so ``custom_components.nestquest`` is never touched.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    path = str(_INTEGRATION_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    _BOOTSTRAPPED = True


def _ensure_core() -> ModuleType:
    """Import ``core`` (bootstrapping first) and return the module object."""
    bootstrap_core()
    import core  # type: ignore[import-not-found]  # noqa: F401

    return core


#: The bundled core package, imported via the sys.path bootstrap.  Hold a
#: reference here so callers import the submodules through it
#: (``core.db``, ``core.migrations``) the same way the integration does.
core: ModuleType = _ensure_core()

#: Re-exported for convenience; route handlers import these names from
#: here rather than reaching into ``core`` directly.
core_db = __import__("core.db", fromlist=["db"])  # type: ignore[import-not-found]
core_migrations = __import__(  # type: ignore[import-not-found]
    "core.migrations", fromlist=["migrations"]
)

__all__ = ["bootstrap_core", "core", "core_db", "core_migrations"]
