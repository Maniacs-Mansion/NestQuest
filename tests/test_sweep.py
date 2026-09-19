"""Tests for the nightly missed-quest sweep (Feature 11, task 1)."""
from __future__ import annotations

import datetime
import re

from conftest import wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import create_child, list_children
from custom_components.nestquest.completion import (
    complete_instance,
    uncomplete_instance,
)
from custom_components.nestquest.const import EVENT_QUEST_MISSED
from custom_components.nestquest.dao_instances import (
    CompletionEventsDao,
    QuestInstancesDao,
)
from custom_components.nestquest.dao_meta import MetaStateDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule
from custom_components.nestquest.sweep import (
    SWEEP_WATERMARK_KEY,
    run_missed_sweep,
)

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


async def _seed(hass, make_entry) -> tuple:
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    ada = await create_child(database, "Ada")
    bo = await create_child(database, "Bo")
    today = datetime.date.today()
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": today.isoformat()}
        ),
        [ada.id, bo.id],
        ["morning"],
    )
    end = (today + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today.isoformat(), end, today=today)
    return entry, ada, bo


async def test_sweep_fires_one_event_per_past_due_open_instance(
    hass, make_entry
) -> None:
    entry, ada, bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    fired = await run_missed_sweep(hass, database, today=tomorrow)
    assert fired == 2, "one per child for today's now-past-due instance"

    events = hass.bus.fired(EVENT_QUEST_MISSED)
    assert len(events) == 2
    payload = events[0]
    assert payload["child_name"] in ("Ada", "Bo")
    assert payload["quest_title"] == "Brush teeth"
    assert payload["window"] == "morning"
    assert payload["due_date"] == today.isoformat()
    assert payload["due_time"] is None
    assert _TIMESTAMP.match(payload["occurred_at"])
    assert {payload["child_id"] for payload in events} == {ada.id, bo.id}
    # The sweep is read-only over the domain tables.
    assert await _count_events(database) == 0


async def test_sweep_is_idempotent_same_night(hass, make_entry) -> None:
    entry, _ada, _bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)

    first = await run_missed_sweep(hass, database, today=tomorrow)
    second = await run_missed_sweep(hass, database, today=tomorrow)
    assert first == 2
    assert second == 0, "the watermark makes a rerun fire nothing"
    assert len(hass.bus.fired(EVENT_QUEST_MISSED)) == 2
    assert await MetaStateDao(database).get(SWEEP_WATERMARK_KEY) == (
        tomorrow.isoformat()
    )


async def test_sweep_only_fires_new_instances_after_watermark(
    hass, make_entry
) -> None:
    entry, ada, _bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    day_after = today + datetime.timedelta(days=2)

    # First sweep one day ahead: today's instances fire.
    fired = await run_missed_sweep(hass, database, today=tomorrow)
    assert fired == 2
    first_events = hass.bus.fired(EVENT_QUEST_MISSED)
    assert all(
        payload["due_date"] == today.isoformat()
        for payload in first_events
    )

    # One more day passes: only tomorrow's instances fire now.
    fired = await run_missed_sweep(hass, database, today=day_after)
    assert fired == 2
    all_events = hass.bus.fired(EVENT_QUEST_MISSED)
    assert len(all_events) == 4
    assert all(
        payload["due_date"] == tomorrow.isoformat()
        for payload in all_events[2:]
    )


async def test_sweep_never_reports_completed_or_reversed_instances(
    hass, make_entry
) -> None:
    entry, ada, bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    instances_ada = await QuestInstancesDao(database).list_by_date_range(
        ada.id, today.isoformat(), today.isoformat()
    )
    instances_bo = await QuestInstancesDao(database).list_by_date_range(
        bo.id, today.isoformat(), today.isoformat()
    )
    # Ada completed hers; Bo completed his then reversed it.
    await complete_instance(
        database,
        instances_ada[0].id,
        actor_source="panel",
        actor_child_id=ada.id,
    )
    await complete_instance(
        database,
        instances_bo[0].id,
        actor_source="panel",
        actor_child_id=bo.id,
    )
    await uncomplete_instance(
        database,
        instances_bo[0].id,
        actor_source="user",
        actor_user_id="admin-1",
    )

    fired = await run_missed_sweep(hass, database, today=tomorrow)
    assert fired == 0, (
        "no-completion-event rule excludes both the completed and the "
        "reversed instance (append-only history keeps both)"
    )
    assert hass.bus.fired(EVENT_QUEST_MISSED) == []


async def test_sweep_skips_instance_completed_after_sweep(
    hass, make_entry
) -> None:
    """A missed instance completed later is never re-announced; the
    late completion still lands in the append-only log."""
    entry, ada, _bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    day3 = today + datetime.timedelta(days=2)

    await run_missed_sweep(hass, database, today=tomorrow)
    instance = (
        await QuestInstancesDao(database).list_by_date_range(
            ada.id, today.isoformat(), today.isoformat()
        )
    )[0]
    await complete_instance(
        database,
        instance.id,
        actor_source="panel",
        actor_child_id=ada.id,
    )
    fired = await run_missed_sweep(hass, database, today=day3)
    assert fired == 0 or all(
        payload["instance_id"] != instance.id
        for payload in hass.bus.fired(EVENT_QUEST_MISSED)[2:]
    )


async def test_rollover_listener_runs_sweep_after_materialization(
    hass, make_entry, monkeypatch
) -> None:
    import custom_components.nestquest as nestquest

    calls = []

    async def _record_sweep(hass_arg, database, **kwargs):
        calls.append("sweep")

    monkeypatch.setattr(nestquest, "run_missed_sweep", _record_sweep)

    entry = wire_entry_to_registry(
        make_entry(options={"day_rollover_time": "00:00"}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    assert calls == ["sweep"], "startup runs the sweep once"

    await hass.time_change.fire()
    assert calls == ["sweep", "sweep"], "the rollover listener sweeps too"


async def test_v6_database_migrates_to_v7_meta_state(
    hass, make_entry
) -> None:
    """A database stamped at version 6 gains the meta_state table and
    version 7 on the next startup; existing rows are untouched."""
    entry = wire_entry_to_registry(make_entry(), hass.registry)
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    version = await database.fetch_one(
        "SELECT version FROM nestquest_schema_version"
    )
    assert version == (7,)
    tables = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='nestquest_meta_state'"
    )
    assert tables, "migration 7 created the meta_state table"


async def _count_events(database) -> int:
    rows = await database.fetch_all("SELECT COUNT(*) FROM completion_events")
    return rows[0][0]


async def test_overlapping_sweeps_never_double_announce(
    hass, make_entry
) -> None:
    """A startup sweep and a rollover sweep racing on the same night
    queue on the sweep lock: the winner announces, the loser re-reads
    the watermark inside the lock and fires nothing."""
    import asyncio

    entry, _ada, _bo = await _seed(hass, make_entry)
    database = entry.runtime_data.database
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)

    first, second = await asyncio.gather(
        run_missed_sweep(hass, database, today=tomorrow),
        run_missed_sweep(hass, database, today=tomorrow),
    )
    assert first + second == 2, "each instance announced exactly once"
    assert len(hass.bus.fired(EVENT_QUEST_MISSED)) == 2
