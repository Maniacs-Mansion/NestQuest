"""Panel-plane API client for the NestQuest integration (Feature 18).

The integration talks to the NestQuest API service (Feature 16) over
HTTP instead of reading the database: this module is the ONE place that
speaks the API's panel plane — ``GET /api/v1/panel/snapshot`` (today's
household snapshot) and ``POST /api/v1/panel/instances/{id}/complete``
(completion as the tapped child profile) — authenticated with the
static panel service token as a Bearer credential on every request.

Transport-injected by construction: the constructor takes the base URL,
the panel token, and the HTTP session to use.  The session speaks the
aiohttp ``ClientSession`` surface (``request(method, url, headers=...,
json=...)`` returning an async context manager whose response carries
``status`` and ``await text()``), so tests stub the transport with NO
network and NO aiohttp installed; production builds the client through
:func:`client_from_entry`, which hands in Home Assistant's shared
aiohttp session (``homeassistant.helpers.aiohttp_client
.async_get_clientsession``).  The module itself imports NEITHER
homeassistant NOR aiohttp at runtime (aiohttp appears only behind
``TYPE_CHECKING`` for annotations), so the client is usable anywhere —
the HA coupling lives in the one production factory.

Every failure is typed: a transport failure (connection refused, DNS
failure, timeout — the exchange never produced a response) and every
non-2xx HTTP response raise :class:`NestQuestApiError`.  The error
carries the HTTP status where there is one (so 401 and 404 are
distinguishable at the call site) and ``None`` when there is not; the
original transport error is chained as ``__cause__`` — nothing is
swallowed.  There are NO retries and the client logs nothing: refresh
cadence is the coordinator's concern (the next task), and the panel
token is a secret that must never reach a log line or an error
message — the error texts name the method, path, and status only.

The panel plane's SSE event stream (``GET /api/v1/panel/events``) is
exposed by :meth:`NestQuestApiClient.stream_events` — an async
generator yielding ``(event_type, payload)`` per Server-Sent Events
frame (``event: <type>`` / ``data: <json>`` lines separated by a blank
line).  Opening the stream gets the same one-timeout, typed-error
contract as every other call; reading it has NO body-wide timeout (a
healthy stream is long-lived — the subscription manager owns
reconnection and backoff).
"""
from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .const import (
    CONF_API_BASE_URL,
    CONF_PANEL_TOKEN,
    DEFAULT_API_BASE_URL,
    DEFAULT_PANEL_TOKEN,
)

if TYPE_CHECKING:
    import aiohttp

__all__ = [
    "COMPLETE_INSTANCE_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "EVENTS_PATH",
    "NestQuestApiError",
    "NestQuestApiClient",
    "SNAPSHOT_PATH",
    "client_from_entry",
    "is_valid_base_url",
    "resolve_api_config",
]

#: The panel plane's snapshot route (Feature 16).
SNAPSHOT_PATH = "/api/v1/panel/snapshot"

#: The panel plane's SSE event-stream route (Feature 16): each
#: transition arrives as an ``event: <type>`` / ``data: <json>`` frame.
EVENTS_PATH = "/api/v1/panel/events"

#: The panel plane's completion route template (Feature 16); the
#: ``{instance_id}`` placeholder is filled per call.
COMPLETE_INSTANCE_PATH = "/api/v1/panel/instances/{instance_id}/complete"

#: Request timeout, in seconds.  One attempt, one timeout: a hung API
#: call surfaces as a typed error for the coordinator to report, never
#: a retry loop.
DEFAULT_TIMEOUT_SECONDS = 10.0


