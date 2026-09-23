# NestQuest - House Chaos Coordination

Home Assistant custom integration for managing chores, custody schedules, and house coordination.

## Overview

NestQuest helps households coordinate daily life, chore tracking, custody schedules, and shared tasks directly within Home Assistant. Version 0.2.0 ships the integration foundation (a configuration scaffold providing the package and manifest, shared constants, a single-instance config flow, setup/unload lifecycle handling with an options-reload listener, an options flow for horizon days / day rollover time / panel idle timeout, and HACS metadata) plus its persistence layer: an integration-owned SQLite database (`nestquest.db`) with WAL mode and foreign keys, a versioned migration runner stamping schema version 1 across eight tables (children, admin_users, schedule_rules, task_definitions, presence_schedules, presence_overrides, task_instances, completion_events), typed DAO layers so no other feature writes raw SQL, an append-only completion-event log, and startup handling that creates a missing database, opens a valid one, and refuses — without touching a single byte — to start on a corrupt one. Sensors, calendar events, and service calls are forthcoming in later releases and are not yet part of the integration.

## Installation

### HACS Installation (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Select the three-dots menu in the top right and click **Custom repositories**.
4. Enter the repository URL: `https://github.com/Maniacs-Mansion/NestQuest`
5. Select category **Integration** and click **Add**.
6. Search for **NestQuest** and click **Download**.
7. Restart Home Assistant.

> **Note:** Development happens in the private Gitea repository
> (`https://code.cubecraftlabs.com/Maniacs_Mansion/NestQuest`). The GitHub
> repository is a private mirror maintained for HACS distribution.

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
    value_template: "{{ trigger.event.data.child_name == 'Declan' }}"
actions:
  - action: notify.mobile_app_declans_phone
    data:
      message: "Every quest cleared — legendary!"
```

## Automation Blueprints

NestQuest ships four automation blueprints in
`custom_components/nestquest/blueprints/automation/`. Import them in
Home Assistant under **Settings → Automations & Scenes → Blueprints**
(or place the files in your `config/blueprints/automation/` folder),
then create one automation per blueprint, filling the inputs with your
household's choices.

### Wiring to the integration's notification settings

The integration's options flow records your notification choices —
notify target, morning/afternoon/end-of-day times, and a toggle per
automation. The blueprints take their own inputs at import time;
fill them from the same values you stored in the options flow (the
integration does not push its settings into imported automations):

| Blueprint input | Options-flow counterpart |
|---|---|
| `morning_time` (default 08:00) | `morning_summary_time` |
| `afternoon_time` (default 15:00) | `afternoon_reminder_time` |
| `report_time` (default 20:00) | `end_of_day_report_time` |
| `send_summary` / `send_reminder` / `send_report` / `celebrate` | the four `*_enabled` toggles |
| `notify_target` | `notify_target` (your notify service, e.g. `notify.mobile_app_your_phone`) |

The end-of-day report deliberately runs BEFORE the midnight missed
sweep and reads the same day's data — do not schedule it at the
day-rollover time.

### The four blueprints

1. **Morning summary** (`morning_summary.yaml`) — at the configured
   time, lists every child whose `binary_sensor.nestquest_<child>_present_today`
   is on and what they owe from `sensor.nestquest_<child>_quests_remaining_today`.
   Children not present today are omitted entirely.

2. **Afternoon reminder** (`afternoon_reminder.yaml`) — at the
   configured time, notifies only about present children who still
   have open quests. Sends nothing at all when every present child is
   clear.

3. **End-of-day report** (`end_of_day_report.yaml`) — one message per
   evening: each present child's completion count and the quests they
   still owe (the ones the midnight sweep will mark
   `nestquest_quest_missed`). Absent children are omitted. Sends
   nothing on an all-clear day unless `send_even_when_clear` is on.

4. **Day-complete celebration** (`day_complete_celebration.yaml`) —
   triggers on the `nestquest_child_day_complete` event (which only
   fires when quests were owed and all are complete, so a zero-quest
   day never celebrates). Create one `input_text` helper
   (`nestquest_last_celebrated`) for the dedupe: the automation
   records each celebrated child as `<child_id>:<today>` and
   celebrates each child at most once per day — a re-cleared day does
   not re-fire, but a second child clearing the same day still
   celebrates.

### Example package

```yaml
# One automation per blueprint — Settings → Automations & Scenes →
# Create → Blueprint, then pick each NestQuest blueprint.
#
# morning_summary:   morning_time 08:00, notify_target notify.mobile_app_your_phone
# afternoon_reminder: afternoon_time 15:00, same notify target
# end_of_day_report:  report_time 20:00, send_even_when_clear false, same target
# day_complete_celebration: input_text.nestquest_last_celebrated,
#                            celebration_message "Legendary! {{ trigger.event.data.child_name }} cleared every quest today!"
#
# Every blueprint has its own send/celebrate toggle input; turn an
# automation off entirely from HA's automation menu.
```

### Events the automations rely on

| Event | Payload |
|---|---|
| `nestquest_quest_completed` | child_id, child_name, instance_id, quest_title, window, due_date, due_time, occurred_at (UTC ISO-8601), was_on_time |
| `nestquest_quest_uncompleted` | child_id, child_name, instance_id, quest_title, window, due_date, due_time, occurred_at |
| `nestquest_child_day_complete` | child_id, child_name, quests_due, quests_completed, occurred_at |
| `nestquest_quest_missed` | child_id, child_name, instance_id, quest_title, window, due_date, due_time, occurred_at (fired by the nightly sweep) |

Sensors the automations read: `sensor.nestquest_<child>_quests_due_today`
(attributes: `child_id`, `child_name`, `present`, `instances`,
`admin_instances`), `..._quests_remaining_today`,
`..._quests_completed_today`, and
`binary_sensor.nestquest_<child>_present_today`.

## TouchHub setup

Run these steps in order to display the NestQuest panel on a TouchHub
wall device. The panel is an HA Lovelace dashboard, so the kiosk browser
is simply a Home Assistant client. The path below is zero-config: the
integration registers its panel dashboard itself on setup, so no YAML
and no hand-built views are involved.

1. **Install the integration and add the config entry.** Install
   NestQuest via HACS or manually (see Installation above) and restart
   Home Assistant. Then, in *Settings → Devices & Services*, click
   **Add Integration**, search for **NestQuest**, and submit the flow —
   it has no fields; it just creates the single config entry. Then open
   the entry, click **Configure**, and fill the panel-plane API
   connection in the options flow:

   - **NestQuest API base URL** — the full `http://host:port` URL of
     your NestQuest API service (default `http://127.0.0.1:8000`).
   - **Panel service token** — the token the panel presents to the API
     service as its Bearer credential. It may stay empty until you have
     one; a pasted token must be unpadded.

   The form's remaining fields (panel idle timeout, coordinator update
   interval, last-good snapshot staleness) have defaults that serve the
   panel and need no change here.

