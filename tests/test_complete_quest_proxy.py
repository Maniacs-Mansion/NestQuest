"""The ``nestquest.complete_quest`` proxy to the API client (Feature 18).

The service is a thin proxy: a panel tap must reach the API's panel
complete route through the entry's ONE shared API client (the same
instance the coordinator polls and the SSE subscription reads), with
exactly the payload contract the panel cards send (``instance_id``,
``actor=panel``, ``actor_child_id``).  The service performs NO local
database completion and fires NO local bus event — the API service
emits the transition on its SSE stream and the integration's
subscription re-fires it (firing it locally too would double-fire) —
and it refreshes the coordinator after a successful call so the
sensors reflect the completion immediately.  Every failure (a typed
:class:`NestQuestApiError`, an unconfigured client, a non-panel
actor) surfaces as a :class:`HomeAssistantError`, token-free.

The scripted clients here stand in for the API service: recording and
failing ``complete_instance`` implementations, no network, no aiohttp.
"""
from __future__ import annotations

import datetime

import pytest
from homeassistant.exceptions import HomeAssistantError

from conftest import (
    LazyLocalSnapshotClient,
    set_coordinator_client,
    wire_entry_to_registry,
)

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.api_client import NestQuestApiError
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    CONF_PANEL_TOKEN,
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    SERVICE_COMPLETE_QUEST,
)
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

ADMIN_CTX = {"user_id": "admin-1"}


class _RecordingApiClient(LazyLocalSnapshotClient):
    """Snapshot-only stand-in that RECORDS completion calls.

    ``complete_instance`` deliberately performs NO database write: the
    API service is remote, and the assertions below must be able to
    prove the service handler itself completed nothing locally.
    """

    def __init__(self, hass, entry_id: str) -> None:
        super().__init__(hass, entry_id)
        self.complete_calls: list[tuple[int, int]] = []

    async def complete_instance(
        self, instance_id: int, actor_child_id: int
    ) -> dict:
        self.complete_calls.append((instance_id, actor_child_id))
        return {"status": "done"}


class _FailingApiClient(_RecordingApiClient):
    """A stand-in whose completion fails the way the client types it."""

    def __init__(self, hass, entry_id: str, error: NestQuestApiError) -> None:
        super().__init__(hass, entry_id)
        self._error = error

    async def complete_instance(
        self, instance_id: int, actor_child_id: int
    ) -> dict:
        self.complete_calls.append((instance_id, actor_child_id))
        raise self._error


async def _setup_seeded_entry(hass, make_entry, client):
    """Wire, script, and set up an entry with one child's daily quest."""
    entry = wire_entry_to_registry(
        make_entry(
            data={
                CONF_ADMIN_USER_IDS: [ADMIN_CTX["user_id"]],
                CONF_PANEL_TOKEN: "secret-panel-token",
            }
        ),
        hass.registry,
    )
    set_coordinator_client(entry, client)
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    from custom_components.nestquest.children import create_child

    child = await create_child(database, "Ada")
    today = datetime.date.today()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today.isoformat()}
        ),
        [child.id],
        ["morning"],
    )
    end = (today + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today.isoformat(), end, today=today)
    instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today.isoformat(), today.isoformat()
    )
    assert instances
    return entry, client, child, instances[0]


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
    client with the tapped child, completes NOTHING locally, fires NO
    local event, and refreshes the coordinator immediately."""
    entry, client, child, instance = await _setup_seeded_entry(
        hass, make_entry, _RecordingApiClient(hass, "test_entry")
    )
    assert entry.runtime_data.coordinator.api_client is client, (
        "the service must proxy through the entry's ONE shared client"
    )
    refreshes = _record_refreshes(entry)

    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instance.id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )

    assert client.complete_calls == [(instance.id, child.id)]
    # No local completion: the instance is still open in the local
    # database — only the API service writes (through its own client).
    from custom_components.nestquest.completion import instance_state

    assert (
        await instance_state(entry.runtime_data.database, instance.id)
        == "open"
    )
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
    includes the panel token — with nothing completed or fired
    locally, and no refresh for a mutation that never happened."""
    entry, client, child, instance = await _setup_seeded_entry(
        hass,
        make_entry,
        _FailingApiClient(hass, "test_entry", error),
    )
    refreshes = _record_refreshes(entry)

    with pytest.raises(HomeAssistantError, match=fragment) as excinfo:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
    # The typed error is chained, and the service error carries the
    # typed message only — never the panel token.
    assert excinfo.value.__cause__ is error
    assert "secret-panel-token" not in str(excinfo.value)
    assert client.complete_calls == [(instance.id, child.id)]
    from custom_components.nestquest.completion import instance_state

    assert (
        await instance_state(entry.runtime_data.database, instance.id)
        == "open"
    )
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

    entry, _client, child, instance = await _setup_seeded_entry(
        hass, make_entry, _UnconfiguredApiClient()
    )

    with pytest.raises(
        HomeAssistantError, match="NestQuest API is not configured"
    ):
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )


async def test_non_panel_actor_is_rejected_before_the_client(
    hass, make_entry
) -> None:
    """The API's panel route completes as the tapped child only: a
    user-actor call fails fast with a clear error and never reaches
    the client."""
    entry, client, child, instance = await _setup_seeded_entry(
        hass, make_entry, _RecordingApiClient(hass, "test_entry")
    )

    with pytest.raises(HomeAssistantError, match="actor must be 'panel'"):
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "user",
                "actor_user_id": ADMIN_CTX["user_id"],
            },
            context=ADMIN_CTX,
        )
    assert client.complete_calls == []
