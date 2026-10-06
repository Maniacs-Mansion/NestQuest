# NestQuest Release Notes

## Version 0.10.4 — 2026-10-06

### Scope

Patch release carrying the integration brand icons onto `main` (PR #304, task
ac84fa96).

### Behaviour

- `custom_components/nestquest/brand/` now ships the transparent NestQuest logo
  (`icon.png`/`icon@2x.png`/`logo.png`/`logo@2x.png`), so Home Assistant 2026.3+
  shows it on the integrations page and tile after a HACS update.
- `README.md` embeds the logo at the top (shown on the HACS repository page).

### Requirements

- Home Assistant floor 2024.6.0 (unchanged). The brand-image UI itself requires
  Home Assistant 2026.3+; older versions show the generic icon.

### Breaking changes

- None. Schema unchanged at version 9; no migration, no database backup
  required.

### Rollback

- No schema change: rolling back to 0.10.3 requires no database restore.

## Version 0.10.3 — 2026-10-06

### Scope

Patch release carrying the admin PWA desktop-icon update onto `main` (PR #301,
task 55e1e687).

### Behaviour

- The admin PWA's installable icons (192, 512, and 512 maskable) are now
  generated from `design/logos/NestQuest_Logo.png` instead of placeholder
  graphics, so a home-screen install of the admin app shows the NestQuest logo.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None. Schema unchanged at version 9; no migration, no database backup
  required.

### Rollback

- No schema change: rolling back to 0.10.2 requires no database restore.

## Version 0.10.2 — 2026-10-06

### Scope

Patch release carrying the panel SSE idle-timeout fix onto `main` (PR #298, task
6c4b0fa4).

### Behaviour

- The panel event-stream request is no longer subject to aiohttp's default
  ~300 s total timeout; it now uses an unbounded total with a bounded connect,
  so a healthy stream stays open instead of reconnecting every ~5 minutes.
  Because the API does not replay transitions onto the Home Assistant event bus,
  this also shrinks the windows in which a transition could be missed.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None. Schema unchanged at version 9; no migration, no database backup
  required.

### Rollback

- No schema change: rolling back to 0.10.1 requires no database restore.

## Version 0.10.1 — 2026-10-06

### Scope

Patch release carrying the panel SSE stream fix onto `main` (PR #295, task
4cbf2e96).

### Behaviour

- The Home Assistant integration now reads the panel event stream from the
  response body (`response.content`), fixing the logged failure
  `'async for' requires an object with __aiter__ method, got HassClientResponse`
  that logged ~935 times and prevented live panel events (completions,
  un-completions, day-complete, missed) from re-firing from the API's SSE
  stream. SSE line-buffering and JSON-frame parsing are unchanged.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None. Schema unchanged at version 9; no migration, no database backup
  required.

### Known limitations

- Intermittent `GET /api/v1/panel/events failed with HTTP 502` during API
  restarts/redeploys is expected (the integration reconnects with backoff).
- The event stream still reconnects periodically because Home Assistant's
  shared aiohttp session applies a default total timeout — tracked as a
  follow-up; it does not affect correctness.

### Rollback

- No schema change: rolling back to 0.10.0 requires no database restore.

## Version 0.10.0 — 2026-09-30

### Scope

Feature release: choose task icons by typing any Font Awesome Free **solid**
icon name, not just the curated subset. The shared icon registry now embeds the
full Font Awesome Free solid set offline (no CDN — the panel may be offline),
the admin icon picker is searchable with free-text entry and validation, and the
kids' panel renders any Free Solid icon. (Feature `6c681b17`; PRs #289–#292.)

### Behaviour

- **Full Free Solid set**: the panel and admin bundles now carry ~1,422 Font
  Awesome Free solid glyphs as inline SVG path data, in addition to the existing
  curated quick-pick lists (Lucide and Font Awesome). `fa:<name>` resolves any
  Free Solid icon; unknown names still render the fallback glyph.
- **Searchable picker**: the admin definition icon picker's Font Awesome tab has
  a search input. Empty shows the curated quick picks; typing filters the full
  set into a bounded (≤40 per page) result grid, with Previous / Show more.
- **Free-text entry**: typing an exact Free Solid name selects and stores
  `fa:<name>`. A partial, misspelled, Pro, or Brands name is rejected with an
  inline message and nothing is saved.
