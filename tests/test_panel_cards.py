"""Source-level tests for the kid panel cards.

The panel cards are Lit/TypeScript modules bundled by Vite; these tests assert
the contract by reading the card sources and the built bundle, in the same
spirit as test_frontend.py. They cover the states decided in
design/PANEL-EMPTY-STATES.md and PANEL-SPEC.md, and guard the kid-facing
bundles against ever gaining a parent-only service call.

The cards additionally have render tests: they drive the jsdom harnesses in
frontend/tests — render-party-board.mjs imports the built bundle into a
jsdom window and reports the ordered plates the shadow DOM renders plus
where a crest tap navigates, and render-quest-log.mjs reports where the
quest log's idle return navigates — so the zero-config discovery and
navigation contracts are asserted against the bundle HACS ships.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_CARDS_DIR = FRONTEND_DIR / "src" / "cards"
PARTY_BOARD = FRONTEND_CARDS_DIR / "party-board.ts"
QUEST_LOG = FRONTEND_CARDS_DIR / "quest-log.ts"
BUNDLE_PATH = REPO_ROOT / "custom_components" / "nestquest" / "www" / "nestquest-cards.js"
RENDER_HARNESS = FRONTEND_DIR / "tests" / "render-party-board.mjs"
QUEST_LOG_HARNESS = FRONTEND_DIR / "tests" / "render-quest-log.mjs"
STRATEGY_HARNESS = FRONTEND_DIR / "tests" / "render-strategy.mjs"
STRATEGY_SOURCE = FRONTEND_DIR / "src" / "strategy.ts"

PANEL_SOURCES = (PARTY_BOARD, QUEST_LOG)

# Parent-only NestQuest services. The party board and quest log are the
# kid-facing panel: they may complete a quest for the tapped child, and nothing
# else. Any of these names appearing in a panel source or bundle means an admin
# control has leaked into the kid panel.
ADMIN_ONLY_SERVICES = (
    "uncomplete_quest",
    "create_quest_definition",
    "update_quest_definition",
    "set_quest_definition_active",
    "set_presence_pattern",
    "create_presence_override",
    "delete_presence_override",
    "export_history_csv",
    "manage_child",
    "regenerate",
)

WINDOW_KEYS = ("morning", "afternoon", "evening")
WINDOW_NAMES = ("Morning", "Afternoon", "Evening")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_party_board_renders_present_and_away_plates() -> None:
    source = _read(PARTY_BOARD)
    assert "nestquest-party-board-card" in source
    # Present adventurers get the tappable crest plate.
    assert "button.plate" in source
    assert 'class="plate"' in source
    assert "Home today" in source
    assert "aria-label=\"Open ${plate.name}'s Quest Log\"" in source
    # Away adventurers get the dashed On travels plate, not a tappable one.
    assert ".plate.away" in source
    assert 'class="plate away"' in source
    assert "On travels" in source
    assert "next_present" in source
    assert "Returns ${formatDay(returnsDate" in source


def test_quest_log_renders_three_window_columns() -> None:
    source = _read(QUEST_LOG)
    for key, name in zip(WINDOW_KEYS, WINDOW_NAMES):
        assert f'key: "{key}"' in source, key
        assert f'name: "{name}"' in source, name
    assert "grid-template-columns: repeat(3, 1fr)" in source
    assert 'class="column-head"' in source
    assert 'class="column-names"' in source
    assert 'class="column-range"' in source


def test_empty_window_still_renders_its_column_head() -> None:
    """A window with no quests renders the head alone (PANEL-SPEC §3.1)."""
    source = _read(QUEST_LOG)
    column = source[source.index("private _renderColumn(windowDef: WindowDef)") :]
    column = column[: column.index("private _renderQuest(")]
    # The head is emitted unconditionally, before the stack is built.
    assert 'class="column-head"' in column
    assert "sealed.length}/${instances.length}" in column
    # There is no early return that would drop the head on an empty window.
    assert "instances.length === 0" not in column
    assert "return nothing" not in column


def test_complete_quest_is_optimistic_with_rollback() -> None:
    source = _read(QUEST_LOG)
    assert "_optimistic" in source
    assert "new Date().toISOString()" in source
    assert ".set(instance.id, stampedAt)" in source
    # The overlay is applied to the rendered instance before the service answers.
    assert 'instance.state = "completed"' in source
    # A rejected call reverts the overlay and raises the parchment toast.
    assert "reverted.delete(instance.id)" in source
    assert "NestQuest could not set the seal just now. Please try again." in source
    assert "_showToast(" in source
    assert "await this._callCompleteQuest(instance)" in source
    assert '"nestquest", "complete_quest"' in source


def test_idle_return_to_board() -> None:
    source = _read(QUEST_LOG)
    assert "idle_return_seconds" in source
    assert "_armIdle" in source
    assert "_clearIdle" in source
    assert "this._idleSeconds() * 1000" in source
    assert "board_path" in source
    assert "_returnToBoard" in source
    assert 'window.dispatchEvent(new Event("location-changed"))' in source


def test_decided_empty_and_error_states_are_present() -> None:
    log = _read(QUEST_LOG)
    board = _read(PARTY_BOARD)
    for kind in (
        "no-adventurer",
        "not-set-up",
        "unreachable",
        "away",
        "empty-day",
        "complete-day",
    ):
        assert f'kind: "{kind}"' in log, kind
    assert "PANEL-EMPTY-STATES" in log
    assert "No adventurer chosen" in log
    assert "NestQuest is not set up yet" in log
    assert "The records cannot be reached" in log
    assert "No quests today" in log
    assert 'role="status"' in log
    # The board distinguishes the same setup/unreachable cases at board level.
    assert "NestQuest is not set up yet" in board
    assert "The records cannot be reached" in board
    assert "BOARD_NOTICE_NOT_SET_UP" in board
    assert "BOARD_NOTICE_UNREACHABLE" in board


def test_quest_complete_trigger() -> None:
    source = _read(QUEST_LOG)
    assert "binary_sensor.nestquest_${slug}_all_done" in source
    assert "nestquest_child_day_complete" in source
    assert "NESTQUEST_EVENT_TYPES" in source
    assert 'class="complete-screen"' in source
    assert "Quest complete" in source
    assert "Returning to The Party in" in source
    assert "_armCompleteTimer" in source
    assert "complete_screen_seconds" in source


def test_panel_cards_reference_no_admin_only_services() -> None:
    # Only the kid panel sources are scanned: the bundle also contains the
    # sibling admin card, so its parent-only service names are expected there.
    for path in PANEL_SOURCES:
        text = _read(path)
        for service in ADMIN_ONLY_SERVICES:
            assert service not in text, f"{path}: {service}"
    # The bundle is still built and carries both panel card custom elements.
    assert BUNDLE_PATH.is_file()
    bundle = _read(BUNDLE_PATH)
    assert "nestquest-party-board-card" in bundle
    assert "nestquest-quest-log-card" in bundle


def test_party_board_discovers_children_from_the_household_roster() -> None:
    """Feature 20: with no child_order configured, the board discovers
    the ordered child slugs from the household rollup's child_roster
    attribute; explicit configuration still wins."""
    source = _read(PARTY_BOARD)
    assert "child_roster" in source
    assert "sensor.nestquest_household_quests_due_today" in source
    # Discovery only fills in for a MISSING child_order; a supplied
    # order array is honoured verbatim before the discovered list is
    # ever consulted.
    assert "Array.isArray(order)" in source
    assert "_discoveredChildSlugs()" in source


# --- Render tests (built bundle under jsdom) ---------------------------------

#: The seeded three-child household, in the API's sort order: Ada and
#: Bo share one daily quest (Bo is away today), Cory has none.
ROSTER = [
    {"child_id": 1, "name": "Ada", "slug": "ada"},
    {"child_id": 2, "name": "Bo", "slug": "bo"},
    {"child_id": 3, "name": "Cory", "slug": "cory"},
]


def _state(state: str, **attributes) -> dict:
    return {"state": state, "attributes": attributes}


def _three_child_states() -> dict:
    """The hass states a three-child household exposes.

    Entity ids follow the documented naming contract
    (design/ENTITIES-AND-SERVICES.md §1): the household rollup and the
    per-child sensors slugged from the child names.
    """
    return {
        "sensor.nestquest_household_quests_due_today": _state(
            "2",
            children={"1": 1, "2": 1, "3": 0},
            child_roster=ROSTER,
        ),
        "sensor.nestquest_ada_quests_due_today": _state(
            "1", child_name="Ada", present=True
        ),
        "sensor.nestquest_ada_quests_completed_today": _state("0"),
        "sensor.nestquest_ada_completion_pct_today": _state("0"),
        "binary_sensor.nestquest_ada_present_today": _state("on"),
        "sensor.nestquest_bo_quests_due_today": _state(
            "1", child_name="Bo", present=False
        ),
        "sensor.nestquest_bo_quests_completed_today": _state("0"),
        "sensor.nestquest_bo_completion_pct_today": _state("0"),
        "binary_sensor.nestquest_bo_present_today": _state("off"),
        "sensor.nestquest_cory_quests_due_today": _state(
            "0", child_name="Cory", present=True
        ),
        "sensor.nestquest_cory_quests_completed_today": _state("0"),
        "sensor.nestquest_cory_completion_pct_today": _state("100"),
        "binary_sensor.nestquest_cory_present_today": _state("on"),
    }


def _render_party_board(
    config: dict,
    states: dict,
    url: str | None = None,
    click_plate: str | None = None,
) -> dict:
    """Render the built bundle's party board and return its plates.

    Drives frontend/tests/render-party-board.mjs: the harness imports
    the committed bundle (the artifact HACS ships) into a jsdom window,
    mounts the card with the given config and hass snapshot, optionally
    taps the named plate, and prints the ordered plates its shadow DOM
    renders, which of them are tappable buttons, and the pathname after
    the optional tap.
    """
    assert BUNDLE_PATH.is_file(), "bundle missing: run cd frontend && npm run build"
    assert RENDER_HARNESS.is_file()
    spec = {
        "bundle": str(BUNDLE_PATH),
        "tag": "nestquest-party-board-card",
        "config": config,
        "hass": {"config": {"time_zone": "UTC"}, "states": states},
    }
    if url is not None:
        spec["url"] = url
    if click_plate is not None:
        spec["click_plate"] = click_plate
    completed = subprocess.run(
        ["node", str(RENDER_HARNESS)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"render harness failed: {completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_party_board_renders_discovered_children_in_sort_order() -> None:
    """No child_order key: three plates render in the roster's sort
    order (the coordinator snapshot's order), one per child."""
    result = _render_party_board(
        {"type": "custom:nestquest-party-board-card"},
        _three_child_states(),
    )
    assert result["plates"] == [
        {"name": "Ada", "kind": "present"},
        {"name": "Bo", "kind": "away"},
        {"name": "Cory", "kind": "present"},
    ]


def test_explicit_child_order_still_wins_over_discovery() -> None:
    """A supplied child_order keeps working: it overrides the household
    roster's order and limits the plates to the configured slugs."""
    result = _render_party_board(
        {
            "type": "custom:nestquest-party-board-card",
            "child_order": ["bo", "ada"],
        },
        _three_child_states(),
    )
    assert [plate["name"] for plate in result["plates"]] == ["Bo", "Ada"]
    assert "Cory" not in [plate["name"] for plate in result["plates"]]

# --- Dashboard strategy tests -------------------------------------------------

STRATEGY_NAME = "nestquest-party"


def _generate_dashboard(config: dict, states: dict, url: str | None = None) -> dict:
    """Generate the strategy's dashboard from the built bundle.

    Drives frontend/tests/render-strategy.mjs: the harness imports the
    committed bundle into a jsdom window at the given dashboard URL and
    prints the views ``window.customStrategies["nestquest-party"].
    generate(config, hass)`` returns.
    """
    assert BUNDLE_PATH.is_file(), "bundle missing: run cd frontend && npm run build"
    assert STRATEGY_HARNESS.is_file()
    spec = {
        "bundle": str(BUNDLE_PATH),
        "url": url or "http://homeassistant.local/nestquest/party",
        "config": config,
        "hass": {"config": {"time_zone": "UTC"}, "states": states},
    }
    completed = subprocess.run(
        ["node", str(STRATEGY_HARNESS)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"strategy harness failed: {completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_strategy_is_registered_on_the_bundle() -> None:
    """The strategy ships in the same bundle as the cards and registers
    itself under window.customStrategies so a dashboard can use
    strategy: { type: custom:nestquest-party }."""
    source = _read(STRATEGY_SOURCE)
    assert "customStrategies" in source
    assert f'["{STRATEGY_NAME}"]' in source or f'"{STRATEGY_NAME}"' in source
    bundle = _read(BUNDLE_PATH)
    assert "nestquest-party" in bundle


def test_strategy_generates_views_for_three_children() -> None:
    """For the seeded three-child household the strategy generates one
    party-board view plus one quest-log view per child in roster order,
    with COMPUTED paths: the board view at the dashboard root, each log
    view at the child's slug so quest-log.ts's childSlugFromPath reads
    the child from the URL's last segment."""
    result = _generate_dashboard({}, _three_child_states())
    views = result["views"]
    assert len(views) == 4
    assert [view["path"] for view in views] == [
        "party",
        "ada",
        "bo",
        "cory",
    ]
    assert [view["title"] for view in views] == [
        "The Party",
        "Ada's Quest Log",
        "Bo's Quest Log",
        "Cory's Quest Log",
    ]


def test_strategy_every_view_is_panel_type() -> None:
    """Every generated view carries ``type: "panel"``: Home Assistant
    defaults an unspecified view to Masonry, which constrains the
    1080px-tall NestQuest card to a narrow column (README's TouchHub
    setup warns of exactly this); with a generated dashboard there is
    no editor step left to set Panel by hand."""
    result = _generate_dashboard({}, _three_child_states())
    for view in result["views"]:
        assert view["type"] == "panel"


def test_strategy_log_view_titles_use_the_roster_display_name() -> None:
    """Quest-log view titles come from the roster's ``name`` field (the
    child's display name), not the lowercased entity-id slug; the slug
    stays the view's path."""
    result = _generate_dashboard(
        {},
        {
            "sensor.nestquest_household_quests_due_today": _state(
                "0",
                child_roster=[
                    {"child_id": 7, "name": "Milo", "slug": "milo"},
                ],
            ),
        },
    )
    views = result["views"]
    assert len(views) == 2
    assert views[1]["path"] == "milo"
    assert views[1]["title"] == "Milo's Quest Log"


def test_strategy_passes_weather_entity_through_to_the_cards() -> None:
    """An explicit ``weather_entity`` in the strategy configuration is
    passed through to the generated card configs (both the board and
    the quest log render the weather dock when it is set)."""
    result = _generate_dashboard(
        {"weather_entity": "weather.home"},
        _three_child_states(),
    )
    views = result["views"]
    for view in views:
        assert view["cards"][0]["weather_entity"] == "weather.home"
    # And without it, no weather_entity key is emitted at all.
    unset = _generate_dashboard({}, _three_child_states())
    for view in unset["views"]:
        assert "weather_entity" not in view["cards"][0]


def test_strategy_wires_navigation_between_the_views() -> None:
    """The board's quest_log_path and each log's board_path are computed
    to the dashboard root the strategy renders at, so party-board.ts's
    crest tap pushes <root>/<slug> and quest-log.ts's idle return goes
    back to the board — neither path is configured by hand."""
    dashboard_url = "http://homeassistant.local/nestquest"
    root = "/nestquest"
    result = _generate_dashboard(
        {}, _three_child_states(), url=dashboard_url
    )
    views = result["views"]
    board = views[0]["cards"][0]
    assert board["type"] == "custom:nestquest-party-board-card"
    assert board["quest_log_path"] == root
    for slug, view in zip(("ada", "bo", "cory"), views[1:]):
        assert view["cards"][0]["type"] == "custom:nestquest-quest-log-card"
        assert view["cards"][0]["board_path"] == root


def test_strategy_zero_children_still_generates_the_board() -> None:
    """With an empty roster (NestQuest not set up yet) the strategy
    renders the board view alone — the board card shows its own
    "not set up yet" notice for an empty roster — and never crashes."""
    result = _generate_dashboard({}, {})
    assert len(result["views"]) == 1
    assert result["views"][0]["path"] == "party"


def test_strategy_config_overrides_still_apply() -> None:
    """Explicit strategy configuration wins where the design allows: an
    explicit url_path pins the computed dashboard root."""
    result = _generate_dashboard(
        {"url_path": "/wallboard"},
        _three_child_states(),
    )
    root = "/wallboard"
    assert result["views"][0]["cards"][0]["quest_log_path"] == root
    for view in result["views"][1:]:
        assert view["cards"][0]["board_path"] == root


# --- Navigation tests (strategy-computed paths under jsdom) -------------------


def _render_quest_log(
    config: dict,
    states: dict,
    url: str,
    idle_ms: int | None = None,
) -> dict:
    """Render the built bundle's quest log and report its location.

    Drives frontend/tests/render-quest-log.mjs: the harness imports the
    committed bundle (the artifact HACS ships) into a jsdom window at
    ``url`` — the card resolves its child from the pathname's last
    segment — waits the optional idle window, and prints the pathname
    and the rendered title.
    """
    assert BUNDLE_PATH.is_file(), "bundle missing: run cd frontend && npm run build"
    assert QUEST_LOG_HARNESS.is_file()
    spec = {
        "bundle": str(BUNDLE_PATH),
        "url": url,
        "config": config,
        "hass": {"config": {"time_zone": "UTC"}, "states": states},
    }
    if idle_ms is not None:
        spec["idle_ms"] = idle_ms
    completed = subprocess.run(
        ["node", str(QUEST_LOG_HARNESS)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"quest-log harness failed: {completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_present_crest_tap_navigates_to_the_child_quest_log() -> None:
    """Tapping a present crest pushes <dashboard root>/<slug>: the exact
    URL the strategy computed for that child's quest log view (the log
    then resolves its child from the path's last segment)."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    board_config = generated["views"][0]["cards"][0]
    result = _render_party_board(
        board_config,
        _three_child_states(),
        url="http://homeassistant.local/nestquest",
        click_plate="Ada",
    )
    # Only the present adventurers' plates are tappable buttons.
    assert result["tappable"] == ["Ada", "Cory"]
    assert result["location"] == "/nestquest/ada"


def test_away_plate_does_not_navigate() -> None:
    """Bo is away today: his plate is not a button, and tapping it leaves
    the URL at the dashboard root — away adventurers cannot open a log."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    board_config = generated["views"][0]["cards"][0]
    result = _render_party_board(
        board_config,
        _three_child_states(),
        url="http://homeassistant.local/nestquest",
        click_plate="Bo",
    )
    assert "Bo" not in result["tappable"]
    assert result["location"] == "/nestquest"


def test_quest_log_idle_return_navigates_to_the_board() -> None:
    """After the idle window the quest log returns to the board using the
    strategy-computed board_path (the dashboard root) — and it resolved
    Ada from the URL's last segment first.  ``idle_return_seconds`` is
    set by hand because the card's 40-second default is too slow for a
    test; the strategy never generates that knob."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    log_config = {**generated["views"][1]["cards"][0], "idle_return_seconds": 1}
    result = _render_quest_log(
        log_config,
        _three_child_states(),
        url="http://homeassistant.local/nestquest/ada",
        idle_ms=2000,
    )
    assert result["headline"] == "Ada's Quest Log"
    assert result["location"] == "/nestquest"
