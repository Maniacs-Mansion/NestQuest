"""The ``nestquest.complete_quest`` proxy to the API client (Feature 18).

The service is a thin proxy: a panel tap must reach the API's panel
complete route through the entry's ONE shared API client (the same
instance the coordinator polls and the SSE subscription reads), with
exactly the payload contract the panel cards send (``instance_id``,
``actor=panel``, ``actor_child_id``).  The service performs NO local
completion and fires NO local bus event — the API service emits the
transition on its SSE stream and the integration's subscription
re-fires it (firing it locally too would double-fire) — and it
refreshes the coordinator after a successful call so the sensors
reflect the completion immediately.  Every failure (a typed
:class:`NestQuestApiError`, an unconfigured client, a non-panel actor)
surfaces as a :class:`HomeAssistantError`, token-free.

The scripted clients here stand in for the API service: recording and
failing ``complete_instance`` implementations, no network, no aiohttp.
"""
from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from conftest import ScriptedPanelClient, set_coordinator_client, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.api_client import NestQuestApiError
from custom_components.nestquest.const import (
    CONF_PANEL_TOKEN,
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    SERVICE_COMPLETE_QUEST,
)


class _RecordingApiClient(ScriptedPanelClient):
    """Snapshot-only stand-in that RECORDS completion calls.

    ``complete_instance`` deliberately performs NO local write: the
    API service is remote, and the assertions below must be able to
    prove the service handler itself completed nothing locally.
    """


class _FailingApiClient(_RecordingApiClient):
    """A stand-in whose completion fails the way the client types it."""

    def __init__(self, error: NestQuestApiError, *outcomes) -> None:
        super().__init__(*outcomes)
        self.fail_complete_with = error


def _empty_snapshot() -> dict:
    return {
        "today_iso": "2026-09-23",
        "cycle_day": 0,
        "children": [],
    }


async def _setup_entry(hass, make_entry, client):
    """Wire, script, and set up an entry against the scripted client."""
    entry = wire_entry_to_registry(
        make_entry(data={CONF_PANEL_TOKEN: "secret-panel-token"}),
        hass.registry,
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    return entry


def _record_refreshes(entry) -> list[bool]:
    """Replace the coordinator's refresh with a recording stand-in."""
    refreshes: list[bool] = []

    async def _fake_refresh():
        refreshes.append(True)

    entry.runtime_data.coordinator.async_refresh = _fake_refresh
    return refreshes


async def test_complete_quest_reaches_the_shared_api_client(
    hass, make_entry
) -> None:
    """A panel tap calls ``complete_instance`` on the entry's shared
    client with the tapped child, fires NO local event, and refreshes
    the coordinator immediately."""
    client = _RecordingApiClient(_empty_snapshot())
    entry = await _setup_entry(hass, make_entry, client)
    assert entry.runtime_data.coordinator.api_client is client, (
        "the service must proxy through the entry's ONE shared client"
    )
    refreshes = _record_refreshes(entry)

    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": 7,
            "actor": "panel",
            "actor_child_id": 1,
        },
    )

    assert client.complete_calls == [(7, 1)]
    # No local firing: the completed (and day-complete) events arrive
    # over the SSE stream, re-fired by the subscription — never from
    # this handler.
    assert hass.bus.fired(EVENT_QUEST_COMPLETED) == []
    assert hass.bus.fired(EVENT_CHILD_DAY_COMPLETE) == []
    # The old immediate-update behaviour: the sensors' coordinator
    # refresh runs before the service call returns.
    assert refreshes == [True]


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (
            NestQuestApiError(
                "NestQuest API POST /api/v1/panel/instances/7/complete "
                "failed with HTTP 401",
                status=401,
            ),
            "failed with HTTP 401",
        ),
        (
            NestQuestApiError(
                "NestQuest API POST /api/v1/panel/instances/7/complete "
                "transport failure: connection refused",
                status=None,
            ),
            "transport failure",
        ),
    ],
)
async def test_api_failure_surfaces_as_a_service_error(
    hass, make_entry, error, fragment
) -> None:
    """A typed API failure (non-2xx or transport) raises
    ``HomeAssistantError`` carrying the typed message — which never
    includes the panel token — with nothing fired locally, and no
    refresh for a mutation that never happened."""
    client = _FailingApiClient(error, _empty_snapshot())
    entry = await _setup_entry(hass, make_entry, client)
    refreshes = _record_refreshes(entry)

    with pytest.raises(HomeAssistantError, match=fragment) as excinfo:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": 7,
                "actor": "panel",
                "actor_child_id": 1,
            },
        )
    # The typed error is chained, and the service error carries the
    # typed message only — never the panel token.
    assert excinfo.value.__cause__ is error
    assert "secret-panel-token" not in str(excinfo.value)
    assert client.complete_calls == [(7, 1)]
    assert hass.bus.fired(EVENT_QUEST_COMPLETED) == []
    assert hass.bus.fired(EVENT_CHILD_DAY_COMPLETE) == []
    assert refreshes == []


async def test_unconfigured_api_client_surfaces_as_a_service_error(
    hass, make_entry
) -> None:
    """An entry with no completion surface (the unconfigured-token
    stub the coordinator swaps in) fails the service clearly instead
    of reaching an attribute error."""
    from custom_components.nestquest.coordinator import _UnconfiguredApiClient

    await _setup_entry(hass, make_entry, _UnconfiguredApiClient())

    with pytest.raises(
        HomeAssistantError, match="NestQuest API is not configured"
    ):
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": 7,
                "actor": "panel",
                "actor_child_id": 1,
            },
        )


async def test_non_panel_actor_is_rejected_before_the_client(
    hass, make_entry
) -> None:
    """The API's panel route completes as the tapped child only: a
    user-actor call fails fast with a clear error and never reaches
    the client."""
    client = _RecordingApiClient(_empty_snapshot())
    await _setup_entry(hass, make_entry, client)

    with pytest.raises(HomeAssistantError, match="actor must be 'panel'"):
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": 7,
                "actor": "user",
                "actor_user_id": "admin-1",
            },
            context={"user_id": "admin-1"},
        )
    assert client.complete_calls == []
