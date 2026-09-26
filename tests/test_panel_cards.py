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

The motion contract (PANEL-SPEC §3.3/§3.5/§4/§5 entrances and timings) and
the §1/§6 hard rules are asserted on the card sources in the motion
section below, and the quest-complete screen's countdown return is driven
end-to-end through the quest-log harness.
"""
from __future__ import annotations

import json
import re
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

# The approved token pair: the bundle must serve the design copy
# verbatim. The values below are what PANEL-SPEC times the panel with
# (§3.3 seal entrance, §4 dialog entrance, §3.2 press feedback) and the
# ink set §1 pins at >=4.5:1 on parchment.
DESIGN_TOKENS = REPO_ROOT / "design" / "tokens" / "nestquest-panel-tokens.css"
REWARD_TOKENS = (
    REPO_ROOT
    / "custom_components"
    / "nestquest"
    / "www"
    / "nestquest-panel-tokens.css"
)

MOTION_TOKENS = {
    "--nq-ease-out": "cubic-bezier(0, 0, .2, 1)",
    "--nq-dur-micro": "120ms",
    "--nq-dur-base": "200ms",
    "--nq-dur-modal": "350ms",
}

PANEL_INK_TOKENS = {
    "--nq-p-ink": "#2b1f14",
    "--nq-p-ink-secondary": "#5c452a",
    "--nq-p-ink-muted": "#6f6455",
    "--nq-p-ink-away": "#4d4433",
    "--nq-p-ink-late": "#8f1526",
    "--nq-p-dock-ink": "#f7efdb",
    "--nq-p-dock-ink-secondary": "#d8c9a6",
}

# Text colors the panel styles may use beyond the token inks: the
# spec's own literals (§2.1 pill, §3.3 seal check, §4 dialog body),
# glyphs on the brand gradient, gradient text fills (§2 wordmark, §5
# title), and the plate button inheriting its plate's ink.
APPROVED_NON_TOKEN_INKS = {
    "inherit",
    "transparent",
    "#ffffff",
    "rgba(255, 235, 235, 0.95)",
    "#3f2f1c",
    "#146b36",
    "#157a3c",
}

#: Each card's styles live in one css template literal, keyed by the
#: constant that holds it.
STYLE_CONSTANTS = {
    PARTY_BOARD: "boardStyles",
    QUEST_LOG: "logStyles",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _style_literal(source: str, constant: str) -> str:
    """A card's css template literal — the styles between the backticks."""
    marker = f"const {constant} = css`"
    start = source.index(marker) + len(marker)
    return source[start : source.index("`;", start)]


def _keyframes_block(style: str, name: str) -> str:
    """A @keyframes rule's text, from its name through its to-block."""
    start = style.index(f"@keyframes {name}")
    return style[start : style.index("}", style.index("to {", start))]


def _css_rules(style: str) -> list[tuple[str, str]]:
    """(selector, declarations) pairs for every rule in a card's styles.

    Lit interpolations are blanked first so the clip-path/unsafeCSS
    braces cannot confuse the parse; @keyframes' from/to count as rules
    but carry no font-size, so the size checks skip them.
    """
    flattened = re.sub(r"\$\{[^}]*\}", " ", style)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", flattened)


def _size_tokens(tokens: str) -> dict[str, int]:
    """Every px length token declared in the panel tokens."""
    return {
        name: int(px)
        for name, px in re.findall(r"(--[a-z0-9-]+):\s*(\d+)px", tokens)
    }


def _font_size_px(declaration: str, sizes: dict[str, int]) -> int | None:
    """A font-size value's pixel amount; None when it is neither a px
    length nor one of the panel size tokens."""
    declaration = declaration.strip()
    if declaration.endswith("px"):
        return round(float(declaration[:-2]))
    match = re.fullmatch(r"var\((--[a-z0-9-]+)\)", declaration)
    if match and match.group(1) in sizes:
        return sizes[match.group(1)]
    return None


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


# --- Panel motion and hard rules (PANEL-SPEC §1, §3.3, §3.5, §4–§6) -----------


