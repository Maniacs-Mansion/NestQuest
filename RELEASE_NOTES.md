# NestQuest Release Notes

## Version 0.2.0 — 2026-09-14

### Scope

Second release of NestQuest, shipping Feature 02 — the persistence layer the integration owns outright:

- Integration-owned SQLite database (`nestquest.db`) in the Home Assistant config directory: WAL journal mode, foreign-key enforcement, executor-backed access so the event loop never blocks.
- Schema v1 for all eight tables: `children`, `admin_users`, `schedule_rules`, `task_definitions`, `presence_schedules`, `presence_overrides`, `task_instances`, `completion_events` — validated by declarative CHECK constraints (no triggers).
- Versioned migration runner: on first start the database is created at schema version 1; later starts are a verified no-op; a failed migration rolls back to its prior version. A database stamped with a future version refuses to start.
- Typed DAO layers for every table so no other feature writes raw SQL. Assignment validation is atomic; `completion_events` is strictly append-only — the DAO exposes no update or delete method, and a package-wide guard keeps mutation SQL out of every module.
- Startup handling for missing (created fresh), valid (opened), and corrupt (logged, retried, left byte-identical for backup restore) database files via a read-only `integrity_check` preflight that cannot write or create sidecars.

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