2. **The panel dashboard appears automatically.** On setup the
   integration registers one storage-mode Lovelace dashboard: a sidebar
   entry titled **NestQuest** at the URL path `/nestquest`, whose stored
   config is nothing but the **`custom:nestquest-party` strategy**
   (`strategy: { type: custom:nestquest-party }`). The strategy
   generates the views at render time from the household roster:

   - **The Party** — the party-board view at `/nestquest/party`; the
     dashboard root `/nestquest` shows it as the first view.
   - one quest-log view per child at `/nestquest/<child-slug>`
     ("Ada's Quest Log", …), in roster order.

   Nothing is hand-configured: no YAML, no manual views, no
   `child_order`, no `quest_log_path`/`board_path` — the board and the
   quest logs compute their navigation paths from the dashboard's own
   URL — and every generated view is already in **Panel** layout (see
   the two constraints below). If the Lovelace surfaces are unavailable
   (for example when Lovelace runs in YAML mode), setup logs a warning
   and skips the registration; create the dashboard manually with the
   same strategy as described in the manual alternative below.

3. **Create a dedicated kiosk user.** In *Settings → People → Users*, add
   a new user for the wall device. Make it **non-admin**, and ensure it is
   not in the NestQuest admin allowlist. The allowlist blocks the NestQuest
   **admin** operations — `uncomplete_quest`, `create_quest_definition`,
   `update_quest_definition`, `set_quest_definition_active`,
   `set_presence_pattern`, `create_presence_override`,
   `delete_presence_override`, `export_history_csv`, and `manage_child`
   (plus `regenerate` flows) — it does not make the account view-only. The
   kiosk user *can* call `nestquest.complete_quest`, the one open NestQuest
   service, to complete quests from the panel, and as a non-admin Home
   Assistant user it may also reach other permitted Home Assistant entities
   and services.

4. **Open the dashboard and point TouchHub at it.** Open
   `http://<home-assistant>/nestquest` in a browser first and check the
   party board renders with your children's crests. Then, in the
   TouchHub launcher, add the **Home Assistant Lovelace** app to the
   dock and paste the dashboard URL from step 2 — the dashboard root,
   `/nestquest` (TouchHub loads that URL directly as the kiosk landing
   page). Set TouchHub **Auto-Return** to a value GREATER than the
   quest log's `idle_return_seconds` (default 40s) — recommend **60s or
   higher**. If Auto-Return is at or below 40s, TouchHub returns to its
   launcher before the quest log's idle return can navigate back to the
   party board.

