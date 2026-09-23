"""Admin-plane quest-definition route tests (task b586a2f1).

These tests exercise the admin plane's quest-definition routes against
the ASGI app with httpx, reusing the shared local-RSA-key/stubbed-JWKS
harness (:mod:`tests.admin_jwt_harness`) so an admin JWT genuinely
authenticates — signature, issuer, audience, expiry and the
nestquest-admins group — with NO network access.

Every done-condition case is proven against the DATABASE, read through
the SAME core copy the app uses (``nestquest_core.*``; see the two-copy
caveat in api/nestquest_core.py):

- Authentication runs through the router's ONE ``require_admin``
  dependency: an admin JWT passes, a JWT without the group is 403, an
  absent credential is 401 — and no definition is written.
- ``POST /api/v1/admin/quest-definitions``: the created definition
  EXISTS with its title, description, icon, decoded rule, assignees
  and windows exactly as posted.
- ``PATCH /api/v1/admin/quest-definitions/{id}``: an edit PERSISTS the
  supplied fields and leaves omitted fields untouched (exclude_unset
  semantics); a supplied ``windows`` list replaces the whole set;
  assignment is not settable through the edit.
- ``PATCH /api/v1/admin/quest-definitions/{id}/active`` with
  ``is_active: false`` sets the flag FALSE and the definition STILL
  EXISTS with its rule, assignees and windows (never hard-deleted);
  reactivation restores it.

Error mapping (documented in api/routes_admin.py): a core ValueError
for a non-existent DEFINITION is 404; every other core ValueError — a
rejected rule (RuleValidationError), a bad window name or due time, a
rejected assignee list (an unknown assignee arrives in the BODY, so it
is 422, never 404) — is 422, the same failure class FastAPI reports
for malformed bodies.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from tests.admin_jwt_harness import (
    ADMIN_KEY,
    KID,
    AdminRunner,
    jwks_for,
    make_token,
)

# The quest-definition business layer and its DAO through the SAME core
# copy the app uses (nestquest_core.*, NOT the conftest-stubbed
# custom_components copy) — used for the tests' database assertions
# only; the routes reach them through api.nestquest_core.
_quest_definitions = importlib.import_module(
    "nestquest_core.quest_definitions"
)
_dao_rules = importlib.import_module("nestquest_core.dao_rules")


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _weekly_rule_body() -> dict[str, object]:
    """A valid weekly rule body: Mondays and Wednesdays from 2026-03-02."""
    return {
        "rule_type": "weekly",
        "interval": 1,
        "weekday_set": [0, 2],
        "start_date": "2026-03-02",
    }


def _weekly_rule_dict() -> dict[str, object]:
    """The lossless dict form _weekly_rule_body() must decode back to."""
    return {
        "rule_type": "weekly",
        "interval": 1,
        "weekday_set": [0, 2],
        "day_of_month": None,
        "nth_weekday": None,
        "nth_weekday_weekday": None,
        "month": None,
        "start_date": "2026-03-02",
        "end_date": None,
    }


async def _create_children(
    client: object, names: tuple[str, ...]
) -> list[int]:
    """Create ACTIVE children through the admin children route."""
    ids = []
    for name in names:
        created = await client.post(
            "/api/v1/admin/children",
            json={"display_name": name},
            headers=_admin_headers(),
        )
        assert created.status_code == 201
        ids.append(created.json()["id"])
    return ids


async def _create_definition(
    client: object, assignee_ids: list[int]
) -> object:
    """POST a valid two-window definition for the given assignees."""
    return await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Tidy the den",
            "rule": _weekly_rule_body(),
            "assignee_child_ids": assignee_ids,
            "windows": ["morning", ["evening", "19:30"]],
            "description": "Put everything back where it belongs.",
            "icon": "toy-box",
        },
        headers=_admin_headers(),
    )


async def _definitions_by_id(database: object) -> dict[int, object]:
    """Every ACTIVE definition bundle through the app's core copy."""
    bundles = await _quest_definitions.list_active_definitions(database)
    return {bundle.definition.id: bundle for bundle in bundles}


