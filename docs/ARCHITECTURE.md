# NestQuest Architecture

Status: approved direction (2026-09-21). This document supersedes the
single-process design implied by Features 01–14, in which the Home Assistant
integration owned the database and the parent admin surface was planned as a
Lovelace card inside Home Assistant.

## 1. Why this changed

The original design put everything inside the Home Assistant integration: the
SQLite database, the business logic, the kid panel cards, and (planned) the
parent admin card. Three problems surfaced:

1. **The panel needed hand configuration.** Standing up the kid panel required
   hand-writing card YAML (`child_order`, `quest_log_path`, `board_path`) and
   hand-creating a Lovelace dashboard. A fresh install rendered nothing.
2. **The admin surface fought Home Assistant.** The admin design
   (`design/ADMIN-SPEC.md`) is drawn at 390×844 — it is a phone app. Trapping it
   inside a Lovelace card meant fighting HA's UI constraints for a mobile-first
   experience.
3. **Data was locked to one process.** A standalone admin web app cannot reach a
   SQLite file inside Home Assistant's config directory.

The re-imagined design keeps the panel in Home Assistant (TouchHub loads an HA
dashboard), moves data ownership to a standalone API service, and promotes the
admin surface to a standalone mobile-first PWA.

## 2. Target architecture

```
 DAKboard TouchHub
       │  (loads an HA dashboard URL)
       ▼
 HA box                                        API box
 ┌───────────────────────────────┐            ┌───────────────────────────────────┐
 │ Lovelace panel dashboard      │            │ reverse proxy (TLS)               │
 │  ├ nestquest-party-board-card │  service   │  ├ /api/v1/panel/*   LAN-only     │
 │  └ nestquest-quest-log-card   │  token     │  └ /api/v1/admin/*   public       │
 │                               │ ─────────▶ │ FastAPI (imports core/)           │
 │ NestQuest integration         │            │  └ SQLite (owned here)            │
 │  (thin client, no database)   │ ◀───────── │ Authentik (OIDC)                  │
 │  sensors + HA bus events      │  SSE       └───────────────────────────────────┘
 └───────────────────────────────┘                          ▲
                                            PWA ───────────┘
                                  https://nestquest.cubecraftlabs.com
```

One owner of the data (the API). Two clients (the HA integration, the PWA).

## 3. Data ownership

**The API service is the only writer.** The HA integration never opens the
database; it reads a snapshot and posts completions. This removes the
two-writer problem entirely.

- **Storage:** SQLite on the API box. Single household, trivial concurrency,
  and the existing schema, migrations, and DAO tests are already SQLite. Postgres
  buys nothing at this scale.
- **Schema:** unchanged. The cutover from the current HA-hosted database is a
  file copy — same schema, same migration version.
- **Backups:** continuous replication (e.g. Litestream) plus a proven restore.
  A configured-but-untested backup is not a backup.

## 4. Authentication: two planes

The kid panel and the admin PWA have opposite trust levels, so they use
separate credentials and separate network exposure.

### Panel plane (machine)

- **Credential:** a static service token.
- **Exposure:** `/api/v1/panel/*` is reachable **only from the LAN**.
- **Grants:** read the snapshot, and the single open write — complete a quest as
  `actor: panel` with the tapped `actor_child_id`.
- **Refused:** admin routes reject the service token outright, not merely as a
  non-admin. The internet cannot reach these routes at all.

This preserves the original fail-closed boundary: the kiosk can complete a
quest and nothing else.

### Admin plane (human)

- **Credential:** an Authentik OIDC JWT (authorization code + PKCE).
- **Exposure:** `/api/v1/admin/*` is internet-facing behind Authentik.
- **Grants:** everything a parent can do — definitions, assignment, presence,
  children, un-complete, history, export, settings, regenerate.
- **Gate:** the API validates the JWT (issuer, audience, JWKS signature, expiry)
  and requires membership in the `nestquest-admins` group. The Authentik group
  is the single source of truth for "who is a parent", replacing the
  integration-side admin allowlist.

## 5. Components

### `core/` — domain library

The extracted domain layer: schema, migrations, database access, DAOs, the pure
recurrence and presence engines, materialization, completion, event payload
construction, and the children/definitions/allowlist business layers. **No
Home Assistant imports.** Consumed by both the API and (during transition) the
integration. This is where the ~1500 existing tests live after extraction.

