"""Source-level tests for the kid panel cards.

The panel cards are Lit/TypeScript modules bundled by Vite; these tests assert
the contract by reading the card sources and the built bundle, in the same
spirit as test_frontend.py. They cover the states decided in
design/PANEL-EMPTY-STATES.md and PANEL-SPEC.md, and guard the kid-facing
bundles against ever gaining a parent-only service call.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FRONTEND_CARDS_DIR = REPO_ROOT / "frontend" / "src" / "cards"
PARTY_BOARD = FRONTEND_CARDS_DIR / "party-board.ts"
QUEST_LOG = FRONTEND_CARDS_DIR / "quest-log.ts"
BUNDLE_PATH = REPO_ROOT / "custom_components" / "nestquest" / "www" / "nestquest-cards.js"

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