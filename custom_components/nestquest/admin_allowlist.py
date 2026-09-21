"""Re-export of :mod:`custom_components.nestquest.core.admin_allowlist` for the integration package.

The admin allowlist business layer lives in
:mod:`custom_components.nestquest.core.admin_allowlist` (extracted in
task 510c1f78); this module re-exports it so existing
``from .admin_allowlist import ...`` references inside the integration
keep working.
"""
from __future__ import annotations

from .core.admin_allowlist import *  # noqa: F401,F403
