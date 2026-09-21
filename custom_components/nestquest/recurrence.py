"""Re-export of :mod:`core.recurrence` for the integration package.

The recurrence model lives in :mod:`core.recurrence` (extracted in task
d0b691d8); this module re-exports it so existing
``from .recurrence import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.recurrence import *  # noqa: F401,F403
from .core.recurrence import _month_end, _nth_weekday_of_month  # noqa: F401