def test_panel_serves_the_exact_design_token_copy() -> None:
    """The bundle's served tokens are byte-for-byte the approved design
    copy. The motion tokens time every panel entrance and the ink set is
    the documented >=4.5:1 set — the cards only reference the tokens, so
    a drifted value fails here before it can reach the panel."""
    assert _read(REWARD_TOKENS) == _read(DESIGN_TOKENS)
    tokens = _read(REWARD_TOKENS)
    for declared in (MOTION_TOKENS, PANEL_INK_TOKENS):
        for name, value in declared.items():
            pattern = rf"^\s*{re.escape(name)}:\s*{re.escape(value)};"
            assert re.search(pattern, tokens, re.MULTILINE), name
    # The 22px meta floor is the declared panel minimum (§1).
    assert re.search(
        r"^\s*--nq-p-size-body:\s*22px;.*PANEL MINIMUM", tokens, re.MULTILINE
    )


def test_quest_log_entrances_use_the_design_timing_and_easing() -> None:
    """PANEL-SPEC §3.3/§4: the seal enters with fade + scale(1.15 → 1)
    over --nq-dur-base and the confirm dialog with fade + scale(.96 → 1)
    over --nq-dur-modal, both --nq-ease-out; press feedback is scale(.98)
    over --nq-dur-micro."""
    style = _style_literal(_read(QUEST_LOG), STYLE_CONSTANTS[QUEST_LOG])
    assert "animation: dialog-in var(--nq-dur-modal) var(--nq-ease-out);" in style
    dialog = _keyframes_block(style, "dialog-in")
    assert "opacity: 0;" in dialog and "transform: scale(0.96);" in dialog
    assert "opacity: 1;" in dialog and "transform: scale(1);" in dialog
    assert "animation: seal-in var(--nq-dur-base) var(--nq-ease-out);" in style
    seal = _keyframes_block(style, "seal-in")
    assert "opacity: 0;" in seal
    # The per-card rotation is preserved through the stamp animation.
    assert "transform: scale(1.15) rotate(var(--seal-rot, 0deg));" in seal
    assert "transform: scale(1) rotate(var(--seal-rot, 0deg));" in seal
    assert "animation: toast-in var(--nq-dur-base) var(--nq-ease-out);" in style
    for selector in (
        ".quest.tappable:active",
        "button.complete:active",
        "button.confirm-button:active",
    ):
        start = style.index(selector)
        block = style[start : style.index("}", start)]
        assert "transform: scale(0.98);" in block, selector
    assert (
        style.count("transition: transform var(--nq-dur-micro) var(--nq-ease-out);")
        == 3
    )  # quest card, Complete button, confirm buttons
    board_style = _style_literal(_read(PARTY_BOARD), STYLE_CONSTANTS[PARTY_BOARD])
    start = board_style.index("button.plate:active")
    block = board_style[start : board_style.index("}", start)]
    assert "transform: scale(0.98);" in block
    assert (
        "transition: transform var(--nq-dur-micro) var(--nq-ease-out);" in board_style
    )


def test_quest_complete_screen_times_the_12_second_return() -> None:
    """PANEL-SPEC §5: the 1c screen auto-returns to the board 12 s after
    the day completes, driven by the per-second countdown line."""
    source = _read(QUEST_LOG)
    assert "asNumber(this._config?.complete_screen_seconds, 12)" in source
    assert "this._countdown = this._completeSeconds();" in source
    assert "}, 1000);" in source
    assert "Returning to The Party in ${remaining} seconds" in source
    # Zero reaches the idle-return navigation itself.
    assert "this._returnToBoard();" in source


def test_idle_return_uses_the_40_second_design_timing() -> None:
    """PANEL-SPEC §3.5: 40 s with no touch returns to the party board;
    any pointer or touch event re-arms the timer. The config knob only
    shortens the default (tests do; the strategy never sets it)."""
    source = _read(QUEST_LOG)
    assert "asNumber(this._config?.idle_return_seconds, 40)" in source
    for event in ("pointerdown", "touchstart"):
        assert (
            f'window.addEventListener("{event}", this._onActivity, true)' in source
        ), event


