"""Tests for the Feature 09 admin-only versus open service registry."""
from __future__ import annotations

from custom_components.nestquest.const import (
    DOMAIN_SERVICES,
    SERVICE_COMPLETE_QUEST,
)
from custom_components.nestquest.service_policy import (
    ADMIN_ONLY,
    OPEN,
    SERVICE_POLICY,
)


def test_policy_covers_exactly_the_registered_services() -> None:
    assert frozenset(SERVICE_POLICY) == frozenset(DOMAIN_SERVICES)


def test_only_complete_quest_is_open() -> None:
    open_services = {
        name for name, access in SERVICE_POLICY.items() if access == OPEN
    }
    assert open_services == {SERVICE_COMPLETE_QUEST}
    assert all(
        access == ADMIN_ONLY
        for name, access in SERVICE_POLICY.items()
        if name != SERVICE_COMPLETE_QUEST
    )


def test_policy_values_are_only_open_or_admin_only() -> None:
    assert set(SERVICE_POLICY.values()) <= {OPEN, ADMIN_ONLY}