class NestQuestApiError(Exception):
    """A failed NestQuest API exchange, raised for every failure mode.

    ``status`` carries the HTTP status when a response arrived (a
    non-2xx response — 401 for a bad token, 404 for an unknown
    instance) and is ``None`` when the exchange failed at the transport
    level (connection refused, DNS failure, timeout) — so callers
    distinguish the two with ``is_transport_error``.  The original
    transport error, where there is one, is chained as ``__cause__``.
    Messages carry the method, path, and status — never the request
    headers, so the panel token can never leak through an error.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def is_transport_error(self) -> bool:
        """True when the exchange failed before any response arrived."""
        return self.status is None


def is_valid_base_url(value: object) -> bool:
    """Return True when ``value`` is a usable API base URL.

    A full ``http://`` or ``https://`` URL with a host — the exact
    shape the options flow validates (form ergonomics) and the client
    constructor enforces (fail fast, never build requests against a
    scheme-less or host-less string).
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    parsed = urlparse(candidate)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_api_config(entry: Any) -> tuple[str, str]:
    """Resolve ``(base_url, panel_token)`` off a config entry.

    Precedence mirrors the options flow's stored-values resolution:
    ``entry.options`` first (the live options-flow copy), then
    ``entry.data`` (the config-flow-era copy), then the const defaults.
    The token is a secret: callers must never log the returned pair.
    """
    options = getattr(entry, "options", None) or {}
    data = getattr(entry, "data", None) or {}

    def _pick(key: str, default: str) -> str:
        if key in options:
            return options[key]
        if key in data:
            return data[key]
        return default

    return (
        _pick(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
        _pick(CONF_PANEL_TOKEN, DEFAULT_PANEL_TOKEN),
    )


def client_from_entry(hass: Any, entry: Any) -> NestQuestApiClient:
    """Build the production client for a config entry.

    Reads the configured base URL and panel token off the entry
    (:func:`resolve_api_config`) and hands the client Home Assistant's
    SHARED aiohttp session (``homeassistant.helpers.aiohttp_client
    .async_get_clientsession``) so panel calls ride HA's one connection
    pool.  The helper import is deferred into this function on purpose:
    the test harness is mock-only and the module must import (and the
    client must be stub-transport testable) without homeassistant or
    aiohttp installed.
    """
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    base_url, panel_token = resolve_api_config(entry)
    return NestQuestApiClient(
        base_url, panel_token, async_get_clientsession(hass)
    )


class NestQuestApiClient:
    """Async client for the NestQuest API service's panel plane.

    ONE instance per config entry (the coordinator task wires it into
    the refresh cycle).  The client is deliberately thin: it adds the
    Bearer credential and the base URL, enforces one timeout per
    request, and turns every failure into :class:`NestQuestApiError` —
    no business logic, no retries, no caching.
    """

    def __init__(
        self,
        base_url: str,
        panel_token: str,
        session: aiohttp.ClientSession,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Store the connection settings; the session is injected.

        ``session`` is an aiohttp ``ClientSession`` in production and a
        stub transport in tests.  ``base_url`` must be a full http(s)
        URL and ``panel_token`` must be non-empty — a client built
        without either can only fail later at request time with a
        less-explicable error, so construction fails fast instead.
        """
        if not is_valid_base_url(base_url):
            raise ValueError(
                f"base_url must be a full http(s) URL, got {base_url!r}"
            )
        if not isinstance(panel_token, str) or not panel_token.strip():
            raise ValueError("panel_token must be a non-empty string")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise ValueError(
                f"timeout_seconds must be a positive number, got {timeout_seconds!r}"
            )
        self._base_url = base_url.strip().rstrip("/")
        self._panel_token = panel_token
        self._session = session
        self._timeout_seconds = float(timeout_seconds)

    async def get_snapshot(self) -> dict[str, Any]:
        """Fetch and parse today's household snapshot.

        Returns the JSON the snapshot route returns (``today_iso``,
        ``cycle_day``, and the per-child list — see
        ``api/routes_panel.py`` for the documented shape).  Raises
        :class:`NestQuestApiError` on transport failure, timeout, or a
        non-2xx response.
        """
        return await self._request_json("GET", SNAPSHOT_PATH)

    async def complete_instance(
        self, instance_id: int, actor_child_id: int
    ) -> dict[str, Any]:
        """Complete one quest instance as the tapped child profile.

        POSTs ``{"actor_child_id": actor_child_id}`` to the complete
        route and returns the parsed response body (the route answers
        ``{"status": ...}`` both for a first completion and for an
        idempotent repeat, so a retried panel tap succeeds).  Raises
        :class:`NestQuestApiError` on transport failure, timeout, or a
        non-2xx response — 401 for a wrong token, 404 for an unknown
        instance.
        """
        path = COMPLETE_INSTANCE_PATH.format(instance_id=instance_id)
        return await self._request_json(
            "POST", path, json_body={"actor_child_id": actor_child_id}
        )

    async def stream_events(
        self,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield ``(event_type, payload)`` for every panel SSE frame.

        Opens ``GET /api/v1/panel/events`` with the Bearer credential
        and parses the Server-Sent Events framing the API service
        emits: ``event: <type>`` and ``data: <json>`` lines closed by a
        blank line (one frame per transition event; a frame's ``data``
        may span several ``data:`` lines, joined with newlines — the
        standard SSE rule).  Line splits across chunk boundaries are
        buffered, so frames are parsed correctly whatever chunking the
        transport produces.

        Opening the stream carries the SAME one-timeout, typed-error
        contract as every other call: a non-2xx response raises
        :class:`NestQuestApiError` with its status and a transport
        failure (connection refused, DNS, the open timing out) raises
        one with ``status=None`` and the original error chained.  The
        reading loop itself has NO timeout — a healthy stream is
        long-lived — but any failure raised from the transport
        mid-stream raises typed as well, so the consumer can reconnect.
        A frame whose ``data`` is not valid JSON is a protocol failure
        and raises typed, carrying the response status it arrived
        with.  Cancellation is never converted: closing the generator
        (``aclose``, i.e. the consumer's task being cancelled) stops
        cleanly and closes the underlying response in every path.
        """
        url = f"{self._base_url}{EVENTS_PATH}"
        headers = {"Authorization": f"Bearer {self._panel_token}"}
        # Opening the response gets ONE request timeout, exactly like
        # ``_request_json``; the read loop below runs WITHOUT one — a
        # body-wide timeout would kill a healthy long-lived stream.
        # The response context manager is entered manually (not via
        # ``async with``) because the block must span the yields below;
        # the ``finally`` closes it on EVERY exit path.
        try:
            async with asyncio.timeout(self._timeout_seconds):
                stream_cm = self._session.request(
                    "GET", url, headers=headers, json=None
                )
                response = await stream_cm.__aenter__()
        except asyncio.CancelledError:
            # Cancellation is never converted (see ``_request_json``).
            raise
        except NestQuestApiError:
            raise
        except Exception as err:
            raise NestQuestApiError(
                f"NestQuest API GET {EVENTS_PATH} transport failure: {err}",
                status=None,
            ) from err

        status = response.status
        if not 200 <= status < 300:
            await self._close_stream(stream_cm)
            raise NestQuestApiError(
                f"NestQuest API GET {EVENTS_PATH} failed with HTTP {status}",
                status=status,
            )

        try:
            event_type: str | None = None
            data_lines: list[str] = []
            buffer = ""
            async for chunk in response:
                if isinstance(chunk, (bytes, bytearray)):
                    chunk = chunk.decode("utf-8")
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())
                    elif not line and event_type is not None:
                        # A blank line ends the frame.  A trailing
                        # incomplete frame (stream ends without its
                        # closing blank line) is discarded, per the
                        # SSE spec's treatment of incomplete events.
                        try:
                            payload = json.loads("\n".join(data_lines))
                        except ValueError as err:
                            raise NestQuestApiError(
                                f"NestQuest API GET {EVENTS_PATH} "
                                f"delivered a malformed SSE frame: {err}",
                                status=status,
                            ) from err
                        yield event_type, payload
                        event_type = None
                        data_lines = []
        except asyncio.CancelledError:
            raise
        except NestQuestApiError:
            raise
        except Exception as err:
            raise NestQuestApiError(
                f"NestQuest API GET {EVENTS_PATH} transport failure: {err}",
                status=None,
            ) from err
        finally:
            await self._close_stream(stream_cm)

    @staticmethod
    async def _close_stream(stream_cm: Any) -> None:
        """Close an opened streaming response context manager.

        Works for aiohttp's response context manager (whose
        ``__aexit__`` is a coroutine) and for test stubs that return
        either a coroutine or a plain value.
        """
        result = stream_cm.__aexit__(None, None, None)
        if inspect.isawaitable(result):
            await result

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Run ONE request and return the parsed JSON body.

        The Bearer token rides the Authorization header only.  A
        non-2xx response raises :class:`NestQuestApiError` with its
        status; anything the transport raises (connection, timeout) is
        wrapped as a transport-level :class:`NestQuestApiError` with
        the original error chained — never swallowed, never retried.
        A 2xx body that is not valid JSON is a protocol failure and
        raises typed too, carrying the status it arrived with.
        """
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._panel_token}"}
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.request(
                    method, url, headers=headers, json=json_body
                ) as response:
                    status = response.status
                    if not 200 <= status < 300:
                        raise NestQuestApiError(
                            f"NestQuest API {method} {path} failed with "
                            f"HTTP {status}",
                            status=status,
                        )
                    body_text = await response.text()
        except asyncio.CancelledError:
            # Cancellation is never converted: a shutting-down event
            # loop must stop, not read a synthesized API error.
            raise
        except NestQuestApiError:
            raise
        except Exception as err:
            raise NestQuestApiError(
                f"NestQuest API {method} {path} transport failure: {err}",
                status=None,
            ) from err
        try:
            return json.loads(body_text)
        except ValueError as err:
            raise NestQuestApiError(
                f"NestQuest API {method} {path} returned malformed "
                f"JSON: {err}",
                status=status,
            ) from err