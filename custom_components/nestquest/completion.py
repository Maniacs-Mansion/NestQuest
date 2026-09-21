"""Re-export of :mod:`custom_components.nestquest.core.completion` for the integration package.

The completion business layer lives in
:mod:`custom_components.nestquest.core.completion` (extracted in
task 510c1f78); this module re-exports it so existing
``from .completion import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.completion import *  # noqa: F401,F403
