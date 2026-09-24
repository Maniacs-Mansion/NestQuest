# NestQuest API

Standalone FastAPI service owning the NestQuest database (Feature 16).
Served with ``uvicorn --factory api.app:create_app``; configuration is
environment-supplied (``api/config.py``) and every variable is required.

## Runtime dependencies

``api/requirements.txt`` is the API deployable's OWN dependency
manifest (fastapi, uvicorn, pyjwt[crypto], httpx) — deliberately kept
out of the integration's ``pyproject.toml`` dev group, which exists only
so the monorepo test venv can run the API tests.

## Container deployment (scaffold)

The image is built from the repository ROOT context (the API loads the
bundled domain core from ``custom_components/nestquest/core/`` by file
location, so both trees must be in the build context):

    docker build -t nestquest-api:latest .

Run it with compose — the SQLite file lives on the named volume
``nestquest-db`` so recreating the container keeps household data:

    cp deploy/.env.example deploy/.env   # then fill in real values
    docker compose -f deploy/compose.yaml up -d --build

``deploy/.env`` is git-ignored and supplies the secrets (panel service
token, Authentik OIDC settings); ``NESTQUEST_DB_PATH`` is fixed to
``/var/lib/nestquest/nestquest.db`` by compose.

The published port binds ``NESTQUEST_BIND_ADDRESS`` from
``deploy/.env`` and defaults to ``127.0.0.1`` (localhost only). In
production TLS is terminated by the shared Traefik reverse proxy,
which serves ``https://nestquest.cubecraftlabs.com`` (Let's Encrypt,
auto-renewed, HTTP redirected to HTTPS) and forwards to the API box
on port 8080 — so on that box set ``NESTQUEST_BIND_ADDRESS`` to its
LAN address (``10.60.1.14``). Traefik only allows
``/api/v1/panel`` from the Home Assistant host. Network separation
and the full restore runbook are later Feature 17 tasks.

## Continuous backup (Litestream)

Compose also runs a ``litestream`` sidecar
(``litestream/litestream:0.5.17``, config ``deploy/litestream.yml``).
It mounts the same ``nestquest-db`` volume and continuously replicates
``/var/lib/nestquest/nestquest.db`` over SFTP to the Synology NAS
``CubeCraft-SRVR1`` (``joshua@10.60.1.50``), directory
``/volume1/homes/Joshua/nestquest-backups`` (``/homes/Joshua/...`` in
the NAS's chrooted SFTP view) — so the backup is outside the Docker
host and its volume. A snapshot is taken daily and a week of
snapshots plus incremental changes is retained; the NAS host key is
pinned in the config.

The SFTP login uses a dedicated keypair that lives only on the API
box and is git-ignored. Create it once, before ``up``:

    ssh-keygen -t ed25519 -N "" -C nestquest-litestream -f deploy/litestream_key

then append ``restrict `` + the contents of ``deploy/litestream_key.pub``
to ``joshua@10.60.1.50:~/.ssh/authorized_keys``. Compose mounts the
private key read-only at ``/etc/litestream/sftp_key``.

Check replication with
``docker compose -f deploy/compose.yaml logs litestream`` or
``docker compose -f deploy/compose.yaml exec litestream litestream ltx /var/lib/nestquest/nestquest.db``.
To restore (high level): stop the ``api`` service, run
``litestream restore -config /etc/litestream.yml -o <new path>
/var/lib/nestquest/nestquest.db`` from a litestream container with the
same mounts, verify the restored file, move it into place on the
volume (removing any stale ``-wal``/``-shm`` files), and start ``api``
again.