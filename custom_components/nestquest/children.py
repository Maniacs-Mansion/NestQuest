"""Business layer for the children registry (Feature 03).

Sits between the Feature 09 service gate and the typed
:class:`~.dao_children.ChildrenDao`: callers get validation, name
policies and the duplicate-name warning here, and never talk to the
DAO or SQL directly.  Children are never hard-deleted — deactivation
is a separate explicit operation (:func:`set_child_active`), so
completion history keeps its references (feature guardrail).

Name policy: the display name is required and trimmed; an empty or
whitespace-only name is rejected with ValueError.  A duplicate display
name is ALLOWED (two children may legitimately share a nickname) but
logged as a warning so an accidental double-add is visible in the HA
log.  The duplicate check is case-insensitive and whitespace-normalised
on both sides, because "ada" and "Ada " are the same name to a parent.

Colour and avatar are optional free-form strings, trimmed when present;
``sort_order`` is an int with the DAO/schema default of 0.  Clearing an
optional field back to NULL is deliberately rejected: the DAO's update
writes only provided fields (it cannot express NULL), so the business
layer refuses an explicit ``None`` instead of silently ignoring it.
Timestamps follow the module timestamp policy: the business layer
stamps UTC ISO-8601 at second precision so every row it creates is
uniform.
"""
from __future__ import annotations

import datetime
import logging

from .dao_children import ChildRecord, ChildrenDao, _connection_lock
from .db import NestQuestDatabase

LOGGER = logging.getLogger(__name__)

#: Sentinel distinguishing "argument omitted" from "explicit SQL NULL"
#: in :func:`edit_child`.
_UNSET = object()


def _now_stamp() -> str:
    """Return the module's strict UTC second-precision stamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _validate_text(
    value: object, field: str, *, required: bool = False
) -> str | None:
    """Validate a free-text field and return it trimmed.

    ``None`` raises when ``required`` and otherwise returns None.  A
    non-string value is rejected; an empty result is rejected for
    required fields (whitespace-only names are empty to a parent).
    """
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {value!r}")
    trimmed = value.strip()
    if required and not trimmed:
        raise ValueError(f"{field} is required")
    return trimmed


def _validate_sort_order(value: object) -> int:
    """Reject non-int sort orders (bools included) before the DAO."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"sort_order must be an integer, got {value!r}")
    return value


async def _warn_on_duplicate_name(
    database: NestQuestDatabase,
    display_name: str,
    *,
    exclude_child_id: int | None = None,
) -> None:
    """Log a warning when ``display_name`` duplicates an existing child.

    Case-insensitive and whitespace-normalised on both sides.  The
    duplicate is still allowed — this only makes it visible; the log
    line names both rows so an accidental double-add can be found.
    ``exclude_child_id`` removes the child being edited from the scan,
    so an edit only warns when the result collides with a DIFFERENT
    child's name — including case-only edits, where the self-comparison
    would otherwise hide a real duplicate.
    """
    lowered = display_name.casefold()
    for child in await ChildrenDao(database).list_all():
        if exclude_child_id is not None and child.id == exclude_child_id:
            continue
        if child.display_name.strip().casefold() == lowered:
            LOGGER.warning(
                "Child display name %r duplicates existing child %d "
                "(%r); allowed, but check this was intentional",
                display_name,
                child.id,
                child.display_name,
            )
            return


async def create_child(
    database: NestQuestDatabase,
    display_name: str,
    *,
    colour: str | None = None,
    avatar_ref: str | None = None,
    sort_order: int = 0,
) -> ChildRecord:
    """Create a child profile and return the stored record.

    The display name is required, trimmed, and rejected when empty.
    A duplicate display name (case-insensitive) is allowed but logged
    as a warning.  The scan and the INSERT run inside the
    connection-scoped lock shared with the DAOs, so a concurrent
    create of the same normalised name queues behind the first insert
    and sees it — the duplicate still warns; it can never slip through
    unlogged.
    """
    name = _validate_text(display_name, "display_name", required=True)
    assert name is not None
    colour_value = _validate_text(colour, "colour")
    avatar_value = _validate_text(avatar_ref, "avatar_ref")
    order = _validate_sort_order(sort_order)
    async with _connection_lock(database):
        await _warn_on_duplicate_name(database, name)
        created = await ChildrenDao(database).create(
            name,
            _now_stamp(),
            colour=colour_value,
            avatar_ref=avatar_value,
            sort_order=order,
        )
    return created


