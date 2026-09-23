"""Re-export of :mod:`custom_components.nestquest.core.presence_management` for the integration package.

The presence-write business layer lives in
:mod:`custom_components.nestquest.core.presence_management` (added for
task e4a9d31b); this module re-exports it so the integration's service
handlers call the ONE implementation the API admin plane shares.
"""
from __future__ import annotations

from .core.presence_management import *  # noqa: F401,F403
