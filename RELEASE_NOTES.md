# NestQuest Release Notes

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