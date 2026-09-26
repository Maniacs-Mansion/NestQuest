"""Admin-plane settings route tests (task 2b3de7e5).

These tests exercise the admin plane's settings read and update routes
against the ASGI app with httpx, reusing the shared local-RSA-key/
stubbed-JWKS harness (:mod:`tests.admin_jwt_harness`) so an admin JWT
genuinely authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.  The stored settings
document is read back through the SAME core copy the app uses
(``nestquest_core.*``; see the two-copy caveat in api/nestquest_core.py)
via its :class:`nestquest_core.dao_meta.MetaStateDao`, so persistence is
proven against the DATABASE the routes wrote, not a parallel copy.

Proven per the done-condition, everything read back through the API:

- ``GET /api/v1/admin/settings`` returns the current effective settings
  — the twelve documented fields at their defaults on a fresh database.
- ``PATCH /api/v1/admin/settings`` PERSISTS the supplied fields and the
  NEXT read reflects them; a later partial update merges onto the
  current effective settings (omitted fields keep their stored value),
  and the document is stored under the well-known ``nestquest_meta_state``
  key.
- An invalid value (a non-positive or boolean horizon, a non-strict
  time, a non-bool toggle, a non-string target) is rejected with 422
  naming the field, and the stored settings are UNCHANGED — the next
  read still shows the previous value.  An unknown field is rejected
  the same way, also when mixed with a valid field (validate
  everything before writing).
- A corrupt stored document (invalid JSON, a non-object, an invalid
  field value) does not crash the service: the read falls back to the
  defaults, per field where possible.
- Authentication runs through the router's ONE ``require_admin``
  dependency: a non-admin JWT is 403 and an absent credential is 401
  on both routes — and no refused patch writes anything.
"""
from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest

from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

# The meta-state DAO through the SAME core copy the app uses
# (nestquest_core.*, NOT the conftest-stubbed custom_components copy) —
# used for the tests' database assertions only; the routes reach it
# through api.nestquest_core.
_dao_meta = importlib.import_module("nestquest_core.dao_meta")

#: The well-known ``nestquest_meta_state`` key the API stores its
#: settings under — asserted literally so the contract is pinned here,
#: independent of the core constant.
SETTINGS_META_KEY = "settings"

