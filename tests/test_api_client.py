"""Tests for the panel-plane API client (Feature 18).

The client is exercised against a STUB transport only — no network, no
aiohttp, no homeassistant: the injected session is a fake that speaks
the same ``request(...)`` surface aiohttp's ``ClientSession`` exposes
and records every call, so the tests assert exactly what the client
puts on the wire (method, URL, Bearer header, JSON body) and how every
failure mode (non-2xx, connection failure, timeout, malformed JSON)
surfaces as the typed :class:`NestQuestApiError`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from conftest import make_config_entry

from custom_components.nestquest import api_client
from custom_components.nestquest.api_client import (
    NestQuestApiClient,
    NestQuestApiError,
    is_valid_base_url,
    resolve_api_config,
)
from custom_components.nestquest.const import (
    CONF_API_BASE_URL,
    CONF_PANEL_TOKEN,
    DEFAULT_API_BASE_URL,
    DEFAULT_PANEL_TOKEN,
)

BASE_URL = "http://api.test:8000"
TOKEN = "test-panel-token"

#: A realistic panel snapshot payload (the documented shape of the
#: Feature 16 snapshot route).
SNAPSHOT_PAYLOAD = {
    "today_iso": "2026-09-23",
    "cycle_day": 2,
    "children": [
        {
            "child_id": 1,
            "child_name": "Ada",
            "present": False,
            "next_present": "2026-09-24",
            "due_today": 1,
            "completed_today": 0,
            "remaining_today": 1,
            "completion_pct": 0,
            "instances": [
                {
                    "id": 7,
                    "definition_id": 3,
                    "child_id": 1,
                    "title": "Pack bag",
                    "icon": None,
                    "window": "morning",
                    "due_time": "10:00",
                    "state": "open",
                    "overdue": True,
                    "completed_at": None,
                    "on_time": None,
                }
            ],
        }
    ],
}


class StubResponse:
    """A fake aiohttp response: ``status`` plus ``await text()``."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body


