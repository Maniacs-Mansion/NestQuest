"""No-HA end-to-end smoke test (task 628473ad).

The bundled core package (``custom_components.nestquest.core``) is
self-contained and Home-Assistant-free, but the parent integration
package ``custom_components.nestquest`` is NOT: its ``__init__.py``
imports ``homeassistant``.  A genuine "core runs with no Home
Assistant installed" proof therefore cannot live inside the suite
process — the suite's ``conftest.py`` installs mock ``homeassistant``
modules globally before any test imports the integration, so an
in-process exercise can never distinguish "core never touched HA"
from "conftest already stubbed HA for us".

This module runs the smoke test in a SUBPROCESS (``sys.executable -c
<script>``) that starts with a clean ``sys.modules`` and no
``homeassistant`` installed.  The subprocess script:

- asserts ``homeassistant`` is NOT in ``sys.modules`` before importing
  core;
- installs a STUB parent package ``custom_components.nestquest`` (a
  bare :class:`types.ModuleType` whose ``__path__`` points at the real
  ``custom_components/nestquest`` directory) into ``sys.modules``
  WITHOUT executing its ``__init__.py`` — so importing
  ``custom_components.nestquest.core.<x>`` resolves the real core
  subpackage without dragging the integration's HA imports along;
- installs a ``custom_components`` namespace entry too, so the
  subpackage resolves;
- imports the core modules (db, migrations, children,
  quest_definitions, materialize, completion, recurrence);
- asserts ``homeassistant`` is STILL not in ``sys.modules`` after
  those imports;
- opens a FRESH SQLite file, applies migrations, creates two children
  and one quest definition (a daily recurrence rule with a start date
  and one ``morning`` window), runs :func:`materialize` over a 28-day
  window, completes one instance via :func:`complete_instance`
  (``actor_source='panel'``), and derives the instance state via
  :func:`instance_state`, asserting it is ``done``;
- prints a clear success marker.

The pytest test asserts the subprocess exit code is 0 and the marker
is printed, and fails with the subprocess stderr otherwise.  This
guards the storage/engines/business extraction (tasks d0b691d8 /
510c1f78 / 4dd8f870) from regressing into a HA-coupled bundle: the
moment a core module grows a ``homeassistant`` import (direct or via
the parent package's ``__init__``), this test fails in a process
where HA is genuinely absent.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

#: The marker the subprocess prints on success.  Kept short and unique
#: so the parent test can assert it survived intact in stdout.
SUCCESS_MARKER = "NO-HA SMOKE TEST OK"

#: The repo root, so the subprocess can locate the real
#: ``custom_components/nestquest`` directory regardless of its own
#: working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent

#: The smoke-test script, run with ``sys.executable -c``.  It is a
#: real no-HA process: the suite's conftest stubs do not exist here,
#: and ``homeassistant`` is not installed in this venv, so any core
#: import of HA (direct or via the parent package ``__init__``) raises
#: ``ModuleNotFoundError`` and the subprocess exits non-zero.
_SCRIPT = textwrap.dedent(
    """\
    import asyncio
    import datetime
    import sys
    import tempfile
    import types
    from pathlib import Path

    REPO_ROOT = Path(sys.argv[1])
    CC_PATH = REPO_ROOT / "custom_components"
    NQ_PATH = CC_PATH / "nestquest"

    # 1. homeassistant must not be imported before we touch core.
    assert "homeassistant" not in sys.modules, (
        "homeassistant already in sys.modules before core import — "
        "the subprocess is not a clean no-HA process"
    )

    # 2. Stub the parent packages WITHOUT running their __init__.py.
    #    custom_components is a namespace package; nestquest's __init__
    #    imports homeassistant, so we install a bare ModuleType whose
    #    __path__ points at the real directory instead of executing it.
    cc = types.ModuleType("custom_components")
    cc.__path__ = [str(CC_PATH)]
    sys.modules["custom_components"] = cc

    nq = types.ModuleType("custom_components.nestquest")
    nq.__path__ = [str(NQ_PATH)]
    nq.__package__ = "custom_components.nestquest"
    sys.modules["custom_components.nestquest"] = nq
    cc.nestquest = nq

    # 3. Import the core modules directly from the bundle.
    from custom_components.nestquest.core.db import NestQuestDatabase
    from custom_components.nestquest.core.migrations import apply_migrations
    from custom_components.nestquest.core.children import create_child
    from custom_components.nestquest.core.quest_definitions import (
        create_quest_definition,
    )
    from custom_components.nestquest.core.materialize import materialize
    from custom_components.nestquest.core.completion import (
        complete_instance,
        instance_state,
    )
    from custom_components.nestquest.core.recurrence import (
        RuleType,
        ScheduleRule,
    )
    from custom_components.nestquest.core.dao_instances import (
        QuestInstancesDao,
    )

    # 4. core must not have pulled in homeassistant.
    assert "homeassistant" not in sys.modules, (
        "homeassistant imported by core — the core bundle is no longer "
        "Home-Assistant-free"
    )


    async def _executor(fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)


    async def main() -> None:
        db_path = Path(tempfile.mkdtemp(prefix="nq-noha-smoke-")) / "nestquest.db"
        database = NestQuestDatabase(_executor)
        await database.open(str(db_path))
        try:
            await apply_migrations(database)

            # Two children.
            child_a = await create_child(database, "Ada")
            child_b = await create_child(database, "Bee")

            # One quest definition: daily recurrence, one morning window.
            today = datetime.date.today()
            start_iso = today.isoformat()
            rule = ScheduleRule(
                rule_type=RuleType.DAILY, interval=1, start_date=start_iso
            )
            created = await create_quest_definition(
                database,
                "Brush teeth",
                rule,
                [child_a.id, child_b.id],
                ["morning"],
            )
            assert created.definition.id is not None

            # Materialize over a 28-day window (inclusive of both ends).
            end_iso = (today + datetime.timedelta(days=27)).isoformat()
            count = await materialize(database, start_iso, end_iso, today=today)
            assert count > 0, (
                f"materialize produced no instances over the 28-day "
                f"window (count={count})"
            )

            # Complete one instance for child_a on the start date.
            instances = QuestInstancesDao(database)
            rows = await instances.list_by_child_and_date(
                child_a.id, start_iso
            )
            assert rows, (
                "no materialized instance for child_a on the start date"
            )
            instance = rows[0]

            result = await complete_instance(
                database,
                instance.id,
                actor_source="panel",
                actor_child_id=child_a.id,
                today=today,
            )
            assert result == "done", (
                f"complete_instance returned {result!r}, expected 'done'"
            )

            state = await instance_state(database, instance.id, today=today)
            assert state == "done", (
                f"instance_state returned {state!r}, expected 'done'"
            )
        finally:
            await database.close()

        print("NO-HA SMOKE TEST OK")


    asyncio.run(main())
    """
)


def test_core_runs_end_to_end_without_homeassistant() -> None:
    """Run the no-HA smoke test in a subprocess and assert its marker.

    The subprocess is a genuine no-HA process: the suite's conftest
    stubs are not present there, and ``homeassistant`` is not installed
    in this venv.  If any core module ever grows a ``homeassistant``
    import (directly or via the parent package ``__init__``), the
    subprocess exits non-zero with a ``ModuleNotFoundError`` and this
    test fails with the subprocess's stderr.
    """
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"no-HA smoke subprocess exited {result.returncode}.\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    assert SUCCESS_MARKER in result.stdout, (
        f"success marker {SUCCESS_MARKER!r} not printed by subprocess.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
