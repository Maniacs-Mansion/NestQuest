"""Re-export of :mod:`custom_components.nestquest.core.db` for the integration package.

The async SQLite wrapper lives in :mod:`custom_components.nestquest.core.db` (extracted in task
d0b691d8) and is Home-Assistant-free: :class:`NestQuestDatabase` takes
an executor callable rather than a ``hass`` object.  This module
re-exports it and provides :func:`make_database`, a thin adapter that
constructs a wrapper backed by ``hass.async_add_executor_job``, so the
integration constructs the database the same way it always did.
"""
from __future__ import annotations

from typing import Any, TypeVar

from homeassistant.core import HomeAssistant

from .core.db import ExecutionResult, NestQuestDatabase

__all__ = ["ExecutionResult", "NestQuestDatabase", "make_database"]

T = TypeVar("T")


def make_database(hass: HomeAssistant) -> NestQuestDatabase:
    """Construct a :class:`NestQuestDatabase` wired to ``hass``'s executor.

    Mirrors the pre-extraction ``NestQuestDatabase(hass)`` call: the
    wrapper's executor is ``hass.async_add_executor_job``, so every
    sqlite3 call runs on the HA executor thread and the event loop
    never blocks.
    """
    return NestQuestDatabase(hass.async_add_executor_job)
