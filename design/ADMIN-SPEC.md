# Admin spec — parent phone card

Screens `1d`–`1i`. One card, `nestquest-admin-card`, four tabs. Reference viewport
390×844. Plain CubeCraft styling and plain domain words — no parchment, no Cinzel, no
quest vocabulary in this surface.

## 1. Shell

- Page `--nq-a-page`; cards `--nq-a-surface` with 1px `--nq-a-border`.
- **Header** white, 1px bottom border: screen title 24px/800, tracking −.02em, plus a
  12px/600 `--nq-a-ink-secondary` sub-line. Optional trailing action (icon square 36px,
  or a gradient `New` button).
- **Tab bar** absolute bottom, `--nq-a-tabbar-height` 70px + 12px bottom padding, white,
  1px top border, 4 items: `house` Today · `list-checks` Tasks · `calendar-days` Schedule ·
  `history` History. Active icon and label `--nq-brand-blue` at 700; inactive icon
  `--nq-a-ink-tertiary`, label `--nq-a-ink-secondary` 600.
- **Every scroll column ends with 92px bottom padding** so content clears the tab bar.
  This was a real defect in review — do not omit it.
- Two densities exist. Ship **compact**; `--nq-a-density-*` carries the roomy values.
- Everything this card mutates goes through a NestQuest service, which enforces the admin
  allowlist server-side. The card must assume it can be rendered by a non-admin and still
  be safe — hiding controls is not the boundary (D-003).

## 2. Today (1d compact, 1h roomy)

### 2.1 Header
Title `Today`; sub `<weekday>, <Month D> · cycle day N of 14`; trailing `settings` square.

### 2.2 Stat row
Three equal cards, 8px gap, padding 12px: numeral 22px/800 (done in `--nq-brand-blue`,
remaining in `--nq-a-ink`, overdue in `--nq-a-danger`), label 10px/600 uppercase tracking
.08em `--nq-a-ink-secondary` — `Done`, `Remaining`, `Overdue`.

### 2.3 Child rows
One card, rows divided by `--nq-a-divider`, row padding 11px 13px:
30px gradient avatar square (radius 7px, initial 13px/800 white) · name 14px/700 ·
meta 11px/600 (`3 of 7 · 1 overdue`; all-done in `--nq-a-success`; away reads
`Away · returns <Mon D>`) · 82×6px progress track with gradient fill. An away child's
avatar is flat `#9898A8` and the row carries a lowercase `override` pill when the absence
comes from a presence override rather than a presence pattern.

### 2.4 Roomy variant (1h)
Header becomes a hero: kicker 11px/700 uppercase, `8 of 12 done` 32px/800, 10px gradient
progress bar, 13px/600 sub-line. Each child gets its own 12px-radius card with
`0 4px 12px rgba(0,0,0,.06)`, 48px avatar, 19px/800 name, right-aligned `3/7` +
status line, and its overdue item inlined as a `--nq-a-danger-bg` row with a
`Mark done` action.

### 2.5 Needs attention
Section label 11px/700 uppercase, then one card of event rows: Lucide glyph 18px ·
title `<Quest> · <Child>` 13px/700 · meta 11px/600 (`Overdue since 9:00 AM` in
`--nq-a-danger`; `Completed 7:04 AM from panel` in `--nq-a-ink-secondary`) · trailing
text action `Mark done` (`--nq-brand-blue`) or `Undo` (`--nq-brand-purple`).

### 2.6 Permission note
An info strip (`--nq-a-info-bg`, `info` glyph, 11.5px/600 `--nq-a-info-ink`):
"Undo is admin-only. A panel tap can never reverse a completion." Keep this copy — it is
the one place the security model is explained to the user.

## 3. Definitions (1e)

### 3.1 List
Header `Tasks` / `7 definitions · 3 children` + gradient `New` button. Filter chips row
(All / one per child): active `#18181D` fill white text, inactive white with border.
Rows: glyph 17px · title 13.5px/700 · meta 11px/600 `<assignees> · <recurrence> · <windows>`
· `chevron-right`. An inactive definition renders the whole row at
`--nq-a-ink-tertiary` with `· inactive` in the meta. A definition with completion
history is never hard-deleted (glossary, D-017): Delete retires it to this inactive state.
The row being edited takes `--nq-a-selected` with brand-blue glyph, `Editing` meta and
`chevron-down`.