#: The all-defaults effective settings a fresh database reports — the
#: documented twelve fields, asserted literally so the payload contract is
#: pinned here, independent of the core constants.
DEFAULT_SETTINGS = {
    "horizon_days": 14,
    "day_rollover_time": "00:00",
    "notify_target": "",
    "morning_summary_time": "08:00",
    "afternoon_reminder_time": "15:00",
    "end_of_day_report_time": "20:00",
    "morning_summary_enabled": True,
    "afternoon_reminder_enabled": True,
    "end_of_day_report_enabled": True,
    "celebration_enabled": True,
    "timezone": "",
    "timezone_configured": False,
}


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
async def settings_client(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database.

    The same runner the children tests use (stubbed JWKS, no network);
    the fixture also exposes the app's ONE database connection so tests
    can read (or corrupt) the stored settings document itself.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


# --- read: the effective settings, defaults on a fresh database --------


async def test_get_settings_returns_defaults_on_a_fresh_database(
    settings_client: SimpleNamespace,
) -> None:
    """GET returns the twelve documented fields at their defaults."""
    response = await settings_client.client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == DEFAULT_SETTINGS


# --- update: persists, and the NEXT read reflects it --------------------


async def test_update_persists_and_the_next_read_reflects_it(
    settings_client: SimpleNamespace,
) -> None:
    """PATCH persists the supplied fields; GET reads them back."""
    client = settings_client.client
    changes = {
        "horizon_days": 21,
        "day_rollover_time": "03:30",
        "notify_target": "notify.mobile_app_dads_phone",
        "celebration_enabled": False,
    }
    patched = await client.patch(
        "/api/v1/admin/settings", json=changes, headers=_admin_headers()
    )
    assert patched.status_code == 200
    expected = {**DEFAULT_SETTINGS, **changes}
    assert patched.json() == expected

    # The NEXT read reflects the persisted settings...
    reread = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert reread.status_code == 200
    assert reread.json() == expected

    # ...and the DATABASE holds the merged document: the complete twelve
    # fields, keyed by field name, under the well-known meta_state key.
    raw = await _dao_meta.MetaStateDao(settings_client.database).get(
        SETTINGS_META_KEY
    )
    assert raw is not None
    assert json.loads(raw) == expected


async def test_partial_update_merges_onto_the_current_settings(
    settings_client: SimpleNamespace,
) -> None:
    """A later PATCH changes only its own fields; the rest survive."""
    client = settings_client.client
    first = await client.patch(
        "/api/v1/admin/settings",
        json={"horizon_days": 7, "notify_target": " notify.x "},
        headers=_admin_headers(),
    )
    assert first.status_code == 200
    # The notify target went through the core's own normalizer: stripped.
    assert first.json()["horizon_days"] == 7
    assert first.json()["notify_target"] == "notify.x"

    second = await client.patch(
        "/api/v1/admin/settings",
        json={"morning_summary_time": "07:45"},
        headers=_admin_headers(),
    )
    assert second.status_code == 200
    assert second.json() == {
        **DEFAULT_SETTINGS,
        "horizon_days": 7,
        "notify_target": "notify.x",
        "morning_summary_time": "07:45",
    }

    reread = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert reread.json() == second.json()


async def test_empty_update_is_a_noop(
    settings_client: SimpleNamespace,
) -> None:
    """PATCHing no fields leaves the effective settings as they are."""
    client = settings_client.client
    response = await client.patch(
        "/api/v1/admin/settings", json={}, headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == DEFAULT_SETTINGS


async def test_null_resets_a_field_to_its_default(
    settings_client: SimpleNamespace,
) -> None:
    """A JSON ``null`` maps to the field's default (None-as-absent)."""
    client = settings_client.client
    set_horizon = await client.patch(
        "/api/v1/admin/settings",
        json={"horizon_days": 7},
        headers=_admin_headers(),
    )
    assert set_horizon.status_code == 200
    assert set_horizon.json()["horizon_days"] == 7

    reset = await client.patch(
        "/api/v1/admin/settings",
        json={"horizon_days": None},
        headers=_admin_headers(),
    )
    assert reset.status_code == 200
    assert reset.json()["horizon_days"] == 14

    reread = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert reread.json()["horizon_days"] == 14


async def test_timezone_configured_round_trips_with_an_explicit_empty_zone(
    settings_client: SimpleNamespace,
) -> None:
    """An explicit empty (host-local) zone persists as configured.

    The admin clearing the zone PATCHes ``timezone: ""`` together with
    ``timezone_configured: true``; the NEXT read — a reopened settings
    screen — sees the marker, so the empty value is a persisted choice
    rather than a fresh install to auto-set.
    """
    client = settings_client.client
    fresh = await client.get("/api/v1/admin/settings", headers=_admin_headers())
    assert fresh.json()["timezone_configured"] is False

    patched = await client.patch(
        "/api/v1/admin/settings",
        json={"timezone": "", "timezone_configured": True},
        headers=_admin_headers(),
    )
    assert patched.status_code == 200
    expected = {**DEFAULT_SETTINGS, "timezone_configured": True}
    assert patched.json() == expected

    reread = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert reread.json() == expected
    raw = await _dao_meta.MetaStateDao(settings_client.database).get(
        SETTINGS_META_KEY
    )
    assert raw is not None
    assert json.loads(raw)["timezone_configured"] is True


# --- validation: rejected values never change the stored settings -------


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"horizon_days": 0}, "horizon_days"),
        ({"horizon_days": -3}, "horizon_days"),
        # A bool is rejected — the core's guardrail survives the route.
        ({"horizon_days": True}, "horizon_days"),
        ({"horizon_days": "soon"}, "horizon_days"),
        ({"day_rollover_time": "25:00"}, "day_rollover_time"),
        ({"day_rollover_time": "7:30"}, "day_rollover_time"),
        ({"morning_summary_enabled": "yes"}, "morning_summary_enabled"),
        ({"celebration_enabled": 1}, "celebration_enabled"),
        ({"notify_target": 5}, "notify_target"),
        ({"timezone_configured": "true"}, "timezone_configured"),
        ({"timezone_configured": 1}, "timezone_configured"),
    ],
)
async def test_invalid_value_is_rejected_and_stored_settings_unchanged(
    settings_client: SimpleNamespace, changes: dict[str, object], field: str
) -> None:
    """A rejected value is 422 naming the field; the next read is same."""
    client = settings_client.client
    seeded = await client.patch(
        "/api/v1/admin/settings",
        json={
            "horizon_days": 21,
            "day_rollover_time": "01:30",
            "morning_summary_enabled": False,
        },
        headers=_admin_headers(),
    )
    assert seeded.status_code == 200
    before = seeded.json()

    response = await client.patch(
        "/api/v1/admin/settings", json=changes, headers=_admin_headers()
    )
    assert response.status_code == 422, changes
    assert field in str(response.json()["detail"]), changes

    after = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert after.status_code == 200
    assert after.json() == before


