"""Re-export of :mod:`core.migrations` for the integration package.

The versioned migration runner lives in :mod:`core.migrations`
(extracted in task d0b691d8); this module re-exports it so existing
``from .migrations import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from core.migrations import *  # noqa: F401,F403
