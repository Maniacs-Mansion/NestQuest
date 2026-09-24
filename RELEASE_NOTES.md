# NestQuest Release Notes

## Version 0.7.0 — 2026-09-24

### Scope

Seventh release of NestQuest, promoting the admin surface from `dev` onto
0.6.0: the standalone admin PWA and the admin-plane API work it depends on.

- **Feature 19 — Admin PWA:** the parent-facing admin surface is now a
  standalone mobile-first React progressive web app (`admin/`), implementing
  `design/ADMIN-SPEC.md`: Authentik OIDC authorization-code + PKCE login with
  an explicit refusal for a user outside `nestquest-admins`; an installable
  PWA (manifest + service worker); and the Today, Definitions, Schedule and
  History screens. Every mutating action goes through the API admin routes;
  the API remains the security boundary (D-003/D-012). Today shows the
  household snapshot; Definitions supports create/edit with multi-select
  assignees, a recurrence rule with interval and per-window due times, a
  skip-on-away toggle, a shipped Lucide icon subset and a backend-computed
  occurrence preview; Schedule has a presence month grid (cycle position from
  the anchor date, never ISO parity, D-004) and an override editor with a live
  "removes N upcoming tasks" consequence count; History has All/Reversals/
  Missed filters, day-grouped rows, per-period stats, CSV export and the
  append-only footer. Undo reverses a completion, and live updates arrive over
  the admin SSE stream without a manual reload. (PRs #187–#210, plus the
  feature-review fix #212.)
- **Feature 21 — Admin Today Snapshot API:** `GET /api/v1/admin/snapshot`
  serves the Today view's household snapshot on the admin plane (reusing the
  core snapshot builder with missed instances included, D-009). (PRs #190/#191.)
- **Feature 22 — Admin Definitions Read and skip_on_away:**
  `GET /api/v1/admin/quest-definitions` lists all definitions (active and
  inactive), and a persisted per-definition `skip_on_away` boolean is accepted
  by create/update and honoured by materialization. Adds an optional
  `assignee_child_ids` to the edit route so the PWA can reassign children.
  (PRs #193, #194, #196, #197.)
- **Feature 23 — Admin API Completion (preview, presence, live):** a bounded
  rule occurrence-preview route; presence-schedule and presence-override
  reads; a live override consequence count computed from the same core
  generator the materializer uses; and an admin-plane transition SSE stream
  (`GET /api/v1/admin/events`) off the one in-process publisher. (PRs
  #199–#203.)

### Requirements

- Minimum Home Assistant version: **2024.6.0**.
- A running NestQuest API service, reachable at the base URL and panel service
  token configured in the integration options. The API service source ships in
  `api/`; there is still **no container image, compose file or deployment
  runbook in this release** because Feature 17 is not part of it.
- The admin PWA is built to run at `https://nestquest.cubecraftlabs.com`
  behind Authentik; hosting it is part of the Feature 17 deployment, which is
  **not** in this release.

### Breaking changes

- **Schema version advances 7 → 8.** Migration 8 adds the additive
  `skip_on_away` column to `quest_definitions` (default 1, so every existing
  definition keeps today's skip-when-absent behaviour). The migration runs on
  the first start of this version.
- **Once migrated, a plain downgrade to 0.6.0 is impossible** — older builds
  refuse a newer schema version. **Back up `nestquest.db` (plus `-wal`/`-shm`)
  before upgrading**; see Rollback.
- No Home Assistant entity, service, event or automation surface changes in
  this release. The API's new admin routes are additive.

### Known Limitations

- **Feature 17 (API deployment and identity) is not in this release.** There
  is no API box, TLS reverse proxy, Authentik application/provider/
  `nestquest-admins` group, proven network separation, or backup/restore. The
  integration and the admin PWA therefore cannot run end-to-end yet; Feature
  19's end-to-end Authentik/HTTPS acceptance remains **unverified** until
  Feature 17 is deployed.
- **The admin PWA is not hosted.** `admin/` builds and is unit/integration
  tested, but there is no deployment for it (it depends on Feature 17).
- **Feature 12's TouchHub/DAKOS runbook task remains physically unverified**
  (needs the wall panel).
- Moving the household database from Home Assistant to the API box is a manual
  file copy (the schema is unchanged by that move beyond the v8 migration).
- Single household; single API service.

### Rollback

**Schema version advances 7 → 8.** Migration 8 is additive, but a migrated
database **cannot** be read by 0.6.0 or earlier (they refuse a newer schema
version). **Back up `nestquest.db` (plus `-wal`/`-shm`) before upgrading.** To
return to 0.6.0 you must restore that backup; a plain downgrade is impossible
once migrated.

**HACS installs:**

1. Before upgrading, stop HA and back up `nestquest.db` (plus `-wal`/`-shm`)
   from the HA config directory.
2. To roll back: HACS > Integrations > NestQuest > Redownload > 0.6.0, restore
   the backed-up database, restart Home Assistant.

**Manual installs:**

1. Back up `nestquest.db` (plus `-wal`/`-shm`) before upgrading.
2. To roll back: replace `custom_components/nestquest/` with the 0.6.0 tree,
   restore the backed-up database, restart Home Assistant.

**Repository operators:** git-revert the 0.7.0 release merge on `main`.

## Version 0.6.0 — 2026-09-23

### Scope

Sixth release of NestQuest, promoting the re-imagined architecture
(Features 15, 16, 18 and 20) and the foreground development-orchestration
tooling from `dev` onto 0.5.0. This is a major architectural change: the
Home Assistant integration becomes a thin client of a standalone NestQuest
API service that owns the database.

- **Feature 15 — Domain Core Extraction:** all domain code (schema,
  migrations, database access, the DAOs, the pure recurrence/presence
  engines, materialization, completion, the SSE-free event payload
  builders, the panel snapshot builder, the children/definitions/allowlist
  business layers, and an explicit settings object) now lives in a
  Home-Assistant-free package bundled inside the integration at
  `custom_components/nestquest/core/`. The SQLite schema and migration
  versions are unchanged, so an existing `nestquest.db` opens without
  migration. Covered by a no-Home-Assistant end-to-end smoke test.
  (Tasks d0b691d8, 510c1f78, 4dd8f870, 628473ad.)
- **Feature 16 — NestQuest API Service:** a standalone FastAPI service
  (`api/`) that imports `core/` and is the only writer of the database.
  Panel plane (`/api/v1/panel/*`) is authenticated by a static service
  token: household snapshot and an idempotent complete route. Admin plane
  (`/api/v1/admin/*`): children, quest definitions, presence
  schedule/override, uncomplete, regenerate, history query + CSV export,
  and settings — authenticated by an Authentik OIDC JWT (issuer, audience,
  JWKS signature and expiry) plus membership in `nestquest-admins`, with
  the panel service token rejected outright. A server-sent-events stream
  publishes the quest-completed, quest-uncompleted, quest-missed and
  child-day-complete transitions; the missed sweep runs in the API with a
  cross-process-safe watermark. `/health` and the OpenAPI document are
  served. (Tasks 042dfc5c, ae7e90ae, 1860ef76, 4d7bae00, 44c93cfd,
  e70e6bfb, 0f2afb29, e4845baa, b586a2f1, e4a9d31b, da0226b3, 2d2dda53,
  2b3de7e5, 9047a97b, 9a118da9, 058c7b69, a232c4f5.)
- **Feature 18 — HA Integration as API Client:** the integration no longer
  owns a database. It polls `GET /api/v1/panel/snapshot` and builds the
  existing sensors (entity ids and per-child instance payload shape
  unchanged), subscribes to the SSE stream and re-fires the four HA bus
  events, proxies `nestquest.complete_quest` to the panel complete route,
  and caches the last-good snapshot so a brief API outage does not blank
  the panel. The HA admin services and the service permission gate are
  removed; only the panel completion path remains. (Tasks 37d5e806,
  6e70d166, b1ed9c45, 47c7c90e, d25b875f, d04f5bf3, ad67fc44.)
- **Feature 20 — Zero-Config Panel Dashboard:** the panel installs with no
  hand-written card YAML and no manual dashboard creation. The cards
  auto-discover children from a household entity attribute (ordered by the
  API's `sort_order`), a Lovelace dashboard strategy generates the
  party-board view and one quest-log view per child at render time with
  computed navigation paths, and the integration registers the dashboard
  on first setup. Navigation and the panel transitions match the design
  mockups. (Tasks 1b6d91d2, c859af23, c2d4dd8e, 107b8fbe, 50067c1f,
  fc69c940, 67775be9.)
- **Development orchestration tooling:** durable OpenCode controller and
  role launchers, the foreground terminal orchestrator, the independent
  review/approval gates, and the automatic release-preparation policy.

### Requirements

- Minimum Home Assistant version: **2024.6.0**.
- A running NestQuest API service, reachable at the base URL and panel
  service token configured in the integration options. The API service
  source ships in `api/`; there is no container image, compose file or
  deployment runbook in this release, and Feature 17 — the deployment
  (TLS reverse proxy, Authentik, network separation, backups) — is **not**
  part of this release and must be completed before the integration is
  functional. See `docs/ARCHITECTURE.md` for the target design.

### Breaking changes

- **The HA integration no longer owns a database.** It reads exclusively
  from the NestQuest API. The local `nestquest.db` is no longer opened,
  migrated or written by the integration (the file is left untouched on
  disk). Without a reachable API the entities become unavailable after the
  configured staleness threshold; the panel serves the last-good snapshot
  in the meantime.
- **HA admin services are removed** (`uncomplete`, quest-definition
  create/update/set-active, presence pattern/override, CSV export,
  `manage_child`, `regenerate`) and the HA-side permission gate is gone.
  Admin operations move to the API, and — once Feature 19 lands — the
  admin PWA. Any automation that called an admin service must be
  repointed at the API.
- **Logger namespaces moved** under `custom_components.nestquest.core.*`:
  the migrations runner now logs under
  `custom_components.nestquest.core.migrations` (previously
  `custom_components.nestquest.migrations`), and the children registry and
  admin allowlist log under `custom_components.nestquest.core.children` and
  `custom_components.nestquest.core.admin_allowlist`. The parent
  `custom_components.nestquest` logger still catches all three; only users
  who pinned a leaf logger name by its old spelling must update.
- **The panel installs with no configuration.** `child_order`,
  `quest_log_path` and `board_path` are no longer required (an explicit
  value still wins). The integration registers a `custom:nestquest-party`
  dashboard on setup; point TouchHub at it.
- **Schema is unchanged at version 7** — no migration runs on upgrade.

### Known Limitations

- **Feature 17 (API deployment and identity) is not in this release.** The
  API service source ships in `api/`, but no container image, compose
  file, TLS reverse proxy, Authentik application/provider/`nestquest-admins`
  group, proven network separation of the panel routes, or backup/restore
  is included. Feature 17's containerization groundwork was completed on
  its own feature branch, which is **not** merged into `dev` and therefore
  is not part of this release. Until that deployment is completed the
  integration has nothing to talk to.
- **Feature 19 (admin PWA) is not in this release.** There is no admin UI
  in 0.6.0; admin operations are reachable only through the API directly.
- Moving the household database from Home Assistant to the API box is a
  manual file copy (the schema is unchanged).
- Single household; single API service.

### Rollback

Schema version is unchanged (7), so no migration is involved in either
direction. Nevertheless **back up `nestquest.db` (plus `-wal`/`-shm`)
before upgrading**: 0.6.0 never touches it, and a downgrade to 0.5.0
resumes using exactly that file.

**HACS installs:**

1. Downgrade via HACS (HACS > Integrations > NestQuest > Redownload > 0.5.0).
2. Restart Home Assistant.

**Manual installs:**

1. Replace `custom_components/nestquest/` with the 0.5.0 tree.
2. Restart Home Assistant.

**Repository operators:** git-revert the 0.6.0 release merge on `main`.

## Version 0.5.0 — 2026-09-18

### Scope

Fifth release of NestQuest, promoting Features 06, 07, and 08 from `dev` onto 0.4.0 (quest model, children registry, presence engine):

- **Feature 06 — quest definitions and assignment:** business layer `quest_definitions.py` over the multi-assignee / multi-window model (D-008). Create/edit/deactivate definitions; assign/unassign children; query helpers for materialization. `ScheduleRule` ⇄ `schedule_rules` storage mapping in the DAO layer.
- **Feature 07 — instance materialization:** `materialize.py` fans out one instance per (definition, child, window, firing date) when the recurrence rule fires and the child is present. Idempotent on `(definition_id, child_id, due_date, window)`; skips completed instances; never generates past dates. HA-local `today` and configured `horizon_days` threaded end-to-end. Regeneration on definition/assignee/presence changes; daily rollover listener; startup backfill; `nestquest.regenerate` service.
- **Feature 08 — completion and event log:** business layer `completion.py` wrapping the existing append-only `CompletionEventsDao`. `complete_instance` / `uncomplete_instance` (reversal event, original row untouched); state derived from the latest event; HA-local `was_on_time`; derived `missed` (never stored). Actor shapes `'user'` / `'panel'` with `actor_child_id` (D-008). Permission gating of un-complete is Feature 09.

### Requirements

- Minimum Home Assistant version: **2024.6.0**.

### Breaking changes

- None at the schema layer. Schema remains **version 6** (advanced in 0.4.0). This release adds application code only.

### Known Limitations

- No permission decorator yet (Feature 09): `complete_instance` / `uncomplete_instance` are Python APIs, not gated HA services. The only HA service in this release is `nestquest.regenerate`.
- No entity or event surface (Feature 10): no sensors, no `nestquest_quest_completed` bus events.
- No panel or admin Lovelace cards (Features 12/13).
- Un-complete is implemented but not admin-gated until Feature 09.
- Single-instance only.

### Rollback

Schema version is unchanged from 0.4.0 (still 6). A code downgrade to 0.4.0 does not require a database restore for schema compatibility, but **back up `nestquest.db` (plus `-wal`/`-shm`) before upgrading** — generated instances and completion events written by 0.5.0 remain in the file after downgrade; 0.4.0 will not generate or complete them.

**HACS installs:**

1. Downgrade via HACS (HACS > Integrations > NestQuest > Redownload > 0.4.0).
2. Restart Home Assistant.

**Manual installs:**

1. Replace `custom_components/nestquest/` with the 0.4.0 tree.
2. Restart Home Assistant.

**Repository operators:** git-revert the 0.5.0 release merge on `main`.

## Version 0.4.0 — 2026-09-15

### Scope

Fourth release of NestQuest, shipping three completed features on top of the data layer and recurrence engine:

- **Feature 14 — quest domain model (BREAKING rename, D-007/D-008):** `task_definitions`/`task_instances` are now `quest_definitions`/`quest_instances` everywhere; definitions are multi-assignee (`quest_definition_assignees`, no single child column) and multi-window (`quest_definition_windows` — morning/afternoon/evening, clock ranges in `const.py`); the instance key widens to `(definition_id, child_id, due_date, window)` so twice-daily and shared quests materialise one instance per child per window per day; `completion_events` gains `actor_child_id` (the tapped panel profile; admin events stay NULL) with a second actor-pair CHECK. Schema version advances to **6**.
- **Feature 03 — children registry & admin allowlist:** typed business layer for child profiles (create/edit with trimmed required names and duplicate-name warnings, whole-table reorder, deactivation as the only removal path — history is never touched); the admin allowlist with a fail-closed `is_admin` resolver (empty allowlist denies everyone; the last admin cannot be removed); automatic seeding on first setup (the config-flow user is persisted in entry data, with the options-flow list and HA owner accounts as fallbacks) so the owner is never locked out; the options flow gains a multi-select picker of existing Home Assistant users.
- **Feature 05 — presence & custody engine:** a pure `PresenceSchedule`/`PresenceOverride` model with total validation and lossless round-trips; anchor-date cycle arithmetic (D-004 — never ISO week numbers or parity); `PresenceEngine.is_present` with the always-present default for schedule-free children; date overrides beat the repeating pattern; a `next_present_dates` preview for the admin schedule UI; a full-year regression guard walking 2020 (366 days, ISO week 53) and 2015 (365 days, ISO week 53) proving the rotation never inverts at a year boundary.

### Requirements

- Minimum Home Assistant version: **2024.6.0**.

### Breaking changes

- The database schema advances from version 1 to version 6. Upgrades are automatic and data-preserving (legacy `task_*` tables are renamed; the definitions table is rebuilt for multi-assignee; legacy instances pin to the morning window; panel events backfill `actor_child_id`). **Back up `nestquest.db` before upgrading** — see Rollback.
- Dev installs from before 2026-09-15 migrate automatically on first start.

### Known Limitations

- Still no entities, services, calendar platforms, or panel cards: nothing is user-visible in Home Assistant yet (Features 06-10 land the business layer, materialisation, permission gate, and entity surface).
- No materialisation yet: instances are not generated from definitions + presence yet (Feature 07).
- Single-instance only.

### Rollback

**Back up `nestquest.db` (plus `-wal`/`-shm` sidecars) BEFORE upgrading.** This release migrates the database to schema version 6 with renamed tables; an older NestQuest build refuses a version-6 database ("newer than this integration understands") and cannot read renamed tables at all — a plain downgrade is NOT possible once the database has been migrated.

**Rollback procedure (after a migrated database):**

1. Stop Home Assistant.
2. Restore the pre-upgrade `nestquest.db` backup (and sidecars) you made before upgrading.
3. Downgrade the integration (HACS > Integrations > NestQuest > Redownload > 0.3.0) or replace `custom_components/nestquest/` manually.
4. Restart Home Assistant.

Without a backup, the only path is staying on 0.4.0 (recommended) or deleting the integration and its database to start fresh (Settings > Devices & Services > NestQuest > Delete, then remove `nestquest.db`).

**Repository operators:** instead of uninstalling, git-revert the release merge on `main` and restore the pre-upgrade database.

## Version 0.3.0 — 2026-09-14

### Scope

Third release of NestQuest, shipping Feature 04 — the recurrence rule engine:

- `ScheduleRule`: an immutable, validated rule model (frozen dataclass) covering six recurrence shapes — daily, weekly (weekday sets), monthly by day-of-month, monthly by nth-weekday, yearly, and custom day-sets — with interval multipliers (every N days/weeks/months) and optional start/end dates.
- `occurs_on(rule, date)`: pure calendar evaluation answering "does this rule fire on this date?"
- `occurrences_between(rule, start, end)`: ordered, duplicate-free date lists, inclusive bounds, clamped to the rule's window.
- Documented month-end policy: a rule for a day absent from a month (the 31st in April, the 30th/29th in February) fires on that month's LAST day — one firing per eligible month, interval anchored on nominal months elapsed.
- Documented leap-day policy: a YEARLY February 29th rule fires February 28th in non-leap years (clamp, never skip).
- Week offsets anchored at `start_date` by whole weeks elapsed — never ISO week numbers or parity (53-week years cannot silently invert schedules).
- The engine is pure: no Home Assistant imports, no database access, no timezone logic.

### Requirements

- Minimum Home Assistant version: **2024.6.0**.

### Known Limitations

- No entities, services, or calendar platforms yet — the integration does not expose sensors, calendar events, or service calls in this release (data layer + recurrence engine only).
- No business logic yet: nothing materializes task instances (Feature 07 combines this engine with presence schedules) — storage and scheduling math only.
- Single-instance only — one NestQuest config entry is permitted per Home Assistant instance.

### Rollback

Downgrading from 0.3.0 to 0.2.0 removes the recurrence engine's code but leaves the `nestquest.db` file in place (untouched by both releases; no code path deletes an existing database). The file's schema version stamp is unaffected — this release ships no schema migration.

**HACS installs:**

1. Downgrade via HACS (HACS > Integrations > NestQuest > Redownload > 0.2.0) or Remove entirely.
2. Restart Home Assistant.
3. If removing: delete the integration in Home Assistant (Settings > Devices & Services > NestQuest > Delete), then restart Home Assistant again.

**Manual installs:**

1. Replace or delete the `custom_components/nestquest/` directory in your Home Assistant configuration directory.
2. Restart Home Assistant.

**Data:** the `nestquest.db` file (plus any `-wal`/`-shm` sidecars) is intentionally left untouched by both upgrade and rollback — back it up before upgrading.

**Repository operators:** instead of uninstalling, git-revert the release merge on `main`.

## Version 0.2.0 — 2026-09-14

### Scope

Second release of NestQuest, shipping Feature 02 — the persistence layer the integration owns outright:

- Integration-owned SQLite database (`nestquest.db`) in the Home Assistant config directory: WAL journal mode, foreign-key enforcement, executor-backed access so the event loop never blocks.
- Schema v1 for all eight tables: `children`, `admin_users`, `schedule_rules`, `task_definitions`, `presence_schedules`, `presence_overrides`, `task_instances`, `completion_events` — validated by declarative CHECK constraints (no triggers).
- Versioned migration runner: on first start the database is created at schema version 1; later starts are a verified no-op; a failed migration rolls back to its prior version. A database stamped with a future version refuses to start.
- Typed DAO layers for every table so no other feature writes raw SQL. Assignment validation is atomic; `completion_events` is strictly append-only — the DAO exposes no update or delete method, and a package-wide guard keeps mutation SQL out of every module.
- Startup handling for missing (created fresh), valid (opened), and corrupt (logged, retried, left byte-identical for backup restore) database files via a read-only `integrity_check` preflight that cannot write or create sidecars. An existing zero-byte file is treated as corrupt and left untouched, not silently initialized.

### Requirements

- Minimum Home Assistant version: **2024.6.0**.

### Known Limitations

- No entities, services, or calendar platforms yet — the integration does not expose sensors, calendar events, or service calls in this release (data layer only).
- No business logic yet: nothing materializes task instances and nothing can be completed — storage and schema only.
- Single-instance only — one NestQuest config entry is permitted per Home Assistant instance.

### Rollback

Downgrading from 0.2.0 to 0.1.0 removes the data layer's code but leaves the `nestquest.db` file in place (0.1.0 never touches it, and no code path deletes an existing database). The file is compatible with this release's schema version stamp; a later reinstall of 0.2.0 or newer resumes from the stored version without re-migrating.

**HACS installs:**

1. Downgrade via HACS (HACS > Integrations > NestQuest > Redownload > 0.1.0) or Remove entirely.
2. Restart Home Assistant.
3. If removing: delete the integration in Home Assistant (Settings > Devices & Services > NestQuest > Delete), then restart Home Assistant again.

**Manual installs:**

1. Replace or delete the `custom_components/nestquest/` directory in your Home Assistant configuration directory.
2. Restart Home Assistant.

**Data:** the `nestquest.db` file (plus any `-wal`/`-shm` sidecars) is intentionally left untouched by both upgrade and rollback — back it up before upgrading. Removing the integration via Home Assistant deletes the config entry but not the database file.

**Repository operators:** instead of uninstalling, git-revert the release merge on `main`. The database file is independent of the code and is never deleted by code.

## Version 0.1.0 — 2026-09-13

### Scope

First release of NestQuest, a Home Assistant custom integration for managing chores, custody schedules, and house coordination. This release ships the integration foundation/configuration scaffold only (Feature 01):

- Integration package and manifest, plus HACS metadata (`hacs.json`).
- Shared constants module.
- Single-instance config flow for initial setup.
- Setup/unload lifecycle handling with an options-reload listener.
- Options flow for configuring `horizon_days`, `day_rollover_time`, and `panel_idle_timeout`.
- SQLite storage path resolver — path resolution only; the database itself is not created in this release.
- Test harness (`pytest` via `uv`).

### Requirements

- Minimum Home Assistant version: **2024.6.0**.

### Known Limitations

- No entities, services, or calendar platforms yet — the integration does not expose sensors, calendar events, or service calls in this release.
- Single-instance only — one NestQuest config entry is permitted per Home Assistant instance.
- The integration does not yet create its database file; storage is limited to resolved configuration paths.

### Rollback

v0.1.0 is the first release — there is no previous NestQuest version to downgrade to, so rollback means complete removal. This release performs no data or schema migrations.

**HACS installs:**

1. Remove the NestQuest integration via HACS (HACS > Integrations > NestQuest > Remove).
2. Restart Home Assistant.
3. Remove the integration in Home Assistant (Settings > Devices & Services > NestQuest > Delete), then restart Home Assistant again.

**Manual installs:**

1. Delete the `custom_components/nestquest/` directory from your Home Assistant configuration directory.
2. Restart Home Assistant.
3. Remove the integration in Home Assistant (Settings > Devices & Services > NestQuest > Delete), then restart Home Assistant again.

**Data:** the integration does not yet create its own database file, so there is no application data. However, Home Assistant persists the config entry and its selected options — removing the integration deletes that configuration, and the option values (`horizon_days`, `day_rollover_time`, `panel_idle_timeout`) will be lost on removal.

**Repository operators:** instead of uninstalling, you may git-revert the release merge on `main`, which removes the integration files entirely. End users should use the uninstall path above.
