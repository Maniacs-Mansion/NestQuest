"""Re-export of :mod:`core.dao_children` for the integration package.

The children/admin DAO lives in :mod:`core.dao_children` (extracted in
task d0b691d8); this module re-exports it so existing
``from .dao_children import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from core.dao_children import *  # noqa: F401,F403
from core.dao_children import _CONNECTION_LOCKS, _connection_lock  # noqa: F401