### 3.2 Edit sheet
Bottom sheet, `--nq-a-radius-sheet`, `--nq-a-sheet-shadow`, 38×4px grabber, padding
14px 18px 24px. Title 19px/800. Fields, 11px gap, each with a 10px/700 uppercase label:

| Field | Control |
|---|---|
| Assigned children | multi-select row → sheet; shows `Declan` or `All three` |
| Repeats | select (Daily / Weekly / Monthly / Yearly / Custom + interval) |
| Due time | time field per window |
| Window | 3-up segmented, **multi-select** — a definition may own several |
| Skip on away days | toggle, gradient when on, sub "No instance when the child is absent" |

Footer: `Cancel` (flex 1, bordered) + `Save changes` (flex 2, gradient), both 13px vertical
padding. Sheet enters over the dimmed list in `--nq-dur-modal`.

Delete (editing an existing definition only, never on `New`): a full-width bordered
`Delete task` button below the footer, danger-ink text. Tapping it swaps the footer for a
danger-tinted confirm — "Delete this task? If it has no completion history it is deleted;
otherwise it is retired (deactivated) and its history is kept." — with `Go back` and a
danger-filled `Delete task`. Confirming calls `DELETE /api/v1/admin/quest-definitions/{id}`
(admin plane only; the kids' panel has no equivalent control). Hybrid outcome (D-017): no
completion event on any instance → the definition, its instances, assignees, windows and
unreferenced rule are hard-deleted and the row leaves the list; otherwise the definition
is retired (deactivated) and the row stays, shown inactive. Retirement preserves the
definition row, schedule rule, assignees, windows and all durable completion history. Like
any deactivation it regenerates, so future uncompleted instances are cleared (they are
rolling, regenerable rows) and none are recreated while the definition is inactive — the
retired task stops generating and no longer shows open work. Durable instance history lives
only in the append-only `completion_events`. An error keeps the sheet open with the API's
detail.

### 3.3 Icon picker
Each definition carries one optional icon, shown on both surfaces. The picker offers three
sources:

- **Lucide** — a grid of the curated Lucide glyphs, drawn stroked.
- **Font Awesome** — a grid of a curated subset of the Font Awesome Free *solid* set,
  drawn filled.
- **Emoji** — a text input; the typed emoji is stored as entered (not trimmed) and must be
  1–8 code points with no whitespace, control characters, `<`, `>` or `&`.

Both curated lists come from `tools/icons/curated-icons.json`; their glyph path data is
generated into the admin and panel bundles by `tools/icons/generate.mjs` (no CDN, no
runtime fetch). See `THIRD-PARTY-NOTICES.md` for licences.

The stored value is a **namespaced key**:

| Source | Stored key | Example |
|---|---|---|
| Lucide | `lucide:<name>` | `lucide:dog` |
| Font Awesome | `fa:<name>` | `fa:paw` |
| Emoji | `emoji:<grapheme>` | `emoji:🐶` |

`<name>` is a lowercase kebab name (`[a-z0-9-]`, no leading or trailing `-`). A **legacy
bare name** written before namespacing (`dog`) reads as `lucide:<name>` — the API returns it
namespaced, and any write of a bare name is stored as `lucide:<name>`; no data migration. An
empty value clears the icon. An empty, unknown, or unresolvable key renders the **fallback
glyph** — in the admin, the generic task glyph (clipboard with a check); on the panel, the
star (`PANEL-SPEC.md` §3.2).

## 4. Schedule (1f)

A child has **zero or more** presence patterns (schema 9). Each pattern has a name, a
kind (`Home` or `Away`), its own cycle length (1–4 weeks), its own anchor date, and a
weekday set per cycle week. The screen shows one child at a time.

- Header `Schedule` / `<Child> · N patterns` (`<Child> · no patterns, home every day`
  when the child has none).
- **Child** chip row: one chip per child; the selected chip drives everything below.
- **Month grid** card: month label 11px/700 uppercase + chevron pair; weekday initials
  10px/700 `--nq-a-ink-tertiary`, **Sunday first** (`S M T W T F S`); day cells
  `aspect-ratio: 1`, radius 6px — home days `--nq-a-selected` with `#201F7A` numerals,
  away days `--nq-a-page` with `--nq-a-ink-secondary`, override days
  `--nq-a-warning-bg` with `--nq-a-warning-ink` and a 1px warning border, today filled
  with the brand gradient in white 800. Legend row beneath, 10.5px/600, one swatch per
  state (`Home`, `Away`, `Override · away`, `Override · home`, `Today`), then the note
  "Combined from every pattern: away beats home; overrides beat both."
- The grid shows the child's **combined** presence, first match wins: an override
  covering the date; else away if any Away pattern covers it; else home if any Home
  pattern covers it; else away when the child has at least one Home pattern (a Home
  pattern lists the days the child is here); else home (only Away patterns, or none).
- **Presence patterns** card: `Add` text action; one row per pattern with
  `calendar-check` (Home) / `calendar-x` (Away), title = pattern name 13px/700, meta
  `Home · Every 2 weeks` 12px/600, and the weekday set (`Thu, Fri` for a 1-week cycle,
  otherwise `Week 1: Sat, Sun · Week 2: No days`). Trailing `pencil` opens the pattern
  editor (§4.1); trailing `trash-2` asks `Delete pattern?` inline before deleting. With
  no patterns the card reads "No patterns for <Child> — home every day."
- **Overrides** card: `Add` text action; rows with `calendar-x` / `calendar-check`,
  title `<Child> away · <Mon D – D>`, meta reason, trailing `trash-2`.
- Cycle position is always computed from each pattern's own anchor date. **Never** from
  ISO week numbers or week parity (D-004).
- Weekday numbering on the wire stays **Monday=0 .. Sunday=6**; Sunday-first is display
  order only.

### 4.1 Pattern editor

Pushed screen with a back chevron; title `New pattern` / `Edit pattern`, sub "Repeating
presence for <Child>". Form card fields:

- **Name** text field (required, not blank).
- **Covered days are** 2-up segmented (`Away` / `Home`), selected = `#18181D`.
- **Cycle length** select (`1 week` … `4 weeks`) and **Anchor date** side by side.
  Changing the cycle length keeps existing weeks and adds new weeks covering no day.
- One **weekday picker** per cycle week, labelled `Week N · from <Mon D>` (the date is
  anchor + (N−1) weeks): seven toggle cells in **Sunday-first** order
  (`Su Mo Tu We Th Fr Sa`). A week may cover no day.

Footer: `Cancel` (flex 1, white, bordered) + `Save pattern` (flex 2, gradient), as the
override editor (§6). Save stays disabled until the name is set, the anchor is a valid
date, and something changed.

## 5. History (1g)

- Header `History` / `Append-only event log · last 14 days` + bordered `CSV` button
  (`download` glyph) that exports the filtered range.
- Stat row: `91%` On time · `128` Completed · `7` Missed, numerals 20px/800.
- Filter chips: `All events` / `Reversals` / `Missed`.
- Day-grouped sections (label 11px/700 uppercase) of event rows: 7px status dot
  (green completed, `--nq-a-reversal` un-completed, `--nq-a-danger` missed) ·
  title `<Quest> · <Child>` 12.5px/700 · meta 10.5px/600 giving event type, actor and
  on-time flag (`completed · panel (Declan) · on time`, `uncompleted · joshua (admin)`,
  `missed · nightly sweep`, `completed · panel (Declan) · late 22 min`) · time 11px/600.
- Footer strip (`--nq-a-page`, `lock` glyph): "Events are never edited or deleted. A
  reversal is its own row." Rows are never editable in the UI (D-005).

## 6. Presence override editor (1i)

Pushed screen with a back chevron; title `Presence override` / sub "Beats the custody
pattern for these dates".

- Form card (roomy density, 18px padding, 16px gaps):
  **Child** 3-up segmented, selected = gradient;
  **Status for these dates** 2-up segmented (`Away` / `Home`), selected = `#18181D`;
  **From** / **Through** date fields side by side, 13px padding, 14px/700 values;
  **Reason (optional)** text field.
- **Consequence warning** — `--nq-a-warning-bg` card with `alert-circle`:
  headline `This removes N upcoming tasks` 13.5px/700 `--nq-a-warning-ink`, body 12px/600
  `--nq-a-warning-ink-2` naming the child, the date range, and stating "Completed days are
  untouched." The count must be computed live from the materialiser before saving.
- Footer: `Cancel` (flex 1, white, bordered) + `Save override` (flex 2, gradient), 15px
  vertical padding.
- Saving must never delete an instance that already has a completion event.
