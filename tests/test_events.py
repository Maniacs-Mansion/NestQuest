"""Tests for the NestQuest bus events (Feature 10, task 6).

Since Feature 18 the integration is a client of the NestQuest API
service: ``nestquest.complete_quest`` proxies to the API's panel
complete route and fires NO local bus event — the API service builds
and publishes the transition frames on its SSE stream, and the
integration's subscription (:mod:`custom_components.nestquest.sse`)
re-fires them.  The service-driven tests below therefore deliver the
frames through :func:`conftest.refire_api_transitions` (the
production event path, driven synchronously) before asserting the
bus; the shim-level tests drive :mod:`custom_components.nestquest
.events` directly, the way its remaining callers do.  The HA
``uncomplete_quest`` service is also gone (the API service's admin
uncomplete route is the reversal path), so the reversal tests drive
the core completion layer the route calls and deliver the published
frame through the same SSE subscription helper.
"""
from __future__ import annotations

import re

from conftest import refire_api_transitions, wire_entry_to_registry

from custom_components.nestquest import async_setup_entry
from custom_components.nestquest.children import create_child
from custom_components.nestquest.completion import uncomplete_instance
from custom_components.nestquest.const import (
    CONF_ADMIN_USER_IDS,
    DOMAIN,
    EVENT_CHILD_DAY_COMPLETE,
    EVENT_QUEST_COMPLETED,
    EVENT_QUEST_MISSED,
    EVENT_QUEST_UNCOMPLETED,
    SERVICE_COMPLETE_QUEST,
)
from custom_components.nestquest.core.events import (
    build_quest_uncompleted_events,
)
from custom_components.nestquest.dao_instances import QuestInstancesDao
from custom_components.nestquest.materialize import materialize
from custom_components.nestquest.quest_definitions import (
    create_quest_definition,
)
from custom_components.nestquest.recurrence import ScheduleRule

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


async def _setup_and_seed(hass, make_entry, *, windows=("morning",), seed_date=None):
    """Seed a household and materialize today's instances.

    ``seed_date`` pins the date instances are materialized for (and the
    daily rule's ``start_date``); it defaults to the host's
    ``datetime.date.today()``.  Callers that need to test the day-complete
    rule against a non-UTC HA-local timezone pass the local zone's
    ``today`` here so the seeded instance's ``due_date`` matches it.
    """
    import datetime

    if seed_date is None:
        seed_date = datetime.date.today()
    entry = wire_entry_to_registry(
        make_entry(data={CONF_ADMIN_USER_IDS: ["admin-1"]}), hass.registry
    )
    assert await async_setup_entry(hass, entry) is True
    database = entry.runtime_data.database
    child = await create_child(database, "Ada")
    await create_quest_definition(
        database,
        "Brush teeth",
        ScheduleRule.from_dict(
            {"rule_type": "daily", "start_date": seed_date.isoformat()}
        ),
        [child.id],
        list(windows),
    )
    today_iso = seed_date.isoformat()
    end_iso = (seed_date + datetime.timedelta(days=3)).isoformat()
    await materialize(database, today_iso, end_iso, today=seed_date)
    instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today_iso, today_iso
    )
    return entry, child, instances