def test_panel_hard_rules_hold_in_the_card_sources() -> None:
    """PANEL-SPEC §1/§6 hard rules on both panel card sources: no hover
    states (touch-only surface), no animation loops (entrances only,
    each timed on a design duration token with --nq-ease-out), an inert
    dock strip and pointer-none frames, the whole plate as one tap
    target with the away plate control-free, and both the quest card
    and its button opening the confirm dialog. The away plate's
    navigation contract is asserted against the bundle by
    test_away_plate_does_not_navigate."""
    board = _read(PARTY_BOARD)
    log = _read(QUEST_LOG)
    for source in (board, log):
        assert ":hover" not in source
        assert "infinite" not in source
        for animation in re.findall(r"animation:[^;]+;", source):
            assert re.fullmatch(
                r"animation: [a-z-]+ var\(--nq-dur-(?:micro|base|modal)\) "
                r"var\(--nq-ease-out\);",
                " ".join(animation.split()),
            ), animation
        for transition in re.findall(r"transition:[^;]+;", source):
            assert transition in (
                "transition: transform var(--nq-dur-micro) var(--nq-ease-out);",
            ), transition
        dock = re.search(r"\n  \.dock \{([^}]*)\}", source)
        assert dock is not None
        assert "pointer-events: none" in dock.group(1)
        assert "user-select: none" in dock.group(1)
        frame = re.search(r"\n  \.frame \{([^}]*)\}", source)
        assert frame is not None
        assert "pointer-events: none" in frame.group(1)
    # Nothing in either dock's markup can be tapped: no handlers, no
    # button, no focusable or role-bearing element.
    board_dock = board[board.index("private _renderDock") :]
    log_dock = log[
        log.index("private _renderDock") : log.index("private _returnToBoard")
    ]
    for markup in (board_dock, log_dock):
        for tappable in ("@click", "@keydown", "<button", 'role="button"', "tabindex"):
            assert tappable not in markup, tappable
    # The whole plate is the tap target: the button wraps crest, name,
    # pill, progress line and bar, and it is the board's only button.
    plate = board[board.index('class="plate"') : board.index('class="plate away"')]
    for part in (
        'class="crest"',
        'class="name"',
        'class="pill"',
        'class="progress-line"',
        'class="bar"',
    ):
        assert part in plate, part
    assert board.count("<button") == 1
    # The away plate is a plain div — nothing tappable, never navigates.
    away = board[
        board.index('class="plate away"') : board.index("private _openQuestLog")
    ]
    assert "<button" not in away
    assert "@click" not in away
    # On the log, the whole quest card AND its button open the confirm
    # dialog (§3.2); the sealed card renders no control at all.
    quest = log[log.index("private _renderQuest") : log.index("private _renderRollup")]
    assert quest.count("() => this._openConfirm(instance.id)") == 2
    sealed_template = quest[
        quest.index('class="quest sealed"') : quest.index('class="quest tappable"')
    ]
    assert "@click" not in sealed_template


def test_party_board_hint_clears_the_dock() -> None:
    """PANEL-SPEC §2/§2.3: the hint line reads fully above the dock at
    1920x1080. The hint's line box (top + font-size x line-height) must
    end above the dock's top edge (1080 - bottom inset - dock height)
    with a visible gap, at the 27px/600 design size. The hint is a <p>,
    so its user-agent 1em top margin must be reset or it shifts the box
    down by a whole font-size."""
    style = _style_literal(_read(PARTY_BOARD), STYLE_CONSTANTS[PARTY_BOARD])
    rules = {selector.strip(): body for selector, body in _css_rules(style)}
    sizes = _size_tokens(_read(REWARD_TOKENS))

    def px(body: str, prop: str) -> float:
        declared = re.search(rf"(?<![-\w]){prop}:\s*([^;]+);", body)
        assert declared is not None, prop
        value = _font_size_px(declared.group(1), sizes)
        assert value is not None, f"{prop}: {declared.group(1)}"
        return value

    board, hint, dock = rules[".board"], rules[".hint"], rules[".dock"]
    assert "margin: 0;" in hint
    line_height = float(re.search(r"line-height:\s*([\d.]+);", hint).group(1))
    hint_bottom = px(hint, "top") + px(hint, "font-size") * line_height
    dock_top = px(board, "height") - px(dock, "bottom") - px(dock, "height")
    assert px(dock, "height") == 84
    assert px(dock, "bottom") == 46
    assert hint_bottom + 12 <= dock_top, (hint_bottom, dock_top)
    assert px(hint, "font-size") == 27
    assert "font-weight: 600;" in hint


