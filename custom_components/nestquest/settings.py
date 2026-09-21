"""Re-export of :mod:`custom_components.nestquest.core.settings` for the integration package.

The explicit, Home-Assistant-free settings object lives in
:mod:`custom_components.nestquest.core.settings` (introduced in task
4dd8f870); this module re-exports it so the integration constructs the
settings object from ``entry.options`` and threads it into the core
paths without core ever reading HA config itself.
"""
from __future__ import annotations

from .core.settings import NestQuestSettings

__all__ = ["NestQuestSettings"]