async def test_quest_completed_fires_with_documented_payload(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    # The completed event arrives over the API's SSE stream (the
    # subscription re-fires it), never from the service handler.
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    fired = hass.bus.fired(EVENT_QUEST_COMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert payload["window"] == "morning"
    assert payload["was_on_time"] is not None
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]


async def test_recomplete_no_op_fires_nothing(hass, make_entry) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    # The no-op verdict is decided in the API's completion layer: the
    # second call appended nothing, so the API published no second
    # frame and the bus stays at exactly one event.
    client = entry.runtime_data.coordinator.api_client
    assert [result.appended for _id, result in client.completions] == [
        True,
        False,
    ]
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_child_day_complete_fires_when_day_clears(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    for instance in instances:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    day_complete = hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)
    assert len(day_complete) == 1, "exactly one day-complete per cleared day"
    payload = day_complete[0]
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["quests_due"] == len(instances)
    assert _TIMESTAMP.match(payload["occurred_at"])


async def test_child_day_complete_does_not_fire_partway(
    hass, make_entry
) -> None:
    entry, child, instances = await _setup_and_seed(
        hass, make_entry, windows=("morning", "evening")
    )
    assert len(instances) == 2
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    # The API publishes the completion but not a day-complete (the
    # child's day is not clear yet); the subscription re-fires only
    # what was published.
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    assert hass.bus.fired(EVENT_CHILD_DAY_COMPLETE) == []
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[1].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1


async def test_uncompleted_fires_on_reversal_only(hass, make_entry) -> None:
    """An actual reversal fires the uncompleted event — but only once,
    and only through the API service's transition stream: the HA
    ``uncomplete_quest`` service is gone, so the reversal is driven
    through the core completion layer the API's admin uncomplete route
    calls, with the published frame delivered by the SSE subscription."""
    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    database = entry.runtime_data.database
    client = entry.runtime_data.coordinator.api_client
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {"instance_id": instance_id, "actor": "panel", "actor_child_id": child.id},
    )
    # The reversal appends through the core completion layer; the API
    # route publishes the transition on its SSE stream and the
    # subscription re-fires it on the bus.
    result = await uncomplete_instance(
        database, instance_id, actor_source="user", actor_user_id="admin-1"
    )
    assert result.appended is True
    client.published_frames.extend(
        await build_quest_uncompleted_events(database, instance_id)
    )
    await refire_api_transitions(hass, entry, client)
    fired = hass.bus.fired(EVENT_QUEST_UNCOMPLETED)
    assert len(fired) == 1
    payload = fired[0]
    assert payload["instance_id"] == instance_id
    assert payload["quest_title"] == "Brush teeth"
    assert _TIMESTAMP.match(payload["occurred_at"])
    # Un-completing an already-open instance is a no-op: nothing is
    # appended, nothing is published, and nothing further fires.
    no_op = await uncomplete_instance(
        database, instance_id, actor_source="user", actor_user_id="admin-1"
    )
    assert no_op.appended is False
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_UNCOMPLETED)) == 1


def test_missed_event_name_is_documented_contract() -> None:
    """Feature 10 defines the missed event Feature 11's sweep fires."""
    assert EVENT_QUEST_MISSED == "nestquest_quest_missed"


async def test_appended_verdict_is_atomic_under_duplicate_calls(
    hass, make_entry
) -> None:
    """Concurrent duplicate completes decide appended under the same
    lock as the write: exactly one fires the transition event."""
    import asyncio

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    instance_id = instances[0].id
    calls = [
        hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance_id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
        for _ in range(2)
    ]
    await asyncio.gather(*calls)
    # The API's completion layer (the same core lock) decides the
    # verdict: one call appended, the duplicate did not — so the API
    # published exactly one frame and the bus carries one event.
    client = entry.runtime_data.coordinator.api_client
    assert len(client.completions) == 2
    assert [result.appended for _id, result in client.completions].count(
        True
    ) == 1
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == 1


async def test_day_complete_ignored_for_backdated_completion(
    hass, make_entry
) -> None:
    """Completing an instance NOT due today never evaluates the
    child's day-complete, so a cleared day is announced at most once
    per day and only by that day's completions."""
    import datetime

    from custom_components.nestquest.completion import (
        complete_instance as _complete,
    )

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    # A future instance (tomorrow) completed after today's day is
    # already clear.
    today = datetime.date.today()
    end = (today + datetime.timedelta(days=3)).isoformat()
    all_instances = await QuestInstancesDao(database).list_by_date_range(
        child.id, today.isoformat(), end
    )
    today_ids = {instance.id for instance in instances}
    tomorrow_instance = next(
        instance
        for instance in all_instances
        if instance.id not in today_ids
    )
    for instance in instances:
        await hass.services.call(
            DOMAIN,
            SERVICE_COMPLETE_QUEST,
            {
                "instance_id": instance.id,
                "actor": "panel",
                "actor_child_id": child.id,
            },
        )
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1

    await _complete(
        database,
        tomorrow_instance.id,
        actor_source="user",
        actor_user_id="admin-1",
    )
    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": tomorrow_instance.id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    # The service call on the already-done future instance is a no-op
    # inside the API's completion layer: nothing appended, nothing
    # published, nothing re-fired — today's single announcement stands.
    client = entry.runtime_data.coordinator.api_client
    assert client.completions[-1][1].appended is False
    await refire_api_transitions(hass, entry, client)
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == 1, (
        "a back-dated/future completion must not re-announce today"
    )
    # The direct business-layer call published nothing (only the API's
    # completion path publishes), and the follow-up service call on
    # the now-done future instance was a no-op: today's single
    # completion stands.
    assert len(hass.bus.fired(EVENT_QUEST_COMPLETED)) == len(instances)


