# NestQuest API — deployment and restore runbook

Operator procedure to rebuild the production NestQuest API deployment end
to end from this repository, restore its database from backup, and verify
it. Every value below is the real, non-secret production value. **No
secret appears in this file** — secrets are named and their location is
given, never their content.

| Piece | Where | Real value |
| --- | --- | --- |
| API box (Docker host) | this repository's `deploy/` | `10.60.1.14`, port `8080` (API), `8081` (admin PWA, section 10) |
| Reverse proxy / TLS | shared Traefik on `nukapi-03` | `10.60.1.33` |
| Public hostname | Cloudflare DNS | `nestquest.cubecraftlabs.com` |
| Identity | Authentik | `https://auth.cubecraftlabs.com` |
| Home Assistant box (panel client) | LAN | `10.60.1.80` |
| Local DNS | Pi-hole | `10.60.1.101` |
| Backup target | Synology NAS `CubeCraft-SRVR1`, SFTP | `10.60.1.50:/homes/Joshua/nestquest-backups` |

All `docker compose` commands below are run **on the API box, from the
repository root**. The shorthand `dc` means:

    alias dc='docker compose -f deploy/compose.yaml'

Compose v2.24 or newer is required (`env_file` uses the `path`/`required`
form).

---

## 1. Image build

The image is defined by the root `Dockerfile` and is built from the
**repository root** as the build context: the API (`api/`) loads the
bundled domain core from `custom_components/nestquest/core/` by file
location, so both trees must be in the context. `.dockerignore` keeps
everything else (including `deploy/`, `.env` files and `*.db`) out of the
build.

- Multi-stage on `python:3.12-slim`: the builder installs
  `api/requirements.txt`, the runtime copies only the installed packages
  plus `api/` and `custom_components/nestquest/core/` into `/app`.
- Runs as the non-root system user `nestquest` (uid/gid `999`), which owns
  `/var/lib/nestquest`.
- Command: `uvicorn --factory api.app:create_app --host 0.0.0.0 --port 8080`.

Get the code and build:

    git clone ssh://code.cubecraftlabs.com:2288/Maniacs_Mansion/NestQuest.git
    cd NestQuest
    git checkout <release branch or tag being deployed>
    dc build api          # equivalent: docker build -t nestquest-api:latest .

Confirm the runtime user (the Litestream sidecar and the key ownership in
section 5 depend on uid 999):

    docker run --rm --entrypoint id nestquest-api:latest
    # uid=999(nestquest) gid=999(nestquest) groups=999(nestquest)

## 2. Compose

`deploy/compose.yaml` defines three services and one named volume:

| Service | Image | Role |
| --- | --- | --- |
| `api` | `nestquest-api:latest` (built, section 1) | FastAPI service on `8080`, healthcheck on `/health` |
| `litestream` | `litestream/litestream:0.5.17` | Continuous SFTP backup of the database (section 7); starts only once `api` is healthy |
| `pwa` | `nestquest-pwa:latest` (built from `deploy/pwa`, section 10) | Admin PWA served by nginx on `8081`; independent of the other two |