- Stored format is unchanged: `lucide:<name>`, `fa:<name>`, `emoji:<grapheme>`,
  or a legacy bare name.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None to the database: schema unchanged at version 9, no migration and no
  database backup required.
- Font Awesome **Pro** and **Brands/Regular** icons are NOT included — only the
  Free Solid set. A Pro/Brands name is rejected in the picker (and an unknown
  `fa:` name falls back on the panel).

### Known limitations

- **Bundle size**: the embedded icon set increases the committed panel bundle to
  ~1.06 MB raw (~276 kB gzip) and the admin PWA bundle similarly. This is
  expected for the full Free Solid set.
- Alias names (e.g. Font Awesome's `fa:home` alias of `fa:house`) are
  de-duplicated to the canonical name, so `fa:house` resolves but `fa:home`
  falls back.
- The backend still validates only the `fa:<kebab-name>` format; unknown names
  are caught in the picker and render as the fallback on the panel.

### Rollback

- No schema change: rolling back to 0.9.8 requires no database restore.

## Version 0.9.8 — 2026-09-30

### Scope

Owner-directed change: the application's timezone is now **manual-only and
admin-authoritative**. Nothing sets it automatically any more; an admin sets it
from the admin app, and the saved value is the single source of local time for
the whole application. This reverses the automatic Home Assistant zone adoption
shipped in 0.9.6 and the admin app's browser-zone auto-set, and supersedes
decision D-018 with D-019. (PRs #282, #283, #285, #286; feature
`a3cd8e27` "Manual application timezone control".)

### Behaviour

- **No automatic timezone setting.** Removed: the API's adoption of Home
  Assistant's reported zone (the `X-NestQuest-Timezone` request header and the
  `adopt_reported_timezone` path), the integration's reporting of
  `hass.config.time_zone`, the admin app's browser-zone auto-detect and
  automatic save, and the `timezone_configured` marker.
- **The admin sets it manually**, in the admin app's Preferences: a curated IANA
  zone picker plus a free "Other IANA zone" entry, with an explicit choice for
  empty ("API host local time"). Nothing is auto-filled or auto-saved.
- **The saved value is authoritative across the whole application**: the panel
  snapshot's overdue/today derivation, both panel cards' dates and clocks,
  completion timestamps, the missed-sweep scheduler, and the admin reads all use
  it. The API publishes the effective zone (`api/host_zone.effective_timezone`:
  the saved value, else the API host's own zone) on the panel snapshot and the
  admin settings response, so the panel and admin app render in the same zone.
- **The kids' panel now follows the application zone, not the browser.** This
  supersedes the panel-local overdue behaviour from 0.9.7; a quest is overdue
  when the application clock says so, not when the panel device's clock does.
- **An admin save of the timezone or the day-rollover time re-plans the running
  missed-sweep scheduler.**
- The integration tolerates an API snapshot without the timezone field, so the
  integration and the API may be upgraded in either order.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None to the database. The schema is unchanged at version 9: no migration and
  no database backup is required for this release.
- Behavioural reversal: if a timezone had been auto-set by 0.9.6–0.9.7, the
  stored value persists after upgrading (it is simply no longer changed
  automatically), so no action is needed unless a different zone is wanted.
- With no timezone saved, the API host's local zone applies (UTC on the standard
  deployment). Set the timezone in the admin Preferences for correct
  household-local behaviour. A previously auto-set value counts as saved and
  will be kept.

### Known limitations

- If no timezone has been saved, the API host zone applies; on the standard
  UTC-host deployment, overdue and day boundaries will be wrong until an admin
  sets the zone.
- The admin app's timezone picker replaces any zone outside its curated list via
  the "Other IANA zone" entry; the value is validated as an IANA name.

### Rollback

- No schema change: rolling back to 0.9.7 requires no database restore.

## Version 0.9.7 — 2026-09-29

### Scope