async def edit_child(
    database: NestQuestDatabase,
    child_id: int,
    *,
    display_name: str | object = _UNSET,
    colour: str | None | object = _UNSET,
    avatar_ref: str | None | object = _UNSET,
    sort_order: int | object = _UNSET,
) -> ChildRecord:
    """Edit a child profile and return the updated record.

    Arguments default to the module sentinel ``_UNSET`` meaning "leave
    this field alone".  An explicitly passed ``None`` for an optional
    field raises: the DAO's update writes only provided fields and
    cannot express NULL, so a silent no-op would mask the caller's
    intent (see the module docstring).  A provided display name is
    validated like create's; the duplicate scan excludes only the child
    being edited, so a case-only edit colliding with another child's
    normalised name still warns.  Raises ValueError when the child does
    not exist.

    Atomicity: the existence check, the duplicate scan, the UPDATE and
    the readback all run inside the connection-scoped lock shared with
    the DAOs, so another edit cannot slip between this call's UPDATE
    and its readback — the returned record is exactly the one this
    edit produced, not a later writer's.
    """
    async with _connection_lock(database):
        dao = ChildrenDao(database)
        existing = await dao.get(child_id)
        if existing is None:
            raise ValueError(f"child {child_id} does not exist")
        updates: dict[str, object] = {}
        if display_name is not _UNSET:
            name = _validate_text(
                display_name, "display_name", required=True
            )
            assert name is not None
            await _warn_on_duplicate_name(
                database, name, exclude_child_id=child_id
            )
            updates["display_name"] = name
        if colour is not _UNSET:
            value = _validate_text(colour, "colour")
            if value is None:
                raise ValueError(
                    "clearing colour is not supported; pass a replacement "
                    "value or omit the field"
                )
            updates["colour"] = value
        if avatar_ref is not _UNSET:
            value = _validate_text(avatar_ref, "avatar_ref")
            if value is None:
                raise ValueError(
                    "clearing avatar_ref is not supported; pass a "
                    "replacement value or omit the field"
                )
            updates["avatar_ref"] = value
        if sort_order is not _UNSET:
            updates["sort_order"] = _validate_sort_order(sort_order)
        if updates:
            await dao.update(child_id, **updates)
        edited = await dao.get(child_id)
    assert edited is not None
    return edited


async def set_child_active(
    database: NestQuestDatabase, child_id: int, is_active: bool
) -> ChildRecord:
    """Deactivate or reactivate a child; returns the updated record.

    Deactivation hides the child from the panel without deleting their
    history (feature guardrail); this is the only removal path.
    ``is_active`` must be a real bool: the DAO's ``int()`` would
    otherwise silently coerce strings and numerics ("1", 0) into a
    state the caller never asked for.  Raises ValueError when the
    child does not exist.

    Atomicity: existence check, UPDATE and readback run inside the
    connection-scoped lock, so a concurrent opposite transition cannot
    make this call report the other caller's value.
    """
    async with _connection_lock(database):
        dao = ChildrenDao(database)
        if await dao.get(child_id) is None:
            raise ValueError(f"child {child_id} does not exist")
        if not isinstance(is_active, bool):
            raise ValueError(
                f"is_active must be a real bool, got {is_active!r}"
            )
        await dao.set_active(child_id, is_active)
        updated = await dao.get(child_id)
    assert updated is not None
    return updated


async def reorder_children(
    database: NestQuestDatabase, ordered_ids: list[int]
) -> None:
    """Rewrite the children's panel display order in one transaction.

    ``ordered_ids`` must be a complete permutation of the children
    table — every child id exactly once.  A partial list (missing an
    existing child), an unknown id, or a duplicate is rejected with
    ValueError before any write, so the current order survives a
    rejected call.  The DAO enforces this inside its own transaction
    (check and write are atomic under the connection lock); this
    wrapper additionally rejects non-integer ids up front, since
    ``bool`` and floats would silently compare against stored integer
    ids at the SQL layer.
    """
    for child_id in ordered_ids:
        if isinstance(child_id, bool) or not isinstance(child_id, int):
            raise ValueError(
                f"ordered_ids must contain only integer child ids, got "
                f"{child_id!r}"
            )
    await ChildrenDao(database).reorder(ordered_ids)


async def list_children(
    database: NestQuestDatabase, *, active_only: bool = False
) -> list[ChildRecord]:
    """Return children in display order (sort_order, then id)."""
    dao = ChildrenDao(database)
    if active_only:
        return await dao.list_active()
    return await dao.list_all()