- **Volume `nestquest-db`** is mounted at `/var/lib/nestquest` in both
  services. The database is `NESTQUEST_DB_PATH=/var/lib/nestquest/nestquest.db`
  (fixed by compose, not a secret). `docker compose down` keeps named
  volumes; **never run `down -v`** on the API box. Docker prefixes the
  volume with the compose project name — with the default project
  (`deploy`, the compose file's directory) it is `deploy_nestquest-db`;
  confirm with `docker volume ls | grep nestquest-db`.
- **Published port**: `${NESTQUEST_BIND_ADDRESS:-127.0.0.1}:8080:8080`.
  The default binds localhost only, so an unconfigured host is never
  exposed. On the API box `deploy/.env` sets
  `NESTQUEST_BIND_ADDRESS=10.60.1.14` so Traefik on nukapi-03 can reach
  `http://10.60.1.14:8080`.
- **Secrets** come from `deploy/.env` (git-ignored, section 5) via
  `env_file`.

Bring the stack up (after section 5's secrets exist):

    dc up -d --build
    dc ps          # api "healthy", litestream "Up"
    curl -s http://10.60.1.14:8080/health      # {"status":"ok"}

## 3. TLS and reverse proxy (Traefik on nukapi-03)

TLS is terminated by the **shared** Traefik instance on `nukapi-03`
(`10.60.1.33`), not by this repository. Its NestQuest routing is the
owner-authored dynamic file-provider config
**`config/dynamic/nestquest-ccl.yml`** in the Traefik deployment on
nukapi-03 — that live file is authoritative; it is not stored in this
repository. What it must contain:

| Router | Rule | Middleware | Service |
| --- | --- | --- | --- |
| `nestquest-panel` (priority 200) | ``Host(`nestquest.cubecraftlabs.com`) && PathPrefix(`/api/v1/panel`)`` | `nestquest-panel-lan`: `ipAllowList`, `sourceRange: ["10.60.1.80/32"]` (HA box only) | `nestquest-api` → `http://10.60.1.14:8080` |
| `nestquest-admin` (priority 100: `/api/v1/admin`, `/health`, `/openapi.json`, `/docs`) | ``Host(`nestquest.cubecraftlabs.com`) && (PathPrefix(`/api/v1/admin`) \|\| Path(`/health`) \|\| Path(`/openapi.json`) \|\| PathPrefix(`/docs`))`` | `nestquest-headers` — no source restriction; the API itself enforces Authentik JWTs (section 4) | `nestquest-api` → `http://10.60.1.14:8080` |
| `nestquest-app` (priority 50: everything else — the admin PWA) | see section 10 | none at Traefik; nginx allow-lists the proxy | `nestquest-pwa` → `http://10.60.1.14:8081` |

All routers use the HTTPS entrypoint `websecure` with `tls.certResolver: myresolver`
(HTTP is redirected to HTTPS by the shared Traefik). Priorities are set
explicitly so the order never depends on rule length: panel (200) above
admin (100), and the PWA's `nestquest-app` router (50) below both. The
admin router is scoped to `/api/v1/admin`, `/health`, `/openapi.json`
and `/docs` — a bare ``Host(...)`` rule at a higher priority would
swallow `/` and every PWA route. Any other `/api/*` path matches no
router (the app router excludes `/api`), so Traefik answers `404`.

Reference shape, to rebuild the file if it is ever lost (entrypoint names
must match the shared Traefik's static config on nukapi-03):

```yaml
http:
  routers:
    nestquest-panel:
      rule: "Host(`nestquest.cubecraftlabs.com`) && PathPrefix(`/api/v1/panel`)"
      priority: 200
      entryPoints: [websecure]
      middlewares: [nestquest-panel-lan]
      service: nestquest-api
      tls:
        certResolver: myresolver
    nestquest-admin:
      rule: "Host(`nestquest.cubecraftlabs.com`) && (PathPrefix(`/api/v1/admin`) || Path(`/health`) || Path(`/openapi.json`) || PathPrefix(`/docs`))"
      priority: 100
      entryPoints: [websecure]
      middlewares: [nestquest-headers]
      service: nestquest-api
      tls:
        certResolver: myresolver
    nestquest-app:
      rule: "Host(`nestquest.cubecraftlabs.com`) && !PathPrefix(`/api`) && !Path(`/health`) && !Path(`/openapi.json`) && !PathPrefix(`/docs`)"
      priority: 50
      entryPoints: [websecure]
      service: nestquest-pwa
      tls:
        certResolver: myresolver
  middlewares:
    nestquest-panel-lan:
      ipAllowList:
        sourceRange: ["10.60.1.80/32"]
    nestquest-headers:
      # headers middleware; copy its definition from the live file
  services:
    nestquest-api:
      loadBalancer:
        servers:
          - url: "http://10.60.1.14:8080"
    nestquest-pwa:
      loadBalancer:
        servers:
          - url: "http://10.60.1.14:8081"
```

**Certificates.** `myresolver` is the shared Traefik's ACME (Let's
Encrypt) resolver using the **Cloudflare DNS-01 challenge**; the
Cloudflare API token is held by the Traefik deployment on
nukapi-03, never in this repository. Because DNS-01 proves control
through a DNS TXT record, issuance and renewal need no inbound HTTP and
work regardless of the Cloudflare proxy setting. Certificates renew
automatically.

**Cloudflare proxy note.** Public traffic for
`nestquest.cubecraftlabs.com` resolves through Cloudflare, so a request
from the internet reaches Traefik from a Cloudflare edge address, never
from `10.60.1.80` — which is exactly why the panel allowlist refuses it
(403). The HA box does not go through Cloudflare at all: the local DNS
override in section 6 sends it straight to Traefik on the LAN, so Traefik
sees its real address. Do **not** add Cloudflare ranges to the panel
allowlist or make the allowlist trust `X-Forwarded-For`; that would let
any internet client through to the panel plane.

## 4. Authentik (admin identity)

Admin-plane requests (`/api/v1/admin/*`) carry an Authentik OIDC access
token (JWT). The API verifies issuer, audience, RS256 signature against
the JWKS, and expiry, then requires the `groups` claim to contain
`nestquest-admins` (`api/auth.py`). Configure in Authentik
(`https://auth.cubecraftlabs.com`, admin interface):

1. **Provider** — *OAuth2/OpenID Provider*:
   - Client type: **Public** (no client secret; the admin PWA is a browser
     SPA).
   - PKCE: the PWA always uses the authorization-code flow with PKCE,
     `code_challenge_method=S256`, and never sends a client secret.
   - Redirect URI (strict): `https://nestquest.cubecraftlabs.com/auth/callback`.
   - Signing key: an **RSA** certificate (the API only accepts `RS256`).
   - Scopes: the default `openid`, `email`, `profile` mappings (the PWA
     requests `openid email profile`; Authentik's default `profile`
     mapping emits the `groups` claim the API checks).
   - Note the generated **Client ID** — it is the audience below and the
     PWA's `VITE_AUTHENTIK_CLIENT_ID`.
2. **Application** — slug **`nestquest`**, bound to the provider above.
   The slug fixes the issuer URL.
3. **Group** — **`nestquest-admins`**. Add each parent's Authentik user.
   Membership is the single source of truth for "who is an admin"; the
   API refuses a signed-in non-member with 403.

API settings (in `deploy/.env`, section 5):

| Variable | Value |
| --- | --- |
| `NESTQUEST_OIDC_ISSUER` | `https://auth.cubecraftlabs.com/application/o/nestquest/` |
| `NESTQUEST_OIDC_AUDIENCE` | the provider's Client ID |
| `NESTQUEST_OIDC_JWKS_URL` | `https://auth.cubecraftlabs.com/application/o/nestquest/jwks/` |

Check them against Authentik's discovery document (the issuer must match
byte for byte, including the trailing slash):

    curl -s https://auth.cubecraftlabs.com/application/o/nestquest/.well-known/openid-configuration \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["issuer"]); print(d["jwks_uri"])'

## 5. Secrets

Nothing below is ever committed; `.gitignore` excludes `.env`,
`**/.env`, `deploy/*key*` and `deploy/litestream_key*`.

**`deploy/.env`** — created on the API box from the committed example:

    cp deploy/.env.example deploy/.env
    chmod 600 deploy/.env
    # edit deploy/.env and fill in:
    #   NESTQUEST_PANEL_TOKEN   = a new random token, e.g.
    #                             python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    #                             (the same value is configured in the HA integration)
    #   NESTQUEST_OIDC_ISSUER   = section 4
    #   NESTQUEST_OIDC_AUDIENCE = section 4 (Authentik Client ID)
    #   NESTQUEST_OIDC_JWKS_URL = section 4
    #   NESTQUEST_BIND_ADDRESS  = 10.60.1.14

The API fails fast at startup if any of the four API
variables is unset or empty (`api/config.py`); `dc logs api` names the
missing one. `NESTQUEST_BIND_ADDRESS` is read by compose only.

**Litestream SFTP key `deploy/litestream_key`** — a dedicated keypair that
lives only on the API box. Create it once, before the first `up`:

    ssh-keygen -t ed25519 -N "" -C nestquest-litestream -f deploy/litestream_key
    sudo chown 999:999 deploy/litestream_key
    chmod 600 deploy/litestream_key

Then append `restrict ` followed by the contents of
`deploy/litestream_key.pub` as one line to
`joshua@10.60.1.50:~/.ssh/authorized_keys` on the NAS. Compose mounts the
private key read-only at `/etc/litestream/sftp_key` in the sidecar, which
runs as uid 999 — hence the ownership. The NAS host key is pinned in the
committed `deploy/litestream.yml` (`host-key`, the NAS's ECDSA key), so no
`known_hosts` is involved.

| Secret | Supplied by | Consumed by |
| --- | --- | --- |
| `NESTQUEST_PANEL_TOKEN` | `deploy/.env` → `env_file` | `api` (panel plane); also set in the HA integration |
| `NESTQUEST_OIDC_*` (not secret, but environment-supplied) | `deploy/.env` → `env_file` | `api` (admin plane) |
| SFTP private key | `deploy/litestream_key` → read-only bind mount | `litestream` |
| Cloudflare DNS API token | Traefik deployment on nukapi-03 | Traefik ACME `myresolver` |

## 6. Network separation and firewall

- **Panel plane** (`/api/v1/panel/*`, static service token): reachable
  only from the HA box. Traefik's `ipAllowList` on the panel router allows
  `10.60.1.80/32` and returns **403** to every other source, before the
  request reaches the API. The API additionally requires the panel token
  (401 without it).
- **Admin plane** (`/api/v1/admin/*`) and `/health`, `/docs`: public
  through Cloudflare and Traefik; admin routes are protected by the API's
  Authentik JWT check (401 without a valid token, 403 without
  `nestquest-admins` or when a panel token is presented).
- **Local DNS override** so the HA box reaches Traefik directly, keeping
  its real source address: in Pi-hole (`10.60.1.101`) local DNS records,
  add `nestquest.cubecraftlabs.com` → `10.60.1.33`. The HA box
  must use Pi-hole as its resolver. Check from the HA box:

      nslookup nestquest.cubecraftlabs.com 10.60.1.101   # Address: 10.60.1.33

- **Direct `:8080` access is firewalled.** The API box publishes `8080`
  on `10.60.1.14`, which alone would let any LAN host bypass Traefik and
  the panel `ipAllowList`. This is enforced on the API box in Docker's
  `DOCKER-USER` chain (which Docker evaluates before its own forwarding
  rules for published ports), in this order:

      -A DOCKER-USER -s 10.60.1.33/32 -p tcp --dport 8080 -j RETURN   # Traefik on nukapi-03
      -A DOCKER-USER -s 10.60.1.14/32 -p tcp --dport 8080 -j RETURN   # the API box itself
      -A DOCKER-USER -p tcp --dport 8080 -j DROP                      # every other source

  The rules are persisted by the systemd oneshot unit
  **`nestquest-api-firewall.service`**, committed as
  `deploy/systemd/nestquest-api-firewall.service` (ordered after
  `docker.service`, it idempotently applies the three rules at every
  boot). Install and enable it on the API box, from the repository
  checkout, **before** exposing the API:

      sudo cp deploy/systemd/nestquest-api-firewall.service /etc/systemd/system/ \
        && sudo systemctl daemon-reload \
        && sudo systemctl enable --now nestquest-api-firewall.service

  The HA box and every other client must use the Traefik hostname,
  never `:8080` directly. Check it:

      sudo systemctl is-enabled nestquest-api-firewall.service   # enabled
      sudo systemctl is-active nestquest-api-firewall.service    # active
      sudo iptables -S DOCKER-USER                               # the three rules above, in that order

      # on nukapi-03 (10.60.1.33) — allowed:
      curl -s -o /dev/null -w '%{http_code}\n' http://10.60.1.14:8080/health   # 200
      # on any other LAN host, e.g. 10.60.1.101 — dropped:
      curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://10.60.1.14:8080/health   # 000, timeout
      # public path still works:
      curl -s -o /dev/null -w '%{http_code}\n' https://nestquest.cubecraftlabs.com/health   # 200

  On a rebuilt API box, install the unit with the commands above before
  exposing the API. The committed file is the authoritative copy; the
  deployed unit must match it:

      diff deploy/systemd/nestquest-api-firewall.service \
        /etc/systemd/system/nestquest-api-firewall.service   # no output

## 7. Backup (Litestream to the Synology NAS)

The `litestream` sidecar (config `deploy/litestream.yml`, mounted at
`/etc/litestream.yml`) replicates `/var/lib/nestquest/nestquest.db` to:

- SFTP `joshua@10.60.1.50`, path `/homes/Joshua/nestquest-backups` (the
  NAS's SFTP view is chrooted to the shared folders; over SSH the same
  directory is `/volume1/homes/Joshua/nestquest-backups`).
- Every committed change is shipped as an LTX file within about a second.
  Litestream 0.5.17 compacts them into coarser levels on its built-in
  schedule (level 1 every 30s, level 2 every 5m, level 3 every 1h).
- **Snapshots**: `snapshot.interval: 24h` (a full snapshot daily);
  **retention**: `snapshot.retention: 168h` — a week of snapshots plus the
  changes between them, i.e. a 7-day point-in-time restore window.

The sidecar runs as uid 999 with a read-only root filesystem,
`no-new-privileges` and all capabilities dropped. It needs the database
volume read-write (it keeps its `_litestream_*` tables and writes the
WAL); its local state lives beside the database in
`/var/lib/nestquest/.nestquest.db-litestream/`.

Check it:

    dc ps litestream                                           # Up
    dc logs --tail 50 litestream                               # no "error" lines
    dc exec litestream litestream status                       # status "ok", local txid advancing
    dc exec litestream litestream ltx /var/lib/nestquest/nestquest.db | tail   # newest LTX files and timestamps

A change made in the app should appear as a new level-0 LTX file within
seconds. On the NAS, the files are under
`/volume1/homes/Joshua/nestquest-backups/ltx/`.

## 8. Restore

Restores the database from the SFTP replica into the `nestquest-db`
volume at `NESTQUEST_DB_PATH` (`/var/lib/nestquest/nestquest.db`). The
same procedure serves both a damaged database on the existing box and a
rebuilt box. The restore runs in one-off `litestream` containers so it
has the same user (999), volume, config and SFTP key as the sidecar.

**0. Fresh box only.** Complete sections 1 and 5, then start **only the
API** once so the volume exists and is owned by uid 999:

    dc up -d api

Do not start `litestream` yet — it would begin replicating the new,
empty database the API just created. The swap in step 4 moves that empty
file aside, and step 5 creates and starts the sidecar with
`dc up -d litestream` once the API is healthy.

**1. Stop writers** — both the API and the sidecar (Litestream must not
replicate while the file is being replaced):

    dc stop api litestream

**2. Restore beside the live database** (never over it), with a full
integrity check:

    dc run --rm --no-deps litestream restore \
      -config /etc/litestream.yml \
      -integrity-check full \
      -o /var/lib/nestquest/nestquest.db.restored \
      /var/lib/nestquest/nestquest.db

Expect `post-restore integrity check passed` and exit code 0. For a
point in time within the retention window, add
`-timestamp 2026-09-24T12:00:00Z` (UTC). To preview without writing, add
`-dry-run`.

**3. Inspect the restored file** before switching to it — confirm known
children and definitions are present:

    dc run --rm --no-deps --entrypoint sqlite3 litestream \
      /var/lib/nestquest/nestquest.db.restored \
      'PRAGMA integrity_check;' \
      'SELECT id, display_name FROM children;' \
      'SELECT id, title FROM quest_definitions;'

Expect `ok`, then the household's children and quest definitions.

**4. Swap it into place**, keeping the old files (database, its
`-wal`/`-shm`, and Litestream's local state) in a timestamped directory
on the volume:

    dc run --rm --no-deps --entrypoint sh litestream -c '
      set -e
      cd /var/lib/nestquest
      ts=$(date -u +%Y%m%dT%H%M%SZ)
      mkdir -p "pre-restore-$ts"
      for f in nestquest.db nestquest.db-wal nestquest.db-shm .nestquest.db-litestream; do
        if [ -e "$f" ]; then mv "$f" "pre-restore-$ts/"; fi
      done
      mv nestquest.db.restored nestquest.db
      ls -la'

**5. Start the API, then the sidecar:**

    dc start api
    dc ps api            # wait for "healthy"
    dc up -d litestream
    dc ps litestream     # Up
    dc logs --tail 20 litestream

Use `dc up -d litestream`, not `dc start`: on a fresh box step 0 never
created the sidecar container, and `start` cannot start a container that
does not exist. `up -d` creates it if needed (or starts the existing one),
so continuous replication is back online on both paths.

The sidecar resumes replication from the restored position (it logs
`detected database behind replica` / `fetched latest L0 file from
replica`, then continues normally).

**6. Verify through the API** — the panel snapshot lists the restored
children. On the API box against `10.60.1.14:8080` directly (other LAN
hosts, including the HA box, are dropped on `:8080` by the section 6
firewall; from the HA box use the Traefik hostname instead):

    PANEL_TOKEN=$(grep '^NESTQUEST_PANEL_TOKEN=' deploy/.env | cut -d= -f2-)
    curl -s -H "Authorization: Bearer $PANEL_TOKEN" \
      http://10.60.1.14:8080/api/v1/panel/snapshot

Expect HTTP 200 and `children` naming the known child(ren). Then run
section 9.

Once satisfied, remove the old copy:
`dc run --rm --no-deps --entrypoint rm litestream -rf /var/lib/nestquest/pre-restore-<ts>`.

This exact sequence (stop, restore with integrity check, inspect, swap,
start, snapshot shows the restored child, replication resumes) was
rehearsed against a local file replica with the committed compose file;
the live proof against the SFTP replica is recorded separately by the
controller.

## 9. Verification checklist

Run after every deploy and every restore. `$PANEL_TOKEN` is the value from
`deploy/.env`; never paste it into shared logs.

| # | Check | Command | Expect |
| --- | --- | --- | --- |
| 1 | Health over TLS | `curl -s -o /dev/null -w '%{http_code}\n' https://nestquest.cubecraftlabs.com/health` | `200` |
| 2 | Valid certificate | `curl -sv https://nestquest.cubecraftlabs.com/health 2>&1 \| grep -E 'issuer\|expire date'` | Let's Encrypt issuer, future expiry (no `-k` needed) |
| 3 | Docs public | `curl -s -o /dev/null -w '%{http_code}\n' https://nestquest.cubecraftlabs.com/docs` | `200` |
| 4 | Panel refused externally | from any host other than `10.60.1.80` (e.g. a phone off Wi-Fi, or a LAN machine): `curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $PANEL_TOKEN" https://nestquest.cubecraftlabs.com/api/v1/panel/snapshot` | `403` (Traefik allowlist) |
| 5 | Panel allowed from HA box | on `10.60.1.80`: same command | `200`, snapshot JSON |
| 6 | Panel needs the token | on `10.60.1.80`, without the header | `401` |
| 7 | Admin JWT accepted | `curl -s -w '\n%{http_code}\n' -H "Authorization: Bearer $ADMIN_JWT" https://nestquest.cubecraftlabs.com/api/v1/admin/ping` with a token of a `nestquest-admins` member | `200`, `{"status":"ok","sub":...}` |
| 8 | Non-admin refused | same, with a token of a user **not** in `nestquest-admins` | `403`, "Admin access requires membership in the nestquest-admins group" |
| 9 | No/invalid token refused | same, without a header or with garbage | `401` |
| 10 | Panel token refused on admin | same, with `$PANEL_TOKEN` | `403` |
| 11 | Backup running | `dc exec litestream litestream status` | status `ok` |

To obtain `$ADMIN_JWT`: sign in to the admin PWA as the user, open the
browser developer tools, and copy the session-storage value
`nestquest.access_token`. Tokens are short-lived and are credentials —
do not store them.

## 10. Admin PWA hosting

The admin PWA (`admin/`, a Vite + React single-page app) is served from
the API box by the compose service **`pwa`**: nginx on container port
`80`, published on `${NESTQUEST_BIND_ADDRESS:-127.0.0.1}:8081` (on the API
box `10.60.1.14:8081`). Traefik sends every path of
`nestquest.cubecraftlabs.com` that is not the API to it.

**Image** — `deploy/pwa/Dockerfile`, built from the **repository root**
(it needs `admin/`); `deploy/pwa/Dockerfile.dockerignore` limits the
context to `admin/` (without `node_modules`, `dist` or `.env` files) and
`deploy/pwa/nginx.conf`.

- Stage 1, `node:22-alpine` (pinned by digest): `npm ci`, then
  `npm run build` with the three `VITE_*` build args below. Vite bakes
  them into the bundle, so **changing any of them needs a rebuild**. The
  build fails if any is empty.
- Stage 2, `nginx:alpine` pinned to
  `sha256:1ed1b0e1d7652937d6cbdaf4018c7b6fc009a7dd6c3047351e2eddda745de43f`
  (nginx 1.31.6): the built `dist/` in `/usr/share/nginx/html` and
  `deploy/pwa/nginx.conf` as `conf.d/default.conf`.

**Build args** — compose reads them from `deploy/.env` (documented in
`deploy/.env.example`). They are **public values, not secrets**: the
Authentik application is a PKCE client with no client secret.

| `deploy/.env` variable | Build arg | Production value |
| --- | --- | --- |
| `NESTQUEST_AUTHENTIK_CLIENT_ID` | `VITE_AUTHENTIK_CLIENT_ID` | client id of the Authentik NestQuest application (Authentik admin → Applications → Providers) |
| `NESTQUEST_AUTHENTIK_ISSUER` | `VITE_AUTHENTIK_ISSUER` | `https://auth.cubecraftlabs.com/application/o/nestquest/` |
| `NESTQUEST_API_BASE_URL` | `VITE_API_BASE_URL` | `https://nestquest.cubecraftlabs.com` |

The Authentik application's redirect URI must include
`https://nestquest.cubecraftlabs.com/auth/callback`.

**nginx** (`deploy/pwa/nginx.conf`):

- `allow 10.60.1.33; allow 10.60.1.14; deny all;` — only Traefik on
  nukapi-03 and the API box itself get content; any other source gets
  `403`, even with the port reachable on the LAN. Checks run on the API
  box must use its LAN address (`10.60.1.14:8081`), not `127.0.0.1`.
- SPA fallback: unknown paths (e.g. `/auth/callback`) serve `index.html`;
  `/assets/*` (content-hashed, cached for a year) returns a real `404`
  when missing.
- `/sw.js` and `/manifest.webmanifest` (`application/manifest+json`) are
  served from the site root with `Cache-Control: no-cache`, as is
  `index.html`, so a new release's service worker is picked up.

Build and start (the `api` and `litestream` services are unaffected):

    dc build pwa
    dc up -d pwa
    dc ps pwa      # "Up"

**Traefik router** — in `config/dynamic/nestquest-ccl.yml` on nukapi-03
(reference shape in section 3):

| Router | Rule | Priority | Service |
| --- | --- | --- | --- |
| `nestquest-app` | ``Host(`nestquest.cubecraftlabs.com`) && !PathPrefix(`/api`) && !Path(`/health`) && !Path(`/openapi.json`) && !PathPrefix(`/docs`)`` | `50` — below `nestquest-admin` (100) and `nestquest-panel` (200) | `nestquest-pwa` → `http://10.60.1.14:8081` |

Same `websecure` entrypoint and `myresolver` certificate as the API
routers; no Traefik middleware (nginx enforces the source allow-list).
The file provider reloads the dynamic file on save.

**Verification** (in addition to section 9):

| # | Check | Command | Expect |
| --- | --- | --- | --- |
| 1 | PWA root over TLS | `curl -s -w '\n%{http_code}\n' https://nestquest.cubecraftlabs.com/ \| tail -3` | `200`, the `NestQuest Admin` shell |
| 2 | Client route fallback | `curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://nestquest.cubecraftlabs.com/auth/callback` | `200 text/html` |
| 3 | Manifest and worker | `curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://nestquest.cubecraftlabs.com/manifest.webmanifest` and the same for `/sw.js` | `200 application/manifest+json`, `200 application/javascript` |
| 4 | API still routed to the API | `curl -s -o /dev/null -w '%{http_code}\n' https://nestquest.cubecraftlabs.com/health` | `200` (`{"status":"ok"}`, not HTML) |
| 5 | Panel refused externally | section 9 check 4 | `403` |
| 6 | Non-Traefik source refused | from a LAN machine other than `10.60.1.33`/`10.60.1.14`: `curl -s -o /dev/null -w '%{http_code}\n' http://10.60.1.14:8081/` | `403` (nginx `deny all`) |
| 7 | Proxy source allowed | on `10.60.1.14`: `curl -s -o /dev/null -w '%{http_code}\n' http://10.60.1.14:8081/` | `200` |