@pytest.fixture
async def admin_questdefs(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database.

    The same runner the auth and children tests use (stubbed JWKS, no
    network); the fixture also exposes the app's ONE database connection
    so tests assert the routes' effects on the stored rows themselves.
    """
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


# --- authentication: the ONE require_admin dependency guards every route ---


async def test_quest_definition_routes_refuse_non_admin_and_absent(
    admin_questdefs: SimpleNamespace,
) -> None:
    """A non-admin JWT is 403, an absent credential is 401: nothing written."""
    client = admin_questdefs.client
    body = {"title": "Sweep the porch"}
    non_admin = make_token(groups=("some-other-group",))

    forbidden = await client.post(
        "/api/v1/admin/quest-definitions",
        json=body,
        headers={"Authorization": f"Bearer {non_admin}"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == (
        "Admin access requires membership in the nestquest-admins group"
    )

    unauthenticated_create = await client.post(
        "/api/v1/admin/quest-definitions", json=body
    )
    assert unauthenticated_create.status_code == 401

    unauthenticated_edit = await client.patch(
        "/api/v1/admin/quest-definitions/1", json={"title": "X"}
    )
    assert unauthenticated_edit.status_code == 401

    unauthenticated_active = await client.patch(
        "/api/v1/admin/quest-definitions/1/active", json={"is_active": False}
    )
    assert unauthenticated_active.status_code == 401

    # No route ran its handler: no definition was written.
    assert await _definitions_by_id(admin_questdefs.database) == {}


# --- create -----------------------------------------------------------------


async def test_create_persists_definition_with_assignees_and_windows(
    admin_questdefs: SimpleNamespace,
) -> None:
    """POST /quest-definitions persists rule, assignees and windows."""
    client = admin_questdefs.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))

    response = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Tidy the den",
            "rule": _weekly_rule_body(),
            "assignee_child_ids": [ada, bo],
            "windows": ["morning", ["evening", "19:30"]],
            "description": "Put everything back where it belongs.",
            "icon": "toy-box",
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 201
    payload = response.json()
    definition_id = payload["id"]
    # The serialized shape is the documented definition payload.
    assert set(payload) == {
        "id",
        "title",
        "description",
        "icon",
        "is_active",
        "rule",
        "assignees",
        "windows",
    }
    assert payload["title"] == "Tidy the den"
    assert payload["description"] == "Put everything back where it belongs."
    assert payload["icon"] == "toy-box"
    assert payload["is_active"] is True
    assert payload["rule"] == _weekly_rule_dict()
    assert {a["id"]: a["display_name"] for a in payload["assignees"]} == {
        ada: "Ada",
        bo: "Bo",
    }
    assert {w["window"]: w["due_time"] for w in payload["windows"]} == {
        "morning": None,
        "evening": "19:30",
    }

    # Database proof through the app's core copy: the definition, its
    # decoded rule, its assignees and its windows all exist as posted.
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.title == "Tidy the den"
    assert stored.definition.description == (
        "Put everything back where it belongs."
    )
    assert stored.definition.icon == "toy-box"
    assert stored.definition.is_active is True
    assert stored.rule.to_dict() == _weekly_rule_dict()
    assert sorted(child.id for child in stored.assignees) == [ada, bo]
    assert {(w.window, w.due_time) for w in stored.windows} == {
        ("morning", None),
        ("evening", "19:30"),
    }


async def test_create_with_required_fields_only_uses_core_defaults(
    admin_questdefs: SimpleNamespace,
) -> None:
    """Omitted optional fields default to NULL through the core layer."""
    client = admin_questdefs.client
    ada = (await _create_children(client, ("Ada",)))[0]

    response = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Water the plants",
            "rule": _weekly_rule_body(),
            "assignee_child_ids": [ada],
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["description"] is None
    assert payload["icon"] is None
    stored = (await _definitions_by_id(admin_questdefs.database))[
        payload["id"]
    ]
    assert stored.definition.description is None
    assert stored.definition.icon is None


async def test_create_without_required_fields_is_422(
    admin_questdefs: SimpleNamespace,
) -> None:
    """A body missing any required field is 422 and creates nothing."""
    client = admin_questdefs.client
    bodies: list[dict[str, object]] = [
        {},  # everything missing
        {"title": "Tidy the den"},  # rule, assignees, windows missing
        {
            "title": "Tidy the den",
            "rule": _weekly_rule_body(),
        },  # assignees and windows missing
        {
            "title": "Tidy the den",
            "rule": _weekly_rule_body(),
            "assignee_child_ids": [1],
        },  # windows missing
    ]
    for body in bodies:
        response = await client.post(
            "/api/v1/admin/quest-definitions",
            json=body,
            headers=_admin_headers(),
        )
        assert response.status_code == 422, body
    assert await _definitions_by_id(admin_questdefs.database) == {}


@pytest.mark.parametrize(
    "override",
    [
        {"title": ""},  # empty: the core rejects it
        {"title": "   "},  # whitespace-only: empty to a parent
        {"assignee_child_ids": []},  # empty assignee list
        {"assignee_child_ids": [999, 1000]},  # unknown children: 422 not 404
        {"assignee_child_ids": ["Ada"]},  # wrong-typed ids
        {"windows": []},  # empty window set
        {"windows": "morning"},  # not a list
        {"windows": ["attic"]},  # not a const.QUEST_WINDOWS name
        {"windows": [["morning", "25:00"]]},  # not a 24-hour time
        {"windows": [["morning", "8:00"]]},  # not a strict HH:MM
        {"windows": [["morning", None], "morning"]},  # duplicate window
        {"rule": {"rule_type": "weekly"}},  # weekly without weekday_set
        {"rule": {"rule_type": "fortnightly"}},  # unknown rule_type
        {"rule": {"rule_type": "daily", "interval": 0}},  # interval < 1
        {"rule": {"rule_type": "weekly", "weekday_set": [7]}},  # out of range
        {"rule": {"rule_type": "monthly_day"}},  # missing day_of_month
        {"rule": {"rule_type": "daily", "day_of_month": 5}},  # forbidden field
        {"rule": {"rule_type": "daily", "start_date": "2026-13-01"}},
        {"rule": None},  # an explicit null rule is a supplied invalid value
    ],
)
async def test_create_rejections_are_422_and_persist_nothing(
    admin_questdefs: SimpleNamespace, override: dict[str, object]
) -> None:
    """Rejected bodies are 422 and never create a definition."""
    client = admin_questdefs.client
    ids = await _create_children(client, ("Ada", "Bo"))
    body: dict[str, object] = {
        "title": "Tidy the den",
        "rule": _weekly_rule_body(),
        "assignee_child_ids": ids,
        "windows": ["morning", ["evening", "19:30"]],
    }
    body.update(override)

    response = await client.post(
        "/api/v1/admin/quest-definitions",
        json=body,
        headers=_admin_headers(),
    )
    assert response.status_code == 422, override
    assert await _definitions_by_id(admin_questdefs.database) == {}


# --- edit -------------------------------------------------------------------


async def test_edit_persists_supplied_fields_and_leaves_omitted_untouched(
    admin_questdefs: SimpleNamespace,
) -> None:
    """PATCH persists exactly the supplied fields (exclude_unset)."""
    client = admin_questdefs.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    created = await _create_definition(client, [ada, bo])
    assert created.status_code == 201
    definition_id = created.json()["id"]
    dao = _dao_rules.QuestDefinitionsDao(admin_questdefs.database)
    original_rule_id = (await dao.get(definition_id)).schedule_rule_id

    # Only title and windows: description, icon, rule and assignees
    # must survive; the supplied windows REPLACE the whole set.
    edited = await client.patch(
        f"/api/v1/admin/quest-definitions/{definition_id}",
        json={"title": "Clear the den", "windows": ["afternoon"]},
        headers=_admin_headers(),
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Clear the den"
    assert {w["window"]: w["due_time"] for w in edited.json()["windows"]} == {
        "afternoon": None
    }
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.title == "Clear the den"
    assert {(w.window, w.due_time) for w in stored.windows} == {
        ("afternoon", None)
    }
    # Omitted fields were never passed to the core: unchanged.
    assert stored.definition.description == (
        "Put everything back where it belongs."
    )
    assert stored.definition.icon == "toy-box"
    assert stored.rule.to_dict() == _weekly_rule_dict()
    # Assignment is not settable through the edit route: untouched.
    assert sorted(child.id for child in stored.assignees) == [ada, bo]

    # A second edit touching only the rule leaves the metadata and the
    # windows alone, and updates the rule row IN PLACE (same rule id).
    rescheduled = await client.patch(
        f"/api/v1/admin/quest-definitions/{definition_id}",
        json={"rule": {"rule_type": "daily", "start_date": "2026-04-01"}},
        headers=_admin_headers(),
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["rule"]["rule_type"] == "daily"
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.title == "Clear the den"
    assert {(w.window, w.due_time) for w in stored.windows} == {
        ("afternoon", None)
    }
    assert stored.rule.to_dict() == {
        "rule_type": "daily",
        "interval": 1,
        "weekday_set": None,
        "day_of_month": None,
        "nth_weekday": None,
        "nth_weekday_weekday": None,
        "month": None,
        "start_date": "2026-04-01",
        "end_date": None,
    }
    record = await dao.get(definition_id)
    assert record.schedule_rule_id == original_rule_id
    rule_row = await _dao_rules.ScheduleRulesDao(
        admin_questdefs.database
    ).get(record.schedule_rule_id)
    assert rule_row.rule_type == "daily"
    assert rule_row.start_date == "2026-04-01"


async def test_edit_can_clear_description_and_icon_explicitly(
    admin_questdefs: SimpleNamespace,
) -> None:
    """An explicit null description/icon clears them (the core's edit path).

    Unlike the children edit, the definition edit supports clearing: a
    supplied null IS forwarded and writes NULL; everything omitted
    stays untouched.
    """
    client = admin_questdefs.client
    ada = (await _create_children(client, ("Ada",)))[0]
    created = await _create_definition(client, [ada])
    definition_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/admin/quest-definitions/{definition_id}",
        json={"description": None, "icon": None},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["icon"] is None
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.description is None
    assert stored.definition.icon is None
    assert stored.definition.title == "Tidy the den"
    assert stored.rule.to_dict() == _weekly_rule_dict()


async def test_edit_unknown_definition_is_404(
    admin_questdefs: SimpleNamespace,
) -> None:
    """An edit naming a definition that does not exist is 404."""
    response = await admin_questdefs.client.patch(
        "/api/v1/admin/quest-definitions/999",
        json={"title": "Ghost chore"},
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Quest definition not found"


async def test_edit_rejections_are_422_and_change_nothing(
    admin_questdefs: SimpleNamespace,
) -> None:
    """A rejected rule or window set is 422; the stored state survives.

    The core rejects BEFORE any write (and the DAO edit runs in one
    transaction), so a 422 never leaves a half-applied change behind.
    """
    client = admin_questdefs.client
    ada = (await _create_children(client, ("Ada",)))[0]
    created = await _create_definition(client, [ada])
    definition_id = created.json()["id"]

    rejected_bodies: list[dict[str, object]] = [
        {"rule": {"rule_type": "weekly"}},  # weekly without weekday_set
        {"rule": None},  # an explicit null rule is rejected by the core
        {"windows": ["attic"]},  # unknown window name
        {"windows": None},  # an explicit null window set is rejected
        {"title": ""},  # the core rejects an empty title
    ]
    for body in rejected_bodies:
        response = await client.patch(
            f"/api/v1/admin/quest-definitions/{definition_id}",
            json=body,
            headers=_admin_headers(),
        )
        assert response.status_code == 422, body

    # Database proof: nothing changed for any rejected call.
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.title == "Tidy the den"
    assert stored.definition.description == (
        "Put everything back where it belongs."
    )
    assert stored.rule.to_dict() == _weekly_rule_dict()
    assert {(w.window, w.due_time) for w in stored.windows} == {
        ("morning", None),
        ("evening", "19:30"),
    }


# --- set_active -------------------------------------------------------------


async def test_set_active_toggles_the_flag_and_the_definition_survives(
    admin_questdefs: SimpleNamespace,
) -> None:
    """is_active=false deactivates; the definition STILL exists intact.

    Deactivation is the only removal path: the row, rule, assignees and
    windows all survive, and reactivation through the same route
    restores the flag without anything having been lost.
    """
    client = admin_questdefs.client
    ada = (await _create_children(client, ("Ada",)))[0]
    created = await _create_definition(client, [ada])
    assert created.status_code == 201
    definition_id = created.json()["id"]

    deactivated = await client.patch(
        f"/api/v1/admin/quest-definitions/{definition_id}/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200
    payload = deactivated.json()
    assert payload["is_active"] is False
    # Everything else came back unchanged: deactivation only flips a flag.
    assert payload["title"] == "Tidy the den"
    assert payload["rule"] == _weekly_rule_dict()
    assert [a["id"] for a in payload["assignees"]] == [ada]
    assert {w["window"]: w["due_time"] for w in payload["windows"]} == {
        "morning": None,
        "evening": "19:30",
    }

    # Database proof: the definition left the ACTIVE list but its row,
    # rule, assignees and windows were NOT hard-deleted.
    assert definition_id not in await _definitions_by_id(
        admin_questdefs.database
    )
    dao = _dao_rules.QuestDefinitionsDao(admin_questdefs.database)
    record = await dao.get(definition_id)
    assert record is not None
    assert record.is_active is False
    assert record.title == "Tidy the den"
    assert await dao.list_assignees(definition_id) != []
    assert await dao.list_windows(definition_id) != []

    # Reactivation goes through the same route: the flag is set, not
    # one-way, and the surviving rule is still the one that was stored.
    reactivated = await client.patch(
        f"/api/v1/admin/quest-definitions/{definition_id}/active",
        json={"is_active": True},
        headers=_admin_headers(),
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    stored = (await _definitions_by_id(admin_questdefs.database))[
        definition_id
    ]
    assert stored.definition.is_active is True
    assert stored.rule.to_dict() == _weekly_rule_dict()
    assert [child.id for child in stored.assignees] == [ada]


async def test_set_active_unknown_definition_is_404(
    admin_questdefs: SimpleNamespace,
) -> None:
    """A set_active naming a definition that does not exist is 404."""
    response = await admin_questdefs.client.patch(
        "/api/v1/admin/quest-definitions/999/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Quest definition not found"


async def test_set_active_malformed_body_is_422(
    admin_questdefs: SimpleNamespace,
) -> None:
    """A non-bool is_active is rejected by the body model (422)."""
    response = await admin_questdefs.client.patch(
        "/api/v1/admin/quest-definitions/1/active",
        json={"is_active": "maybe"},
        headers=_admin_headers(),
    )
    assert response.status_code == 422