5. **Log the kiosk session in.** Sign in on the device as the dedicated
   kiosk user from step 3, and leave that session logged in.

TouchHub loads the dashboard URL directly. The NestQuest cards are normal
Lovelace cards, not an iframe, so no Home Assistant framing setting is
needed.

### The two constraints

- **Panel layout.** Every view must be in **Panel** (single-card)
  layout: Home Assistant's default Masonry layout constrains the
  1080px-tall NestQuest card to a narrow column, while Panel renders the
  card full-screen at 1920×1080. The zero-config path already satisfies
  the requirement — the strategy generates every view as
  `type: panel` — while the manual alternative below requires setting
  the layout by hand on each view (Edit Dashboard → pencil on the view
  → View type: Panel).

- **TouchHub Auto-Return.** TouchHub's **Auto-Return** must be greater
  than the quest log's `idle_return_seconds` (default 40s) — recommend
  **60s or higher** — so the launcher does not reclaim the wall device
  before the quest log's own idle return navigates back to the party
  board.

### Manual alternative: build the dashboard by hand

If you prefer not to use the zero-config dashboard above — or its
registration was skipped — configure a Lovelace dashboard whose **URL
slug is `nestquest`** (Settings → Dashboards → Edit → URL slug)
yourself. Two options, in decreasing order of convenience:

- **Use the strategy.** Give the dashboard

  ```yaml
  strategy:
    type: custom:nestquest-party
  ```

  and no views of your own — the strategy generates the party-board and
  quest-log views (each already in Panel layout) from the household
  roster at render time. Optional `url_path` and `weather_entity` keys
  may sit beside `strategy:`.

- **Build the two views by hand.** A functional panel needs **two**
  views in that dashboard, each with its own card config from
  `design/ENTITIES-AND-SERVICES.md` §4. Give the views these exact URL
  paths (the path segment after the dashboard slug):

  - **View 1 path `board`** (URL `/nestquest/board`) — party board
    (`type: custom:nestquest-party-board-card`): the household quest
    board. Set `weather_entity` (optional; the dock falls back to
    date/time), `quest_log_path: /nestquest/log` (the view the crest tap
    navigates to), and `child_order: [slug1, slug2, slug3]` listing each
    child's slug in display order.

  - **View 2 path `log`** (URL `/nestquest/log`) — quest log
    (`type: custom:nestquest-quest-log-card`): the per-child quest screen
    the party board hops to. Set `board_path: /nestquest/board` (the
    party-board view to return to), `weather_entity`,
    `idle_return_seconds` (must be shorter than TouchHub Auto-Return —
    see the two constraints above), `confirm_timeout_seconds`, and
    `complete_screen_seconds`. The quest log reads the selected child's
    slug from the view's URL path, so the board → log hop is a plain
    Lovelace navigation.

  The dashboard contains only the NestQuest panel card for each view —
  no other cards, no admin controls. Each view's layout MUST be set to
  **Panel** — see the two constraints above for why; the strategy
  generates it for you, hand-built views do not get it for free.

  The `quest_log_path` and `board_path` values must match the dashboard
  slug and view paths above: `/<slug>/<view>`. If you chose `nestquest`
  as the dashboard slug with view paths `board` and `log`, the card
  configs are already correct. If you pick different names, substitute
  your actual paths in **both** card configs — e.g. a dashboard slug
  `chores` with view paths `main` and `history` needs
  `quest_log_path: /chores/history` and `board_path: /chores/main`.
  Navigation between the two views fails (the crest tap or back button
  lands on a 404) if the card config paths do not match the dashboard
  slug and view paths exactly.

  See `design/ENTITIES-AND-SERVICES.md` §4 for the full card YAML.

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

### Frontend cards

The Lovelace cards live in `frontend/` (TypeScript + Lit) and build to a
single bundle at `custom_components/nestquest/www/nestquest-cards.js`. The
integration registers that bundle as a Lovelace resource automatically on
setup — do not add it by hand. Card YAML is documented in
`design/ENTITIES-AND-SERVICES.md` §4.

```bash
cd frontend
npm install
npm run build
```

### Kids panel layout

The Lovelace panel cards are designed for the wall display's confirmed
resolution, 1920×1080 landscape, with no page scroll. TouchHub's bottom
dock overlays the NestQuest weather dock strip until it auto-hides, so
no tappable NestQuest control sits in that strip (the dock carries
`pointer-events: none`). Keep it that way when editing the cards.

### Running Tests

Run the test suite with `pytest`:

```bash
uv run pytest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
