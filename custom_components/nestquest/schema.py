"""Declarative schema DDL for the NestQuest SQLite database.

Every v1 table is declared here as plain SQL statements so later schema
tasks can append their own DDL to :data:`SCHEMA_V1_STATEMENTS` without
touching this module's tables.  All statements use
``CREATE TABLE IF NOT EXISTS`` so application is idempotent; the versioned
migration runner is a separate later concern.

Timestamp policy: all timestamps are UTC ISO-8601 strings, set by the
caller/DAO rather than a DB default, per the feature guardrails.  No
``length(created_at) = 25`` CHECK is added: the exact string shape
produced by callers is not fixed yet (``datetime.isoformat()`` may
include microseconds, changing the length), so enforcing a fixed length
here would reject valid values.  Only non-null is enforced for now.

Date policy: ``start_date``/``end_date`` are ISO date strings (YYYY-MM-DD,
no time component) compared lexically by the ``end_date >= start_date``
CHECK; due_date/due_time string shapes are caller-validated by the rule
engine and DAO layers, not by DDL.

``weekday_set`` format: comma-separated weekday integers (CSV), 0 =
Monday .. 6 = Sunday, e.g. ``'0,2,4'`` for Mon/Wed/Fri.  Chosen over JSON
because it sorts, compares and parses trivially in SQL.  The format is
enforced at the DB level: a CHECK matches ``weekday_set`` against GLOB
patterns for element counts 1..7 of single digits 0-6 (GLOB has no
repetition quantifier, so the element count is enumerated; more than 7
elements is impossible for a weekday set).  ``''``, ``'x'``, ``'7'`` and
``'0,x'`` are all rejected; NULL stays allowed for non-weekly rules.
This keeps the schema layer storage-only — the DAO layer (tasks
8c72300c+) does not need its own validator, it can rely on the CHECK.

Type affinity: SQLite applies column affinity on insert, but CHECKs
still observe text and fractional values ('abc' stays text, '1.5'
becomes REAL), so every INTEGER column carrying rule semantics carries
a ``typeof(...) = 'integer'`` guard in its CHECK.

Rule-type coherence: two CHECKs enforce that ``weekly`` carries a
non-null ``weekday_set``, ``monthly`` carries a ``day_of_month`` or an
``nth_weekday``, ``yearly`` carries a ``month``, and ``daily``/``custom``
carry none of the month-specific fields.  Relaxed deliberately: the DDL
does NOT forbid ``month`` on weekly/monthly rules (an "every 2 weeks"
rule or a monthly rule could later be pinned to a month) nor extra
fields on weekly/monthly/yearly rules generally, so the CHECKs only
reject what the rule engine definitively cannot express now.
"""
from __future__ import annotations

from .db import NestQuestDatabase

#: GLOB patterns matching a valid ``weekday_set`` CSV: one GLOB per
#: possible element count 1..7 (a weekday set cannot exceed 7 elements).
#: Each element is a single digit 0-6, separated by a literal comma.
#: GLOB has no repetition quantifier, so the element count is enumerated.
#: ``''`` and NULL are deliberately NOT matched: NULL is allowed for
#: non-weekly rules via a separate ``IS NULL`` arm, and '' is invalid
#: because weekly rules need at least one weekday.
WEEKDAY_SET_GLOB_PATTERNS: list[str] = [
    "[0-6]",
    "[0-6],[0-6]",
    "[0-6],[0-6],[0-6]",
    "[0-6],[0-6],[0-6],[0-6]",
    "[0-6],[0-6],[0-6],[0-6],[0-6]",
    "[0-6],[0-6],[0-6],[0-6],[0-6],[0-6]",
    "[0-6],[0-6],[0-6],[0-6],[0-6],[0-6],[0-6]",
]

SCHEMA_V1_CHILDREN_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        colour TEXT,
        avatar_ref TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0 CHECK (typeof(sort_order) = 'integer'),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
]

SCHEMA_V1_ADMIN_USERS_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS admin_users (
        ha_user_id TEXT PRIMARY KEY NOT NULL,
        added_at TEXT NOT NULL
    )
    """,
]

_WEEKDAY_SET_CHECK = " OR ".join(
    f"weekday_set GLOB '{pattern}'" for pattern in WEEKDAY_SET_GLOB_PATTERNS
)

SCHEMA_V1_SCHEDULE_RULES_DDL: list[str] = [
    f"""
    CREATE TABLE IF NOT EXISTS schedule_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT NOT NULL CHECK (rule_type IN ('daily', 'weekly', 'monthly', 'yearly', 'custom')),
        interval INTEGER NOT NULL DEFAULT 1 CHECK (typeof(interval) = 'integer' AND interval >= 1),
        weekday_set TEXT CHECK (weekday_set IS NULL OR ({_WEEKDAY_SET_CHECK})),
        day_of_month INTEGER CHECK (day_of_month IS NULL OR (typeof(day_of_month) = 'integer' AND day_of_month >= 1 AND day_of_month <= 31)),
        nth_weekday INTEGER CHECK (nth_weekday IS NULL OR (typeof(nth_weekday) = 'integer' AND nth_weekday IN (-1, 1, 2, 3, 4, 5))),
        month INTEGER CHECK (month IS NULL OR (typeof(month) = 'integer' AND month >= 1 AND month <= 12)),
        start_date TEXT NOT NULL,
        end_date TEXT,
        CHECK (end_date IS NULL OR end_date >= start_date),
        CHECK (
            (rule_type = 'weekly' AND weekday_set IS NOT NULL)
            OR (rule_type = 'monthly' AND (day_of_month IS NOT NULL OR nth_weekday IS NOT NULL))
            OR (rule_type = 'yearly' AND month IS NOT NULL)
            OR (rule_type IN ('daily', 'custom') AND day_of_month IS NULL AND nth_weekday IS NULL AND month IS NULL)
        )
    )
    """,
]

SCHEMA_V1_TASK_DEFINITIONS_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS task_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        icon TEXT,
        child_id INTEGER NOT NULL REFERENCES children(id),
        schedule_rule_id INTEGER NOT NULL REFERENCES schedule_rules(id),
        due_time TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
]

SCHEMA_V1_STATEMENTS: list[str] = [
    *SCHEMA_V1_CHILDREN_DDL,
    *SCHEMA_V1_ADMIN_USERS_DDL,
    *SCHEMA_V1_SCHEDULE_RULES_DDL,
    *SCHEMA_V1_TASK_DEFINITIONS_DDL,
]


async def async_apply_ddl(
    database: NestQuestDatabase, statements: list[str]
) -> None:
    """Apply each DDL statement inside one transaction on ``database``.

    Idempotent: every statement is ``CREATE TABLE IF NOT EXISTS``, so
    applying the same list twice leaves the schema and its rows intact.
    """
    async with database.transaction():
        for sql in statements:
            await database.execute(sql)