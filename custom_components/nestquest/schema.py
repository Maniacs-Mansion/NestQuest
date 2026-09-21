"""Re-export of :mod:`core.schema` for the integration package.

The declarative schema DDL lives in :mod:`core.schema` (extracted in
task d0b691d8); this module re-exports it so existing
``from .schema import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from core.schema import *  # noqa: F401,F403