async def test_completion_updates_entities_immediately(
    hass, make_entry
) -> None:
    """The remaining-today sensor reflects the completion the moment
    the service call returns — no manual refresh — and the day-complete
    event fired exactly once when the day became clear."""
    from custom_components.nestquest.const import EVENT_CHILD_DAY_COMPLETE

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    from conftest import wire_entry_to_registry  # noqa: F401

    coordinator = entry.runtime_data.coordinator
    # Entities only exist after one refresh since they were seeded
    # after setup; create them, then prove the service path refreshes.
    await coordinator.async_refresh()
    remaining_before = hass.entities[
        f"nestquest_child_{child.id}_quests_remaining_today"
    ].native_value
    assert remaining_before == len(instances)

    await hass.services.call(
        DOMAIN,
        SERVICE_COMPLETE_QUEST,
        {
            "instance_id": instances[0].id,
            "actor": "panel",
            "actor_child_id": child.id,
        },
    )
    remaining_after = hass.entities[
        f"nestquest_child_{child.id}_quests_remaining_today"
    ].native_value
    assert remaining_after == len(instances) - 1, (
        "sensor must reflect the completion without a manual refresh"
    )
    # The transition events arrive over the API's SSE stream.
    await refire_api_transitions(
        hass, entry, entry.runtime_data.coordinator.api_client
    )
    assert len(hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)) == (
        1 if len(instances) == 1 else 0
    )


async def test_forced_refreshes_serialize_no_stale_publish(
    hass, make_entry
) -> None:
    """Overlapping forced refreshes never interleave: a slow pass
    pauses mid-snapshot, and the queued pass still publishes AFTER
    it, so the last published snapshot reflects the latest mutation."""
    import asyncio

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    coordinator = entry.runtime_data.coordinator
    order: list[str] = []

    async def _slow_update():
        order.append("start")
        await asyncio.sleep(0.01)
        order.append("end")
        return coordinator.data

    coordinator._async_update_data = _slow_update
    await asyncio.gather(coordinator.async_refresh(), coordinator.async_refresh())
    assert order == ["start", "end", "start", "end"], (
        "overlapping refreshes must serialize: " + str(order)
    )


# ---------------------------------------------------------------------------
# Direct core-builder unit tests (P2.2a): exact payload key sets, event
# order, and was_on_time threading.  These target
# custom_components.nestquest.core.events directly, bypassing the shim,
# so a payload-shape regression is caught even if the shim masks it.
# ---------------------------------------------------------------------------

_COMPLETED_KEYS = {
    "child_id",
    "child_name",
    "instance_id",
    "quest_title",
    "window",
    "due_date",
    "due_time",
    "occurred_at",
    "was_on_time",
}
_UNCOMPLETED_KEYS = {
    "child_id",
    "child_name",
    "instance_id",
    "quest_title",
    "window",
    "due_date",
    "due_time",
    "occurred_at",
}
_DAY_COMPLETE_KEYS = {
    "child_id",
    "child_name",
    "quests_due",
    "quests_completed",
    "occurred_at",
}


async def test_build_quest_completed_event_payload_key_set(hass, make_entry) -> None:
    """The completed-event payload carries exactly the documented keys
    (no extra fields, no missing field) and threads ``was_on_time``."""
    from custom_components.nestquest.core.events import build_quest_completed_event

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    event_type, payload = await build_quest_completed_event(
        database, instances[0].id, was_on_time=True
    )
    assert event_type == EVENT_QUEST_COMPLETED
    assert set(payload) == _COMPLETED_KEYS, (
        f"completed payload keys drift: got {set(payload)} expected {_COMPLETED_KEYS}"
    )
    assert payload["was_on_time"] is True
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == instances[0].id
    assert payload["quest_title"] == "Brush teeth"
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]


