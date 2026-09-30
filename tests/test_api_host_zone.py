"""The API host's zone and the effective application timezone (task 7e173881).

With no zone stored the API reads its clock in the host's local time, so
:func:`api.host_zone.effective_timezone` names that host zone — resolved
the way the C library resolves local time — for the panel and admin app
to format in.  Every host configuration here is a temporary file tree.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from api import host_zone


def _host(tmp_path: Path, *, link: str | None = None, name: str | None = None):
    """A fake ``/etc``: ``localtime`` linked into a zoneinfo tree at
    ``link``, and/or an ``/etc/timezone`` file holding ``name``."""
    localtime = tmp_path / "etc" / "localtime"
    timezone_file = tmp_path / "etc" / "timezone"
    localtime.parent.mkdir(parents=True)
    if link is not None:
        target = tmp_path / "usr" / "share" / "zoneinfo" / link
        target.parent.mkdir(parents=True)
        target.write_bytes(b"TZif")
        localtime.symlink_to(target)
    if name is not None:
        timezone_file.write_text(f"{name}\n", encoding="utf-8")
    return {"timezone_file": timezone_file, "localtime": localtime}


def test_tz_environment_variable_wins(tmp_path: Path) -> None:
    paths = _host(tmp_path, link="Europe/Paris")
    assert host_zone.host_timezone({"TZ": "Asia/Kolkata"}, **paths) == "Asia/Kolkata"
    assert host_zone.host_timezone({"TZ": ":Asia/Kolkata"}, **paths) == "Asia/Kolkata"
    assert host_zone.host_timezone({"TZ": ""}, **paths) == "UTC"


def test_localtime_link_names_the_zone(tmp_path: Path) -> None:
    paths = _host(tmp_path, link="America/Argentina/Buenos_Aires")
    assert host_zone.host_timezone({}, **paths) == "America/Argentina/Buenos_Aires"


def test_etc_timezone_names_a_copied_localtime(tmp_path: Path) -> None:
    paths = _host(tmp_path, name="Pacific/Auckland")
    paths["localtime"].write_bytes(b"TZif")
    assert host_zone.host_timezone({}, **paths) == "Pacific/Auckland"


def test_unconfigured_host_runs_utc(tmp_path: Path) -> None:
    assert host_zone.host_timezone({}, **_host(tmp_path)) == "UTC"


@pytest.mark.parametrize("tz", ["EST+5", "Not/AZone", ":/etc/localtime"])
def test_an_unnamed_host_zone_is_empty(tmp_path: Path, tz: str) -> None:
    assert host_zone.host_timezone({"TZ": tz}, **_host(tmp_path)) == ""


def test_unnamed_copied_localtime_is_empty(tmp_path: Path) -> None:
    paths = _host(tmp_path)
    paths["localtime"].write_bytes(b"TZif")
    assert host_zone.host_timezone({}, **paths) == ""


def test_effective_timezone_is_the_stored_zone_else_the_host_zone(
    monkeypatch,
) -> None:
    monkeypatch.setattr(host_zone, "host_timezone", lambda: "Europe/Dublin")
    assert host_zone.effective_timezone("America/Chicago") == "America/Chicago"
    assert host_zone.effective_timezone("") == "Europe/Dublin"