async def test_unknown_field_is_rejected_and_stored_settings_unchanged(
    settings_client: SimpleNamespace,
) -> None:
    """An unknown field is 422 naming it — alone or beside a valid one."""
    client = settings_client.client
    unknown = await client.patch(
        "/api/v1/admin/settings",
        json={"bogus_setting": 1},
        headers=_admin_headers(),
    )
    assert unknown.status_code == 422
    assert "bogus_setting" in str(unknown.json()["detail"])

    mixed = await client.patch(
        "/api/v1/admin/settings",
        json={"horizon_days": 7, "bogus_setting": 1},
        headers=_admin_headers(),
    )
    assert mixed.status_code == 422
    assert "bogus_setting" in str(mixed.json()["detail"])

    # Neither rejection wrote anything, not even the valid sibling.
    after = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert after.json() == DEFAULT_SETTINGS


async def test_non_object_body_is_422(
    settings_client: SimpleNamespace,
) -> None:
    """A body that is not a JSON object is FastAPI's 422 (the shape)."""
    client = settings_client.client
    for body in ([1, 2], "nope", 5):
        response = await client.patch(
            "/api/v1/admin/settings", json=body, headers=_admin_headers()
        )
        assert response.status_code == 422, body
    # A bare JSON null is likewise not an object.
    response = await client.patch(
        "/api/v1/admin/settings",
        content=b"null",
        headers={**_admin_headers(), "content-type": "application/json"},
    )
    assert response.status_code == 422

    after = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert after.json() == DEFAULT_SETTINGS


# --- resilience: a corrupt stored document does not crash the service ---


async def test_corrupt_stored_document_falls_back_to_defaults(
    settings_client: SimpleNamespace,
) -> None:
    """GET degrades gracefully over an unusable settings document."""
    client = settings_client.client
    dao = _dao_meta.MetaStateDao(settings_client.database)

    # Not JSON at all: all defaults, no crash.
    await dao.set(SETTINGS_META_KEY, "{not-json")
    response = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == DEFAULT_SETTINGS

    # JSON but not an object: all defaults, no crash.
    await dao.set(SETTINGS_META_KEY, json.dumps([1, 2]))
    response = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == DEFAULT_SETTINGS

    # An object with one invalid field: PER-FIELD fallback — the valid
    # sibling survives, the invalid one falls back to its default.
    await dao.set(
        SETTINGS_META_KEY,
        json.dumps({"horizon_days": 7, "day_rollover_time": "soon"}),
    )
    response = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {**DEFAULT_SETTINGS, "horizon_days": 7}


# --- authentication: the ONE require_admin dependency guards both routes


async def test_settings_routes_refuse_non_admin_and_absent_credentials(
    settings_client: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401; none write."""
    client = settings_client.client
    non_admin = make_token(groups=("some-other-group",))
    forbidden_get = await client.get(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden_get.status_code == 403
    assert forbidden_get.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )
    forbidden_patch = await client.patch(
        "/api/v1/admin/settings",
        json={"horizon_days": 7},
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden_patch.status_code == 403

    absent_get = await client.get("/api/v1/admin/settings")
    assert absent_get.status_code == 401
    absent_patch = await client.patch(
        "/api/v1/admin/settings", json={"horizon_days": 7}
    )
    assert absent_patch.status_code == 401

    # No refused request changed anything: the settings are untouched.
    after = await client.get(
        "/api/v1/admin/settings", headers=_admin_headers()
    )
    assert after.json() == DEFAULT_SETTINGS
