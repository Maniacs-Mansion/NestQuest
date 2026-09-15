# NestQuest Release Notes

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