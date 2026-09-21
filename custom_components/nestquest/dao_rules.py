"""Re-export of :mod:`core.dao_rules` for the integration package.

The schedule-rules/quest-definitions DAO lives in
:mod:`core.dao_rules` (extracted in task d0b691d8); this module
re-exports it so existing ``from .dao_rules import ...`` references
inside the integration keep working.
"""
from __future__ import annotations

from core.dao_rules import *  # noqa: F401,F403
from core.dao_rules import (  # noqa: F401
    _UNSET,
    _validate_date,
    _validate_time,
    _validate_window,
)