def test_panel_text_sizes_respect_the_22px_floor() -> None:
    """PANEL-SPEC §1: no body text below 22px. Every font-size in the
    panel styles resolves against the panel size tokens or an explicit
    px value, and the only text under the floor is the spec's own
    tracked uppercase Cinzel labels (§3 header sub, §3.1 range, §3.4
    roll-up label, §4 kicker, §5 stat labels) and the d20 mark numerals
    the spec sizes by hand (§2, §3) — never a Nunito body line."""
    sizes = _size_tokens(_read(REWARD_TOKENS))
    for path in (PARTY_BOARD, QUEST_LOG):
        style = _style_literal(_read(path), STYLE_CONSTANTS[path])
        for selector, body in _css_rules(style):
            declared = re.search(r"font-size:\s*([^;]+);", body)
            if declared is None:
                continue
            px = _font_size_px(declared.group(1), sizes)
            assert px is not None, (
                f"{path.name}: {selector.strip()} {declared.group(1)}"
            )
            if px >= 22:
                continue
            assert (
                "text-transform: uppercase" in body or ".d20-numeral" in selector
            ), f"{path.name}: {selector.strip()} is {px}px below the panel floor"


def test_panel_text_inks_come_from_the_token_set() -> None:
    """PANEL-SPEC §1: every ink is a token from the approved >=4.5:1 set
    or one of the spec's own literals — no alpha-muted text is ever
    introduced."""
    declared = set(
        re.findall(r"^\s*(--[a-z0-9-]+):", _read(REWARD_TOKENS), re.MULTILINE)
    )
    for path in (PARTY_BOARD, QUEST_LOG):
        style = _style_literal(_read(path), STYLE_CONSTANTS[path])
        for value in re.findall(r"(?<![-\w])color:\s*([^;]+);", style):
            value = " ".join(value.split())
            if value.startswith("var("):
                assert value[4:-1] in declared, f"{path.name}: {value}"
            else:
                assert value in APPROVED_NON_TOKEN_INKS, f"{path.name}: {value}"


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