class _OutcomeContext:
    """Async context manager yielding one scripted outcome.

    Mirrors aiohttp's ``session.request(...)`` return value: entering
    the context performs the request, so a scripted transport error
    raises THERE — before any response object exists, exactly where
    aiohttp's connector raises on a refused connection.
    """

    def __init__(self, response, error) -> None:
        self._response = response
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class StubTransport:
    """A no-network stand-in for aiohttp's ``ClientSession``.

    Records every ``request(...)`` call as a dict (method, url, headers,
    json body) and answers from a scripted queue of outcomes — a
    :class:`StubResponse` or an exception per call, consumed in order —
    so each test drives exactly one exchange.
    """

    def __init__(self, *outcomes) -> None:
        self.calls: list[dict] = []
        self._outcomes = list(outcomes)

    def request(self, method: str, url: str, **kwargs):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": kwargs.get("headers"),
                "json": kwargs.get("json"),
            }
        )
        if not self._outcomes:
            raise AssertionError("StubTransport ran out of scripted outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            return _OutcomeContext(None, outcome)
        return _OutcomeContext(outcome, None)


class HangingTransport:
    """A transport whose request never answers (for the timeout test)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url})
        return _HangingContext()


class _HangingContext:
    async def __aenter__(self):
        await asyncio.sleep(5)
        raise AssertionError("hanging transport was never cancelled")

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def make_client(transport, *, timeout_seconds: float = 5.0) -> NestQuestApiClient:
    """Build a client over the stub transport with the test credentials."""
    return NestQuestApiClient(
        BASE_URL, TOKEN, transport, timeout_seconds=timeout_seconds
    )


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


async def test_get_snapshot_parses_payload_and_sends_bearer() -> None:
    transport = StubTransport(
        StubResponse(200, json.dumps(SNAPSHOT_PAYLOAD))
    )
    client = make_client(transport)

    snapshot = await client.get_snapshot()

    assert snapshot == SNAPSHOT_PAYLOAD
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{BASE_URL}/api/v1/panel/snapshot"
    assert call["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert call["json"] is None


async def test_complete_instance_posts_body_and_headers() -> None:
    transport = StubTransport(StubResponse(200, '{"status": "done"}'))
    client = make_client(transport)

    result = await client.complete_instance(42, 3)

    assert result == {"status": "done"}
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == f"{BASE_URL}/api/v1/panel/instances/42/complete"
    assert call["json"] == {"actor_child_id": 3}
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"


async def test_base_url_trailing_slash_is_normalized() -> None:
    """A base URL with a trailing slash must not double the path slash."""
    transport = StubTransport(StubResponse(200, "{}"))
    client = NestQuestApiClient(
        f"{BASE_URL}/", TOKEN, transport, timeout_seconds=5.0
    )
    await client.get_snapshot()
    assert transport.calls[0]["url"] == f"{BASE_URL}/api/v1/panel/snapshot"


# ---------------------------------------------------------------------------
# HTTP failures: the typed error carries the status
# ---------------------------------------------------------------------------


async def test_snapshot_401_raises_typed_error() -> None:
    """A wrong/missing token answers 401 and surfaces with that status."""
    transport = StubTransport(
        StubResponse(401, '{"detail": "Missing or invalid panel service token"}')
    )
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.get_snapshot()

    error = excinfo.value
    assert error.status == 401
    assert not error.is_transport_error
    assert error.__cause__ is None
    # The token is a secret: it never reaches the raised message.
    assert TOKEN not in str(error)


async def test_complete_unknown_instance_404_raises_typed_error() -> None:
    transport = StubTransport(
        StubResponse(404, '{"detail": "Quest instance not found"}')
    )
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.complete_instance(999999, 1)

    assert excinfo.value.status == 404
    assert not excinfo.value.is_transport_error


async def test_snapshot_500_raises_typed_error() -> None:
    """Any non-2xx response is typed, whatever the status."""
    transport = StubTransport(StubResponse(500, "{}"))
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.get_snapshot()

    assert excinfo.value.status == 500


async def test_malformed_2xx_body_raises_typed_with_status() -> None:
    """A 2xx body that is not JSON is a protocol failure, carrying its status."""
    transport = StubTransport(StubResponse(200, "<html>not json</html>"))
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.get_snapshot()

    assert excinfo.value.status == 200


# ---------------------------------------------------------------------------
# Transport failures: the typed error carries no status and chains the cause
# ---------------------------------------------------------------------------


async def test_connection_failure_raises_transport_error() -> None:
    transport = StubTransport(OSError("connection refused"))
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.get_snapshot()

    error = excinfo.value
    assert error.status is None
    assert error.is_transport_error
    assert isinstance(error.__cause__, OSError)


async def test_connection_failure_on_complete_is_typed() -> None:
    transport = StubTransport(OSError("connection refused"))
    client = make_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.complete_instance(7, 1)

    assert excinfo.value.status is None
    assert excinfo.value.is_transport_error


async def test_request_timeout_raises_transport_error() -> None:
    """A hung API call surfaces as a typed transport error, once, with
    no retry: the one request is cancelled by the client's timeout."""
    transport = HangingTransport()
    client = make_client(transport, timeout_seconds=0.05)

    with pytest.raises(NestQuestApiError) as excinfo:
        await client.get_snapshot()

    assert excinfo.value.status is None
    assert excinfo.value.is_transport_error
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# Construction and config resolution
# ---------------------------------------------------------------------------


def test_constructor_requires_full_base_url() -> None:
    for bad_url in (None, "", "   ", "api.lan:8000", "http://", "ftp://x"):
        with pytest.raises(ValueError):
            NestQuestApiClient(bad_url, TOKEN, StubTransport())


def test_constructor_requires_non_empty_token() -> None:
    for bad_token in (None, "", "   "):
        with pytest.raises(ValueError):
            NestQuestApiClient(BASE_URL, bad_token, StubTransport())


def test_constructor_requires_positive_timeout() -> None:
    for bad_timeout in (0, -1, "5", True, None):
        with pytest.raises(ValueError):
            NestQuestApiClient(
                BASE_URL, TOKEN, StubTransport(), timeout_seconds=bad_timeout
            )


def test_is_valid_base_url_accepts_full_http_urls() -> None:
    assert is_valid_base_url("http://127.0.0.1:8000")
    assert is_valid_base_url("https://nestquest.lan")
    assert is_valid_base_url(" http://127.0.0.1:8000 ")
    assert not is_valid_base_url("api.lan:8000")
    assert not is_valid_base_url("http://")
    assert not is_valid_base_url("")
    assert not is_valid_base_url(None)
    assert not is_valid_base_url(42)


def test_resolve_api_config_prefers_options_then_data_then_defaults() -> None:
    options_only = make_config_entry(
        options={CONF_API_BASE_URL: "http://from-options:1"}
    )
    assert resolve_api_config(options_only) == (
        "http://from-options:1",
        DEFAULT_PANEL_TOKEN,
    )

    data_only = make_config_entry(
        data={
            CONF_API_BASE_URL: "http://from-data:2",
            CONF_PANEL_TOKEN: "from-data",
        }
    )
    assert resolve_api_config(data_only) == ("http://from-data:2", "from-data")

    both = make_config_entry(
        options={CONF_API_BASE_URL: "http://from-options:3"},
        data={
            CONF_API_BASE_URL: "http://from-data:4",
            CONF_PANEL_TOKEN: "from-data",
        },
    )
    assert resolve_api_config(both) == (
        "http://from-options:3",
        "from-data",
    )

    bare = make_config_entry()
    assert resolve_api_config(bare) == (DEFAULT_API_BASE_URL, DEFAULT_PANEL_TOKEN)


def test_client_from_entry_reads_config_and_shared_session(monkeypatch) -> None:
    """The production factory resolves the entry config and hands in HA's
    shared aiohttp session (stubbed module — no real HA, no network)."""
    fake_module = types.ModuleType("homeassistant.helpers.aiohttp_client")
    shared_session = object()
    fake_module.async_get_clientsession = lambda hass: shared_session
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", fake_module
    )
    entry = make_config_entry(
        options={
            CONF_API_BASE_URL: "http://panel.lan:8443",
            CONF_PANEL_TOKEN: "entry-token",
        }
    )

    client = api_client.client_from_entry(object(), entry)

    assert client._session is shared_session
    assert client._base_url == "http://panel.lan:8443"
    assert client._panel_token == "entry-token"


async def test_client_logs_nothing() -> None:
    """The client emits no log records at all (the token must never
    reach a log line), success or failure."""
    import logging

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logging.getLogger().addHandler(handler)
    try:
        transport = StubTransport(StubResponse(401, "{}"))
        client = make_client(transport)
        with pytest.raises(NestQuestApiError):
            await client.get_snapshot()
    finally:
        logging.getLogger().removeHandler(handler)
    assert records == []