"""Tests for the panel SSE subscription (HA-bus re-firing task).

Three layers are exercised, all STUB-driven — no network, no aiohttp,
no real Home Assistant:

- The API client's ``stream_events`` (transport stub): what goes on
  the wire (GET, the events URL, the Bearer header), SSE frame
  parsing (``event:``/``data:`` lines, blank-line frame ends, chunk
  boundaries, multi-line data), and every failure mode (non-2xx,
  connection failure, mid-stream drop, malformed frame) surfacing as
  the typed :class:`NestQuestApiError`; cancellation closes the
  stream cleanly.
- The :class:`~custom_components.nestquest.sse.NestQuestEventStream`
  subscription manager (duck-typed stream client): the four documented
  transition events (design/ENTITIES-AND-SERVICES.md §3, exactly as
  ``tests/test_api_sse.py`` observes them on the API side) fire on
  ``hass.bus`` with the documented payload fields; ``stop()`` cancels
  the task so no frame fires afterwards; a stream failure reconnects
  with a bounded, reset-on-success backoff and never crashes the
  task.
- The integration wiring: setup starts the stream alongside the
  runtime record, unload tears it down (no firing afterwards, task
  cancelled), and an entry whose client has no stream surface (the
  unconfigured-token stub, the test snapshot client) starts none.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from conftest import set_coordinator_client, wire_entry_to_registry

import custom_components.nestquest as nq_integration
from custom_components.nestquest import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.nestquest import sse as sse_module
from custom_components.nestquest.api_client import (
    NestQuestApiClient,
    NestQuestApiError,
)
from custom_components.nestquest.sse import NestQuestEventStream

BASE_URL = "http://api.test:8000"
TOKEN = "test-panel-token"

# Captured BEFORE any test patches asyncio.sleep (the reconnect test
# swaps in a recording fake; this reference keeps helpers sleeping for
# real regardless).
_REAL_SLEEP = asyncio.sleep

#: The four documented transition events with their documented payload
#: fields — the exact shapes the API side streams (test_api_sse.py).
DOCUMENTED_FRAMES = (
    (
        "nestquest_quest_completed",
        {
            "child_id": 1,
            "child_name": "Ada",
            "instance_id": 7,
            "quest_title": "Pack bag",
            "window": "morning",
            "due_date": "2026-09-23",
            "due_time": "10:00",
            "occurred_at": "2026-09-23T12:00:00+00:00",
            "was_on_time": False,
        },
    ),
    (
        "nestquest_quest_uncompleted",
        {
            "child_id": 1,
            "child_name": "Ada",
            "instance_id": 7,
            "quest_title": "Pack bag",
            "window": "morning",
            "due_date": "2026-09-23",
            "due_time": "10:00",
            "occurred_at": "2026-09-23T12:00:00+00:00",
        },
    ),
    (
        "nestquest_quest_missed",
        {
            "child_id": 1,
            "child_name": "Ada",
            "instance_id": 9,
            "quest_title": "Stale chore",
            "window": "morning",
            "due_date": "2026-09-23",
            "due_time": "09:00",
            "occurred_at": "2026-09-23T23:30:00+00:00",
        },
    ),
    (
        "nestquest_child_day_complete",
        {
            "child_id": 1,
            "child_name": "Ada",
            "quests_due": 1,
            "quests_completed": 1,
            "occurred_at": "2026-09-23T12:00:00+00:00",
        },
    ),
)

#: The documented payload field sets per event type.
DOCUMENTED_FIELDS = {
    "nestquest_quest_completed": {
        "child_id",
        "child_name",
        "instance_id",
        "quest_title",
        "window",
        "due_date",
        "due_time",
        "occurred_at",
        "was_on_time",
    },
    "nestquest_quest_uncompleted": {
        "child_id",
        "child_name",
        "instance_id",
        "quest_title",
        "window",
        "due_date",
        "due_time",
        "occurred_at",
    },
    "nestquest_quest_missed": {
        "child_id",
        "child_name",
        "instance_id",
        "quest_title",
        "window",
        "due_date",
        "due_time",
        "occurred_at",
    },
    "nestquest_child_day_complete": {
        "child_id",
        "child_name",
        "quests_due",
        "quests_completed",
        "occurred_at",
    },
}

#: A minimal panel snapshot payload for the full-setup wiring tests
#: (the shape ``snapshot_from_api_payload`` consumes; no children).
MINIMAL_SNAPSHOT = {"today_iso": "2026-09-23", "cycle_day": 1, "children": []}


# ---------------------------------------------------------------------------
# Stub transports and stream clients (no network anywhere)
# ---------------------------------------------------------------------------


class _StreamingResponse:
    """A fake aiohttp streaming response: ``status`` + chunk iteration.

    ``chunks`` are the body pieces the stream yields in order; a chunk
    may be an exception, raised when the iteration reaches it (a
    mid-stream transport drop).  ``hold_open`` keeps the stream open
    forever after the chunks run out, for cancellation tests.
    """

    def __init__(self, status: int, chunks, *, hold_open: bool = False) -> None:
        self.status = status
        self._chunks = list(chunks)
        self._hold_open = hold_open
        self.closed = False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self._chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk
        if self._hold_open:
            await asyncio.Event().wait()  # cancelled, never ends


class _RequestContext:
    """Async context manager mirroring ``session.request(...)``'s return.

    Entering performs the request (a scripted transport error raises
    THERE, where aiohttp's connector raises on a refused connection);
    exiting marks the response closed, so tests can assert the stream
    was released.
    """

    def __init__(self, response, error) -> None:
        self._response = response
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._response is not None:
            self._response.closed = True
        return False


class _StreamTransport:
    """A no-network stand-in for aiohttp's ``ClientSession``.

    Records every ``request(...)`` call and answers from a scripted
    queue of outcomes (a :class:`_StreamingResponse` or an exception
    per attempt, consumed in order).
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
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            return _RequestContext(None, outcome)
        return _RequestContext(outcome, None)


def make_stream_client(transport) -> NestQuestApiClient:
    """Build a client over the streaming stub with the test credentials."""
    return NestQuestApiClient(BASE_URL, TOKEN, transport)


def _frame_text(event_type: str, payload: dict) -> str:
    """One documented SSE frame: event line, data line, blank line."""
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


class _ScriptedStreamClient:
    """Duck-typed API client: one scripted stream per connection.

    ``script`` holds generator FACTORIES — ``stream_events()`` pops the
    next one and returns its async generator, so a test scripts exactly
    what each connection attempt yields (or how it fails).
    """

    def __init__(self, script) -> None:
        self._script = list(script)
        self.calls = 0

    def stream_events(self):
        self.calls += 1
        return self._script.pop(0)()


def _frames(*frames):
    """A live stream factory: yields ``frames``, then stays open."""

    def _factory():
        async def _gen():
            for frame in frames:
                yield frame
            await asyncio.Event().wait()  # cancelled, never ends

        return _gen()

    return _factory


def _fail(error: BaseException):
    """A stream factory that fails before yielding anything."""

    def _factory():
        async def _gen():
            raise error
            yield  # noqa: unreachable — makes _gen an async generator

        return _gen()

    return _factory


def _drop_after(error: BaseException, *frames):
    """A stream factory that yields ``frames`` then drops mid-stream."""

    def _factory():
        async def _gen():
            for frame in frames:
                yield frame
            raise error

        return _gen()

    return _factory


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """Poll ``predicate`` until true or the deadline passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met within the deadline")
        await _REAL_SLEEP(0.01)


def make_manager(
    hass, client, *, min_backoff: float = 0.01, max_backoff: float = 0.05
) -> NestQuestEventStream:
    """A manager with fast (test-sized) backoff bounds."""
    return NestQuestEventStream(
        hass,
        client,
        reconnect_min_seconds=min_backoff,
        reconnect_max_seconds=max_backoff,
    )


# ---------------------------------------------------------------------------
# The client's stream_events: parsing and typed failures
# ---------------------------------------------------------------------------


async def test_stream_events_yields_documented_frames_and_sends_bearer() -> None:
    """All four documented frames parse, with the Bearer GET on the wire."""
    body = "".join(
        _frame_text(event_type, payload)
        for event_type, payload in DOCUMENTED_FRAMES
    )
    transport = _StreamTransport(_StreamingResponse(200, [body]))
    client = make_stream_client(transport)

    frames = [frame async for frame in client.stream_events()]

    assert frames == list(DOCUMENTED_FRAMES)
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{BASE_URL}/api/v1/panel/events"
    assert call["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert call["json"] is None


async def test_stream_events_buffers_lines_across_chunks_and_joins_data() -> None:
    """Chunk-split lines parse, and multi-line data joins per SSE rules."""
    first_type, first_payload = DOCUMENTED_FRAMES[0]
    # The first frame is cut MID-LINE across two chunks; the second
    # frame spreads its JSON over two ``data:`` lines.
    chunks = [
        f"event: {first_type}\nda",
        f"ta: {json.dumps(first_payload)}\n\nevent: "
        f"{DOCUMENTED_FRAMES[1][0]}\n",
        f'data: {{"extra":\ndata: true}}\n\n',
    ]
    transport = _StreamTransport(_StreamingResponse(200, chunks))
    client = make_stream_client(transport)

    frames = [frame async for frame in client.stream_events()]

    assert len(frames) == 2
    assert frames[0] == DOCUMENTED_FRAMES[0]
    # The split-out frame's data spread over two ``data:`` lines joins
    # with a newline (the SSE standard) and parses as one JSON body.
    assert frames[1] == (DOCUMENTED_FRAMES[1][0], {"extra": True})


async def test_stream_events_non_2xx_raises_typed_and_closes() -> None:
    """A wrong token (401) is typed with its status; no stream is read."""
    response = _StreamingResponse(401, ["event: x\ndata: {}\n\n"])
    transport = _StreamTransport(response)
    client = make_stream_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        async for _ in client.stream_events():
            pass

    assert excinfo.value.status == 401
    assert not excinfo.value.is_transport_error
    assert TOKEN not in str(excinfo.value)
    assert response.closed


async def test_stream_events_connection_failure_raises_typed_transport_error() -> None:
    """A failure before any response is a typed transport error."""
    transport = _StreamTransport(OSError("connection refused"))
    client = make_stream_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        async for _ in client.stream_events():
            pass

    assert excinfo.value.status is None
    assert excinfo.value.is_transport_error
    assert isinstance(excinfo.value.__cause__, OSError)


async def test_stream_events_midstream_drop_raises_typed() -> None:
    """A transport error mid-stream is typed, so the consumer reconnects."""
    response = _StreamingResponse(
        200,
        [_frame_text(DOCUMENTED_FRAMES[0][0], DOCUMENTED_FRAMES[0][1]), OSError("reset")],
    )
    transport = _StreamTransport(response)
    client = make_stream_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        async for _ in client.stream_events():
            pass

    assert excinfo.value.status is None
    assert excinfo.value.is_transport_error
    assert isinstance(excinfo.value.__cause__, OSError)
    assert response.closed


async def test_stream_events_stops_cleanly_on_cancellation() -> None:
    """Closing the generator (the consumer task's cancellation) stops
    cleanly: no error, the underlying response is closed, and nothing
    further is yielded."""
    response = _StreamingResponse(
        200,
        [_frame_text(DOCUMENTED_FRAMES[0][0], DOCUMENTED_FRAMES[0][1])],
        hold_open=True,
    )
    transport = _StreamTransport(response)
    client = make_stream_client(transport)

    generator = client.stream_events()
    first = await asyncio.wait_for(generator.__anext__(), timeout=2.0)
    assert first == DOCUMENTED_FRAMES[0]

    await asyncio.wait_for(generator.aclose(), timeout=2.0)
    assert response.closed


async def test_stream_events_malformed_frame_raises_typed() -> None:
    """A frame whose data is not JSON is a typed protocol failure."""
    response = _StreamingResponse(
        200, ["event: nestquest_quest_completed\ndata: not-json\n\n"]
    )
    transport = _StreamTransport(response)
    client = make_stream_client(transport)

    with pytest.raises(NestQuestApiError) as excinfo:
        async for _ in client.stream_events():
            pass

    assert excinfo.value.status == 200
    assert response.closed


# ---------------------------------------------------------------------------
# The subscription manager: firing, teardown, reconnect
# ---------------------------------------------------------------------------


async def test_manager_fires_documented_frames_on_ha_bus(hass) -> None:
    """Every documented transition fires on hass.bus with its payload."""
    client = _ScriptedStreamClient([_frames(*DOCUMENTED_FRAMES)])
    manager = make_manager(hass, client)
    manager.start()
    try:
        await _wait_until(lambda: len(hass.bus.events) >= 4)
        assert hass.bus.events == [tuple(f) for f in DOCUMENTED_FRAMES]
        for event_type, payload in DOCUMENTED_FRAMES:
            fired = hass.bus.fired(event_type)
            assert fired, f"{event_type} never fired"
            assert set(fired[-1]) == DOCUMENTED_FIELDS[event_type]
    finally:
        await manager.stop()


async def test_manager_stop_cancels_task_and_blocks_later_frames(hass) -> None:
    """stop() cancels and awaits the task: no frame fires afterwards,
    even when the (dead) stream is later offered more data."""
    stream_release = asyncio.Event()
    first_type, first_payload = DOCUMENTED_FRAMES[0]
    later_type, later_payload = DOCUMENTED_FRAMES[1]

    def _factory():
        async def _gen():
            yield (first_type, dict(first_payload))
            await stream_release.wait()
            yield (later_type, dict(later_payload))

        return _gen()

    client = _ScriptedStreamClient([_factory])
    manager = make_manager(hass, client)
    manager.start()
    await _wait_until(lambda: len(hass.bus.events) == 1)

    task = manager.task
    await manager.stop()
    assert task.cancelled()
    assert manager.task is None

    # Offer the stream more data after teardown: nothing fires.
    stream_release.set()
    await _REAL_SLEEP(0.05)
    assert hass.bus.events == [(first_type, dict(first_payload))]


async def test_manager_reconnects_with_bounded_backoff(hass, monkeypatch) -> None:
    """A failed stream reconnects with a bounded, reset-on-success
    backoff and never crashes the task."""
    delays: list[float] = []

    async def fake_sleep(delay, *args, **kwargs):
        delays.append(delay)
        await _REAL_SLEEP(0)

    monkeypatch.setattr(sse_module.asyncio, "sleep", fake_sleep)

    stream_error = ConnectionError("stream reset")
    client = _ScriptedStreamClient(
        [
            _fail(RuntimeError("api down")),
            _fail(RuntimeError("api down")),
            _fail(RuntimeError("api down")),
            _fail(RuntimeError("api down")),
            _drop_after(stream_error, DOCUMENTED_FRAMES[0]),
            _frames(*DOCUMENTED_FRAMES),
        ]
    )
    manager = make_manager(hass, client, min_backoff=0.05, max_backoff=0.2)
    manager.start()
    try:
        await _wait_until(lambda: len(hass.bus.events) >= 5)
        # 5s → 10s → 20s (cap) → 20s (cap), then a frame on a healthy
        # stream reset it to the 5s minimum for the next failure.
        assert delays == [0.05, 0.1, 0.2, 0.2, 0.05]
        assert hass.bus.events == [
            tuple(DOCUMENTED_FRAMES[0]),
            *[tuple(f) for f in DOCUMENTED_FRAMES],
        ]
        # The task is still alive (subscribed and idle), not crashed.
        assert manager.task is not None and not manager.task.done()
    finally:
        await manager.stop()


def test_manager_rejects_invalid_backoff_bounds(hass) -> None:
    """Non-positive or inverted backoff bounds fail at construction."""
    with pytest.raises(ValueError):
        NestQuestEventStream(hass, object(), reconnect_min_seconds=0)
    with pytest.raises(ValueError):
        NestQuestEventStream(hass, object(), reconnect_min_seconds=-1)
    with pytest.raises(ValueError):
        NestQuestEventStream(hass, object(), reconnect_max_seconds=0)
    with pytest.raises(ValueError):
        NestQuestEventStream(hass, object(), reconnect_min_seconds=10.0, reconnect_max_seconds=5.0)


# ---------------------------------------------------------------------------
# Integration wiring: setup starts the stream, unload stops it
# ---------------------------------------------------------------------------


class _SetupClient:
    """Client for full-setup wiring tests: scripted snapshot + stream."""

    def __init__(self, script) -> None:
        self._script = list(script)
        self.stream_calls = 0

    async def get_snapshot(self) -> dict:
        return dict(MINIMAL_SNAPSHOT)

    def stream_events(self):
        self.stream_calls += 1
        return self._script.pop(0)()


async def test_setup_starts_stream_and_unload_stops_it(hass, make_entry) -> None:
    """Setup starts the subscription alongside the runtime record; unload
    tears the task down so no frame fires afterwards."""
    client = _SetupClient([_frames(*DOCUMENTED_FRAMES)])
    set_coordinator_client(make_entry(), client)
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await nq_integration.async_setup_entry(hass, entry) is True

    runtime = entry.runtime_data
    assert runtime.event_stream is not None
    await _wait_until(lambda: len(hass.bus.events) >= 4)
    assert [event for event, _ in hass.bus.events] == [
        frame[0] for frame in DOCUMENTED_FRAMES
    ]

    task = runtime.event_stream.task
    assert await nq_integration.async_unload_entry(hass, entry) is True
    assert task.cancelled()
    assert runtime.event_stream.task is None

    events_after_unload = len(hass.bus.events)
    await _REAL_SLEEP(0.05)
    assert len(hass.bus.events) == events_after_unload


async def test_setup_without_stream_surface_starts_no_subscription(
    hass, make_entry
) -> None:
    """An entry whose API client has no stream surface (the local-snapshot
    stub the harness installs, like the unconfigured-token stub in
    production) starts NO subscription — and setup still succeeds."""
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await nq_integration.async_setup_entry(hass, entry) is True
    assert entry.runtime_data.event_stream is None
    assert await nq_integration.async_unload_entry(hass, entry) is True
