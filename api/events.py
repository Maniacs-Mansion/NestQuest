"""The ONE in-process transition-event publisher for the API service.

Route handlers call :meth:`TransitionPublisher.publish` synchronously
(no ``await``, callable from any async handler); SSE subscribers stream
those transitions through an async generator.  The scope of "ONE" is
deliberate: a single :class:`TransitionPublisher` instance is created
in the app lifespan and stored on ``app.state.publisher`` — per-app,
so tests build their own hermetic app without module-level state, and
both the panel complete route and the SSE endpoint resolve the SAME
instance off ``request.app.state`` (exactly one publisher exists per
running app; nothing else may create one).

Design (small and dependency-free, asyncio only):

- Each subscriber gets its own ``asyncio.Queue(maxsize=64)``.
- ``publish`` is synchronous and non-blocking: it puts the event on
  every live queue with ``put_nowait``.  A slow subscriber that lets
  its queue fill gets the event DROPPED (oldest overflow) — never a
  blocked publisher, never unbounded growth.
- A disconnected subscriber's queue is removed in the generator's
  ``finally`` block, so teardown is clean and a closed consumer cannot
  leak its queue.

Fan-out is fire-and-forget by design: the SSE plane mirrors transition
events for the panel UI; a dropped event costs the panel one UI
refresh, and the documented recovery path is the next snapshot poll.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

#: Per-subscriber queue capacity.  Bounded so a stalled consumer can
#: never make the publisher or another subscriber wait; beyond this
#: the slow subscriber drops the event (see module docstring).
_QUEUE_MAXSIZE = 64

__all__ = ["TransitionPublisher"]


class TransitionPublisher:
    """A single in-process fan-out point for transition events."""

    def __init__(self) -> None:
        """Create the publisher with no subscribers."""
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, event_type: str, payload: dict) -> None:
        """Fan one transition event out to every current subscriber.

        Synchronous and non-blocking: each subscriber's bounded queue
        is filled with ``put_nowait``, and a FULL queue silently drops
        the event for that (slow) subscriber rather than blocking the
        route handler or growing without bound.
        """
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait((event_type, payload))
            except asyncio.QueueFull:
                # The subscriber is not keeping up; drop the event for
                # it and move on (the panel recovers by polling).
                pass

    async def subscribe(self) -> AsyncIterator[tuple[str, dict]]:
        """Yield ``(event_type, payload)`` tuples until the consumer breaks.

        Registers ONE bounded queue for the duration of the iteration
        and removes it in the ``finally`` block, so a client disconnect
        (or any break out of the loop) tears the subscription down
        cleanly with no leaked queue.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
