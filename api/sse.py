"""The ONE Server-Sent Events response helper for the API service.

Both SSE planes — the panel plane (``/api/v1/panel/events``, panel
service token, LAN-only) and the admin plane (``/api/v1/admin/events``,
Authentik admin JWT) — stream the SAME transitions off the SAME
in-process publisher (``app.state.publisher``, see :mod:`api.events`)
with the SAME framing and teardown, so the stream lives here once and
each plane's route only supplies its own router-level auth.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

__all__ = ["transition_event_stream"]


async def _sse_stream(request: Request) -> AsyncIterator[str]:
    """Yield the SSE frames for every published transition event.

    One subscriber of the app's single publisher (resolved off
    ``app.state.publisher``); each event becomes one
    ``event: <type>\\ndata: <json>\\n\\n`` frame.  Breaking out of the
    publisher's subscription (on client disconnect) tears the
    subscription down cleanly — no queue is leaked.
    """
    publisher = request.app.state.publisher
    async for event_type, payload in publisher.subscribe():
        yield (
            f"event: {event_type}\n"
            f"data: {json.dumps(payload)}\n\n"
        )


def transition_event_stream(request: Request) -> StreamingResponse:
    """A ``text/event-stream`` response over the app's transition events.

    Performs NO auth of its own: the calling route's router-level
    dependency is the ONE check for its plane.  The stream ends when
    the client disconnects, at which point the subscription is torn
    down (its queue removed) with nothing leaked.
    """
    return StreamingResponse(
        _sse_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
