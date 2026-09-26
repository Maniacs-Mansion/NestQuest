# Panel spec — kids' DAKOS wall panel

Screens `1a`, `1b`, `1j`, `1c` of the mockups. Two cards:
`nestquest-party-board-card` (§2) and `nestquest-quest-log-card` (§3–5).

## 1. Frame and constraints

- **Canvas** 1920×1080, landscape, fixed. No scrolling — content must fit. Every screen in
  the mockups measures exactly 1920×1080 with no overflow; keep it that way.
- **Viewing distance** ~3 ft. **No text below 22px.** Meta lines are 22px/600 Nunito;
  quest titles 30px/700 Cinzel; section heads 32px.
- **Contrast** every ink token is ≥4.5:1 on parchment. Do not introduce alpha-muted text.
- **Ground** `--nq-p-parchment` + `--nq-p-vignette`, CSS only, no image assets.
- **Double frame** inset 26px (`--nq-p-frame-outer`, radius 14px) and inset 36px
  (`--nq-p-frame-inner`, radius 8px), both `pointer-events: none`.
- **Dock** bottom strip, 84px, inset 46px, radius 14px, `--nq-p-dock-bg`. Weather only.
  **Nothing in the dock is tappable** (D-006).
- **No login.** Every action comes from the kiosk HA user; the kiosk user is never in the
  admin allowlist.

## 2. The Party — attract state (1a)

Default view on the wall. Layout top to bottom:

1. **Wordmark row** at y=64. Rule · d20 hexagon · `NestQuest` (66px/900 display, brand
   gradient via `background-clip: text`) · d20 · rule. d20 marks are 34px hexagons
   (`clip-path: polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)`) filled with
   the brand gradient, numeral 15px/700 Cinzel.
2. **Kicker** `The Party · <weekday>, <Month D>` — 21px/600 Cinzel, tracking .30em, uppercase.
3. **Adventurer plates**, 3-up grid, 56px gap, page inset 110px, top y=262. One plate per
   child returned by the party sensor, in configured order.
4. **Hint line** `Tap your crest to open your Quest Log`, 27px/600 Nunito, y≈930.
5. **Dock.**

### 2.1 Adventurer plate (present)

Radius 20px, `--nq-p-card-panel`, 2px `--nq-p-panel-border`, `--nq-p-panel-shadow`,
padding 44px 28px 40px, contents centred, 26px gap. **The whole plate is the tap target**
(≥188px wide, ≥600px tall — far above minimum).

- **Crest** 188×214, shield via `clip-path: polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)`,
  `--nq-p-crest`, inset ring `inset 0 0 0 4px rgba(255,255,255,.22)`, child's initial
  82px/700 display in white.
- **Name** 48px/700 Cinzel, `--nq-p-ink`, tracking .02em.
- **Presence pill** radius 9999px, `#e8f4ea` on `rgba(22,120,60,.35)`, `check-circle` 22px
  `#157a3c`, label `Home today` 19px/600 Cinzel uppercase `#146b36`.
- **Progress line** `N of M quests claimed` 26px/700 Cinzel `--nq-p-ink-secondary`.
- **Progress bar** full width, 16px, radius 9999px, track `rgba(92,62,26,.18)` with 1px
  border, fill `--nq-brand-gradient-h`.

### 2.2 Adventurer plate (away)

Same geometry, muted: `linear-gradient(#f2ecdd, #e6dcc6)`, **2px dashed** border, no lift
shadow. Crest uses `--nq-p-crest-away`; initial stays **full-opacity white** (never alpha).
Name in `--nq-p-ink-away`. Pill: `tent` icon, label `On travels`, neutral fill. Progress
line reads `Returns <weekday>, <Mon D>`; empty progress track, no fill. **Not tappable** —
the plate must not navigate, since the child has no instances.

### 2.3 Dock

`cloud-sun` 40px · temperature 38px/800 Nunito `--nq-p-dock-ink` · 1px divider ·
condition + high/low 26px/600 `--nq-p-dock-ink-secondary` · divider · one short forecast
phrase. All read from the configured `weather_entity`; if unset, render the dock with date
and time only rather than removing it (the strip is part of the frame).

## 3. Quest Log (1b)

Reached by tapping a present crest. Header at y=56, page inset 62px:

- Small crest 96×110 (initial 44px/700 display).
- Title `<Name>'s Quest Log` 56px/700 display.
- Sub `<weekday>, <Month D> · N of M claimed` 20px/600 Cinzel, tracking .24em, uppercase.
- **Remaining block** right-aligned: radius 14px panel, d20 mark 44px with the remaining
  count, `N quests left` 28px/700 Cinzel, and a party line
  `Party progress · X of Y today` 22px/600 Nunito.

### 3.1 Window columns

Three equal columns, 34px gap, top y=236, one per window — **Morning** (until 11:59 AM),
**Afternoon** (12:00–5:00 PM), **Evening** (5:00–9:00 PM). Column head: icon
(`sunrise` / `sun` / `moon`) 34px, name 32px/700 Cinzel, sub-label 21px/600 Cinzel
uppercase with the window's clock range, right-aligned `done/total` 26px/700 Cinzel,
14px bottom padding, `--nq-p-rule` underline.

Cards stack at `--nq-p-quest-gap` (24px). Order within a column: **incomplete first,
sealed below**. A window with no quests renders its head and nothing else — do not
collapse the column, the three-column rhythm is the layout.

### 3.2 Quest card — open

`--nq-p-quest-min-height` 116px, radius 12px, `--nq-p-card-open`, 1px
`--nq-p-card-border`, `--nq-p-card-shadow`, padding 22px, 22px gap, row layout:

