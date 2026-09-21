"""Re-export of :mod:`core.dao_presence` for the integration package.

The presence DAOs live in :mod:`core.dao_presence` (extracted in task
d0b691d8); this module re-exports them so existing
``from .dao_presence import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from core.dao_presence import *  # noqa: F401,F403
