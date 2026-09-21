"""Re-export of :mod:`custom_components.nestquest.core.materialize` for the integration package.

The materialization walk lives in
:mod:`custom_components.nestquest.core.materialize` (extracted in
task 510c1f78); this module re-exports it so existing
``from .materialize import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.materialize import *  # noqa: F401,F403