def test_party_board_wordmark_row_is_the_monogram_lockup() -> None:
    """PANEL-SPEC §2 item 1: the wordmark row is rule · compass-rose
    monogram · NestQuest · rule. The monogram is an inline SVG filled
    with the brand gradient — the old d20 hexagon pair and its "20"
    numerals are gone, and nothing is fetched from a remote URL or
    embedded as a raster logo."""
    source = _read(PARTY_BOARD)
    assert "d20" not in _style_literal(source, STYLE_CONSTANTS[PARTY_BOARD])
    assert 'class="d20' not in source
    assert "HEXAGON_CLIP" not in source

    html = _render_party_board(
        {"type": "custom:nestquest-party-board-card"},
        _three_child_states(),
    )["html"]
    row = re.search(r'<div class="wordmark-row">(.*?)</div>', html, re.DOTALL)
    assert row is not None
    row_html = row.group(1)
    classes = re.findall(r'<(?:span|svg) class="([^"]+)"', row_html)
    assert classes == ["rule", "monogram", "wordmark", "rule"]
    assert '<svg class="monogram" viewBox="0 0 100 100" aria-hidden="true"' in row_html
    assert "var(--nq-brand-blue)" in row_html
    assert "var(--nq-brand-purple)" in row_html
    assert ">N</text>" in row_html
    assert ">NestQuest</span>" in row_html
    assert "d20" not in row_html
    assert "<img" not in row_html

    bundle = _read(BUNDLE_PATH)
    assert "d20-numeral\">20<" not in bundle
    assert "data:image/png" not in bundle
    assert not re.search(r"https?://", bundle)


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
    probe_ms: int | None = None,
    tap_complete: int | None = None,
) -> dict:
    """Render the built bundle's quest log and report its location.

    Drives frontend/tests/render-quest-log.mjs: the harness imports the
    committed bundle (the artifact HACS ships) into a jsdom window at
    ``url`` — the card resolves its child from the pathname's last
    segment — waits the optional probe window and captures one snapshot
    of the render mid-wait, then the optional idle window, and prints
    the final pathname and rendered title (plus the probe snapshot when
    ``probe_ms`` was given).
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
    if probe_ms is not None:
        spec["probe_ms"] = probe_ms
    if tap_complete is not None:
        spec["tap_complete"] = tap_complete
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


def test_quest_complete_screen_returns_to_the_board_after_the_countdown() -> None:
    """The 1c screen renders with its countdown line and auto-returns to
    the strategy-computed board path when it reaches zero. The design
    shows it for 12 s; the test shortens complete_screen_seconds to 1
    the same way the idle test shortens idle_return_seconds."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    log_config = {
        **generated["views"][1]["cards"][0],
        "complete_screen_seconds": 1,
    }
    states = {
        **_three_child_states(),
        "binary_sensor.nestquest_ada_all_done": _state("on"),
    }
    result = _render_quest_log(
        log_config,
        states,
        url="http://homeassistant.local/nestquest/ada",
        probe_ms=400,
        idle_ms=2400,
    )
    # Mid-wait the complete screen is up with its countdown line…
    assert result["probe"] is not None
    assert result["probe"]["location"] == "/nestquest/ada"
    assert "Quest complete" in result["probe"]["html"]
    assert result["probe"]["countdown"] == "Returning to The Party in 1 seconds"
    # …and at zero the card has returned to the party board.
    assert result["location"] == "/nestquest"


