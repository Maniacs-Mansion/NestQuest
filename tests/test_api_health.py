"""FastAPI skeleton tests: health, OpenAPI, core wiring (task 042dfc5c).

These tests start the NestQuest API app with httpx against the ASGI
app and assert the skeleton contract of Feature 16's first task:

- ``GET /health`` returns 200 with a JSON status body (``status: ok``)
  and does NOT leak the filesystem path;
- ``GET /docs`` (Swagger UI) is served, and ``GET /openapi.json``
  returns the OpenAPI document;
- the app wires core (opens the configured SQLite file and applies
  migrations on startup via the lifespan) and closes the connection on
  shutdown (``connected is False`` afterwards);
- ``ApiConfig.from_env`` raises when ``NESTQUEST_DB_PATH`` is missing or
  empty, and returns the value when set;
- a startup failure (unwritable path / non-SQLite file) surfaces from
  the lifespan rather than the first request;
- each test is hermetic — it points ``NESTQUEST_DB_PATH`` at a fresh
  temp file.

A SEPARATE subprocess test asserts the stronger invariant the task
calls out: the app imports the bundled ``core`` WITHOUT importing
``homeassistant``.  That cannot run inside the pytest process because
``tests/conftest.py`` installs mock ``homeassistant`` modules globally
before any test imports the integration; a subprocess with a clean
``sys.modules`` is the only honest proof (the same approach
``tests/test_core_no_ha_smoke.py`` takes for the core bundle).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import httpx
import pytest

from api.app import create_app
from api.config import ApiConfig, ConfigError
from api.database import DatabaseState, _executor, make_database

#: The repo root, so the no-HA subprocess can import the API package.
_REPO_ROOT = Path(__file__).resolve().parent.parent

#: The marker the no-HA subprocess prints on success.
_SUCCESS_MARKER = "API NO-HA IMPORT OK"


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


class _AppRunner:
    """Run the app's lifespan around an httpx AsyncClient.

    httpx's :class:`ASGITransport` does NOT run the ASGI lifespan on its
    own, so the database would never open.  Starlette exposes the app's
    lifespan as ``app.router.lifespan_context``; wrapping the client
    session in it drives the same startup/shutdown path uvicorn would,
    so ``open_and_migrate`` runs before the first request and ``close``
    runs after the last.

    ``__aexit__`` uses try/finally so a client-side error still shuts
    the lifespan down — otherwise a failure mid-test would leak the
    database connection open.
    """

    def __init__(self, db_path: str) -> None:
        # The token and OIDC values are irrelevant to these tests (the
        # health route is unauthenticated); they just satisfy the
        # required fields — the panel token's own tests live in
        # test_api_panel.py and the OIDC settings' in
        # test_api_admin_auth.py.
        self.app = create_app(
            ApiConfig(
                db_path=db_path,
                panel_token="health-runner-token",
                oidc_issuer="https://authentik.example.com/application/o/nestquest/",
                oidc_audience="nestquest-api",
                oidc_jwks_url=(
                    "https://authentik.example.com/application/o/nestquest/jwks/"
                ),
            )
        )

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc) -> None:
        try:
            await self._client.__aexit__(*exc)
        finally:
            await self._lifespan.__aexit__(*exc)


@pytest.fixture
async def app_client(temp_db_path: str) -> httpx.AsyncClient:
    async with _AppRunner(temp_db_path) as client:
        yield client


# --- ApiConfig.from_env -------------------------------------------------


def test_from_env_returns_set_value() -> None:
    """Set, non-empty env values are returned verbatim."""
    cfg = ApiConfig.from_env(
        {
            "NESTQUEST_DB_PATH": "/data/nq.db",
            "NESTQUEST_PANEL_TOKEN": "panel-token",
            "NESTQUEST_OIDC_ISSUER": "https://idp.example.com/issuer/",
            "NESTQUEST_OIDC_AUDIENCE": "nestquest-api",
            "NESTQUEST_OIDC_JWKS_URL": "https://idp.example.com/jwks/",
        }
    )
    assert cfg.db_path == "/data/nq.db"
    assert cfg.panel_token == "panel-token"


def test_from_env_raises_on_empty_value() -> None:
    """An empty/whitespace-only value raises ConfigError (no silent default)."""
    with pytest.raises(ConfigError):
        ApiConfig.from_env({"NESTQUEST_DB_PATH": "   "})


def test_from_env_raises_on_missing_value() -> None:
    """A missing NESTQUEST_DB_PATH raises ConfigError (no silent default)."""
    with pytest.raises(ConfigError):
        ApiConfig.from_env({})


# --- health / openapi / docs -------------------------------------------


async def test_health_returns_200_with_status_body(
    app_client: httpx.AsyncClient,
) -> None:
    """GET /health returns 200 with status ok and no filesystem path."""
    response = await app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok"}
    assert "db_path" not in body


async def test_openapi_document_is_served(
    app_client: httpx.AsyncClient,
) -> None:
    """GET /openapi.json returns the OpenAPI document."""
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]


async def test_docs_swagger_ui_is_served(app_client: httpx.AsyncClient) -> None:
    """GET /docs serves the Swagger UI HTML (OpenAPI at /docs)."""
    response = await app_client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


# --- core wiring & shutdown --------------------------------------------


async def test_app_wires_core_and_applies_migrations(
    temp_db_path: str,
) -> None:
    """The lifespan opens the SQLite file and applies migrations.

    After startup, the file exists and carries the NestQuest schema
    version stamp — proving the app imported core, opened the database
    at the configured path, and ran the migration runner.
    """
    async with _AppRunner(temp_db_path):
        assert Path(temp_db_path).exists()
    # Re-open the file with a fresh core database to read the version
    # stamp independent of the app's connection.  Reuse the API's own
    # executor so the test exercises the same wiring the app does.
    from api.nestquest_core import core_db, core_migrations

    database = core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        version = await core_migrations.read_schema_version(database)
    finally:
        await database.close()
    assert version >= 1


async def test_shutdown_closes_the_connection(temp_db_path: str) -> None:
    """The lifespan closes the database connection on shutdown.

    After the runner exits, ``DatabaseState.database.connected`` is
    False — proving ``close()`` ran (the lifespan's finally block) even
    on a clean exit.
    """
    runner = _AppRunner(temp_db_path)
    async with runner as _client:
        state: DatabaseState = runner.app.state.db
        assert state.database.connected
    assert not state.database.connected


# --- startup failure ----------------------------------------------------


async def test_startup_fails_on_unwritable_path(tmp_path: Path) -> None:
    """A database path whose parent directory does not exist fails fast.

    ``sqlite3.connect`` raises ``OperationalError`` for a path under a
    non-existent directory; the lifespan surfaces that as a startup
    error rather than the first request.  The connection is closed
    through the lifespan's finally block (``close`` is a no-op on a
    never-opened wrapper).
    """
    bad_path = str(tmp_path / "does_not_exist" / "nestquest.db")
    runner = _AppRunner(bad_path)
    with pytest.raises(Exception):
        async with runner:
            pass


async def test_startup_fails_on_non_sqlite_file(tmp_path: Path) -> None:
    """A path pointing at a non-SQLite file fails fast on startup.

    Opening an existing file that is not a SQLite database makes the
    ``PRAGMA journal_mode=WAL`` run during :meth:`open` raise
    ``DatabaseError: file is not a database``; the lifespan surfaces it.
    """
    bad_file = tmp_path / "not_a_db.bin"
    bad_file.write_bytes(b"this is not a sqlite database")
    runner = _AppRunner(str(bad_file))
    with pytest.raises(Exception):
        async with runner:
            pass


# --- no-HA subprocess ---------------------------------------------------

#: The no-HA subprocess script.  Runs with ``sys.executable -c`` so it
#: starts with a clean ``sys.modules`` and no ``homeassistant`` installed
#: (the suite's conftest stubs are not present in a subprocess).  It
#: builds the app — which triggers the core bootstrap — and asserts
#: neither ``homeassistant`` nor ``custom_components`` entered
#: ``sys.modules``, and that the loaded core package's ``__file__``
#: points at the bundled directory.
_NO_HA_SCRIPT = textwrap.dedent(
    """\
    import sys
    import tempfile
    from pathlib import Path

    sys.path.insert(0, sys.argv[1])
    REPO_ROOT = Path(sys.argv[1])

    # homeassistant must not be present before we touch the API.
    assert "homeassistant" not in sys.modules, (
        "homeassistant already in sys.modules before app import — the "
        "subprocess is not a clean no-HA process"
    )

    from api.app import create_app
    from api.config import ApiConfig
    from api.nestquest_core import core

    # The app build imports core via api.nestquest_core.  core is a
    # Home-Assistant-free package; if it (or its loader) ever drags HA
    # in, this fails.
    assert "homeassistant" not in sys.modules, (
        "homeassistant imported while building the NestQuest API app — "
        "the core wiring is no longer Home-Assistant-free"
    )
    # The loader registers core under the distinct name "nestquest_core"
    # WITHOUT executing custom_components.nestquest.__init__, so the
    # parent integration package must never be registered, and no
    # sys.path mutation places the integration directory on sys.path.
    assert "custom_components" not in sys.modules, (
        "custom_components registered in sys.modules — the core loader "
        "executed the integration's HA-coupled __init__ instead of loading "
        "core by file location"
    )
    assert "nestquest_core" in sys.modules, "core was not imported"

    # core.__file__ must point at the bundled directory inside the
    # integration, proving the file-location loader resolved against the
    # bundled package rather than some other "core" on sys.path.
    expected_core_dir = (
        REPO_ROOT / "custom_components" / "nestquest" / "core"
    )
    assert Path(core.__file__).resolve() == (
        expected_core_dir / "__init__.py"
    ).resolve(), (
        f"core.__file__={core.__file__} does not point at the bundled "
        f"directory {expected_core_dir}"
    )

    # Build the app (the lifespan is NOT run here, so the path is never
    # opened — it just needs to be a non-empty string to satisfy the
    # fail-fast config check).  Use a temp path so nothing is created;
    # the token and OIDC values are irrelevant to this import-only check.
    app = create_app(ApiConfig(
        db_path=str(Path(tempfile.gettempdir()) / "nq-noha-buildonly.db"),
        panel_token="noha-import-token",
        oidc_issuer="https://authentik.example.com/application/o/nestquest/",
        oidc_audience="nestquest-api",
        oidc_jwks_url=(
            "https://authentik.example.com/application/o/nestquest/jwks/"
        ),
    ))
    assert app is not None

    print("API NO-HA IMPORT OK")
    """
)


def test_app_imports_core_without_importing_homeassistant() -> None:
    """The app imports core without importing homeassistant (subprocess).

    Runs in a subprocess because ``tests/conftest.py`` installs mock
    ``homeassistant`` modules into the pytest process's ``sys.modules``
    before any test runs, so an in-process check could never
    distinguish "core never touched HA" from "conftest already stubbed
    HA for us".  The subprocess is a genuine no-HA process; if the
    core loader (or core itself) ever grows a ``homeassistant``
    import, the subprocess exits non-zero with ``ModuleNotFoundError``.
    """
    result = subprocess.run(
        [sys.executable, "-c", _NO_HA_SCRIPT, str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"no-HA app-import subprocess exited {result.returncode}.\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    assert _SUCCESS_MARKER in result.stdout, (
        f"success marker {_SUCCESS_MARKER!r} not printed.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
