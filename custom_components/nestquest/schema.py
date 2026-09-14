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
"""
from __future__ import annotations

from .db import NestQuestDatabase

SCHEMA_V1_CHILDREN_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        colour TEXT,
        avatar_ref TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
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

SCHEMA_V1_STATEMENTS: list[str] = [
    *SCHEMA_V1_CHILDREN_DDL,
    *SCHEMA_V1_ADMIN_USERS_DDL,
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