def test_tapping_complete_confirms_and_calls_the_service() -> None:
    """Tapping an open quest's Complete opens the confirm dialog, and the
    dialog's Complete calls nestquest.complete_quest with the panel actor.
    With ``useDefineForClassFields`` on (the ES2022 default) the card's
    reactive fields were emitted as native class fields that shadowed
    Lit's accessors: ``_confirm`` changed but no re-render was scheduled,
    so the dialog never opened and the tap did nothing."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    open_quest = {
        "id": 42,
        "definition_id": 7,
        "child_id": 1,
        "title": "Brush Teeth",
        "icon": None,
        "window": "morning",
        "due_time": "08:15",
        "state": "open",
        "overdue": True,
        "completed_at": None,
        "on_time": None,
    }
    states = {
        **_three_child_states(),
        "sensor.nestquest_ada_quests_due_today": _state(
            "1",
            child_name="Ada",
            child_id=1,
            present=True,
            instances=[open_quest],
        ),
    }
    result = _render_quest_log(
        generated["views"][1]["cards"][0],
        states,
        url="http://homeassistant.local/nestquest/ada",
        tap_complete=open_quest["id"],
    )
    assert result["tap"]["dialog_opened"] is True
    assert result["tap"]["service_calls"] == [
        {
            "domain": "nestquest",
            "service": "complete_quest",
            "data": {
                "instance_id": open_quest["id"],
                "actor": "panel",
                "actor_child_id": open_quest["child_id"],
            },
        }
    ]


def test_card_build_keeps_lit_reactive_accessors() -> None:
    """The frontend build must not emit class fields that shadow Lit's
    reactive property accessors (Lit's documented TypeScript setting)."""
    tsconfig = json.loads((FRONTEND_DIR / "tsconfig.json").read_text())
    assert tsconfig["compilerOptions"]["useDefineForClassFields"] is False


def test_quest_log_crest_keeps_its_shield_classes() -> None:
    """PANEL-SPEC §3 header crest: a present child's crest renders as the
    styled shield, not a bare span. Lit removes an attribute outright when
    any interpolated part of it is ``nothing``, so a class written as
    ``crest${away ? " away" : nothing}`` lost ``crest`` for every present
    child and the header showed an unstyled sliver. The rendered markup
    must carry ``class="crest"`` (present) and ``class="crest away"``
    (away), each wrapping the face and initial."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )
    log_config = generated["views"][1]["cards"][0]
    for slug, crest_class in (("ada", "crest"), ("bo", "crest away")):
        result = _render_quest_log(
            log_config,
            _three_child_states(),
            url=f"http://homeassistant.local/nestquest/{slug}",
        )
        header = result["html"][result["html"].index('<header class="header">') :]
        crest = re.match(
            r'<header class="header">\s*(?:<!--[^>]*-->\s*)*<span ([^>]*)>\s*'
            r'<span class="crest-face">\s*<span class="initial">',
            header,
        )
        assert crest is not None, header[:600]
        assert f'class="{crest_class}"' in crest.group(1), crest.group(1)


def test_quest_log_meta_line_keeps_its_meta_class() -> None:
    """An open quest's meta line is styled by ``.quest .meta`` (and
    ``.quest .meta.late`` when overdue). Written as
    ``meta ${late ? "late" : nothing}``, Lit dropped the whole class
    attribute for every quest that was not late, leaving the due line
    unstyled. The rendered markup must carry ``class="meta"`` on time and
    ``class="meta late"`` overdue."""
    generated = _generate_dashboard(
        {}, _three_child_states(), url="http://homeassistant.local/nestquest"
    )

    def quest(instance_id: int, title: str, overdue: bool) -> dict:
        return {
            "id": instance_id,
            "definition_id": instance_id,
            "child_id": 1,
            "title": title,
            "icon": None,
            "window": "morning",
            "due_time": "08:15",
            "state": "open",
            "overdue": overdue,
            "completed_at": None,
            "on_time": None,
        }

    states = {
        **_three_child_states(),
        "sensor.nestquest_ada_quests_due_today": _state(
            "2",
            child_name="Ada",
            child_id=1,
            present=True,
            instances=[
                quest(41, "Make Bed", overdue=False),
                quest(42, "Brush Teeth", overdue=True),
            ],
        ),
    }
    result = _render_quest_log(
        generated["views"][1]["cards"][0],
        states,
        url="http://homeassistant.local/nestquest/ada",
    )
    metas = {}
    for card in result["html"].split('data-instance-id="')[1:]:
        meta = re.search(
            r'<span class="quest-title">.*?</span>'
            r"\s*(?:<!--[^>]*-->\s*)*<span([^>]*)>",
            card,
            re.S,
        )
        assert meta is not None, card[:800]
        metas[card[: card.index('"')]] = meta.group(1)
    assert set(metas) == {"41", "42"}, metas
    assert metas["41"].strip() == 'class="meta"', metas["41"]
    assert metas["42"].strip() == 'class="meta late"', metas["42"]


def test_quest_log_crest_matches_the_spec_geometry() -> None:
    """PANEL-SPEC §3 header crest: 96x110 shield, 4px ring of
    rgba(255,255,255,.22) around the --nq-p-crest face, 44px/700 display
    initial in full-opacity white; away swaps only the face gradient.
    jsdom cannot lay out, so this pins the stylesheet the rendered test
    above shows is applied."""
    source = QUEST_LOG.read_text(encoding="utf-8")

    def rule(selector: str) -> str:
        found = re.search(
            r"\n  " + re.escape(selector) + r" \{(.*?)\n  \}", source, re.DOTALL
        )
        assert found is not None, selector
        return found.group(1)

    crest = rule(".crest")
    for decl in (
        "width: 96px;",
        "height: 110px;",
        "padding: 4px;",
        "clip-path: ${unsafeCSS(SHIELD_CLIP)};",
        "background: rgba(255, 255, 255, 0.22);",
    ):
        assert decl in crest, decl
    face = rule(".crest-face")
    assert "background: var(--nq-p-crest);" in face
    assert "clip-path: ${unsafeCSS(SHIELD_CLIP)};" in face
    initial = rule(".crest .initial")
    for decl in (
        "font-family: var(--nq-p-font-display);",
        "font-size: 44px;",
        "font-weight: 700;",
        "color: #ffffff;",
    ):
        assert decl in initial, decl
    assert "opacity" not in initial
    away = rule(".crest.away .crest-face")
    assert away.strip() == "background: var(--nq-p-crest-away);"
