# NestQuest — design handoff

Approved UI design for the NestQuest Home Assistant integration, ready to implement.
Source of truth for visuals: the mockup file `NestQuest Mockups.dc.html` (9 screens,
option ids `1a`–`1j`). This folder is the written form of those screens.

## What is in here

| File | Contents |
|---|---|
| `PANEL-SPEC.md` | Kids' DAKOS wall panel: party board, quest log, confirm, quest complete |
| `ADMIN-SPEC.md` | Parent phone admin: today, definitions, schedule, history, overrides |
| `ENTITIES-AND-SERVICES.md` | Every screen mapped to the HA entities, services and events it needs |
| `IMPLEMENTATION-ORDER.md` | Build order, with the decisions that change existing code first |
| `tokens/nestquest-panel-tokens.css` | Panel card custom properties |
| `tokens/nestquest-admin-tokens.css` | Admin card custom properties |

## Screen index

| id | Screen | Surface | Spec |
|---|---|---|---|
| 1a | The Party (attract) | panel 1920×1080 | PANEL §2 |
| 1b | Quest Log | panel 1920×1080 | PANEL §3 |
| 1j | Complete confirm | panel 1920×1080 | PANEL §4 |
| 1c | Quest complete | panel 1920×1080 | PANEL §5 |
| 1d | Today (compact) | phone 390×844 | ADMIN §2 |
| 1e | Definitions + edit sheet | phone 390×844 | ADMIN §3 |
| 1f | Schedule + custody | phone 390×844 | ADMIN §4 |
| 1g | History + CSV | phone 390×844 | ADMIN §5 |
| 1h | Today (roomy) | phone 390×844 | ADMIN §2.4 |
| 1i | Presence override | phone 390×844 | ADMIN §6 |

## Design decisions taken during this handoff

These were open in CTXD and are now settled. Several contradict the current repo and
docs — read `IMPLEMENTATION-ORDER.md` §1 before writing code.

1. **`quest_*` naming throughout.** The domain model is renamed from `task_*` to
   `quest_*` in DB, services, entities and UI. Migration note in IMPLEMENTATION-ORDER §1.1.
2. **Instance key becomes `(definition_id, child_id, due_date, window)`.** Required by
   multi-assignee definitions and by twice-daily quests. Supersedes the documented
   `(definition_id, due_date)`.
3. **A definition may have multiple assignees**, and materialises one instance per
   assigned child per date per window. Each child completes their own.
4. **A definition may declare more than one window** (morning / afternoon / evening),
   producing one instance per window per day.
5. **Missed quests vanish from the panel at rollover.** Kids never see a wall of failure;
   the missed event is in the parent's history only.
6. **Three Lovelace cards**: `nestquest-party-board-card`, `nestquest-quest-log-card`,
   `nestquest-admin-card`. Board and log live in separate Lovelace views; a crest tap
   navigates.
7. **Completion needs a confirm step** (screen 1j) because children cannot undo.
8. **The quest log owns idle return**: 40 s of no touch navigates back to the board.
   TouchHub Auto-Return must be configured longer than 40 s so the two do not fight.
9. **Actor on a panel completion** is `panel` plus the tapped child profile, per glossary.
10. **Weather is a configured entity** on the party board card (`weather_entity`), not
    NestQuest data.
11. **Fonts are bundled** as local woff2 in the card's `www/` folder — the panel may be
    offline. Nunito (400/600/700/800) and Cinzel + Cinzel Decorative.

## Vocabulary

The panel speaks tabletop; the admin speaks plainly. Both sit on the same `quest_*` model.

| Model / admin | Panel display string |
|---|---|
| quest instance | quest |
| child | adventurer |
| child's task list | Quest Log |
| household | The Party |
| all complete | Quest complete |
| absent | On travels |

## Open questions

- Empty and error states are unspecified by request (child with no quests, everyone away,
  integration unconfigured, DB unreachable). Panel must not render a blank parchment —
  decide before shipping the card.
- No gamification is in scope. XP, levels, streaks and rarity were explicitly deferred,
  but the append-only event log already supports computing them later.
- Icon per quest definition is chosen by the parent from curated Lucide and Font Awesome
  Free sets or as an emoji, stored as a namespaced key (`lucide:`/`fa:`/`emoji:`) —
  resolved 2026-09-26, see `ADMIN-SPEC.md` §3.3.
