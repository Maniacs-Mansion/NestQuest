"""Durable settings store for the NestQuest API service.

The API service has NO Home Assistant config entry, so it cannot build
:class:`~.settings.NestQuestSettings` from ``entry.options`` the way the
integration does.  This module gives the API its own durable settings
source: a JSON document kept in the EXISTING ``nestquest_meta_state``
key/value table (:class:`~.dao_meta.MetaStateDao`) under the well-known
key :data:`SETTINGS_META_KEY` — no schema change, no new table —
validated through the SAME field table the settings object is built
from (:data:`~.settings._FIELDS`, the table driving
``from_options``/``from_options_resilient``).  No validation rule is
re-implemented here.

OWNERSHIP: the API now owns settings in the database.  The
integration's Home-Assistant config-entry options remain a temporary,
SEPARATE source until Feature 18 converts the integration into a thin
API client; the two are deliberately NOT unified here, and neither
side reads the other's values.

STORED SERIALIZATION — the document at ``SETTINGS_META_KEY`` is a JSON
object holding exactly the ELEVEN settings fields, keyed by field name
(which equals the ``CONF_*`` option key for every field), complete
after the first update:

- ``horizon_days`` — int >= 1,
- ``day_rollover_time``, ``morning_summary_time``,
  ``afternoon_reminder_time``, ``end_of_day_report_time`` — strict
  24-hour ``HH:MM`` strings,
- ``notify_target`` — a string (a padded value is stripped by the
  core's normalizer),
- ``morning_summary_enabled``, ``afternoon_reminder_enabled``,
  ``end_of_day_report_enabled``, ``celebration_enabled`` — real
  booleans,
- ``timezone`` — ``""`` (the API host's local time) or an IANA time
  zone name such as ``America/New_York``.  A document stored before
  this field existed simply lacks it and resolves to ``""``.

Only values whose core validators ACCEPTED are ever written, so a
stored document always round-trips through the core's option builders.
An absent key (a fresh database) resolves to the all-defaults
settings, and a corrupt document degrades to defaults or per-field
defaults rather than crashing the service (see :func:`load_settings`).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from .const import LOGGER
from .dao_meta import MetaStateDao
from .db import NestQuestDatabase
from .settings import NestQuestSettings, _FIELDS

#: The well-known ``nestquest_meta_state`` key holding the settings
#: document.  One key, one JSON object — the same table the missed
#: sweep's watermark already uses, so no migration is needed.
SETTINGS_META_KEY = "settings"

#: The per-field resolution table keyed by field name: each row is the
#: ``(default, validator)`` pair the settings module's ``_FIELDS`` table
#: carries for that field.  ``update_settings`` resolves each PROVIDED
#: field through its row's validator — the SAME core validators
#: ``from_options`` applies — and never re-implements one here.
#: (Field names equal the ``CONF_*`` option keys, so one dict serves
#: both the API's field names and the stored document's keys.)
_RESOLUTIONS: dict[str, tuple[Any, Any]] = {
    key: (default, validator) for _field, key, default, validator in _FIELDS
}

#: The known field names, in the settings module's field order — the
#: allowed keys of an update body and the stored document's key set.
_FIELD_NAMES: tuple[str, ...] = tuple(
    key for _field, key, _default, _validator in _FIELDS
)

#: One asyncio.Lock per (connection wrapper, running loop), the missed
#: sweep's pattern: the whole stored-document read → merge → write span
#: is one critical section, so two concurrent updates queue instead of
#: one losing the other's change — the loser re-reads the document
#: INSIDE the lock and merges onto the winner's settings.
_SETTINGS_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def _settings_lock(database: NestQuestDatabase) -> asyncio.Lock:
    """Return the settings lock bound to ``database``'s running loop."""
    loop = asyncio.get_running_loop()
    key = (id(database), id(loop))
    lock = _SETTINGS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SETTINGS_LOCKS[key] = lock
    return lock


