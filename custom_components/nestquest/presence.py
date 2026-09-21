"""Re-export of :mod:`custom_components.nestquest.core.presence` for the integration package.

The presence and custody model lives in
:mod:`custom_components.nestquest.core.presence` (extracted in
task 510c1f78); this module re-exports it so existing
``from .presence import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.presence import *  # noqa: F401,F403
