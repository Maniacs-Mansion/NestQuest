# Implementation order

Written for an agent working in `code.cubecraftlabs.com/Maniacs_Mansion/NestQuest`.
Steps 1.x change existing code and must land first; the frontend is step 4 onward.

## 1. Model changes (breaking, pre-release)

### 1.1 Rename `task_*` → `quest_*`
Nothing is released (main/dev are at "first commit", version 0.1.0), so rename in place
rather than aliasing.

- `schema.py`: `task_definitions` → `quest_definitions`, `task_instances` →
  `quest_instances`. Keep `completion_events`, `children`, `admin_users`,
  `schedule_rules`, `presence_patterns`, `presence_overrides`. (`presence_patterns` —
  zero or more `home`/`away` patterns per child — replaced the retired one-per-child
  schedule table in schema 9; migration 9 converts its rows into `home` patterns.)
- `db.py` / `store.py`: rename DAO methods and any SQL literals.
- `const.py`: no table names live there today; keep it that way.
- `tests/test_schema.py`, `tests/test_store.py`, `tests/test_db.py`: update expectations.
- **Migration note:** the versioned migration runner has no released version to upgrade
  from. Bump the schema version, and make migration 1 create the `quest_*` tables
  directly. If any dev machine already holds a `nestquest.db` with `task_*` tables, the
  runner should detect the legacy names and `ALTER TABLE ... RENAME TO` before applying
  the widened index — a dev-only path, worth ~20 lines and a test.

### 1.2 Widen the instance key
Unique index becomes `(definition_id, child_id, due_date, window)`. Materialisation stays
idempotent on that tuple. Add a test for the twice-daily case (one definition, two windows,
one child, one date → two rows) and the shared case (one definition, three assignees, one
window → three rows).

### 1.3 Multi-assignee definitions
Add `quest_definition_assignees(definition_id, child_id)`. Drop the single `child_id`
column on the definition. The "exactly one assigned child" rule in GLOSSARY.MD no longer
holds — CTXD has been updated.

### 1.4 Windows
Add `quest_definition_windows(definition_id, window, due_time)` with
`window ∈ ('morning','afternoon','evening')`. Window clock ranges are fixed for now:
morning ≤ 11:59, afternoon 12:00–17:00, evening 17:00–21:00. Store the ranges in
`const.py` so they are configurable later.

### 1.5 `actor_child_id` on completion events
Nullable int. Set for panel completions, null for admin ones. Still append-only.

## 2. Engines and materialisation
Unchanged in intent: pure recurrence engine, pure presence engine with anchor-date
arithmetic (per pattern, each with its own anchor; since schema 9 it combines a child's
patterns and overrides first-match-wins), daily materialiser over `horizon_days` at
`day_rollover_time`. Only the instance fan-out changes (assignees × windows).

## 3. Services, permissions, entities
Implement the service table in `ENTITIES-AND-SERVICES.md` §2 behind the permission
decorator, then the sensors and binary sensors in §1, then the four events in §3.
`complete_quest` is the only service a non-admin context may call.

## 4. Frontend groundwork
1. Create `custom_components/nestquest/www/`.
2. Bundle fonts as woff2: Nunito 400/600/700/800; Cinzel 600/700/900; Cinzel Decorative
   700/900. Declare `@font-face` with `font-display: swap` in a shared
   `nestquest-fonts.css`. No CDN — the panel may be offline.
3. Copy `design/tokens/nestquest-panel-tokens.css` and
   `design/tokens/nestquest-admin-tokens.css` in as the cards' `:host` blocks.
4. Register the three cards with `customCards` and ship editors later; hand-written YAML
   is fine for v1.

## 5. Cards, in this order
1. `nestquest-party-board-card` (screen 1a) — read-only, proves the entity payload.
2. `nestquest-quest-log-card` (1b) — read-only first, no completion.
3. Confirm dialog + `complete_quest` (1j) with optimistic seal and revert-on-failure.
4. Quest complete screen (1c) driven by `nestquest_child_day_complete`.
5. Idle return (40 s) and the documented TouchHub Auto-Return constraint.
6. `nestquest-admin-card`: Today (1d) → Definitions + sheet (1e) → Schedule (1f) →
   History + CSV (1g) → Presence override (1i).

## 6. Before shipping
- `use_x_frame_options: false` is required for TouchHub embedding — document the
  clickjacking trade-off next to the setting, per D-006.
- Verify no NestQuest control in the dock strip is tappable.
- Verify the kiosk HA user is absent from the admin allowlist, and that
  `uncomplete_quest` denies it with a logged denial.
- Empty and error states are still unspecified (see DESIGN-HANDOFF "Open questions").
  Do not ship a card that renders a blank parchment.