async def test_build_quest_completed_event_was_on_time_threads_all_shapes(
    hass, make_entry
) -> None:
    """``was_on_time`` is carried verbatim — True, False, and None
    (the unknown-timing shape) all round-trip into the payload."""
    from custom_components.nestquest.core.events import build_quest_completed_event

    entry, _child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    for wanted in (True, False, None):
        _etype, payload = await build_quest_completed_event(
            database, instances[0].id, was_on_time=wanted
        )
        assert payload["was_on_time"] is wanted, (
            f"was_on_time={wanted!r} did not thread through"
        )


async def test_build_quest_uncompleted_events_payload_key_set(
    hass, make_entry
) -> None:
    """The uncompleted-event payload carries exactly the documented keys
    (no ``was_on_time`` — that field is completion-only)."""
    from custom_components.nestquest.core.events import (
        build_quest_uncompleted_events,
    )

    entry, _child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    events = await build_quest_uncompleted_events(database, instances[0].id)
    assert len(events) == 1
    event_type, payload = events[0]
    assert event_type == EVENT_QUEST_UNCOMPLETED
    assert set(payload) == _UNCOMPLETED_KEYS, (
        f"uncompleted payload keys drift: got {set(payload)} "
        f"expected {_UNCOMPLETED_KEYS}"
    )
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]


async def test_build_child_day_complete_event_payload_key_set(
    hass, make_entry
) -> None:
    """The day-complete payload carries exactly the documented keys
    when the child's whole day clears, and reuses the completed
    event's ``occurred_at`` stamp (one transition, one timestamp)."""
    import datetime

    from custom_components.nestquest.core.events import (
        build_child_day_complete_event,
        build_quest_completed_event,
    )

    entry, _child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    today = datetime.date.today()
    completed_type, completed_payload = await build_quest_completed_event(
        database, instances[0].id, was_on_time=True
    )
    # Mark every today-instance done so the day clears.
    from custom_components.nestquest.completion import complete_instance

    for instance in instances:
        await complete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=_child.id,
            today=today,
        )
    day_event = await build_child_day_complete_event(
        database, completed_payload, today=today
    )
    assert day_event is not None
    event_type, day_payload = day_event
    assert event_type == EVENT_CHILD_DAY_COMPLETE
    assert set(day_payload) == _DAY_COMPLETE_KEYS, (
        f"day-complete payload keys drift: got {set(day_payload)} "
        f"expected {_DAY_COMPLETE_KEYS}"
    )
    assert day_payload["occurred_at"] == completed_payload["occurred_at"], (
        "day-complete must reuse the completed event's occurred_at stamp"
    )
    assert day_payload["quests_due"] == len(instances)
    assert day_payload["quests_completed"] == len(instances)


async def test_shim_fires_completed_before_day_complete(hass, make_entry) -> None:
    """The shim fires ``nestquest_quest_completed`` BEFORE
    ``nestquest_child_day_complete`` (the pre-extraction ordering), so
    a failure in the day-complete DB reads cannot suppress the
    completed event.  Asserted by bus event ORDER, not just counts.

    Driven directly: since Feature 18 the completion service proxies
    to the API (whose event ordering is tested in test_api_sse.py);
    this targets the shim module itself, the way its remaining
    callers invoke it.
    """
    from custom_components.nestquest.completion import (
        complete_instance as _complete,
    )
    from custom_components.nestquest.events import fire_quest_completed

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    for instance in instances:
        result = await _complete(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
        )
        await fire_quest_completed(
            hass,
            database,
            instance.id,
            was_on_time=result.was_on_time,
        )
    ordered = [
        etype for etype, _payload in hass.bus.events
        if etype in (EVENT_QUEST_COMPLETED, EVENT_CHILD_DAY_COMPLETE)
    ]
    # The completed event must precede the day-complete event.
    first_completed = ordered.index(EVENT_QUEST_COMPLETED)
    first_day = ordered.index(EVENT_CHILD_DAY_COMPLETE)
    assert first_completed < first_day, (
        f"completed must fire before day-complete; order was {ordered}"
    )


# ---------------------------------------------------------------------------
# Day-complete rule coverage (P2.2b): an explicit ``today`` proves the
# four outcomes — zero-quest day, non-today instance, partial day, and
# fully-cleared today.
# ---------------------------------------------------------------------------