async def _load_document(database: NestQuestDatabase) -> dict[str, Any]:
    """Read and decode the stored settings document (empty when unusable).

    An absent key — a fresh database that never updated settings — and
    an unparseable value (invalid JSON, or JSON that is not an object)
    return an empty mapping, which the option builders resolve to the
    all-defaults settings; the corrupt cases log a warning first.  A
    parseable object is returned as stored (its per-field validity is
    the builder's concern, not this reader's).
    """
    raw = await MetaStateDao(database).get(SETTINGS_META_KEY)
    if raw is None:
        return {}
    try:
        document = json.loads(raw)
    except ValueError:
        LOGGER.warning(
            "NestQuest stored settings (meta_state key %r) are not valid "
            "JSON; falling back to the default settings",
            SETTINGS_META_KEY,
        )
        return {}
    if not isinstance(document, dict):
        LOGGER.warning(
            "NestQuest stored settings (meta_state key %r) are not a JSON "
            "object; falling back to the default settings",
            SETTINGS_META_KEY,
        )
        return {}
    return document


def _named(field: str, error: ValueError) -> str:
    """Return a field-named message for a rejected validator value.

    The horizon, time and notify-target validators already name their
    field in the message; the boolean validator's message is generic
    (``expected a boolean, got ...``), so it gets the field prefixed.
    Every rejected update's error therefore names its field either way.
    """
    message = str(error)
    if message.startswith(f"{field} "):
        return message
    return f"{field}: {message}"


async def load_settings(database: NestQuestDatabase) -> NestQuestSettings:
    """Return the current effective settings stored for ``database``.

    Reads :data:`SETTINGS_META_KEY` and resolves the stored document
    through the core settings validators, with each absent field
    falling back to its default.  An absent key and an unparseable
    document fall back to the all-defaults settings (via
    :func:`_load_document`), and a parseable document with a single
    invalid FIELD falls back PER FIELD — through
    :meth:`NestQuestSettings.from_options_resilient`, the core's own
    resilient builder — so a corrupt sibling never resets the stored
    values around it.  This never raises: the service must keep
    serving reads even over a corrupt store.
    """
    document = await _load_document(database)
    return NestQuestSettings.from_options_resilient(document)


async def update_settings(
    database: NestQuestDatabase, changes: Mapping[str, Any]
) -> NestQuestSettings:
    """Validate ``changes`` and persist them as the effective settings.

    ``changes`` maps settings field names to new values.  EVERY name is
    checked against the known field table BEFORE anything is validated
    or written: an unknown name raises a ``ValueError`` naming it (and
    the known names), leaving the stored settings untouched.  Each
    PROVIDED field is then resolved from_options-style — its
    :data:`~.settings._FIELDS` validator applied, with a JSON ``null``
    mapping to the field's default (the settings module's uniform
    None-as-absent rule) — and an invalid value raises a ``ValueError``
    naming the field, also BEFORE anything is written, so a rejected
    update can never leave a half-applied document behind.

    The validated changes are merged onto the current effective
    settings and the merged (complete, eleven-field) document is persisted
    in one atomic upsert; the updated settings are returned.  The whole
    read → merge → write span runs inside the per-database settings
    lock, so concurrent updates queue instead of interleaving.
    """
    if not isinstance(changes, Mapping):
        raise ValueError(
            "settings changes must be a JSON object mapping field names "
            "to values"
        )
    unknown = sorted(
        str(name) for name in changes if name not in _RESOLUTIONS
    )
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        known = ", ".join(_FIELD_NAMES)
        raise ValueError(
            f"unknown settings field(s): {listed}; known fields: {known}"
        )
    async with _settings_lock(database):
        current = await load_settings(database)
        document: dict[str, Any] = {
            field: getattr(current, field) for field in _FIELD_NAMES
        }
        for name, raw_value in changes.items():
            default, validator = _RESOLUTIONS[name]
            try:
                document[name] = validator(
                    default if raw_value is None else raw_value
                )
            except ValueError as error:
                raise ValueError(_named(name, error)) from error
        await MetaStateDao(database).set(
            SETTINGS_META_KEY, json.dumps(document, sort_keys=True)
        )
    return NestQuestSettings(**document)
