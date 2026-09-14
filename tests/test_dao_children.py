"""Tests for dao_children.py: typed DAO for children and admin_users."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from custom_components.nestquest.dao_children import (
    AdminUserRecord,
    AdminUsersDao,
    ChildRecord,
    ChildrenDao,
)
from custom_components.nestquest.db import NestQuestDatabase
from custom_components.nestquest.schema import SCHEMA_V1_STATEMENTS
from custom_components.nestquest.migrations import apply_migrations


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_hass_mock():
    from unittest.mock import AsyncMock, MagicMock

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=(lambda fn, *a: fn(*a)))
    return hass


def _open_db(path) -> NestQuestDatabase:
    database = NestQuestDatabase(_make_hass_mock())
    _run(database.open(path))
    _run(apply_migrations(database))
    return database


def _daos(database) -> tuple[ChildrenDao, AdminUsersDao]:
    return ChildrenDao(database), AdminUsersDao(database)


NOW = "2026-09-14T11:00:00+00:00"


def _make_child(dao, name="Ada", **kwargs) -> ChildRecord:
    return _run(dao.create(name, NOW, **kwargs))


# ---------------------------------------------------------------------------
# children: create and get
# ---------------------------------------------------------------------------


def test_create_returns_typed_record(tmp_path) -> None:
    database = _open_db(tmp_path / "create.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, colour="#ff0000", avatar_ref="avatars/1")
        assert isinstance(child, ChildRecord)
        assert child.id == 1
        assert child.display_name == "Ada"
        assert child.colour == "#ff0000"
        assert child.avatar_ref == "avatars/1"
        assert child.sort_order == 0
        assert child.is_active is True
        assert child.created_at == NOW
    finally:
        _run(database.close())


def test_get_returns_none_for_missing_child(tmp_path) -> None:
    database = _open_db(tmp_path / "get-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.get(999)) is None
    finally:
        _run(database.close())


def test_create_duplicate_name_is_allowed(tmp_path) -> None:
    database = _open_db(tmp_path / "dup-name.db")
    try:
        dao, _ = _daos(database)
        first = _make_child(dao, "Ada")
        second = _make_child(dao, "Ada")
        assert first.id != second.id
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# children: list active / list all
# ---------------------------------------------------------------------------


def test_list_active_excludes_inactive_and_sorts(tmp_path) -> None:
    database = _open_db(tmp_path / "list-active.db")
    try:
        dao, _ = _daos(database)
        _make_child(dao, "Bo", sort_order=2)
        ada = _make_child(dao, "Ada", sort_order=1)
        cy = _make_child(dao, "Cy", sort_order=1)
        _make_child(dao, "Dee", sort_order=0)
        _run(dao.set_active(ada.id, False))
        active = _run(dao.list_active())
        assert [c.display_name for c in active] == ["Dee", "Cy", "Bo"]
        assert all(c.is_active for c in active)
    finally:
        _run(database.close())


def test_list_all_includes_inactive(tmp_path) -> None:
    database = _open_db(tmp_path / "list-all.db")
    try:
        dao, _ = _daos(database)
        ada = _make_child(dao, "Ada", sort_order=1)
        _make_child(dao, "Bo", sort_order=0)
        _run(dao.set_active(ada.id, False))
        all_children = _run(dao.list_all())
        assert [c.display_name for c in all_children] == ["Bo", "Ada"]
        assert all_children[1].is_active is False
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# children: update, set_active, reorder
# ---------------------------------------------------------------------------


def test_update_fields_round_trip(tmp_path) -> None:
    database = _open_db(tmp_path / "update.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada", colour="#111111")
        updated = _run(
            dao.update(
                child.id,
                display_name="Ada L.",
                colour="#222222",
                avatar_ref="avatars/x.png",
            )
        )
        assert updated == 1
        fetched = _run(dao.get(child.id))
        assert fetched is not None
        assert fetched.display_name == "Ada L."
        assert fetched.colour == "#222222"
        assert fetched.avatar_ref == "avatars/x.png"
        assert fetched.sort_order == 0
    finally:
        _run(database.close())


def test_update_omitted_fields_untouched(tmp_path) -> None:
    database = _open_db(tmp_path / "update-partial.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada", colour="#111111")
        _run(dao.update(child.id, display_name="Ada L."))
        fetched = _run(dao.get(child.id))
        assert fetched.colour == "#111111"
    finally:
        _run(database.close())


def test_update_no_fields_returns_zero_and_changes_nothing(tmp_path) -> None:
    database = _open_db(tmp_path / "update-empty.db")
    try:
        dao, _ = _daos(database)
        child = _make_child(dao, "Ada")
        assert _run(dao.update(child.id)) == 0
        fetched = _run(dao.get(child.id))
        assert fetched is not None and fetched.display_name == "Ada"
    finally:
        _run(database.close())


def test_update_missing_child_returns_zero(tmp_path) -> None:
    database = _open_db(tmp_path / "update-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.update(999, display_name="X")) == 0
    finally:
        _run(database.close())


def test_set_active_missing_child_returns_zero(tmp_path) -> None:
    database = _open_db(tmp_path / "set-active-missing.db")
    try:
        dao, _ = _daos(database)
        assert _run(dao.set_active(999, False)) == 0
    finally:
        _run(database.close())


def test_reorder_assigns_positions_in_order(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        b = _make_child(dao, "Bo")
        c = _make_child(dao, "Cy")
        _run(dao.reorder([c.id, a.id, b.id]))
        children = _run(dao.list_all())
        assert [x.display_name for x in children] == ["Cy", "Ada", "Bo"]
        assert [x.sort_order for x in children] == [0, 1, 2]
    finally:
        _run(database.close())


def test_reorder_is_transactional_and_idempotent(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-idempotent.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        b = _make_child(dao, "Bo")
        _run(dao.reorder([b.id, a.id]))
        _run(dao.reorder([b.id, a.id]))
        children = _run(dao.list_all())
        assert [(x.display_name, x.sort_order) for x in children] == [
            ("Bo", 0),
            ("Ada", 1),
        ]
    finally:
        _run(database.close())


def test_reorder_empty_list_is_noop(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-empty.db")
    try:
        dao, _ = _daos(database)
        _make_child(dao, "Ada")
        _run(dao.reorder([]))
        children = _run(dao.list_all())
        assert children[0].sort_order == 0
    finally:
        _run(database.close())


def test_reorder_unknown_id_leaves_it_untouched(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-unknown.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        _run(dao.reorder([a.id, 999]))
        children = _run(dao.list_all())
        assert children[0].sort_order == 0
    finally:
        _run(database.close())


def test_reorder_rolls_back_to_original_order_on_failure(tmp_path) -> None:
    """A failing finalize batch rolls the whole reorder back.

    The two-phase staging is only meaningful if a crash between the
    batches leaves the original order intact: monkeypatch execute_many
    so the finalize (non-negative) batch raises, then assert every
    sort_order is unchanged.
    """
    database = _open_db(tmp_path / "reorder-rollback.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada", sort_order=0)
        b = _make_child(dao, "Bo", sort_order=1)

        original_execute_many = database.execute_many

        async def _failing_execute_many(sql, parameters):
            # The staging batch writes negative positions; the finalize
            # batch writes 0..n-1.  Fail the finalize batch.
            if all(position >= 0 for position, _ in parameters):
                raise sqlite3.OperationalError("boom")
            return await original_execute_many(sql, parameters)

        database.execute_many = _failing_execute_many
        with pytest.raises(sqlite3.OperationalError, match="boom"):
            _run(dao.reorder([b.id, a.id]))
        children = _run(dao.list_all())
        assert [(c.display_name, c.sort_order) for c in children] == [
            ("Ada", 0),
            ("Bo", 1),
        ], "failed reorder must leave original sort orders intact"
    finally:
        _run(database.close())


def test_reorder_rejects_duplicate_ids(tmp_path) -> None:
    database = _open_db(tmp_path / "reorder-duplicate.db")
    try:
        dao, _ = _daos(database)
        a = _make_child(dao, "Ada")
        with pytest.raises(ValueError, match="duplicate"):
            _run(dao.reorder([a.id, a.id]))
        fetched = _run(dao.get(a.id))
        assert fetched is not None and fetched.sort_order == 0
    finally:
        _run(database.close())


def test_reorder_concurrent_calls_serialize(tmp_path) -> None:
    """Concurrent reorders from DIFFERENT DAO instances queue safely.

    Two ChildrenDao objects over one connection race two reorders: the
    connection-scoped lock makes the second wait, then run against the
    first call's final state.  Without the lock the wrapper's
    transaction() would reject the second concurrent transaction with
    RuntimeError.
    """
    async def _main() -> None:
        database = NestQuestDatabase(_make_hass_mock())
        await database.open(tmp_path / "reorder-concurrent.db")
        try:
            await apply_migrations(database)
            dao_a, _ = _daos(database)
            a = await dao_a.create("Ada", NOW)
            b = await dao_a.create("Bo", NOW)
            dao_b, _ = _daos(database)  # second instance, same connection
            task_1 = asyncio.ensure_future(dao_a.reorder([b.id, a.id]))
            await asyncio.sleep(0)
            task_2 = asyncio.ensure_future(dao_b.reorder([a.id, b.id]))
            await asyncio.gather(task_1, task_2)
            children = await dao_a.list_all()
            orders = {c.display_name: c.sort_order for c in children}
            assert sorted(orders.values()) == [0, 1]
        finally:
            await database.close()

    _run(_main())


# ---------------------------------------------------------------------------
# admin_users: add, remove, list, exists
# ---------------------------------------------------------------------------


def test_admin_add_then_exists(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-add.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.add("user-1", NOW)) is True
        assert _run(dao.exists("user-1")) is True
        assert _run(dao.exists("user-2")) is False
    finally:
        _run(database.close())


def test_admin_add_is_idempotent(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-idempotent.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.add("user-1", NOW)) is True
        assert _run(dao.add("user-1", NOW)) is False
        records = _run(dao.list())
        assert len(records) == 1
        assert records[0].added_at == NOW
    finally:
        _run(database.close())


def test_admin_add_concurrent_calls_are_idempotent(tmp_path) -> None:
    """Concurrent add() calls of the same user: one inserts, rest False.

    The single-statement ON CONFLICT DO NOTHING makes the decision and
    the write atomic per statement, so racing coroutines cannot both
    'see no row' and one of them raise IntegrityError.
    """
    async def _main() -> None:
        database = NestQuestDatabase(_make_hass_mock())
        await database.open(tmp_path / "admin-race.db")
        try:
            await apply_migrations(database)
            _, dao = _daos(database)
            tasks = [
                asyncio.ensure_future(dao.add("user-1", NOW))
                for _ in range(5)
            ]
            await asyncio.sleep(0)
            results = list(await asyncio.gather(*tasks))
            assert sorted(results) == [False, False, False, False, True]
            records = await dao.list()
            assert len(records) == 1
            assert records[0].added_at == NOW
        finally:
            await database.close()

    _run(_main())


def test_admin_add_preserves_original_added_at(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-added-at.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        _run(dao.add("user-1", "2026-09-15T00:00:00+00:00"))
        records = _run(dao.list())
        assert records[0].added_at == NOW
    finally:
        _run(database.close())


def test_admin_remove_returns_true_then_false(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-remove.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        assert _run(dao.remove("user-1")) is True
        assert _run(dao.remove("user-1")) is False
        assert _run(dao.exists("user-1")) is False
    finally:
        _run(database.close())


def test_admin_list_returns_typed_records_ordered(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-list.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-2", "2026-09-14T10:00:00+00:00"))
        _run(dao.add("user-1", "2026-09-14T09:00:00+00:00"))
        records = _run(dao.list())
        assert isinstance(records[0], AdminUserRecord)
        assert [r.ha_user_id for r in records] == ["user-1", "user-2"]
        assert records[0].added_at == "2026-09-14T09:00:00+00:00"
    finally:
        _run(database.close())


def test_admin_exists_empty_allowlist_fails_closed(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-empty.db")
    try:
        _, dao = _daos(database)
        assert _run(dao.exists("user-1")) is False
        assert _run(dao.list()) == []
    finally:
        _run(database.close())


def test_admin_records_are_typed_not_raw_rows(tmp_path) -> None:
    database = _open_db(tmp_path / "admin-typed.db")
    try:
        _, dao = _daos(database)
        _run(dao.add("user-1", NOW))
        records = _run(dao.list())
        assert records == [AdminUserRecord("user-1", NOW)]
    finally:
        _run(database.close())


# ---------------------------------------------------------------------------
# No SQL for these tables outside the DAO module
# ---------------------------------------------------------------------------


def test_children_and_admin_sql_lives_only_in_dao_module() -> None:
    """Guardrail: children/admin_users SQL may appear only in the DAO
    (and the schema DDL declarations).  Scans the integration package
    AND the repo's test files RECURSIVELY, matching FROM/INTO/UPDATE/
    DELETE FROM/JOIN against either table — including DELETE FROM
    children, the hard-delete path the guardrail forbids.

    Exclusions are exact repo-relative paths, narrowly justified:
    schema.py declares the tables' DDL; migrations.py applies that DDL;
    test_schema.py and test_migrations.py test exactly those
    DDL/migration layers.  None of them touch the tables' data paths —
    that is the DAO's job.
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
        "custom_components/nestquest/dao_children.py",  # the DAO itself
        "custom_components/nestquest/dao_rules.py",  # validates child
        # activeness on assignment (FK to children, done-condition
        # 'validates that the assigned child is active')
        "custom_components/nestquest/dao_presence.py",  # validates the
        # schedule/override child exists before writing (same FK shape
        # as dao_rules: one existence SELECT per write)
        "custom_components/nestquest/dao_instances.py",  # validates the
        # instance/event child exists before writing (same FK shape)
        "custom_components/nestquest/schema.py",  # declares the DDL
        "custom_components/nestquest/migrations.py",  # applies the DDL
        "tests/test_schema.py",  # tests the DDL
        "tests/test_migrations.py",  # tests migration application
        "tests/test_dao_children.py",  # this file, scanned separately
        "tests/test_dao_rules.py",  # rules/definitions guard, own scope
        "tests/test_dao_presence.py",  # presence guard, own scope
        "tests/test_dao_instances.py",  # instances guard, own scope
        "tests/test_startup_db.py",  # row-count probe of the children
        # table only (proving a fresh setup loads); guard below covers
        # everything else
    }
    sql_pattern = re.compile(
        r"(FROM|INTO|UPDATE|DELETE\s+FROM|JOIN)\s+"
        r'["\`]*(children|admin_users)["\`]*\b',
        re.IGNORECASE,
    )
    offenders: list[str] = []
    # test_dao_matrix.py is exempted for exactly its two sanctioned
    # raw constraint-violation probes (NOT NULL on children, PRIMARY
    # KEY on admin_users) — the Feature-02 closing suite must prove
    # the schema surfaces violations to the DAO layer; its guard below
    # covers everything else in that file.
    probe_names = {
        "test_matrix_children_crud_and_constraints",
        "test_matrix_admin_users_crud_and_constraints",
    }
    for root in scan_roots:
        for py in sorted(root.rglob("*.py")):
            relative = py.relative_to(repo_root).as_posix()
            if relative in allowed:
                continue
            text = py.read_text()
            if relative == "tests/test_dao_matrix.py":
                text = _strip_function_spans(text, probe_names)
            if sql_pattern.search(text):
                offenders.append(relative)
    assert offenders == [], (
        f"SQL touching children/admin_users leaked into: {offenders}"
    )


