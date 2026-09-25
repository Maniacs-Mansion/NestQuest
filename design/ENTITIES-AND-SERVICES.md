# Screens → HA entities, services and events

Planned surface from CTXD CONTEXT.MD, adjusted for the design decisions in
`DESIGN-HANDOFF.md`. Names use the `quest_*` model.

## 1. Entities the cards read

| Entity | Type | Used by |
|---|---|---|
| `sensor.nestquest_<child>_quests_due_today` | int | 1a plate progress, 1b counts, 1d stats |
| `sensor.nestquest_<child>_quests_completed_today` | int | 1a, 1b, 1c, 1d, 1h |
| `sensor.nestquest_<child>_quests_remaining_today` | int | 1b remaining block, 1d |
| `sensor.nestquest_<child>_completion_pct_today` | float | progress bars |
| `sensor.nestquest_<child>_next_quest` | str + attrs | optional panel hint |
| `binary_sensor.nestquest_<child>_all_done` | bool | 1c trigger, 1d "all done" |
| `binary_sensor.nestquest_<child>_present_today` | bool | 1a away plate, 1d away row |
| `sensor.nestquest_household_quests_due_today` | int | 1b party line, 1c party stat |
| `sensor.nestquest_household_quests_completed_today` | int | same |
| `sensor.nestquest_cycle_day` | int | 1d sub-line, 1f header |
| *configured* `weather.<entity>` | HA core | panel dock |

`present_today` is the child's **combined** presence across all of their presence patterns
(a child has zero or more, each `home` or `away`) and overrides, first match wins: an
override covering the date; else absent if any `away` pattern covers it; else present if
any `home` pattern covers it; else absent when the child has at least one `home` pattern;
else present. `cycle_day` is the 1-based day in the first patterned child's lowest-id
pattern, from that pattern's anchor date (never ISO week numbers or parity); `0` when no
child has a pattern.

Per-instance data is too granular for entity state. The cards read the day's instance list
from an attribute payload on the per-child sensor (or a websocket command —
implementer's call), shaped:

```json
{
  "instances": [
    { "id": 4821, "definition_id": 12, "child_id": 3, "title": "Fill bird feeder",
      "icon": "bird", "window": "afternoon", "due_time": "17:00",
      "state": "open", "overdue": true, "completed_at": null, "on_time": null }
  ]
}
```

`state` ∈ `open` | `completed`. Missed instances are **omitted** from panel payloads
(decision 5) and included in admin payloads.

## 2. Services the cards call

| Service | Admin only | Called from |
|---|---|---|
| `nestquest.complete_quest` | no (panel allowed) | 1j confirm |
| `nestquest.uncomplete_quest` | **yes** | 1d `Undo` |
| `nestquest.create_quest_definition` | **yes** | 1e `New` |
| `nestquest.update_quest_definition` | **yes** | 1e sheet `Save changes` |
| `nestquest.set_quest_definition_active` | **yes** | 1e row action |
| `nestquest.create_presence_override` | **yes** | 1i `Save override` |
| `nestquest.delete_presence_override` | **yes** | 1f override row `trash-2` |
| `nestquest.export_history_csv` | **yes** | 1g `CSV` |
| `nestquest.manage_child` | **yes** | settings |

Presence patterns have no HA service: the admin surface is the PWA (ARCHITECTURE §10),
which manages a child's patterns through the admin API —
`GET`/`POST /api/v1/admin/children/{child_id}/presence-patterns` to list and add, and
`PATCH`/`DELETE /api/v1/admin/presence-patterns/{pattern_id}` to edit and delete one
pattern (1f patterns card and pattern editor).

`complete_quest` payload from the panel:

```yaml
service: nestquest.complete_quest
data:
  instance_id: 4821
  actor: panel            # kiosk user context
  actor_child_id: 3       # the tapped profile (decision 9)
```

Every service resolves `call.context.user_id` against the admin allowlist and **fails
closed** with no user context (D-003). The panel's kiosk user is never allowlisted, so
`uncomplete_quest` is unreachable from the wall even though the card never renders the
control.

## 3. Events the cards listen for

| Event | Effect |
|---|---|
| `nestquest_quest_completed` | stamp the seal, re-sort the column, refresh counts |
| `nestquest_quest_uncompleted` | un-seal, restore the card (admin action, panel must reflect it) |
| `nestquest_quest_missed` | remove the instance from the panel; add a history row |
| `nestquest_child_day_complete` | show screen 1c |

All four come off the `DataUpdateCoordinator`; cards should also refresh on
`state_changed` for their sensors so they recover if an event is dropped.

## 4. Card configuration

```yaml
# kids' panel, view 1
type: custom:nestquest-party-board-card
weather_entity: weather.home          # optional; dock falls back to date/time
quest_log_path: /nestquest/log        # view the crest tap navigates to
child_order: [declan, jordyn, chloe]

# kids' panel, view 2
type: custom:nestquest-quest-log-card
board_path: /nestquest/board
weather_entity: weather.home          # optional; dock falls back to date/time
idle_return_seconds: 40               # must be shorter than TouchHub Auto-Return
confirm_timeout_seconds: 15
complete_screen_seconds: 12

# parent phone
type: custom:nestquest-admin-card
density: compact                      # compact | roomy
default_tab: today
```

The quest log reads the selected child from the view's URL/`hass` path parameter so the
board → log hop is a plain Lovelace navigation (decision 6).

## 5. Data-shape consequences of the design

1. Instance key is `(definition_id, child_id, due_date, window)` — the schema's
   `task_instances` unique index must widen.
2. `quest_definitions` needs an **assignees** join table, replacing the single
   `child_id` column.
3. `quest_definitions` needs a **windows** set (morning/afternoon/evening) plus an
   optional due time per window.
4. The materialiser emits one instance per (assignee × window × firing date), still
   idempotent on the widened key, still only when the child is present.
5. `completion_events` gains `actor_child_id` so a panel completion records which
   profile was tapped, while `actor` stays `panel`.
