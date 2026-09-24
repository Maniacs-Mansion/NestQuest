"""Admin-plane editable assignees on the definition edit route (task 1c8096f6).

``PATCH /api/v1/admin/quest-definitions/{definition_id}`` accepts an
optional ``assignee_child_ids`` list that REPLACES the definition's
assignee set inside the core edit's ONE transaction
(:func:`nestquest_core.quest_definitions.edit_quest_definition`):

- newly listed children are assigned and unlisted ones unassigned; the
  response and the database both carry the resulting set;
- an empty list, a duplicate, an unknown child or an inactive child is
  422 and NOTHING is written — the stored assignees (and any other
  field supplied in the same body) are unchanged;
- a JSON boolean, float or numeric string id is 422 on create and edit
  (never coerced to an int) and nothing is written;
- an omitted ``assignee_child_ids`` leaves the assignees unchanged;
- an assignment change regenerates the definition's future instances
  through the existing core path;
- the route stays behind the router's ONE ``require_admin`` dependency
  (absent credential 401, panel service token 403, non-admin JWT 403,
  admin JWT 200).

Every case is proven against the DATABASE, read through the SAME core
copy the app uses (``nestquest_core.*``; see api/nestquest_core.py).
"""
from __future__ import annotations

import datetime
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

_dao_rules = importlib.import_module("nestquest_core.dao_rules")
_dao_instances = importlib.import_module("nestquest_core.dao_instances")
_materialize = importlib.import_module("nestquest_core.materialize")
_quest_definitions = importlib.import_module(
    "nestquest_core.quest_definitions"
)

#: The panel service token the harness app is configured with.
HARNESS_PANEL_TOKEN = "admin-test-panel-token"


def _admin_headers() -> dict[str, str]:
    """The Authorization header of a valid nestquest-admins JWT."""
    return {"Authorization": f"Bearer {make_token()}"}


def _edit_path(definition_id: int) -> str:
    """The edit route for one definition."""
    return f"/api/v1/admin/quest-definitions/{definition_id}"


@pytest.fixture
async def admin_assignees(temp_db_path: str) -> SimpleNamespace:
    """An admin-plane app client plus its live database."""
    runner = AdminRunner(temp_db_path, jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        yield SimpleNamespace(
            client=client,
            database=runner.app.state.db.database,
        )


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


async def _create_definition(client: object, assignee_ids: list[int]) -> int:
    """POST a daily morning definition for the given assignees."""
    created = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Brush teeth",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": assignee_ids,
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )
    assert created.status_code == 201
    return created.json()["id"]


async def _stored_assignee_ids(
    database: object, definition_id: int
) -> set[int]:
    """The definition's assignee ids as stored."""
    dao = _dao_rules.QuestDefinitionsDao(database)
    return {child.id for child in await dao.list_assignees(definition_id)}


def _response_assignee_ids(response: object) -> set[int]:
    """The assignee ids a definition payload reports."""
    return {assignee["id"] for assignee in response.json()["assignees"]}


# --- add / remove / replace -------------------------------------------------