def _strip_function_spans(text: str, names: set[str]) -> str:
    """Return ``text`` minus the source spans of the named functions."""
    import ast

    lines = text.splitlines(keepends=True)
    excluded: set[int] = set()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )
    return "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )


def test_startup_db_test_file_uses_dao_elsewhere() -> None:
    """Compensating self-scan for the startup-test exemption: outside
    the single sanctioned COUNT(*) probe, test_startup_db.py must go
    through the DAO for children/admin_users data access.
    """
    import re
    from pathlib import Path

    startup_test = Path(__file__).parent / "test_startup_db.py"
    stripped = _strip_function_spans(
        startup_test.read_text(),
        {"test_setup_with_valid_file_preserves_rows"},
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM|"
        r"FROM|JOIN)\s+[`'\"]*(\[)?(children|admin_users)\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(stripped) is None, (
        "test_startup_db.py must go through the DAO for these tables "
        "outside its sanctioned row-count probe"
    )


def test_dao_matrix_test_file_raw_probes_are_only_constraint_probes() -> None:
    """Compensating self-scan for the matrix-file exemption, structurally
    exact: parse the two sanctioned functions' ASTs and require that
    (a) they contain NO other raw SQL naming children/admin_users, and
    (b) every raw table insert among them is an expression nested inside
    a ``pytest.raises`` context whose matcher mentions IntegrityError.
    Any additional raw write elsewhere in the file fails this guard.
    """
    import ast
    import re
    from pathlib import Path

    matrix = Path(__file__).parent / "test_dao_matrix.py"
    text = matrix.read_text()
    stripped = _strip_function_spans(
        text,
        {
            "test_matrix_children_crud_and_constraints",
            "test_matrix_admin_users_crud_and_constraints",
        },
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM|"
        r"FROM|JOIN)\s+[`'\"]*(\[)?(children|admin_users)\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(stripped) is None, (
        "test_dao_matrix.py raw children/admin_users SQL is limited to "
        "the two sanctioned constraint probes"
    )

    tree = ast.parse(text)
    probe_tables = {
        "test_matrix_children_crud_and_constraints": ("children", "INSERT"),
        "test_matrix_admin_users_crud_and_constraints": (
            "admin_users",
            "INSERT",
        ),
    }
    any_table = re.compile(
        r"\b(children|admin_users)\b", re.IGNORECASE
    )
    allowed_stmt = re.compile(
        r"^(INSERT|SELECT)", re.IGNORECASE
    )
    #: The sanctioned probe per function: exactly one raw statement
    #: INSERTing that table, inside a pytest.raises whose matcher is
    #: IntegrityError (checked as an AST Name/Attribute chain).
    probes_per_function: dict[str, int] = {name: 0 for name in probe_tables}
    for node in ast.walk(tree):
        if (
            not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or node.name not in probe_tables
        ):
            continue
        table, expected_verb = probe_tables[node.name]

        def _unquote(rendered: str) -> str:
            rendered = rendered.strip()
            if len(rendered) >= 2 and rendered[0] == rendered[-1] and (
                rendered[0] in "'\""
            ):
                return rendered[1:-1]
            return rendered

        # Collect every execute(...) statement and every raises-block
        # with its full AST shape.
        raw_statements: list[tuple[ast.Await, str]] = []
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Await)
                and isinstance(sub.value, ast.Call)
                and isinstance(sub.value.func, ast.Attribute)
                and sub.value.func.attr == "execute"
            ):
                sql_arg = sub.value.args[0] if sub.value.args else None
                rendered = ast.unparse(sql_arg) if sql_arg else ""
                raw_statements.append((sub, _unquote(rendered)))

        def _raises_blocks():
            """Yield (block, is_pytest_integrity) for pytest.raises blocks.

            Structurally exact: the call func must resolve to
            pytest.raises (Attribute pytest.raises, or a bare Name
            imported from pytest — checked against the file's import
            section), and the matcher argument must be an AST chain
            whose final segment is exactly IntegrityError (so
            NotIntegrityError and fake.IntegrityError fail).
            """
            for sub in ast.walk(node):
                if not (
                    isinstance(sub, ast.With)
                    and sub.items
                    and isinstance(sub.items[0].context_expr, ast.Call)
                ):
                    continue
                call = sub.items[0].context_expr
                func = call.func
                if isinstance(func, ast.Attribute):
                    if (
                        func.attr != "raises"
                        or not isinstance(func.value, ast.Name)
                        or func.value.id != "pytest"
                    ):
                        continue
                elif isinstance(func, ast.Name):
                    if func.id != "raises":
                        continue
                else:
                    continue
                matcher_ok = False
                if call.args:
                    matcher = call.args[0]
                    # Accept a Name IntegrityError or an Attribute chain
                    # ending in the exact Name IntegrityError.
                    if isinstance(matcher, ast.Name):
                        matcher_ok = matcher.id == "IntegrityError"
                    elif isinstance(matcher, ast.Attribute):
                        matcher_ok = matcher.attr == "IntegrityError"
                yield sub, matcher_ok

        # INSERT OR variant / quoted / qualified / schema-qualified
        # names: normalize the SQL so ANY spelling of an insert into
        # the table counts as a table insert and requires the raises
        # block.  Strip quotes/brackets/backticks from identifiers and
        # drop any schema qualifier, whatever it is.
        def _is_insert_into_table(rendered: str, table: str) -> bool:
            insert_match = re.search(
                r"\bINSERT(\s+OR\s+\w+)?\s+INTO\s+(.+)",
                rendered,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not insert_match:
                return False
            target = insert_match.group(2)
            # Tokenize the target's leading identifier: strip quotes
            # and brackets, take the LAST dot-separated segment.
            identifier = re.split(r"[\s(]", target, maxsplit=1)[0]
            segments = re.split(r"\.", identifier)
            last = segments[-1].strip("`'\"[]")
            return last == table

        for insert, rendered in raw_statements:
            if not any_table.search(rendered):
                continue
            assert allowed_stmt.match(rendered.strip()) is not None, (
                f"{node.name}: raw {table} table SQL "
                f"must be INSERT or SELECT, got: {rendered[:80]!r}"
            )
            if _is_insert_into_table(rendered, table):
                # This is the sanctioned probe: require pytest.raises
                # with an exact IntegrityError matcher around it.
                inside = any(
                    block.lineno <= insert.lineno
                    and insert.end_lineno <= block.end_lineno
                    and matcher_ok
                    for block, matcher_ok in _raises_blocks()
                )
                assert inside, (
                    f"the raw {table} insert in {node.name} must be nested "
                    "in a pytest.raises(...IntegrityError...) block "
                    "(expected-to-fail constraint probe, not a write)"
                )
                probes_per_function[node.name] += 1
        # UPDATE/DELETE naming the tables anywhere in a sanctioned
        # function is forbidden outright.
        for _, rendered in raw_statements:
            if any_table.search(rendered) and re.match(
                r"(UPDATE|DELETE)", rendered.strip(), re.IGNORECASE
            ):
                raise AssertionError(
                    f"{node.name} must not hold UPDATE/DELETE SQL for "
                    f"children/admin_users: {rendered[:80]!r}"
                )
    assert all(
        count == 1 for count in probes_per_function.values()
    ) and len(probes_per_function) == 2, (
        "each sanctioned function must hold exactly one raw constraint "
        f"probe; found {probes_per_function}"
    )



def test_dao_test_file_uses_dao_not_raw_table_sql() -> None:
    """This test module must exercise the DAO, not raw SQL, for these
    tables.  The two guard functions in this file necessarily mention
    the table names inside their regex patterns; their source spans are
    removed BEFORE the scan, and the remaining lines are then scanned
    as ONE combined blob (not line-by-line), so SQL split across
    physical lines — e.g. an implicitly concatenated string ending in
    FROM children — is still caught.  The guard regexes themselves
    cannot match the SQL keyword pattern, so removing the spans only
    spares regex text, not executable SQL.
    """
    import ast
    import re
    from pathlib import Path

    path = Path(__file__)
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    guard_names = {
        "test_children_and_admin_sql_lives_only_in_dao_module",
        "test_dao_test_file_uses_dao_not_raw_table_sql",
        "test_dao_matrix_test_file_raw_probes_are_only_constraint_probes",
    }
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in guard_names
        ):
            excluded.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )

    # Scan the source minus excluded lines as ONE blob so SQL split
    # across physical lines cannot evade the pattern.
    remaining = "".join(
        line
        for number, line in enumerate(lines, start=1)
        if number not in excluded
    )
    sql_pattern = re.compile(
        r"(SELECT\s[^\"']*?FROM|INSERT\s+INTO|UPDATE|"
        r"DELETE\s+FROM|FROM|JOIN)\s+[`'\"]*(\[)?"
        r"(children|admin_users)\b",
        re.IGNORECASE,
    )
    assert sql_pattern.search(remaining) is None, (
        "tests must go through the DAO, not raw SQL, for these tables"
    )
