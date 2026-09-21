"""Re-export of :mod:`core.dao_meta` for the integration package.

The meta-state DAO lives in :mod:`core.dao_meta` (extracted in task
d0b691d8); this module re-exports it so existing
``from .dao_meta import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.dao_meta import *  # noqa: F401,F403