@pytest.mark.parametrize(
    ("initial", "requested"),
    [
        (("Ada",), ("Ada", "Bo")),  # add a child
        (("Ada", "Bo"), ("Ada",)),  # remove a child
        (("Ada", "Bo"), ("Cy",)),  # replace the whole set
    ],
)
async def test_edit_replaces_the_assignee_set(
    admin_assignees: SimpleNamespace,
    initial: tuple[str, ...],
    requested: tuple[str, ...],
) -> None:
    """A supplied list becomes exactly the stored and returned set."""
    client = admin_assignees.client
    names = ("Ada", "Bo", "Cy")
    ids = dict(zip(names, await _create_children(client, names)))
    definition_id = await _create_definition(
        client, [ids[name] for name in initial]
    )
    wanted = {ids[name] for name in requested}

    response = await client.patch(
        _edit_path(definition_id),
        json={"assignee_child_ids": [ids[name] for name in requested]},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert _response_assignee_ids(response) == wanted
    assert {a["display_name"] for a in response.json()["assignees"]} == set(
        requested
    )
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == wanted
    # The rest of the definition is untouched by an assignee-only edit.
    assert response.json()["title"] == "Brush teeth"
    assert [w["window"] for w in response.json()["windows"]] == ["morning"]


async def test_edit_with_assignees_and_other_fields_applies_both(
    admin_assignees: SimpleNamespace,
) -> None:
    """Assignees and metadata supplied together land in one edit."""
    client = admin_assignees.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    definition_id = await _create_definition(client, [ada])

    response = await client.patch(
        _edit_path(definition_id),
        json={"title": "Floss", "assignee_child_ids": [bo]},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Floss"
    assert _response_assignee_ids(response) == {bo}
    dao = _dao_rules.QuestDefinitionsDao(admin_assignees.database)
    assert (await dao.get(definition_id)).title == "Floss"
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {bo}


# --- rejections leave the stored state unchanged ----------------------------


@pytest.mark.parametrize(
    ("case", "expected_detail"),
    [
        ("empty", "assignee_child_ids must not be empty"),
        ("unknown", "assignee_child_ids: child 999 does not exist"),
        ("inactive", "assignee_child_ids: child {cy} is inactive"),
        ("duplicate", "assignee_child_ids must not contain duplicate"),
        ("null", "assignee_child_ids must be a list"),
        ("mixed_unknown", "assignee_child_ids: child 999 does not exist"),
        ("wrong_type", None),  # the body model's own 422
    ],
)
async def test_rejected_assignee_list_is_422_and_changes_nothing(
    admin_assignees: SimpleNamespace,
    case: str,
    expected_detail: str | None,
) -> None:
    """Empty/unknown/inactive/malformed lists are 422 with no mutation.

    The same body also renames the definition, proving the whole edit
    is all-or-nothing: neither the assignees nor the title change.
    """
    client = admin_assignees.client
    ada, bo, cy, di = await _create_children(
        client, ("Ada", "Bo", "Cy", "Di")
    )
    definition_id = await _create_definition(client, [ada, bo])
    deactivated = await client.patch(
        f"/api/v1/admin/children/{cy}/active",
        json={"is_active": False},
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200

    requested: object = {
        "empty": [],
        "unknown": [999],
        "inactive": [ada, cy],
        "duplicate": [ada, ada],
        "null": None,
        # A valid new child alongside an unknown one: di must NOT be
        # assigned (all-or-nothing), and ada/bo must NOT be removed.
        "mixed_unknown": [di, 999],
        "wrong_type": ["Ada"],
    }[case]

    response = await client.patch(
        _edit_path(definition_id),
        json={"title": "Renamed", "assignee_child_ids": requested},
        headers=_admin_headers(),
    )

    assert response.status_code == 422, case
    if expected_detail is not None:
        assert response.json()["detail"].startswith(
            expected_detail.format(cy=cy)
        ), response.json()
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {ada, bo}
    dao = _dao_rules.QuestDefinitionsDao(admin_assignees.database)
    assert (await dao.get(definition_id)).title == "Brush teeth"


#: JSON ids the lax ``int`` parser would coerce (``true`` -> 1).
_COERCIBLE_IDS = [True, 1.0, "1"]


@pytest.mark.parametrize("coercible", _COERCIBLE_IDS)
async def test_edit_rejects_coercible_assignee_ids_and_changes_nothing(
    admin_assignees: SimpleNamespace, coercible: object
) -> None:
    """A bool, float or numeric-string id edit is 422; nothing changes."""
    client = admin_assignees.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    # Assign bo only, so a coerced id 1 (ada) would be a visible change.
    definition_id = await _create_definition(client, [bo])
    assert ada == 1

    response = await client.patch(
        _edit_path(definition_id),
        json={"title": "Renamed", "assignee_child_ids": [coercible]},
        headers=_admin_headers(),
    )

    assert response.status_code == 422
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {bo}
    dao = _dao_rules.QuestDefinitionsDao(admin_assignees.database)
    assert (await dao.get(definition_id)).title == "Brush teeth"


@pytest.mark.parametrize("coercible", _COERCIBLE_IDS)
async def test_create_rejects_coercible_assignee_ids_and_persists_nothing(
    admin_assignees: SimpleNamespace, coercible: object
) -> None:
    """A bool, float or numeric-string id create is 422; nothing is written."""
    client = admin_assignees.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    assert ada == 1
    existing_id = await _create_definition(client, [bo])

    response = await client.post(
        "/api/v1/admin/quest-definitions",
        json={
            "title": "Tidy the den",
            "rule": {"rule_type": "daily"},
            "assignee_child_ids": [coercible],
            "windows": ["morning"],
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 422
    bundles = await _quest_definitions.list_active_definitions(
        admin_assignees.database
    )
    assert [bundle.definition.id for bundle in bundles] == [existing_id]
    assert await _stored_assignee_ids(
        admin_assignees.database, existing_id
    ) == {bo}


async def test_rejected_assignees_on_unknown_definition_is_404(
    admin_assignees: SimpleNamespace,
) -> None:
    """An unknown definition id is still 404 when assignees are supplied."""
    client = admin_assignees.client
    (ada,) = await _create_children(client, ("Ada",))
    response = await client.patch(
        _edit_path(999),
        json={"assignee_child_ids": [ada]},
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Quest definition not found"


# --- omitted keeps ----------------------------------------------------------


async def test_omitted_assignees_are_unchanged(
    admin_assignees: SimpleNamespace,
) -> None:
    """An edit without assignee_child_ids never touches the assignees."""
    client = admin_assignees.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    definition_id = await _create_definition(client, [ada, bo])

    response = await client.patch(
        _edit_path(definition_id),
        json={"title": "Floss"},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert _response_assignee_ids(response) == {ada, bo}
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {ada, bo}


# --- regeneration -----------------------------------------------------------


async def test_assignment_change_regenerates_future_instances(
    admin_assignees: SimpleNamespace,
) -> None:
    """Swapping the assignee moves the future open instances with it.

    The regeneration lives in the core edit path the route calls: the
    definition's open instances at or after today are deleted and the
    horizon re-materialized for the NEW assignee set.
    """
    client = admin_assignees.client
    database = admin_assignees.database
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    definition_id = await _create_definition(client, [ada])

    today = datetime.date.today()
    start = today.isoformat()
    end = (today + datetime.timedelta(days=7)).isoformat()
    await _materialize.materialize(database, start, end, today=today)
    instances = _dao_instances.QuestInstancesDao(database)
    assert await instances.list_by_date_range(ada, start, end)
    assert await instances.list_by_date_range(bo, start, end) == []

    response = await client.patch(
        _edit_path(definition_id),
        json={"assignee_child_ids": [bo]},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert await instances.list_by_date_range(ada, start, end) == []
    regenerated = await instances.list_by_date_range(bo, start, end)
    assert regenerated
    assert {i.definition_id for i in regenerated} == {definition_id}


# --- authentication ---------------------------------------------------------


async def test_assignee_edit_auth_outcomes(
    admin_assignees: SimpleNamespace,
) -> None:
    """401 absent, 403 panel token, 403 non-admin, 200 admin."""
    client = admin_assignees.client
    ada, bo = await _create_children(client, ("Ada", "Bo"))
    definition_id = await _create_definition(client, [ada])
    body = {"assignee_child_ids": [bo]}

    absent = await client.patch(_edit_path(definition_id), json=body)
    assert absent.status_code == 401

    panel = await client.patch(
        _edit_path(definition_id),
        json=body,
        headers={"Authorization": f"Bearer {HARNESS_PANEL_TOKEN}"},
    )
    assert panel.status_code == 403

    non_admin_token = make_token(groups=("some-other-group",))
    non_admin = await client.patch(
        _edit_path(definition_id),
        json=body,
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )
    assert non_admin.status_code == 403

    # None of the refused calls reached the handler.
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {ada}

    admin = await client.patch(
        _edit_path(definition_id), json=body, headers=_admin_headers()
    )
    assert admin.status_code == 200
    assert await _stored_assignee_ids(
        admin_assignees.database, definition_id
    ) == {bo}
