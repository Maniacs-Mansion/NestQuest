"""Permission gate for NestQuest services (Feature 09).

A wrapper factory, applied to EVERY registered service at registration
time (no handler is exempt), reads ``call.context.user_id``, consults
the :data:`~.service_policy.SERVICE_POLICY` registry and
:func:`~.admin_allowlist.is_admin`, and raises
:class:`homeassistant.exceptions.Unauthorized` for an admin-only
operation called by a non-admin — including a call with NO user
context, which fails closed.  ``complete_quest`` (policy ``open``)
proceeds regardless of the allowlist.

Logging (later Feature 09 tasks): every denied admin-only call logs a
warning and every successful one logs a debug line, both carrying the
service, the user id (or ``none``), and a UTC timestamp.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.exceptions import Unauthorized

from .admin_allowlist import is_admin
from .service_policy import ADMIN_ONLY

LOGGER = logging.getLogger(__name__)

ServiceHandler = Callable[[Any], Awaitable[None]]


def _context_user_id(call: Any) -> str | None:
    context = getattr(call, "context", None)
    user_id = getattr(context, "user_id", None) if context is not None else None
    if isinstance(user_id, str) and user_id:
        return user_id
    return None


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def permission_gate(
    service: str,
    policy: str,
    database_of: Callable[[Any], Any],
) -> Callable[[ServiceHandler], ServiceHandler]:
    """Wrap ``handler`` with the Feature 09 permission check.

    ``database_of`` resolves the live database from the call-time
    runtime (the same ``find_runtime`` the handler uses), so the gate
    never opens its own connection.  The verdict is fail-closed:
    absent allowlist row, unknown id, no user context — all not admin.
    """

    def _wrap(handler: ServiceHandler) -> ServiceHandler:
        if policy != ADMIN_ONLY:
            return handler

        async def _gated(call: Any) -> None:
            user_id = _context_user_id(call)
            allowed = user_id is not None and await is_admin(
                database_of(call), user_id
            )
            if not allowed:
                LOGGER.warning(
                    "NestQuest denied %s: caller user_id=%s at %s",
                    service,
                    user_id if user_id is not None else "none",
                    _stamp(),
                )
                raise Unauthorized(
                    f"User '{user_id if user_id is not None else 'none'}' "
                    f"is not allowed to call nestquest.{service}"
                )
            LOGGER.debug(
                "NestQuest allowed %s: caller user_id=%s at %s",
                service,
                user_id,
                _stamp(),
            )
            await handler(call)

        return _gated

    return _wrap