Patch release carrying the panel-local overdue correction onto `main` (PR #279,
task fd1093b5 "Tasks are still showing over due when the local time has not
passed").

### Behaviour

- The kids' Quest Log card now decides whether an open quest is OVERDUE from
  the panel's OWN local clock (the wall time where the panel physically is)
  compared with the quest's due time, instead of trusting the API snapshot's
  `overdue` flag. A quest therefore cannot read OVERDUE before its due time has
  passed on the panel, regardless of the API host's timezone, Home Assistant's
  configured `time_zone`, or whether the 0.9.6 timezone changes have been
  deployed. A quest is overdue at the due minute and after (`>=`); a quest with
  no due time is never overdue.
- The API's `overdue` field is unchanged; it still serves the admin plane and
  automations. This is a panel display correction only.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None. The database schema is unchanged at version 9: no migration and no
  database backup is required for this release.

### Known limitations

- The comparison uses only wall-clock time. If the API is unreachable across
  local midnight and the coordinator serves its last-good snapshot, a quest
  from the previous day with a later due time can briefly read as not overdue
  until that time passes again. On the normal path the API rolls the household
  day over and the missed sweep removes the previous day's open quests.
- The Quest Log header clock still formats in Home Assistant's configured
  `time_zone`; if HA is set to a zone other than the household's, that header
  remains wrong. Set Home Assistant's own `time_zone` correctly — the admin/API
  timezone setting does not affect the header clock.

### Rollback

- No schema change: rolling back to 0.9.6 requires no database restore.

## Version 0.9.6 — 2026-09-28

### Scope

Patch release carrying the household time-zone fix onto `main` (PR #275, task
6351b36d "Time zone errors"), plus its release-review correction (PR #277, task
45243478).

### Behaviour

- The Home Assistant integration now reports `hass.config.time_zone` to the API
  in an `X-NestQuest-Timezone` header on every panel request.
- While the API's `timezone` setting has never been explicitly chosen
  (`timezone_configured` false), the API adopts and persists the reported zone
  (under the settings lock), so the panel's overdue/today calculation, the
  admin plane and the missed-sweep scheduler are all household-local even when
  the API host runs UTC. No manual setup is required.
- The missed-sweep scheduler re-plans immediately when the adopted zone changes
  while it is sleeping, and re-reads the stored zone before sweeping, so it no
  longer fires at the old (UTC) rollover.
- An admin-chosen zone — including an explicit choice of empty (API-host local)
  — still wins over the reported zone. A timezone-only admin update is recorded
  as an explicit choice (`timezone_configured` true); an explicitly supplied
  `timezone_configured` value in the same update is honored as given. An invalid
  reported zone is logged and ignored; the panel keeps serving on the stored
  settings.

### Requirements

- Home Assistant floor 2024.6.0 (unchanged).

### Breaking changes

- None. The database schema is unchanged at version 9: no migration and no
  database backup is required for this release.
- Deployment note: this fix needs BOTH the API service and the HA integration
  upgraded. The integration supplies the zone and the API adopts it; upgrading
  only one side leaves the previous behaviour. An install that sets or clears
  its zone on 0.9.6 or later keeps that choice; see Known limitations for a zone
  stored by an older release.

### Known limitations

- A zone stored by a release before 0.9.6 without the explicit-choice marker
  (for example through the previously documented
  `PATCH /api/v1/admin/settings {"timezone": ...}`) is not distinguishable from
  an automatically adopted value, so 0.9.6 adopts Home Assistant's reported zone
  over it once. If a zone different from Home Assistant's is intended, re-save
  it in the admin Preferences, which now records the explicit choice.
- If `timezone` is empty and `timezone_configured` is true (an explicit
  "host local" choice), that choice is respected and the API host's zone (UTC
  on the standard deployment) still applies until an admin selects a zone in
  the admin Preferences.
- A change to Home Assistant's own `time_zone` takes effect after the
  integration reloads or Home Assistant restarts.

### Rollback

- No schema change: rolling back to 0.9.5 requires no database restore. The API
  and the integration may be rolled back independently; rolling back only the
  integration restores the previous stored-setting-only behaviour.

## Version 0.9.5 — 2026-09-27

### Scope

Patch release carrying the kids' panel Return button onto `main`.