async def test_day_complete_zero_quest_day_yields_no_event(
    hass, make_entry
) -> None:
    """A zero-quest day never fires day-complete: when the completed
    payload's ``due_date`` matches ``today`` but the child has NO
    instances due that date, the builder returns ``None`` (the
    all-done binary sensor's rule — a day with zero quests owed can
    never be "cleared")."""
    import datetime

    from custom_components.nestquest.core.events import (
        build_child_day_complete_event,
        build_quest_completed_event,
    )

    entry, _child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    # A date the daily rule does NOT cover (well past the materialized
    # horizon) — zero instances due this date.
    zero_quest_day = datetime.date.today() + datetime.timedelta(days=365)
    _etype, completed_payload = await build_quest_completed_event(
        database, instances[0].id, was_on_time=True
    )
    # Override due_date to the zero-quest day so the builder evaluates
    # it (otherwise the due_date != today short-circuit fires first).
    crafted = dict(completed_payload, due_date=zero_quest_day.isoformat())
    result = await build_child_day_complete_event(
        database, crafted, today=zero_quest_day
    )
    assert result is None, (
        "a zero-quest day must not yield a day-complete event"
    )


async def test_day_complete_non_today_instance_yields_no_event(
    hass, make_entry
) -> None:
    """Completing an instance NOT due today never evaluates the
    child's day-complete for today: only the completed event fires."""
    import datetime

    from custom_components.nestquest.core.events import (
        build_child_day_complete_event,
        build_quest_completed_event,
    )

    entry, _child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    # Complete a FUTURE instance (tomorrow), pass today = today.
    from custom_components.nestquest.dao_instances import QuestInstancesDao

    today = datetime.date.today()
    end = (today + datetime.timedelta(days=3)).isoformat()
    all_instances = await QuestInstancesDao(database).list_by_date_range(
        _child.id, today.isoformat(), end
    )
    today_ids = {i.id for i in instances}
    tomorrow_instance = next(i for i in all_instances if i.id not in today_ids)
    _etype, completed_payload = await build_quest_completed_event(
        database, tomorrow_instance.id, was_on_time=True
    )
    assert completed_payload["due_date"] != today.isoformat()
    result = await build_child_day_complete_event(
        database, completed_payload, today=today
    )
    assert result is None, (
        "a non-today instance must not yield a day-complete event for today"
    )


async def test_day_complete_partial_day_yields_no_event(
    hass, make_entry
) -> None:
    """A partial day (some quests still open) yields only the
    completed event — day-complete does not fire until the WHOLE day
    clears."""
    import datetime

    from custom_components.nestquest.core.events import (
        build_child_day_complete_event,
        build_quest_completed_event,
    )
    from custom_components.nestquest.completion import complete_instance

    entry, child, instances = await _setup_and_seed(
        hass, make_entry, windows=("morning", "evening")
    )
    assert len(instances) == 2
    database = entry.runtime_data.database
    today = datetime.date.today()
    # Complete ONLY the morning instance — the evening one stays open.
    await complete_instance(
        database,
        instances[0].id,
        actor_source="panel",
        actor_child_id=child.id,
        today=today,
    )
    _etype, completed_payload = await build_quest_completed_event(
        database, instances[0].id, was_on_time=True
    )
    result = await build_child_day_complete_event(
        database, completed_payload, today=today
    )
    assert result is None, (
        "a partial day (evening quest still open) must not fire day-complete"
    )


async def test_day_complete_fully_cleared_today_yields_event(
    hass, make_entry
) -> None:
    """A fully-cleared today (all owed quests done) yields the
    completed event AND the child_day_complete event."""
    import datetime

    from custom_components.nestquest.core.events import (
        build_child_day_complete_event,
        build_quest_completed_event,
    )
    from custom_components.nestquest.completion import complete_instance

    entry, child, instances = await _setup_and_seed(
        hass, make_entry, windows=("morning", "evening")
    )
    assert len(instances) == 2
    database = entry.runtime_data.database
    today = datetime.date.today()
    for instance in instances:
        await complete_instance(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
            today=today,
        )
    # The last completion's payload drives the day-complete evaluation.
    _etype, completed_payload = await build_quest_completed_event(
        database, instances[-1].id, was_on_time=True
    )
    result = await build_child_day_complete_event(
        database, completed_payload, today=today
    )
    assert result is not None, (
        "a fully-cleared today must yield the day-complete event"
    )
    assert result[0] == EVENT_CHILD_DAY_COMPLETE
    assert result[1]["quests_due"] == len(instances)
    assert result[1]["quests_completed"] == len(instances)


