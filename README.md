# NestQuest - House Chaos Coordination

Home Assistant custom integration for managing chores, custody schedules, and house coordination.

## Overview

NestQuest helps households coordinate daily life, chore tracking, custody schedules, and shared tasks directly within Home Assistant. Version 0.2.0 ships the integration foundation (a configuration scaffold providing the package and manifest, shared constants, a single-instance config flow, setup/unload lifecycle handling with an options-reload listener, an options flow for horizon days / day rollover time / panel idle timeout, and HACS metadata) plus its persistence layer: an integration-owned SQLite database (`nestquest.db`) with WAL mode and foreign keys, a versioned migration runner stamping schema version 1 across eight tables (children, admin_users, schedule_rules, task_definitions, presence_schedules, presence_overrides, task_instances, completion_events), typed DAO layers so no other feature writes raw SQL, an append-only completion-event log, and startup handling that creates a missing database, opens a valid one, and refuses — without touching a single byte — to start on a corrupt one. Sensors, calendar events, and service calls are forthcoming in later releases and are not yet part of the integration.

## Installation

### HACS Installation (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Select the three-dots menu in the top right and click **Custom repositories**.
4. Enter the repository URL: `https://github.com/talon2king/NestQuest`
5. Select category **Integration** and click **Add**.
6. Search for **NestQuest** and click **Download**.
7. Restart Home Assistant.

> **Note:** Development happens in the private Gitea repository
> (`https://code.cubecraftlabs.com/Maniacs_Mansion/NestQuest`). The GitHub
> repository is a public mirror maintained for HACS distribution.

### Manual Installation

1. Download the latest release from the repository.
2. Copy the `custom_components/nestquest` directory into your Home Assistant installation's `config/custom_components/` folder:
   ```bash
   cp -R custom_components/nestquest <config_dir>/custom_components/
   ```
3. Restart Home Assistant.

## Configuration

After installation and restart:
1. Navigate to **Settings** > **Devices & Services** in Home Assistant.
2. Click **Add Integration** and search for **NestQuest**.
3. Follow the on-screen configuration flow.

## Events

NestQuest fires Home Assistant bus events so automations can react to a
child's progress. Each payload carries `child_id`, `child_name`,
`instance_id`, `quest_title`, the instance's `window`, `due_date`,
`due_time`, and `occurred_at` (a strict UTC ISO-8601 timestamp).

| Event | Fires when | Extra payload fields |
|---|---|---|
| `nestquest_quest_completed` | a quest is completed (an actual completion, never a re-complete no-op) | `was_on_time` (bool) |
| `nestquest_quest_uncompleted` | an admin reverses a completion | — |
| `nestquest_child_day_complete` | a completion clears the child's whole day (quests were owed and none remain; a zero-quest day never fires it) | `quests_due`, `quests_completed` |
| `nestquest_quest_missed` | the nightly sweep marks a still-open past-due quest missed (integrated in a later release) | — |

Example automation trigger:

```yaml
triggers:
  - trigger: event
    event_type: nestquest_child_day_complete
conditions:
  - condition: template
    value_template: "{{ trigger.payload.child_name == 'Declan' }}"
actions:
  - action: notify.mobile_app_declans_phone
    data:
      message: "Every quest cleared — legendary!"
```

## Developer Setup and Testing

This project uses [`uv`](https://github.com/astral-sh/uv) for fast Python package and dependency management.

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) installed on your machine

### Setup Environment

To set up the development environment and install dependencies:

```bash
uv sync
```

### Running Tests

Run the test suite with `pytest`:

```bash
uv run pytest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
