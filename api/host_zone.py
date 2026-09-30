"""The API's effective application timezone (task 7e173881).

The admin-stored ``timezone`` setting is the single source of local-time
truth; stored empty, the API reads its clock in the API host's local
time.  :func:`effective_timezone` names the zone the API actually uses —
the stored zone, or else the host's own IANA zone — so the panel cards
and the admin app format local time in exactly the API's zone instead of
guessing with Home Assistant's or the browser's.  ``""`` only when the
host's zone genuinely cannot be named.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _valid_zone(name: str) -> str:
    """Return ``name`` if it is a loadable IANA zone key, else ``""``."""
    name = name.strip().removeprefix(":")
    if not name:
        return ""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ""
    return name


def host_timezone(
    environ: Mapping[str, str] = os.environ,
    timezone_file: Path = Path("/etc/timezone"),
    localtime: Path = Path("/etc/localtime"),
) -> str:
    """Name the API host's local zone as an IANA key, or ``""``.

    In the order the C library honours them: the ``TZ`` environment
    variable, then the ``/etc/localtime`` zoneinfo link (with Debian's
    ``/etc/timezone`` naming it when the link is a copy).  A host with
    none of them configured runs UTC.  A setting that names no IANA
    zone (a POSIX rule string, a copied file) is ``""``.
    """
    configured = environ.get("TZ")
    if configured is not None:
        # An empty TZ is UTC to the C library.
        return _valid_zone(configured) if configured.strip() else "UTC"
    if localtime.is_symlink():
        target = str(localtime.resolve())
        marker = "/zoneinfo/"
        if marker in target:
            return _valid_zone(target.split(marker, 1)[1])
    if timezone_file.is_file():
        return _valid_zone(timezone_file.read_text(encoding="utf-8"))
    if not localtime.exists():
        return "UTC"
    return ""


def effective_timezone(stored: str) -> str:
    """The zone the API reads its clock in: ``stored``, else the host's."""
    return stored or host_timezone()
