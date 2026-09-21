"""FastAPI skeleton tests: health, OpenAPI, core wiring (task 042dfc5c).

These tests start the NestQuest API app with httpx against the ASGI
app and assert the skeleton contract of Feature 16's first task:

- ``GET /health`` returns 200 with a JSON status body (``status: ok``
  plus the resolved ``db_path``);
- ``GET /docs`` (Swagger UI) is served, and ``GET /openapi.json``
  returns the OpenAPI document;
- the app wires core (opens the configured SQLite file and applies
  migrations on startup via the lifespan);
- the test is hermetic — each test points ``NESTQUEST_DB_PATH`` at a
  fresh temp file.

A SEPARATE subprocess test asserts the stronger invariant the task
calls out: the app imports the bundled ``core`` WITHOUT importing
``homeassistant``.  That cannot run inside the pytest process because
``tests/conftest.py`` installs mock ``homeassistant`` modules globally
before any test imports the integration; a subprocess with a clean
``sys.modules`` is the only honest proof (the same approach
``tests/test_core_no_ha_smoke.py`` takes for the core bundle).
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import httpx
import pytest

from api.app import create_app
from api.config import ApiConfig

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
    """

    def __init__(self, db_path: str) -> None:
        self.app = create_app(ApiConfig(db_path=db_path))

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc) -> None:
        await self._client.__aexit__(*exc)
        await self._lifespan.__aexit__(*exc)


@pytest.fixture
async def app_client(temp_db_path: str) -> httpx.AsyncClient:
    async with _AppRunner(temp_db_path) as client:
        yield client


async def test_health_returns_200_with_status_body(
    app_client: httpx.AsyncClient, temp_db_path: str
) -> None:
    """GET /health returns 200 with status ok and the resolved db path."""
    response = await app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db_path"] == temp_db_path


async def test_openapi_document_is_served(
    app_client: httpx.AsyncClient
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


async def test_app_wires_core_and_applies_migrations(
    temp_db_path: str
) -> None:
    """The lifespan opens the SQLite file and applies migrations.

    After startup, the file exists and carries the NestQuest schema
    version stamp — proving the app imported core, opened the database
    at the configured path, and ran the migration runner.
    """
    async with _AppRunner(temp_db_path):
        assert Path(temp_db_path).exists()
    # Re-open the file with a fresh core database to read the version
    # stamp independent of the app's connection.
    from api.nestquest_core import core_db, core_migrations

    async def _executor(fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    database = core_db.NestQuestDatabase(_executor)
    await database.open(temp_db_path)
    try:
        version = await core_migrations.read_schema_version(database)
    finally:
        await database.close()
    assert version >= 1


#: The no-HA subprocess script.  Runs with ``sys.executable -c`` so it
#: starts with a clean ``sys.modules`` and no ``homeassistant`` installed
#: (the suite's conftest stubs are not present in a subprocess).  It
#: builds the app — which triggers the core bootstrap — and asserts
#: neither ``homeassistant`` nor ``custom_components`` entered
#: ``sys.modules``.
_NO_HA_SCRIPT = textwrap.dedent(
    """\
    import sys
    sys.path.insert(0, sys.argv[1])

    # homeassistant must not be present before we touch the API.
    assert "homeassistant" not in sys.modules, (
        "homeassistant already in sys.modules before app import — the "
        "subprocess is not a clean no-HA process"
    )

    from api.app import create_app
    from api.config import ApiConfig

    app = create_app(ApiConfig(db_path=":memory:"))

    # The app build imports core via api.nestquest_core.  core is a
    # Home-Assistant-free package; if it (or its bootstrap) ever drags
    # HA in, this fails.
    assert "homeassistant" not in sys.modules, (
        "homeassistant imported while building the NestQuest API app — "
        "the core wiring is no longer Home-Assistant-free"
    )
    # The bootstrap must import core as a TOP-LEVEL package without
    # executing custom_components.nestquest.__init__, so the parent
    # integration package must never be registered.
    assert "custom_components" not in sys.modules, (
        "custom_components registered in sys.modules — the core bootstrap "
        "executed the integration's HA-coupled __init__ instead of importing "
        "core as a top-level package"
    )
    assert "core" in sys.modules, "core was not imported"

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
    core bootstrap (or core itself) ever grows a ``homeassistant``
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
