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
``/var/lib/nestquest/nestquest.db`` by compose. The port is bound to
localhost only — TLS/reverse proxy, Authentik, network separation,
backup and restore are later Feature 17 tasks.