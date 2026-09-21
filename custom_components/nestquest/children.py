"""Re-export of :mod:`custom_components.nestquest.core.children` for the integration package.

The children registry business layer lives in
:mod:`custom_components.nestquest.core.children` (extracted in
task 510c1f78); this module re-exports it so existing
``from .children import ...`` references inside the integration keep
working.
"""
from __future__ import annotations

from .core.children import *  # noqa: F401,F403
