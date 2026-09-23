"""HA-bus subscription over the API service's panel SSE stream.

The NestQuest API service (Feature 16) publishes every quest
transition on ``GET /api/v1/panel/events`` as Server-Sent Events
frames.  This module is the integration-side subscriber: ONE
background task consumes :meth:`~.api_client.NestQuestApiClient
.stream_events` and re-fires each frame on ``hass.bus`` with the SAME
event type and payload fields the local transition path
(:mod:`~.events`) emits — ``nestquest_quest_completed``,
``nestquest_quest_uncompleted``, ``nestquest_quest_missed`` and
``nestquest_child_day_complete`` — so the four blueprints fire
identically whether a completion happens through the integration's own
service or through the API service's panel route.

Failure handling: a failed stream (API down, network blip, non-2xx, a
dropped connection) is retried FOREVER with a bounded exponential
backoff — :data:`RECONNECT_MIN_SECONDS` after the first failure,
doubling up to :data:`RECONNECT_MAX_SECONDS` — so a long API outage
neither pins the event loop nor spams the log, and a frame received on
a healthy stream resets the backoff.  Nothing escapes the task: every
failure is logged with its reason and the loop reconnects; a
:class:`asyncio.CancelledError` (from :meth:`stop` or integration
unload) is the only thing that ends it, and it stops cleanly — no
frame fires after :meth:`stop` returns and the response is closed.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .const import LOGGER

__all__ = [
    "NestQuestEventStream",
    "RECONNECT_MAX_SECONDS",
    "RECONNECT_MIN_SECONDS",
]

#: Delay before the FIRST reconnect attempt after a stream failure.
#: One failed frame must not turn into a hot reconnect loop.
RECONNECT_MIN_SECONDS = 5.0

#: Ceiling for the exponential reconnect backoff: a long API outage
#: retries at a calm fixed cadence instead of growing without bound.
RECONNECT_MAX_SECONDS = 60.0


class NestQuestEventStream:
    """Consume the panel SSE stream in the background, fire the HA bus.

    ONE instance per config entry, built in integration setup with the
    SAME API client the coordinator polls (the client is stateless —
    one shared session, one connection pool).  ``start()`` schedules
    the background task; ``stop()`` cancels and awaits it, so unload
    never leaks the task and no frame fires after teardown.  The task
    itself is failure-proof: any exception from the stream (typed
    :class:`~.api_client.NestQuestApiError` or anything else) is
    logged and retried after the current backoff, never allowed to
    escape the task.
    """

    def __init__(
        self,
        hass: Any,
        client: Any,
        *,
        reconnect_min_seconds: float = RECONNECT_MIN_SECONDS,
        reconnect_max_seconds: float = RECONNECT_MAX_SECONDS,
    ) -> None:
        """Store the hass bus target, the API client, and the backoff.

        The client is anything exposing ``stream_events()`` (the real
        :class:`~.api_client.NestQuestApiClient` in production, a stub
        in tests).  The backoff bounds must be positive and the minimum
        must not exceed the maximum — a misconfiguration should fail
        loudly at construction, not quietly reconnect at delay 0.
        """
        if (
            not isinstance(reconnect_min_seconds, (int, float))
            or isinstance(reconnect_min_seconds, bool)
            or reconnect_min_seconds <= 0
            or reconnect_min_seconds > reconnect_max_seconds
        ):
            raise ValueError(
                "reconnect_min_seconds must be a positive number no "
                f"greater than reconnect_max_seconds, got "
                f"{reconnect_min_seconds!r}"
            )
        if (
            not isinstance(reconnect_max_seconds, (int, float))
            or isinstance(reconnect_max_seconds, bool)
            or reconnect_max_seconds <= 0
        ):
            raise ValueError(
                f"reconnect_max_seconds must be a positive number, got "
                f"{reconnect_max_seconds!r}"
            )
        self._hass = hass
        self._client = client
        self._min_backoff = float(reconnect_min_seconds)
        self._max_backoff = float(reconnect_max_seconds)
        self._backoff = float(reconnect_min_seconds)
        self._task: asyncio.Task | None = None

    @property
    def task(self) -> asyncio.Task | None:
        """The background task, or ``None`` when never started/stopped."""
        return self._task

    def start(self) -> None:
        """Schedule the subscription task (idempotent while it runs)."""
        if self._task is not None and not self._task.done():
            return
        self._backoff = self._min_backoff
        self._task = asyncio.create_task(
            self._run(), name="nestquest-sse-subscription"
        )

    async def stop(self) -> None:
        """Cancel and await the subscription task.

        Returns only after the task has actually finished, so unload
        can rely on: no further frame is fired after ``stop()``, and
        the underlying stream response has been closed.  Safe to call
        when the task was never started or already stopped.
        """
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # The task's own cancellation surfaces here — expected and
            # swallowed; a cancelling the CALLER would re-raise out of
            # the surrounding await on its own.
            pass

    async def _run(self) -> None:
        """Consume stream frames forever, reconnecting on failure."""
        while True:
            try:
                async for event_type, payload in self._client.stream_events():
                    # A frame arrived on a healthy stream: the next
                    # failure reconnects quickly again.
                    self._backoff = self._min_backoff
                    try:
                        self._hass.bus.async_fire(event_type, dict(payload))
                    except Exception as err:
                        # Firing one frame must never tear down a
                        # healthy connection: log and keep consuming.
                        LOGGER.error(
                            "NestQuest panel event %s could not be fired "
                            "on the Home Assistant event bus: %s",
                            event_type,
                            err,
                        )
            except asyncio.CancelledError:
                # Unload / shutdown: stop cleanly, never converted.
                raise
            except Exception as err:
                delay = self._backoff
                self._backoff = min(
                    self._backoff * 2, self._max_backoff
                )
                LOGGER.warning(
                    "NestQuest panel event stream failed (%s); "
                    "reconnecting in %.1f s",
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