- **Return button:** the Quest Log header now shows an explicit Return control —
  a left chevron plus "The Party", 72px high and sized to its label, sitting left
  of the crest — so a child
  can go straight back to the main Party board instead of waiting out the 40 s
  idle return. It calls the same navigation the idle return uses
  (`board_path` + `location-changed`), so there is exactly one navigation path.
  It is hidden when no board path is configured, appears on every header-bearing
  Quest Log screen (normal, away, and "no quests today"), and does not appear on
  the Quest-complete screen, which keeps its 12 s auto-return. The control meets
  the panel's hard rules (72px tap target, 26px label, `:active` feedback only,
  clear of the window columns and the dock), and the 40 s idle return and
  crest-tap navigation are unchanged. (PR #272.)

### Upgrade note

The database schema is unchanged at version **9**; no migration or backup step is
needed. No runtime dependency is added — only the bundled panel card changed.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.9.4 — 2026-09-26

### Scope

Patch release fixing the admin timezone control that shipped in 0.9.3.

- **Clearing the timezone now persists:** in 0.9.3 the Settings screen
  re-detected the browser zone whenever the timezone field was empty, so an admin
  could not leave it empty ("use the API host's local time") — closing and
  reopening the screen set it again. A new persisted, API-only
  `timezone_configured` marker (default `false`) now distinguishes "never set"
  from "admin chose empty": the one-time auto-set runs only when the timezone is
  empty AND the marker is false, and any saved timezone change — including
  clearing it — sets the marker, so an explicit empty choice survives. (PRs #266,
  #268.)
- Nothing else changes: the `timezone` setting, its auto-set from the browser zone
  on a fresh install, the Add/Save flow, and the rest of the Settings screen are
  as in 0.9.3.

### Upgrade note

The database schema is unchanged at version **9**; no migration or backup step is
needed. Settings stored before this release have no `timezone_configured` value
and read it as `false`, so an install whose timezone is empty will auto-set the
browser zone once on the next open — after which the choice persists.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.9.3 — 2026-09-26

### Scope

Patch release carrying the admin timezone control onto `main`.

- **Admins set the system timezone from the PWA:** the Preferences screen gains a
  Timezone field (a text input with a local datalist of common IANA zones;
  `UTC` or `Area/Location`). On a fresh install the value is set AUTOMATICALLY
  from the browser's IANA zone when the setting is empty on first load — no
  geolocation prompt and no network lookup — and an admin can change or clear it
  at any time. Only a changed value is sent, and the API's 422 for an unknown zone
  is shown by the form. (PR #266.)
- This makes the household-local clock (overdue, daily rollover) configurable
  from the UI, replacing the manual
  `PATCH /api/v1/admin/settings {"timezone": ...}` step noted in 0.9.1. The
  setting still defaults to the API host's local time when left empty.

### Upgrade note

The database schema is unchanged at version **9**; no migration or backup step is
needed. No runtime dependency is added.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.9.2 — 2026-09-26

### Scope

Patch release carrying the admin "Delete task" capability onto `main`.

- **Delete a task in the admin PWA:** the definition edit sheet gains an
  admin-only Delete action with hybrid semantics (D-017, owner decision "delete
  if there's no history, retire/deactivate if there is"). If the definition has
  **no completion history**, it is hard-deleted together with its instances,
  assignees, windows and its schedule rule (when unreferenced), all in one
  transaction under the connection lock. If it has **any completion history** (a
  completion or an un-completion), nothing is deleted: it is retired by
  deactivation instead, preserving the definition, rule, assignees, windows and
  all history, with future uncompleted instances cleared as with any
  deactivation. (PR #262.)
- **API:** `DELETE /api/v1/admin/quest-definitions/{id}` lives on the admin plane
  (`require_admin`; a non-admin is refused and an unknown id is 404). The response
  reports `deleted`/`retired` and carries the retired definition (`null` when
  deleted). The kids' panel gains no control, and `QuestDefinitionsDao` now has
  exactly one, history-guarded, delete method.

### Upgrade note

The database schema is unchanged at version **9**; no migration or backup step is
needed beyond the 0.8.0 note. No runtime dependency is added.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.9.1 — 2026-09-26

### Scope

Patch release carrying the owner-reported UI-bug fixes for the kids' panel, plus a
household-timezone correction, onto `main`.

- **Household-local time:** a new `timezone` setting (an IANA name such as
  `America/New_York`; empty keeps the API host's local time) is threaded into the
  API's clock reads, so overdue and the daily rollover use the household's day
  rather than a UTC host's. **Set it once after upgrading** (see the Upgrade
  note); the admin UI has no field for it yet. (PR #254.)
- **Overdue and rollover correctness:** quests are no longer marked overdue
  before their due time, and the missed-sweep scheduler fires at the configured
  rollover across DST transitions — its delay is now a true elapsed-time
  difference, with documented handling of nonexistent/ambiguous local times.
  (PRs #254, #257.)
- **Complete works on the panel:** a TypeScript ES2022 `useDefineForClassFields`
  default emitted native class fields that shadowed Lit's reactive accessors, so
  the confirm dialog never re-rendered and a tap appeared to do nothing; the
  panel now opens the confirm and completes. (PR #254.)
- **Panel polish:** the party-board hint line no longer hides behind the dock
  (#244); the Quest Log header crest renders with its shield classes (#252); the
  party-board wordmark is the new compass-rose monogram plus Cinzel Decorative
  text, replacing the d20 dice (#253); and the quest meta line keeps its `meta`
  class when not late (#255).

### Upgrade note

The database schema is unchanged at version **9**. After upgrading, set the
household timezone once so date, overdue and rollover behaviour match the house
(otherwise it falls back to the API host's local time, which may be UTC):

```
PATCH /api/v1/admin/settings {"timezone": "America/New_York"}
```

No runtime dependency is added.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.9.0 — 2026-09-26

### Scope

Minor release carrying expanded, customisable task icons — Lucide, Font Awesome
Free and emoji — onto `main`.

- **Namespaced icon keys:** a quest definition's `icon` now accepts
  `lucide:<kebab-name>`, `fa:<kebab-name>` and `emoji:<grapheme>`. A legacy bare
  name (e.g. `dog`) is read as `lucide:dog`, so existing rows keep working with
  no stored-data migration. The strict write validator rejects an unknown
  namespace, a malformed name, an over-cap or markup-bearing emoji payload, and
  `javascript:`. (PRs #241, #249.)
- **Shared icon registry:** one canonical set — the curated Lucide set plus a
  curated Font Awesome Free solid subset — generates identical,
  framework-agnostic registry modules for the admin and panel bundles, guarded by
  a drift test. There is no CDN and no runtime fetch, and only the curated Font
  Awesome glyphs are shipped. (PR #242.)
- **Admin PWA picker:** the definition edit sheet offers the Lucide set, the
  Font Awesome subset and an emoji input; a selection stores the namespaced key
  and an existing namespaced or legacy icon pre-fills correctly. The definition
  list renders all three forms with a fallback glyph. Editing a definition whose
  stored icon is a legacy value no longer resubmits the unchanged icon.
  (PRs #243, #250.)
- **Kids' panel:** open quest cards render the definition's icon (Lucide stroked,
  Font Awesome filled, emoji as text) with the existing star fallback; the sealed
  card keeps its star/seal glyph. (PR #245.)
- **Docs and attribution:** ADMIN-SPEC and PANEL-SPEC describe the namespaced
  model; `THIRD-PARTY-NOTICES.md` records Font Awesome Free (icons CC BY 4.0,
  fonts SIL OFL 1.1, code MIT) and Lucide (ISC). (PR #246.)

### Upgrade note

The database schema is unchanged at version **9**; no migration or backup step
is needed beyond the 0.8.0 note. This release adds no runtime dependency — the
icon path data is embedded in the shipped bundles at build time.

### Requirements

Home Assistant 2024.6.0 or newer. Install through HACS from the
`Maniacs-Mansion/NestQuest` GitHub mirror (kept current by the Gitea push
mirror).

## Version 0.8.0 — 2026-09-25

### Scope

Minor release carrying the multi-pattern presence model (schema 9), the
Sunday-first calendar week, and the create-materializes fix, plus the
definition start-date field, onto `main`.

- **Multiple presence patterns per child (schema 9):** a child now has zero or
  more presence patterns instead of at most one. Each pattern has a name, a kind
  (`home` or `away`), its own cycle length (1–4 weeks), its own anchor date and a
  per-week weekday set. Evaluation is first-match-wins — overrides, then away,
  then home, then absent when the child has at least one home pattern, else
  present. Migration 9 copies each existing schedule into a `home` pattern named
  "Home schedule" and drops the old `presence_schedules` table. (PRs #231, #232.)
- **Sunday-first calendar week:** the admin Schedule month grid and the
  Definitions weekday picker now render weeks Sunday-first; the stored/API
  weekday numbering is unchanged (Monday=0..Sunday=6). (PR #230.)
- **Fix — newly created tasks materialize immediately:** creating a quest
  definition now regenerates its future instances over the rolling horizon, so a
  new task reaches the panel without waiting for an unrelated write. (PRs #235,
  #236.)
- **Definition start date:** the definition edit sheet gains a Start date field
  so a task can be scheduled to begin on a future date. (PRs #237, #238.)
- **Docs:** the multi-pattern decision (D-016), the migration-9 rollback step in
  the runbook, and the ADMIN-SPEC Schedule section. (PRs #233, #234.)

### Upgrade note

This release runs schema version **9**. Version 0.7.1 refuses a version-9
database, so take a copy of the SQLite file (or note the Litestream generation)
before the first start on 0.8.0 if you need a rollback path.

### Requirements


## Version 0.7.1 — 2026-09-24

### Scope

Patch release bringing the admin PWA follow-ups and its hosting deployment from
`dev` onto 0.7.0.

- **Feature 24 — Admin PWA Hosting:** the admin PWA's static hosting is now
  reproducible from the repository — `deploy/pwa/Dockerfile` (multi-stage, pinned
  `node`/`nginx` base images by digest, `VITE_AUTHENTIK_CLIENT_ID` /
  `VITE_AUTHENTIK_ISSUER` / `VITE_API_BASE_URL` build args), `deploy/pwa/nginx.conf`
  (SPA fallback plus a source allow-list for the reverse proxy and the host), a
  `pwa` service in `deploy/compose.yaml` published on `:8081`, and a
  `deploy/RUNBOOK.md` section describing the build/serve and the Traefik
  `nestquest-app` router. (PRs #220, #221.)
- **Feature 19 follow-up — Manage children:** the Today header's Settings button
  now opens a Settings screen. Its **Children** section lists the household's
  children and lets a parent add (POST `/api/v1/admin/children`), edit
  (PATCH `.../{id}`), activate/deactivate (PATCH `.../{id}/active`) and reorder
  them (POST `.../reorder`). (PRs #222, #223.)
- **Feature 19 follow-up — Settings preferences:** the same screen has a
  **Preferences** section for the planning horizon, day rollover time, notify
  target, the morning/afternoon/end-of-day notification times and their toggles,
  and celebration, read from `GET /api/v1/admin/settings` and saved with a partial
  `PATCH` of only the changed fields. (PRs #224, #225, #226.)

### Requirements

- Minimum Home Assistant version: **2024.6.0**.
- A running NestQuest API service as in 0.7.0 (the Feature 17 deployment); the
  `admin/` PWA is served from the owner's deployment at
  `https://nestquest.cubecraftlabs.com`, not by HACS.

### Breaking changes

- **None.** The schema is unchanged at version 8 and no migration runs.
  `custom_components/` is unchanged from 0.7.0 apart from the manifest
  release-version metadata — no Home Assistant entity, service, event or
  automation surface changes. This release adds admin PWA screens and deployment
  artifacts only.

### Known Limitations

- **HACS does not ship the admin PWA or the deployment artifacts.** HACS copies
  only `custom_components/nestquest`, so upgrading via HACS changes nothing
  functional over 0.7.0; the PWA screens and hosting are deployed from `admin/`
  and `deploy/` per the runbook.
- Serving the PWA and API still requires the Feature 17 deployment (host, reverse
  proxy, Authentik, backup target) as documented in `deploy/RUNBOOK.md`.
- **Feature 12's TouchHub/DAKOS runbook task remains physically unverified**
  (needs the wall panel).
- The Settings UI does not expose resetting a field to its default with `null`.

### Rollback

Schema is unchanged (8), so no migration is involved in either direction.
`custom_components/` is unchanged from 0.7.0 apart from the release-version
metadata; rolling back the integration is a plain swap, and the PWA/hosting can be
redeployed from the 0.7.0 tree.

**HACS installs:** HACS > Integrations > NestQuest > Redownload > 0.7.0, then
restart Home Assistant.

**Manual installs:** replace `custom_components/nestquest/` with the 0.7.0 tree,
then restart Home Assistant.

**Repository operators:** git-revert the 0.7.1 release merge on `main`.

## Version 0.7.0 — 2026-09-24

### Scope

Seventh release of NestQuest, promoting the re-imagined architecture's admin
surface from `dev` onto 0.6.0: the API deployment and identity layer, the
admin-plane API work, and the standalone admin PWA that uses them.

- **Feature 17 — API Deployment and Identity:** the NestQuest API is packaged as
  a container (`Dockerfile`, `deploy/compose.yaml`, pinned base image and exact
  dependencies) and deployed behind a TLS reverse proxy (the shared Traefik, ACME
  via the Cloudflare DNS-01 challenge); the Authentik application, OIDC provider
  and `nestquest-admins` group are wired and the API validates the provider's
  issuer/audience/JWKS (RS256); the panel plane is restricted to the Home
  Assistant box while the admin plane is internet-facing behind Authentik;
  continuous backup runs as a contained Litestream sidecar over SFTP to a NAS and
  a restore is proven; a deployment runbook (`deploy/RUNBOOK.md`) and the
  host-firewall unit (`deploy/systemd/nestquest-api-firewall.service`) ship.
  (PRs #183, #214, #215, #216, #218.)
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
  token configured in the integration options. The deployable ships in this
  release: `Dockerfile`, `deploy/compose.yaml` (API + a contained Litestream
  backup sidecar), `api/requirements.txt`, the host-firewall unit and
  `deploy/RUNBOOK.md`. Deploying it needs a host, the DNS/TLS path and the
  Authentik/Synology services described in the runbook.
- The admin PWA is built to run at `https://nestquest.cubecraftlabs.com` behind
  Authentik. Serving the built `admin/` static bundle at that hostname is part of
  the deployment described in the runbook.

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

- **The API and its identity/backup layer are deployed by the owner's
  infrastructure, not by this release alone.** The deployment artifacts and
  runbook ship here, but a running service still requires the host, the shared
  reverse proxy, the Authentik application/provider/`nestquest-admins` group, the
  backup target and the panel/admin network separation to be in place as the
  runbook describes.
- **Serving the admin PWA is still outstanding.** `admin/` builds and is
  unit/integration tested and the API it talks to is live, but the built static
  bundle must still be hosted at `https://nestquest.cubecraftlabs.com` behind
  Authentik; until then the PWA is not reachable end-to-end.
- **Feature 12's TouchHub/DAKOS runbook task remains physically unverified**
  (needs the wall panel).
- Moving the household database from Home Assistant to the API box is a manual
  file copy (the schema is unchanged by that move beyond the v8 migration).
- Single household; single API service.

### Rollback

**Schema version advances 7 → 8.** Migration 8 is additive, but a migrated
database **cannot** be read by 0.6.0 or earlier (they refuse a newer schema
version). The database is owned and migrated by the **NestQuest API service**,
not by Home Assistant: it is the file at the API's configured
`NESTQUEST_DB_PATH` on the API host, which need not be anywhere near the Home
Assistant config directory. To return to 0.6.0 you must restore a backup of
that file taken before the upgrade; a plain downgrade is impossible once
migrated.

**API host (database):**

1. Before upgrading, stop the NestQuest API service and back up the database
   file at its configured `NESTQUEST_DB_PATH`, plus its `-wal` and `-shm`
   sidecars (`<NESTQUEST_DB_PATH>-wal`, `<NESTQUEST_DB_PATH>-shm`) if present.
   Only then deploy 0.7.0 and start the API service, which applies migration 8.
2. To roll back: stop the API service, restore the backed-up database and
   sidecars to `NESTQUEST_DB_PATH`, redeploy the API service at 0.6.0, and roll
   back the Home Assistant integration to 0.6.0 (below). Then restart the API
   service and Home Assistant.

**Home Assistant integration — HACS installs** (integration component only;
the database lives with the API, see above):

1. To roll back: HACS > Integrations > NestQuest > Redownload > 0.6.0, then
   restart Home Assistant.

**Home Assistant integration — Manual installs** (integration component only;
the database lives with the API, see above):

1. To roll back: replace `custom_components/nestquest/` with the 0.6.0 tree,
   then restart Home Assistant.

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
