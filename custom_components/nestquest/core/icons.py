"""Namespaced quest-definition icon keys.

A definition's ``icon`` is stored as ``<namespace>:<name>`` where the
namespace is one of :data:`ICON_NAMESPACES`:

- ``lucide:<name>`` / ``fa:<name>`` — ``<name>`` is a lowercase kebab
  name (ASCII ``[a-z0-9-]``, not starting or ending with ``-``).
- ``emoji:<payload>`` — a short emoji string of at most
  :data:`EMOJI_MAX_CODE_POINTS` code points, with no whitespace, no
  control characters and none of ``<``, ``>``, ``&``.

Rows written before namespacing hold a bare Lucide name (``dog``).
:func:`validate_icon` (writes) normalizes such a legacy value to
``lucide:<name>``; :func:`normalize_icon_for_read` (reads) does the same
leniently so legacy rows render without a data migration.

Nothing here imports :mod:`homeassistant`.
"""
from __future__ import annotations

import re
import unicodedata

ICON_NAMESPACE_LUCIDE = "lucide"
ICON_NAMESPACE_FA = "fa"
ICON_NAMESPACE_EMOJI = "emoji"
ICON_NAMESPACES = frozenset(
    {ICON_NAMESPACE_LUCIDE, ICON_NAMESPACE_FA, ICON_NAMESPACE_EMOJI}
)

#: Upper bound on an emoji payload's length in code points — enough for
#: ZWJ sequences such as a family emoji, too short for arbitrary text.
EMOJI_MAX_CODE_POINTS = 8

_KEBAB_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
_EMOJI_FORBIDDEN = frozenset("<>&")


def _is_kebab_name(value: str) -> bool:
    return _KEBAB_NAME.fullmatch(value) is not None


def _is_valid_emoji_payload(value: str) -> bool:
    if not value or len(value) > EMOJI_MAX_CODE_POINTS:
        return False
    return not any(
        char.isspace()
        or char in _EMOJI_FORBIDDEN
        or unicodedata.category(char) == "Cc"
        for char in value
    )


def validate_icon(value: object) -> str | None:
    """Return the canonical namespaced icon key, or raise naming ``icon``.

    ``None`` or an empty/whitespace-only string returns ``None`` (the
    icon is cleared).  Otherwise the raw value is validated untrimmed, so
    edge whitespace or control characters are rejected rather than
    silently stripped.  A value with no ``:`` is a legacy bare Lucide
    name and is stored as ``lucide:<value>``.  An unknown namespace, an
    empty or malformed name, or an invalid emoji payload raises
    ValueError.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"icon must be a string, got {value!r}")
    if not value.strip():
        return None

    namespace, separator, name = value.partition(":")
    if not separator:
        if not _is_kebab_name(value):
            raise ValueError(
                f"icon must be a lowercase kebab name, got {value!r}"
            )
        return f"{ICON_NAMESPACE_LUCIDE}:{value}"

    if namespace not in ICON_NAMESPACES:
        raise ValueError(
            f"icon has an unknown namespace {namespace!r}; expected one of "
            f"{sorted(ICON_NAMESPACES)}"
        )
    if namespace == ICON_NAMESPACE_EMOJI:
        if not _is_valid_emoji_payload(name):
            raise ValueError(
                f"icon emoji must be 1-{EMOJI_MAX_CODE_POINTS} code points "
                f"with no whitespace, control characters or markup, "
                f"got {value!r}"
            )
    elif not _is_kebab_name(name):
        raise ValueError(
            f"icon {namespace} name must be a lowercase kebab name, "
            f"got {value!r}"
        )
    return value


def normalize_icon_for_read(value: str | None) -> str | None:
    """Return a stored icon in namespaced form for output.

    Lenient: ``None``/empty returns ``None``, a recognised namespace is
    returned unchanged, and anything else becomes ``lucide:<value>`` so
    legacy rows render (an unknown name falls through to the frontend's
    fallback icon rather than erroring).
    """
    if not value or not value.strip():
        return None
    namespace, separator, _ = value.partition(":")
    if separator and namespace in ICON_NAMESPACES:
        return value
    return f"{ICON_NAMESPACE_LUCIDE}:{value}"
