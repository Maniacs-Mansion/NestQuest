"""Explicit admin-only versus open service registry (Feature 09).

One mapping, one file: every registered ``nestquest`` service name is
either ``open`` or ``admin_only``.  The permission decorator (later
Feature 09 tasks) reads this table; it does not take per-handler
policy arguments.
"""
from __future__ import annotations

from .const import (
    DOMAIN_SERVICES,
    SERVICE_COMPLETE_QUEST,
    SERVICE_CREATE_PRESENCE_OVERRIDE,
    SERVICE_CREATE_QUEST_DEFINITION,
    SERVICE_DELETE_PRESENCE_OVERRIDE,
    SERVICE_EXPORT_HISTORY_CSV,
    SERVICE_MANAGE_CHILD,
    SERVICE_REGENERATE,
    SERVICE_SET_PRESENCE_PATTERN,
    SERVICE_SET_QUEST_DEFINITION_ACTIVE,
    SERVICE_UNCOMPLETE_QUEST,
    SERVICE_UPDATE_QUEST_DEFINITION,
)

OPEN = "open"
ADMIN_ONLY = "admin_only"

SERVICE_POLICY: dict[str, str] = {
    SERVICE_COMPLETE_QUEST: OPEN,
    SERVICE_UNCOMPLETE_QUEST: ADMIN_ONLY,
    SERVICE_CREATE_QUEST_DEFINITION: ADMIN_ONLY,
    SERVICE_UPDATE_QUEST_DEFINITION: ADMIN_ONLY,
    SERVICE_SET_QUEST_DEFINITION_ACTIVE: ADMIN_ONLY,
    SERVICE_SET_PRESENCE_PATTERN: ADMIN_ONLY,
    SERVICE_CREATE_PRESENCE_OVERRIDE: ADMIN_ONLY,
    SERVICE_DELETE_PRESENCE_OVERRIDE: ADMIN_ONLY,
    SERVICE_EXPORT_HISTORY_CSV: ADMIN_ONLY,
    SERVICE_MANAGE_CHILD: ADMIN_ONLY,
    SERVICE_REGENERATE: ADMIN_ONLY,
}

if frozenset(SERVICE_POLICY) != frozenset(DOMAIN_SERVICES):
    raise RuntimeError(
        "SERVICE_POLICY must name exactly the registered nestquest services, "
        f"got {sorted(SERVICE_POLICY)} vs {list(DOMAIN_SERVICES)}"
    )