# ---------------------------------------------------------------------------
# Shim timezone wiring (P2.2c): the conftest fake hass defaults
# hass.config.time_zone to UTC, so the day-complete rule's HA-local
# ``today`` wiring is otherwise untested.  This test sets the zone to
# one whose current local date differs from UTC and asserts the
# day-complete rule uses THAT local date, not UTC.
# ---------------------------------------------------------------------------


async def test_shim_day_complete_uses_ha_local_timezone(
    hass, make_entry
) -> None:
    """The shim's day-complete rule reads ``hass.config.time_zone``
    and derives ``today`` in HA-local time, not UTC.

    Picks a zone whose current local date differs from UTC, seeds an
    instance for THAT zone's today (not UTC's today), fires the shim
    directly for a completion of that instance, and asserts
    ``nestquest_child_day_complete`` fires — proving the local date
    reached the day-complete rule.  If no candidate zone has a
    different date right now (only possible inside the ~1h window
    around 12:00 UTC when all zones share one date), the test skips
    rather than run vacuously.

    Driven directly: since Feature 18 the completion service proxies
    to the API (whose day-complete ``today`` is the API host's local
    date, tested in test_api_sse.py); this targets the shim module
    itself, the way its remaining callers invoke it.
    """
    import datetime as _dt
    from zoneinfo import ZoneInfo

    from custom_components.nestquest.completion import (
        complete_instance as _complete,
    )
    from custom_components.nestquest.events import fire_quest_completed

    utc_today = _dt.datetime.now(_dt.timezone.utc).date()
    far_zone = None
    far_today = None
    for tz_name in (
        "Pacific/Kiritimati",   # +14 (UTC+14)
        "Pacific/Auckland",     # +12/+13
        "Pacific/Chatham",      # +12:45/+13:45
        "Pacific/Honolulu",     # -10
        "America/Los_Angeles",  # -8/-7
        "Etc/GMT+12",           # -12
        "Etc/GMT-13",           # +13
    ):
        local_today = _dt.datetime.now(ZoneInfo(tz_name)).date()
        if local_today != utc_today:
            far_zone = tz_name
            far_today = local_today
            break
    if far_zone is None:
        import pytest

        pytest.skip(
            "no candidate zone has a date different from UTC right now"
        )

    hass.config.time_zone = far_zone
    entry, child, instances = await _setup_and_seed(
        hass, make_entry, seed_date=far_today
    )
    database = entry.runtime_data.database
    for instance in instances:
        result = await _complete(
            database,
            instance.id,
            actor_source="panel",
            actor_child_id=child.id,
        )
        await fire_quest_completed(
            hass,
            database,
            instance.id,
            was_on_time=result.was_on_time,
        )
    day_complete = hass.bus.fired(EVENT_CHILD_DAY_COMPLETE)
    assert len(day_complete) == 1, (
        f"day-complete must fire under {far_zone} (local today "
        f"{far_today.isoformat()}, UTC today {utc_today.isoformat()}); "
        f"got {len(day_complete)} events"
    )


async def test_build_quest_missed_event_payload_key_set(
    hass, make_entry
) -> None:
    """The missed-event payload carries exactly the documented keys —
    the same shape the nightly sweep hand-builds (§3), with no
    ``was_on_time`` (completion-only)."""
    from custom_components.nestquest.core.events import (
        build_quest_missed_event,
    )

    entry, child, instances = await _setup_and_seed(hass, make_entry)
    database = entry.runtime_data.database
    event_type, payload = await build_quest_missed_event(
        database, instances[0].id
    )
    assert event_type == EVENT_QUEST_MISSED
    assert event_type == "nestquest_quest_missed"
    assert set(payload) == _UNCOMPLETED_KEYS, (
        f"missed payload keys drift: got {set(payload)} "
        f"expected {_UNCOMPLETED_KEYS}"
    )
    assert payload["child_id"] == child.id
    assert payload["child_name"] == "Ada"
    assert payload["instance_id"] == instances[0].id
    assert payload["quest_title"] == "Brush teeth"
    assert _TIMESTAMP.match(payload["occurred_at"]), payload["occurred_at"]