1. **Icon tile** 64×64, radius 10px, `--nq-p-icon-tile`, glyph 34px white — the
   definition's icon, resolved from its namespaced key (`ADMIN-SPEC.md` §3.3):
   `lucide:<name>` draws the curated Lucide glyph **stroked** (fill none, stroke-width 2,
   round caps and joins); `fa:<name>` draws the curated Font Awesome glyph **filled**;
   `emoji:<grapheme>` renders the emoji **as text**. A legacy bare name resolves as
   `lucide:<name>`. No icon, or any key that does not resolve (unknown namespace or name,
   malformed emoji), falls back to the **star** glyph. Glyph data is bundled from the
   shared registry — nothing is fetched at runtime.
2. **Text** title 30px/700 Cinzel `--nq-p-ink`; meta 22px/600 Nunito
   `--nq-p-ink-secondary` reading `Due by <h:mm A>`. If past due:
   `Overdue · due <h:mm A>` in 22px/700 Cinzel uppercase, tracking .10em,
   `--nq-p-ink-late`.
3. **Complete button** `--nq-p-button-height` 72px × min 150px, radius 10px,
   `--nq-brand-gradient`, `check` 30px + `Complete` 24px/700 Cinzel white,
   `box-shadow: 0 3px 0 rgba(40,20,60,.35)`.

Both the card body and the button open the confirm dialog (§4). Press feedback:
`scale(.98)`, `--nq-dur-micro`.

### 3.3 Quest card — sealed

`--nq-p-card-done`, `opacity: .82`, no shadow, **not tappable**. Icon tile
`--nq-p-icon-tile-done` with the glyph in `--nq-p-ink-secondary`. The sealed tile keeps
the static star glyph — it does **not** render the definition icon — alongside the wax
seal below. Title 30px/700 Cinzel
`--nq-p-ink-muted` with `text-decoration: line-through`. Meta reads
`Claimed <h:mm A>` 22px/600 Nunito `--nq-p-ink-secondary`.

**Wax seal** `--nq-p-seal-size` 78px circle, `--nq-p-seal`, `--nq-p-seal-shadow`,
`check` 38px in `rgba(255,235,235,.95)`, absolutely positioned `right: 16px; top: -12px`,
rotated a few degrees — **vary the rotation per card** (−9°, +6°, −4° in the mockup) so the
board looks stamped by hand, not templated. Entrance: fade + `scale(1.15 → 1)`,
`--nq-dur-base`, `--nq-ease-out`.

### 3.4 Party roll-up

An optional dashed panel in the afternoon column: label `Party roll-up` 18px/600 Cinzel
uppercase, body 23px/600 Nunito `--nq-p-ink-secondary` — one or two sentences on the other
children ("Jordyn has finished her log. Chloe is on travels until Sunday."). Read-only.

### 3.5 Idle return

40 s with no touch → navigate back to the party board view. Reset on any pointer or touch
event. The card owns this; TouchHub Auto-Return must be set longer than 40 s.

## 4. Complete confirm (1j)

Modal over the dimmed log — scrim `rgba(30,20,10,.62)` over the live board.

Dialog 1000px wide at `top: 196px; left: 460px`, radius 20px, parchment panel with 3px
`rgba(92,62,26,.5)`, `box-shadow: 0 26px 60px rgba(20,10,0,.5)`, padding 64px 68px 56px.

- Header row: 104px icon tile (radius 12px, brand gradient, glyph 56px) · window kicker
  21px/600 Cinzel uppercase tracking .24em · quest title 58px/700 display.
- Body 32px/600 Nunito `#3f2f1c`: `Mark this quest complete? Once the seal is set, only a
  parent can undo it.`
- Buttons, 24px gap, both `--nq-p-confirm-button` 108px tall:
  **Not yet** flex 1, `rgba(92,62,26,.1)` with 2px border, `x` 34px + 30px/700 Cinzel;
  **Complete** flex 2, brand gradient, `check` 38px + 32px/700 Cinzel white.
- Dialog enters with fade + `scale(.96 → 1)`, `--nq-dur-modal`, `--nq-ease-out`.
- Dismiss: **Not yet**, scrim tap, or 15 s of no input.

On confirm, call the completion service optimistically, stamp the seal, and re-sort the
column. On service failure, revert the card and surface a single-line parchment toast.

## 5. Quest complete (1c)

Shown when the last instance for a child's day is completed; auto-returns to the board
after 12 s (countdown line `Returning to The Party in N seconds`, 25px/600 Nunito).

- Large seal 168px at y=96 (`check` 86px), rotated −6°, `0 10px 24px rgba(60,10,20,.42)`.
- `Quest complete` 86px/900 display, brand-gradient text fill.
- Sub 34px/600 Nunito `--nq-p-ink-secondary`, max-width 1000px, centred, `text-wrap: pretty`:
  names the child, the date, and how the day went.
- **Stat blocks** 4-up at y=540, inset 200px, 26px gap: radius 16px parchment panels,
  numeral 58px/900 Cinzel, label 17px/600 Cinzel uppercase tracking .14em —
  `Quests claimed`, `On time`, `Late`, `The Party` (household X/Y).
- Dock switches to the evening variant (`cloud-moon`).

## 6. Accessibility and input

- Minimum tap target on this surface is the quest card itself (116px) and the 72px button;
  nothing interactive is smaller than 72px.
- 24px between adjacent tap targets so a stray finger cannot claim the wrong quest.
- No hover states — this is a touch-only surface. Provide `:active` feedback only.
- No animation loops. Entrances only, per the CubeCraft motion rules.
