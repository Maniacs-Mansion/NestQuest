"""Tests for the Feature 09 permission gate's audit logging."""
from __future__ import annotations

import logging
import re

import pytest
from homeassistant.exceptions import Unauthorized

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    DOMAIN,
    SERVICE_MANAGE_CHILD,
)

ADMIN_ID = "admin-1"
ADMIN_CTX = {"user_id": ADMIN_ID}
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


async def _set_up(hass, make_entry):
    entry = wire_entry_to_registry(
        make_entry(data={CONF_ADMIN_USER_IDS: [ADMIN_ID]}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    return entry


async def test_denied_call_logs_warning_with_fields(
    hass, make_entry, caplog
) -> None:
    entry = await _set_up(hass, make_entry)
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN,
            SERVICE_MANAGE_CHILD,
            {"action": "create", "display_name": "Ada"},
            context={"user_id": "kiosk-panel"},
        )
    denials = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "denied" in record.getMessage()
    ]
    assert len(denials) == 1
    message = denials[0].getMessage()
    assert SERVICE_MANAGE_CHILD in message
    assert "kiosk-panel" in message
    assert _TIMESTAMP.search(message), message


async def test_denied_no_context_logs_user_none(
    hass, make_entry, caplog
) -> None:
    entry = await _set_up(hass, make_entry)
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN,
            SERVICE_MANAGE_CHILD,
            {"action": "create", "display_name": "Ada"},
        )
    denials = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "denied" in record.getMessage()
    ]
    assert len(denials) == 1
    message = denials[0].getMessage()
    assert "none" in message
    assert _TIMESTAMP.search(message), message


async def test_successful_admin_call_logs_debug_with_fields(
    hass, make_entry, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="custom_components.nestquest")
    entry = await _set_up(hass, make_entry)
    await hass.services.call(
        DOMAIN,
        SERVICE_MANAGE_CHILD,
        {"action": "create", "display_name": "Ada"},
        context=ADMIN_CTX,
    )
    allowed = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "allowed" in record.getMessage()
    ]
    assert len(allowed) == 1
    message = allowed[0].getMessage()
    assert SERVICE_MANAGE_CHILD in message
    assert ADMIN_ID in message
    assert _TIMESTAMP.search(message), message


async def test_denied_log_carries_no_personal_data_beyond_user_id(
    hass, make_entry, caplog
) -> None:
    """The log line names the caller's user id only: the payload's
    display name must not leak into the audit trail."""
    entry = await _set_up(hass, make_entry)
    with pytest.raises(Unauthorized):
        await hass.services.call(
            DOMAIN,
            SERVICE_MANAGE_CHILD,
            {"action": "create", "display_name": "Ada"},
            context={"user_id": "kiosk-panel"},
        )
    denials = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "denied" in record.getMessage()
    ]
    assert denials, "expected a denial log line"
    assert "Ada" not in denials[0]
    assert "display_name" not in denials[0]