"""Tests for dao_presence.py: presence schedules and overrides DAO."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.dao_children import ChildrenDao
from custom_components.nestquest.dao_presence import (
    PresenceOverrideRecord,
    PresenceOverridesDao,
    PresenceScheduleRecord,
    PresenceSchedulesDao,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


NOW = "2026-09-14T12:00:00+00:00"


async def _prepare(path) -> tuple:
    database = NestQuestDatabase(_make_hass_mock().async_add_executor_job)
    await database.open(path)
    await apply_migrations(database)
    schedules = PresenceSchedulesDao(database)
    overrides = PresenceOverridesDao(database)
    children = ChildrenDao(database)
    child = await children.create("Ada", NOW)
    return database, schedules, overrides, children, child


def _with_db(tmp_path, name):
    def _run_test(body):
        async def _main():
            database, schedules, overrides, children, child = await _prepare(
                tmp_path / name
            )
            try:
                return await body(
                    database, schedules, overrides, children, child
                )
            finally:
                await database.close()

        return _run(_main())

    return _run_test


# ---------------------------------------------------------------------------
# presence_schedules: upsert by child
# ---------------------------------------------------------------------------


def test_upsert_creates_then_updates_same_row(tmp_path) -> None:
    """Second upsert for the same child UPDATES, not raises."""
    async def _body(database, schedules, overrides, children, child):
        first = await schedules.upsert_by_child(
            child.id, 2, "2026-09-07", "0,2,4|1,3"
        )
        assert isinstance(first, PresenceScheduleRecord)
        assert first.child_id == child.id
        second = await schedules.upsert_by_child(
            child.id, 2, "2026-09-14", "1,3|0,2,4"
        )
        assert second.id == first.id, "upsert must reuse the existing row"
        fetched = await schedules.get_by_child(child.id)
        assert fetched.anchor_date == "2026-09-14"
        assert fetched.pattern == "1,3|0,2,4"
        rows = await database.fetch_one(
            "SELECT COUNT(*) FROM presence_schedules"
        )
        assert rows == (1,)
        return second

    _with_db(tmp_path, "upsert.db")(_body)


def test_upsert_typed_record_fields(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        record = await schedules.upsert_by_child(
            child.id, 4, "2026-09-07", "0|1|2|3"
        )
        assert record.id == 1
        assert record.child_id == child.id
        assert record.cycle_length_weeks == 4
        assert record.anchor_date == "2026-09-07"
        assert record.pattern == "0|1|2|3"
        return record

    _with_db(tmp_path, "upsert-fields.db")(_body)


def test_upsert_unknown_child_raises_value_error(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await schedules.upsert_by_child(
                999, 2, "2026-09-07", "0,2|1,3"
            )
        return None

    _with_db(tmp_path, "upsert-bad-child.db")(_body)


def test_upsert_malformed_anchor_date_raises(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        for bad in ("not-a-date", "2026-9-7", "2026-13-01", ""):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await schedules.upsert_by_child(child.id, 2, bad, "0|1")
        return None

    _with_db(tmp_path, "upsert-bad-date.db")(_body)


def test_upsert_malformed_pattern_rejected_by_schema(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await schedules.upsert_by_child(
                child.id, 2, "2026-09-07", "0,2"
            )
        return None

    _with_db(tmp_path, "upsert-bad-pattern.db")(_body)


def test_upsert_two_children_have_distinct_rows(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        other = await children.create("Bo", NOW)
        await schedules.upsert_by_child(child.id, 2, "2026-09-07", "0,2|1,3")
        await schedules.upsert_by_child(other.id, 2, "2026-09-07", "1,3|0,2")
        mine = await schedules.get_by_child(child.id)
        theirs = await schedules.get_by_child(other.id)
        assert mine.id != theirs.id
        assert mine.pattern == "0,2|1,3"
        assert theirs.pattern == "1,3|0,2"
        return mine

    _with_db(tmp_path, "upsert-two-children.db")(_body)


def test_upsert_concurrent_same_child_serializes(tmp_path) -> None:
    """Racing upserts for one child both succeed; exactly one row.

    Deterministic interleaving: a controllable executor gates task A's
    job AFTER it has acquired the connection lock and begun its
    transaction, so task B is created while A provably owns the
    transaction and must queue on the lock.  Both upserts land, and
    the table holds exactly one row (the ON CONFLICT upsert, not two
    plain INSERTs, is what avoids a UNIQUE violation).
    """
    async def _main():
        from unittest.mock import MagicMock

        hass = MagicMock()
        # Gate exactly ONE job: the first _fetch_one issued after
        # arming, which is task A's child-existence SELECT inside its
        # transaction.  The transaction's BEGIN runs first and is NOT
        # gated, so when the gated fetch signals, BEGIN has executed
        # and SQLite is inside the open transaction (A holds the
        # connection lock from BEGIN until commit).  Everything before
        # arming (open, migrations, child create)
        # and everything after (B's jobs, A's remaining jobs, reads)
        # pass straight through.
        armed = {"active": False, "gated": False}
        gate_open = asyncio.Event()
        a_started = asyncio.Event()

        async def _gated_executor(fn, *args):
            # Gate the SECOND gated-window job: the first is the
            # transaction's BEGIN (submitted and awaited by
            # transaction() before upsert_by_child's child-SELECT
            # runs).  Pausing the child-existence SELECT proves the
            # BEGIN has EXECUTED — SQLite is actually inside the open
            # transaction, with A holding the connection lock — when
            # task B gets scheduled and must queue.
            if armed["active"]:
                name = getattr(fn, "__name__", "")
                if name == "_fetch_one" and not armed["gated"]:
                    armed["gated"] = True
                    a_started.set()
                    await gate_open.wait()
            return fn(*args)

        hass.async_add_executor_job = _gated_executor
        database = NestQuestDatabase(hass.async_add_executor_job)
        await database.open(tmp_path / "upsert-race.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            schedules = PresenceSchedulesDao(database)
            child = await children.create("Ada", NOW)

            armed["active"] = True
            task_a = asyncio.ensure_future(
                schedules.upsert_by_child(
                    child.id, 2, "2026-09-07", "0,2|1,3"
                )
            )
            # Wait until task A's child-existence SELECT (inside its
            # open transaction, BEGIN already executed) is paused, then
            # schedule task B so it must queue behind the open
            # transaction.
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio.ensure_future(
                schedules.upsert_by_child(
                    child.id, 2, "2026-09-14", "1,3|0,2"
                )
            )
            await asyncio.sleep(0)
            # Release A; B's upsert must wait for A's commit and then
            # land as the ON CONFLICT update path.
            gate_open.set()
            record_a, record_b = await asyncio.gather(task_a, task_b)
            assert record_a.id == record_b.id
            fetched = await schedules.get_by_child(child.id)
            assert fetched is not None
            rows = await database.fetch_one(
                "SELECT COUNT(*) FROM presence_schedules"
            )
            assert rows == (1,)
            return fetched
        finally:
            await database.close()

    fetched = _run(_main())
    assert fetched.pattern in {"0,2|1,3", "1,3|0,2"}


# ---------------------------------------------------------------------------
# presence_schedules: get / delete
# ---------------------------------------------------------------------------


def test_get_by_child_missing_schedule_returns_none(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        return await schedules.get_by_child(child.id)

    assert _with_db(tmp_path, "get-none.db")(_body) is None


def test_get_by_child_unknown_child_raises(tmp_path) -> None:
    """None must mean ONLY 'no schedule row': an unknown child id is a
    caller bug, and silently reading a nonexistent child as 'present
    every day' would be wrong — so get raises instead.
    """
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await schedules.get_by_child(999)
        return None

    _with_db(tmp_path, "get-unknown.db")(_body)


def test_delete_removes_and_returns_true_then_false(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        await schedules.upsert_by_child(child.id, 2, "2026-09-07", "0,2|1,3")
        assert await schedules.delete(child.id) is True
        assert await schedules.get_by_child(child.id) is None
        assert await schedules.delete(child.id) is False
        return None

    _with_db(tmp_path, "delete.db")(_body)


def test_delete_child_without_schedule_returns_false(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        return await schedules.delete(child.id)

    assert _with_db(tmp_path, "delete-none.db")(_body) is False


def test_delete_then_upsert_creates_fresh_row(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        first = await schedules.upsert_by_child(
            child.id, 2, "2026-09-07", "0,2|1,3"
        )
        await schedules.delete(child.id)
        second = await schedules.upsert_by_child(
            child.id, 2, "2026-09-07", "0,2|1,3"
        )
        assert second.id != first.id
        return second

    _with_db(tmp_path, "delete-recreate.db")(_body)


# ---------------------------------------------------------------------------
# presence_overrides: create / list / delete
# ---------------------------------------------------------------------------


def test_override_create_returns_typed_record(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        record = await overrides.create(
            child.id, "2026-12-21", "2027-01-04", False,
            note="Holiday abroad",
        )
        assert isinstance(record, PresenceOverrideRecord)
        assert record.child_id == child.id
        assert record.start_date == "2026-12-21"
        assert record.end_date == "2027-01-04"
        assert record.is_present is False
        assert record.note == "Holiday abroad"
        return record

    _with_db(tmp_path, "override-create.db")(_body)


def test_override_create_single_day_same_start_and_end(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        record = await overrides.create(
            child.id, "2026-09-14", "2026-09-14", True
        )
        assert record.start_date == record.end_date
        assert record.is_present is True
        assert record.note is None
        return record

    _with_db(tmp_path, "override-single-day.db")(_body)


def test_override_create_unknown_child_raises(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(ValueError, match="does not exist"):
            await overrides.create(
                999, "2026-09-14", "2026-09-14", True
            )
        return None

    _with_db(tmp_path, "override-bad-child.db")(_body)


def test_override_create_malformed_dates_raise(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        for bad in ("not-a-date", "2026-9-14", ""):
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await overrides.create(child.id, bad, "2026-09-14", True)
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                await overrides.create(child.id, "2026-09-14", bad, True)
        return None

    _with_db(tmp_path, "override-bad-dates.db")(_body)


def test_override_end_before_start_rejected_by_schema(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await overrides.create(
                child.id, "2026-09-14", "2026-09-13", True
            )
        return None

    _with_db(tmp_path, "override-end-before-start.db")(_body)


def test_override_list_by_child_and_range_filters_correctly(
    tmp_path,
) -> None:
    async def _body(database, schedules, overrides, children, child):
        await overrides.create(
            child.id, "2026-09-01", "2026-09-05", False, note="before"
        )
        inside = await overrides.create(
            child.id, "2026-09-10", "2026-09-12", False, note="inside"
        )
        overlapping = await overrides.create(
            child.id, "2026-09-20", "2026-09-25", True, note="overlap"
        )
        after = await overrides.create(
            child.id, "2026-10-01", "2026-10-02", False, note="after"
        )
        found = await overrides.list_by_child_and_range(
            child.id, "2026-09-09", "2026-09-22"
        )
        assert [r.id for r in found] == [inside.id, overlapping.id]
        # Inclusive boundaries: a range touching the override's edges
        # still matches.
        edge = await overrides.list_by_child_and_range(
            child.id, "2026-09-20", "2026-09-20"
        )
        assert [r.id for r in edge] == [overlapping.id]
        return found

    _with_db(tmp_path, "override-list-range.db")(_body)


def test_override_list_orders_by_start_date(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        late = await overrides.create(
            child.id, "2026-09-20", "2026-09-21", True
        )
        early = await overrides.create(
            child.id, "2026-09-10", "2026-09-11", False
        )
        found = await overrides.list_by_child_and_range(
            child.id, "2026-09-01", "2026-09-30"
        )
        assert [r.id for r in found] == [early.id, late.id]
        return found

    _with_db(tmp_path, "override-list-order.db")(_body)


def test_override_list_per_child_isolation(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        other = await children.create("Bo", NOW)
        await overrides.create(child.id, "2026-09-10", "2026-09-11", True)
        await overrides.create(other.id, "2026-09-10", "2026-09-11", False)
        mine = await overrides.list_by_child_and_range(
            child.id, "2026-09-01", "2026-09-30"
        )
        assert len(mine) == 1
        assert mine[0].is_present is True
        return mine

    _with_db(tmp_path, "override-isolation.db")(_body)


def test_override_list_malformed_range_raises(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            await overrides.list_by_child_and_range(
                child.id, "oops", "2026-09-30"
            )
        with pytest.raises(ValueError, match="on or after"):
            await overrides.list_by_child_and_range(
                child.id, "2026-09-30", "2026-09-01"
            )
        return None

    _with_db(tmp_path, "override-list-bad-range.db")(_body)


def test_override_list_unknown_child_returns_empty(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        return await overrides.list_by_child_and_range(
            999, "2026-09-01", "2026-09-30"
        )

    assert _with_db(tmp_path, "override-list-unknown.db")(_body) == []


def test_override_get_round_trip(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        record = await overrides.create(
            child.id, "2026-09-10", "2026-09-11", True, note="camp"
        )
        found = await overrides.get(record.id)
        assert found == record
        assert await overrides.get(999) is None
        return found

    found = _with_db(tmp_path, "override-get.db")(_body)
    assert found.note == "camp"


def test_override_delete_round_trip(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        record = await overrides.create(
            child.id, "2026-09-10", "2026-09-11", True
        )
        assert await overrides.delete(record.id) is True
        found = await overrides.list_by_child_and_range(
            child.id, "2026-09-01", "2026-09-30"
        )
        assert found == []
        assert await overrides.delete(record.id) is False
        return None

    _with_db(tmp_path, "override-delete.db")(_body)


def test_override_delete_missing_returns_false(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        return await overrides.delete(999)

    assert _with_db(tmp_path, "override-delete-missing.db")(_body) is False


def test_override_delete_leaves_other_overrides(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        first = await overrides.create(
            child.id, "2026-09-10", "2026-09-11", True
        )
        second = await overrides.create(
            child.id, "2026-09-20", "2026-09-21", False
        )
        assert await overrides.delete(first.id) is True
        found = await overrides.list_by_child_and_range(
            child.id, "2026-09-01", "2026-09-30"
        )
        assert [r.id for r in found] == [second.id]
        return found

    _with_db(tmp_path, "override-delete-others.db")(_body)


def test_schedule_and_override_independent_for_same_child(tmp_path) -> None:
    """Deleting the schedule does not touch overrides and vice versa."""
    async def _body(database, schedules, overrides, children, child):
        await schedules.upsert_by_child(child.id, 2, "2026-09-07", "0,2|1,3")
        override = await overrides.create(
            child.id, "2026-09-10", "2026-09-11", True
        )
        assert await schedules.delete(child.id) is True
        found = await overrides.list_by_child_and_range(
            child.id, "2026-09-01", "2026-09-30"
        )
        assert [r.id for r in found] == [override.id]
        return found

    _with_db(tmp_path, "independent.db")(_body)


# ---------------------------------------------------------------------------
# No SQL for these tables outside the DAO module
# ---------------------------------------------------------------------------


def test_presence_sql_lives_only_in_dao_module() -> None:
    """Guardrail: presence_schedules/presence_overrides SQL may appear
    only in the DAO module (and the schema DDL declarations).
    RECURSIVE scan of package and tests, FROM/INTO/UPDATE/DELETE FROM/
    JOIN pattern, with exact repo-relative exclusions justified by
    role: schema.py declares the DDL, migrations.py applies it, and
    the test files for exactly those layers verify DDL, not data
    paths.
    """
    import re
    from pathlib import Path

    package = Path(
        __import__(
            "custom_components.nestquest", fromlist=["__file__"]
        ).__file__
    ).parent
    repo_root = package.parent.parent
    scan_roots = [package, repo_root / "tests"]

    allowed = {
        "custom_components/nestquest/core/dao_presence.py",  # this DAO
        "custom_components/nestquest/core/schema.py",  # declares the DDL
        "custom_components/nestquest/core/migrations.py",  # applies the DDL
        "tests/test_schema.py",  # tests the DDL
        "tests/test_migrations.py",  # tests migration application
        "tests/test_dao_presence.py",  # this file, scanned separately
    }
    sql_pattern = re.compile(
        r"(FROM|INTO|UPDATE|DELETE\s+FROM|JOIN)\s+[`'\"]*(\[)?"
        r"(presence_schedules|presence_overrides)\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for root in scan_roots:
        for py in sorted(root.rglob("*.py")):
            relative = py.relative_to(repo_root).as_posix()
            if relative in allowed:
                continue
            if sql_pattern.search(py.read_text()):
                offenders.append(relative)
    assert offenders == [], (
        f"SQL touching presence_schedules/presence_overrides leaked "
        f"into: {offenders}"
    )


def test_dao_presence_test_file_uses_dao_not_raw_table_sql() -> None:
    """This test module must exercise the DAO, not raw SQL, for these
    tables.  Exemptions are EXACT lines, not whole-function spans: the
    two single-statement COUNT(*) row probes (the only honest way to
    prove 'exactly one row exists' without a listing method) and the
    guard functions' own regex spans.  Any other raw SQL added anywhere
    in this file fails the guard.
    """
    import ast
    import re
    from pathlib import Path

    path = Path(__file__)
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    guard_names = {
        "test_presence_sql_lives_only_in_dao_module",
        "test_dao_presence_test_file_uses_dao_not_raw_table_sql",
    }
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in guard_names:
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )
            continue
        # Narrow probe exemption: only the string-literal line holding
        # the sanctioned COUNT(*) query, not the enclosing function.
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Constant)
                and isinstance(sub.value, str)
                and sub.value.strip()
                == "SELECT COUNT(*) FROM presence_schedules"
                and sub.lineno is not None
            ):
                excluded.add(sub.lineno)

    remaining = "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM|"
        r"FROM|JOIN)\s+[`'\"]*(\[)?(presence_schedules|presence_overrides)"
        r"\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(remaining) is None, (
        "tests must go through the DAO, not raw SQL, for these tables"
    )

# ---------------------------------------------------------------------------
# Presence overrides: overlap rejection naming the conflict
# ---------------------------------------------------------------------------


def test_override_create_round_trip_single_and_range(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        single = await overrides.create(
            child.id, "2026-07-20", "2026-07-20", False
        )
        assert (single.start_date, single.end_date) == ("2026-07-20",) * 2
        span = await overrides.create(
            child.id, "2026-08-01", "2026-08-05", True, note="traded week"
        )
        assert span.is_present is True
        assert span.note == "traded week"
        # Distinct, non-overlapping ranges coexist.
        listed = await overrides.list_by_child_and_range(
            child.id, "2026-01-01", "2026-12-31"
        )
        assert [row.id for row in listed] == [single.id, span.id]
        return listed

    _with_db(tmp_path, "override-round-trip.db")(_body)


def test_override_overlap_rejected_and_names_the_conflict(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        existing = await overrides.create(
            child.id, "2026-07-20", "2026-07-24", False, note="holiday"
        )
        for start, end in (
            ("2026-07-24", "2026-07-26"),  # touches the existing end
            ("2026-07-18", "2026-07-20"),  # touches the existing start
            ("2026-07-21", "2026-07-22"),  # fully inside
            ("2026-07-01", "2026-07-30"),  # fully covering
        ):
            with pytest.raises(ValueError, match="overlaps existing"):
                await overrides.create(
                    child.id, start, end, True, note="swap"
                )
        # The error NAMES the conflicting override (id + its range).
        with pytest.raises(
            ValueError,
            match=(
                rf"override {existing.id} "
                rf"\[2026-07-20, 2026-07-24\].*is_present=False"
            ),
        ):
            await overrides.create(child.id, "2026-07-22", "2026-07-22", True)
        # Nothing was written by any rejected attempt.
        listed = await overrides.list_by_child_and_range(
            child.id, "2026-01-01", "2026-12-31"
        )
        assert [row.id for row in listed] == [existing.id]
        return existing

    _with_db(tmp_path, "override-overlap.db")(_body)


def test_override_overlap_is_per_child(tmp_path) -> None:
    """Different children's overrides may cover the same dates: the
    conflict rule is per child."""
    async def _body(database, schedules, overrides, children, child):
        other = await children.create("Bo", NOW)
        await overrides.create(child.id, "2026-07-20", "2026-07-24", False)
        twin = await overrides.create(
            other.id, "2026-07-20", "2026-07-24", True
        )
        assert twin.child_id == other.id
        listed = await overrides.list_by_child_and_range(
            other.id, "2026-01-01", "2026-12-31"
        )
        assert [row.id for row in listed] == [twin.id]
        return twin

    _with_db(tmp_path, "override-per-child.db")(_body)


def test_override_remove_then_recreate_overlapping(tmp_path) -> None:
    async def _body(database, schedules, overrides, children, child):
        first = await overrides.create(
            child.id, "2026-07-20", "2026-07-24", False
        )
        assert await overrides.delete(first.id) is True
        assert await overrides.delete(first.id) is False
        replacement = await overrides.create(
            child.id, "2026-07-20", "2026-07-24", True, note="swap back"
        )
        assert replacement.is_present is True
        return replacement

    _with_db(tmp_path, "override-recreate.db")(_body)


def test_override_create_racing_conflicts_serialize(tmp_path) -> None:
    """Two racing creates for the same child and dates: exactly one
    lands, the other is rejected with the overlap error.  DETERMINISTIC
    gate: task A is paused at its INSERT — inside its open transaction,
    after its overlap probe — so task B is created while A provably
    holds the connection lock and must queue; B then re-runs the probe
    against A's committed row and is rejected."""
    import asyncio as asyncio_module
    from unittest.mock import MagicMock

    async def _main():
        from custom_components.nestquest.dao_children import ChildrenDao
        from custom_components.nestquest.dao_presence import (
            PresenceOverridesDao,
        )
        from custom_components.nestquest.db import NestQuestDatabase
        from custom_components.nestquest.migrations import apply_migrations

        armed = {"active": False, "gated": False}
        gate_open = asyncio_module.Event()
        a_started = asyncio_module.Event()

        hass = MagicMock()

        async def _gated_executor(fn, *args):
            if armed["active"]:
                # Gate the FIRST _execute after arming: task A's INSERT,
                # which runs inside its open transaction (BEGIN already
                # executed) after the overlap probe.
                if getattr(fn, "__name__", "") == "_execute" and not armed["gated"]:
                    armed["gated"] = True
                    a_started.set()
                    await gate_open.wait()
            return fn(*args)

        hass.async_add_executor_job = _gated_executor
        database = NestQuestDatabase(hass.async_add_executor_job)
        await database.open(tmp_path / "override-race.db")
        try:
            await apply_migrations(database)
            children = ChildrenDao(database)
            overrides = PresenceOverridesDao(database)
            child = await children.create("Ada", NOW)

            armed["active"] = True
            task_a = asyncio_module.ensure_future(
                overrides.create(child.id, "2026-07-20", "2026-07-24", True)
            )
            await a_started.wait()
            armed["active"] = False
            task_b = asyncio_module.ensure_future(
                overrides.create(child.id, "2026-07-22", "2026-07-26", False)
            )
            await asyncio_module.sleep(0)
            gate_open.set()
            record_a, error_b = await asyncio_module.gather(
                task_a, task_b, return_exceptions=True
            )
            assert isinstance(record_a, object) and not isinstance(
                record_a, BaseException
            ), f"A must land: {record_a!r}"
            assert isinstance(error_b, ValueError), (
                f"B must be rejected with the overlap error: {error_b!r}"
            )
            assert "overlaps existing" in str(error_b)
            listed = await overrides.list_by_child_and_range(
                child.id, "2026-01-01", "2026-12-31"
            )
            assert [row.id for row in listed] == [record_a.id]
        finally:
            await database.close()

    asyncio.new_event_loop().run_until_complete(_main())