### `api/` — NestQuest API

A FastAPI service importing `core/`. Owns the database. Serves the panel and
admin planes, validates Authentik tokens, and publishes a transition event
stream (SSE) that the integration consumes. No business logic in route handlers.

### `custom_components/nestquest/` — HA integration (client)

A thin client. Polls the snapshot and builds the existing sensors; subscribes to
the SSE stream and re-fires the four HA bus events; proxies the panel completion.
Holds a last-good snapshot cache so a brief API outage does not blank the panel.
Owns no database and no business logic.

### `panel/` — Lovelace cards and dashboard strategy

The two kid-facing Lit cards plus a dashboard strategy that generates the panel
views at render time. Cards auto-discover children, so no `child_order` is
required; the strategy computes navigation paths, so `quest_log_path` and
`board_path` are not required.

### `admin/` — Admin PWA

A React progressive web app implementing `design/ADMIN-SPEC.md`, authenticated
via Authentik OIDC, installable on a phone. The only admin surface.

## 6. Zero-configuration panel

A fresh install should show the panel with no YAML:

1. **Auto-discovery.** The party-board card reads an ordered child list from a
   household entity attribute instead of a configured `child_order`.
2. **Dashboard strategy.** A Lovelace strategy generates a party-board view and
   one quest-log view per child, wiring navigation between them, so paths are
   computed rather than configured. Explicit configuration still wins if a user
   supplies it.
3. **Auto-registration.** The integration registers the dashboard on first
   setup, so there is no manual dashboard step.

## 7. Home Assistant surface preserved

The re-imagining must not break what already works:

- **Sensors:** the per-child and household sensor entity_ids and the per-child
  instance attribute payload shape are unchanged. The panel cards and the four
  blueprints depend on them.
- **Events:** the four HA bus events (`nestquest_quest_completed`,
  `nestquest_quest_uncompleted`, `nestquest_quest_missed`,
  `nestquest_child_day_complete`) keep firing with their documented payloads.
  They are now driven by the API's transition stream rather than by local
  service handlers.
- **Blueprints:** the morning summary, afternoon reminder, end-of-day report, and
  day-complete celebration continue to work with no change.

## 8. Events without an HA token on the API box

The API publishes transitions on an SSE stream; the integration subscribes and
re-fires the HA bus events locally. This deliberately avoids storing a Home
Assistant long-lived token on the API box, which would grant full HA access.

## 9. Migration phases

Mapped to the Maestro features:

| Phase | Feature | Outcome |
|---|---|---|
| 1 | 15 — Domain Core Extraction | `core/` runs with no HA imports; one implementation of the rules |
| 2 | 16 — NestQuest API Service | Panel and admin planes served with two-plane auth |
| 3 | 17 — API Deployment and Identity | TLS, Authentik, backups, network separation |
| 4 | 18 — HA Integration as API Client | Integration becomes a client; entity/event surface preserved |
| 5 | 19 — Admin PWA | Mobile-first React PWA replaces the admin card |
| 6 | 20 — Zero-Config Panel Dashboard | Panel installs itself; navigation and animations match the mockups |

Cutover: copy the existing SQLite file to the API box (same schema).

## 10. Locked decisions

- **API on its own box** — separate from Home Assistant.
- **Authentik** (`https://auth.cubecraftlabs.com`) for admin identity; a
  `nestquest-admins` group is the admin source of truth.
- **Single household** — no tenant column, no multi-household auth.
- **React** for the admin PWA.
- **Drop the HA admin services** — the PWA is the only admin surface. The panel
  completion path stays.
- **SQLite on the API box** initially; Postgres only if multi-household ever
  becomes real.

## 11. Preserved vs. changed

**Preserved:** the tested Python domain layer, the panel card designs and
tokens, the sensor and event contract, the completion model, the append-only
event log, the panel's fail-closed "complete only" boundary.

**Changed:** data ownership moves to the API; the integration becomes a client;
the admin card becomes a PWA; panel cards become config-free with a
strategy-generated dashboard.

**New:** the API service, Authentik-gated admin auth, the PWA, and a
last-good-snapshot cache in the integration.

**Cost:** two new deployables (the API and the PWA) and one new box. Accepted
knowingly in exchange for a self-installing panel, an admin surface that is not
fighting HA's UI, and a data layer with real auth in front of it.
