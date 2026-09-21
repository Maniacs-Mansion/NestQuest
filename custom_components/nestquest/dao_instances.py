"""Re-export of :mod:`core.dao_instances` for the integration package.

The instances/completion-events DAO lives in :mod:`core.dao_instances`
(extracted in task d0b691d8); this module re-exports it so existing
``from .dao_instances import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.dao_instances import *  # noqa: F401,F403
from .core.dao_instances import _resolve_today  # noqa: F401
