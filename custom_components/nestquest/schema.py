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

Presence pattern format: ``presence_schedules.pattern`` encodes the
whole N-week repeating cycle in one TEXT column as pipe-separated
segments, one per week of the cycle: segment ``i`` is a ``weekday_set``
CSV (same single-digit 0-6 convention as ``schedule_rules.weekday_set``)
for week ``i``, e.g. ``'0,2,4|1,3'`` = Mon/Wed/Fri in week 0, Tue/Thu in
week 1.  An empty segment means the child is absent every day of that
week; a wholly empty pattern with ``cycle_length_weeks = 1`` means
absent every day of every week, which is distinct from having no
schedule row at all (a child with no schedule is present every day, per
the feature guardrails).  Chosen over JSON or per-week rows to stay
consistent with the CSV ``weekday_set`` convention and fully checkable
by plain CHECKs.  DB-level validation is pure CHECK, no triggers or
custom functions: char-class GLOBs reject every character outside
digits 0-6, comma and pipe; adjacency GLOBs reject empty elements
(double comma, comma next to a pipe, leading/trailing comma) and
two-digit runs; a further GLOB rejects contiguous runs of 8+ comma
separated digits, which caps a segment at 7 elements — the GLOB cannot
match across a ``|``, so cross-segment boundaries stay safe; and the
segment count is pinned to ``cycle_length_weeks`` by
``LENGTH(pattern) - LENGTH(REPLACE(pattern, '|', '')) + 1``.  Per
weekday_set this is not full CSV-set normalisation (duplicates like
``'0,0'`` or unsorted sets stay storable, as with ``schedule_rules``);
the engine treats the segment as a set.  A
one-row-per-``week_index`` normalization was considered and rejected:
the flat single-column encoding keeps the done-condition's table shape
and proved fully checkable with plain CHECKs.

``cycle_length_weeks`` is capped at 4: 2 (alternating weeks) is the
common case, and a small cap keeps anchor arithmetic and the encoded
pattern human-readable.  Revisit the cap — and re-run the pattern
validation matrix in tests — if a longer cycle is ever needed.
``anchor_date`` is an ISO date string pinning the cycle: the week index
of a date is (days since anchor) // 7 mod ``cycle_length_weeks``,
computed by the presence engine (Feature 05) from anchor-date
arithmetic, never ISO week parity.  Like other date columns it carries
no shape CHECK, matching the established date policy.

Presence overrides: ``presence_overrides.end_date`` is NOT NULL,
unlike ``schedule_rules.end_date`` — an override is always a concrete
date range; a single-day override stores the same date in both columns.
``is_present`` 0/1 marks the child absent/present for the whole range;
``note`` is optional free text.

Multi-assignee definitions (D-008): ``quest_definitions`` carries no
``child_id`` column.  Assignment lives in
``quest_definition_assignees``, one row per (definition, child) with a
composite primary key and foreign keys to the definition and the child,
so "brush teeth" is one definition covering three children.  The
migration runner rebuilds a pre-D-008 table into this shape and copies
its single-assignee column across.  The composite primary key makes
duplicate assignment impossible at the storage layer.

Quest windows (D-008): ``quest_definition_windows`` declares which day
windows a definition spans — one row per (definition, window), the
composite primary key making a window idempotent per definition.
``window`` is CHECK-constrained to the three spellings ``const`` owns;
``due_time`` optionally pins a due time inside the window and is
caller-validated (strict HH:MM) by the DAO layer, matching the date
policy above.  The window clock ranges live in ``const.py``, not here:
this layer stores what the caller declares and never interprets clocks.

Quest instances: ``quest_instances`` deliberately carries NO completion
status column.  An instance's current state derives from the latest row
in ``completion_events`` (Feature 08), so materialization (Feature 07)
can insert instances without knowing anything about completion and the
append-only log stays the single source of truth.  ``definition_id``,
``child_id``, ``due_date`` and ``window`` snapshot the
materialization-time facts ("why this instance exists"): assignment
edits and rule edits change future instances only and never rewrite
these rows.  ``window`` records which declared day window produced the
instance (D-008), CHECK-constrained to the same three spellings
``const`` owns.  ``due_time`` snapshots the window's optional due time
at generation for the same reason — the instance keeps its
generation-time value even if the definition is edited later.
``generated_at`` is a caller-set UTC ISO-8601 timestamp per the module
timestamp policy (no DB default, so a generation batch stamps one
coherent time).

Uniqueness: the (definition_id, child_id, due_date, window) tuple is
declared as a table-level ``UNIQUE`` constraint rather than a separate
``CREATE UNIQUE INDEX`` statement.  SQLite materializes it as an
implicit unique index (``sqlite_autoindex_quest_instances_1``) — the
required "unique index prevents duplicate instances" — and the
constraint form cannot be silently dropped the way a standalone index
can, so the duplicate door stays shut.  Idempotent materialization keys
on exactly this tuple: the twice-daily case (one definition, two
windows, one child, one date) yields two rows and the shared case (one
definition, three assignees, one window) yields three.  No secondary
indexes beyond it are declared yet: history and board queries (Features
08/10/13) should justify their indexes as a later migration once their
query shapes exist.

No ``ON DELETE`` clauses are declared on any foreign key in this
module: children and definitions are deactivated, never deleted, so a
deletion that would orphan instances or events is a bug and must fail
loudly rather than cascade.

Completion events: ``completion_events`` is strictly append-only.  That
property is enforced at the DAO layer — the completion-events DAO
exposes no UPDATE or DELETE path (task a9ea75fc) — and deliberately NOT
by database triggers, matching the module's no-trigger policy: a RAISE
trigger would be the one exception to "pure CHECK, no triggers",
complicate the later migration runner, and still prove nothing (any
writer can run raw SQL).  ``event_type`` is constrained to
``completed``/``uncompleted``; a ``missed`` row is intentionally not
representable — missed is a derived state announced on the HA event bus
(Feature 10), never an appended event.

``child_id`` is deliberately denormalized (it is also derivable via
``quest_instances``): history reporting (Feature 13) filters and rates
per child directly against the log, and the log should stay
self-describing without joins.

Actor policy: ``actor_source`` distinguishes an authenticated HA user
(``'user'``, with ``actor_user_id`` holding the HA user id) from a
panel tap with no user context (``'panel'``, with ``actor_user_id``
NULL — the tapped child profile is ``actor_child_id``, D-008).  Two
coherence CHECKs make both shapes non-negotiable: ``'user'`` requires
``actor_user_id`` and forbids ``actor_child_id``; ``'panel'`` requires
``actor_child_id`` (the tapped profile) and forbids ``actor_user_id``.
Other actor sources are rejected; if an unattended system actor is
ever needed, that is a schema migration, not a silent widening.

On-time policy: ``was_on_time`` is required (integer 0 or 1) for
``completed`` events — at completion time the due date is known and the
flag is decidable.  For ``uncompleted`` events the flag is optional:
Feature 08 decides whether a reversal carries the reversed completion's
on-time flag or NULL, and the DDL deliberately accepts both rather than
guessing.
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

#: Column body of ``quest_definitions``, shared between the v1 DDL
#: below and the multi-assignee rebuild migration, which must recreate
#: the table in exactly this shape (D-008: one definition, many
#: assignees via ``quest_definition_assignees`` — no ``child_id``
#: column on the definition itself).
QUEST_DEFINITIONS_TABLE_SQL = """(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    schedule_rule_id INTEGER NOT NULL REFERENCES schedule_rules(id),
    due_time TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0, 1)),
    created_at TEXT NOT NULL
)"""

SCHEMA_V1_QUEST_DEFINITIONS_DDL: list[str] = [
    f"""
    CREATE TABLE IF NOT EXISTS quest_definitions {QUEST_DEFINITIONS_TABLE_SQL}
    """,
]

SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS quest_definition_assignees (
        definition_id INTEGER NOT NULL REFERENCES quest_definitions(id),
        child_id INTEGER NOT NULL REFERENCES children(id),
        PRIMARY KEY (definition_id, child_id)
    )
    """,
]

SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS quest_definition_windows (
        definition_id INTEGER NOT NULL REFERENCES quest_definitions(id),
        window TEXT NOT NULL CHECK (window IN ('morning', 'afternoon', 'evening')),
        due_time TEXT,
        PRIMARY KEY (definition_id, window)
    )
    """,
]

SCHEMA_V1_PRESENCE_SCHEDULES_DDL: list[str] = [
    f"""
    CREATE TABLE IF NOT EXISTS presence_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER NOT NULL UNIQUE REFERENCES children(id),
        cycle_length_weeks INTEGER NOT NULL CHECK (typeof(cycle_length_weeks) = 'integer' AND cycle_length_weeks >= 1 AND cycle_length_weeks <= 4),
        anchor_date TEXT NOT NULL,
        pattern TEXT NOT NULL CHECK (
            NOT pattern GLOB '*[^0-6,|]*'
            AND NOT pattern GLOB '*[0-6][0-6]*'
            AND NOT pattern GLOB '*,,*'
            AND NOT pattern GLOB '*,|*'
            AND NOT pattern GLOB '*|,*'
            AND NOT pattern GLOB ',*'
            AND NOT pattern GLOB '*,'
            AND NOT pattern GLOB '*[0-6],[0-6],[0-6],[0-6],[0-6],[0-6],[0-6],[0-6]*'
            AND (LENGTH(pattern) - LENGTH(REPLACE(pattern, '|', '')) + 1) = cycle_length_weeks
        )
    )
    """,
]

SCHEMA_V1_PRESENCE_OVERRIDES_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS presence_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER NOT NULL REFERENCES children(id),
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        is_present INTEGER NOT NULL CHECK (typeof(is_present) = 'integer' AND is_present IN (0, 1)),
        note TEXT,
        CHECK (end_date >= start_date)
    )
    """,
]

#: Column body of ``quest_instances``, shared between the v1 DDL
#: below and the instance-key rebuild migration, which must recreate
#: the table in exactly this shape (D-008: the instance key is
#: (definition_id, child_id, due_date, window) — one instance per
#: assigned child per declared window per firing date).
QUEST_INSTANCES_TABLE_SQL = """(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    definition_id INTEGER NOT NULL REFERENCES quest_definitions(id),
    child_id INTEGER NOT NULL REFERENCES children(id),
    window TEXT NOT NULL CHECK (window IN ('morning', 'afternoon', 'evening')),
    due_date TEXT NOT NULL,
    due_time TEXT,
    generated_at TEXT NOT NULL,
    UNIQUE (definition_id, child_id, due_date, window)
)"""

SCHEMA_V1_QUEST_INSTANCES_DDL: list[str] = [
    f"""
    CREATE TABLE IF NOT EXISTS quest_instances {QUEST_INSTANCES_TABLE_SQL}
    """,
]

#: Column body of ``completion_events``, shared between the v1 DDL
#: below and the actor-child rebuild migration, which must recreate the
#: table in exactly this shape (D-008: ``actor_child_id`` records which
#: panel profile was tapped — set for panel events, NULL for admin
#: ones; legacy panel rows backfill to ``child_id``, the child they
#: always were).
COMPLETION_EVENTS_TABLE_SQL = """(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id INTEGER NOT NULL REFERENCES quest_instances(id),
    child_id INTEGER NOT NULL REFERENCES children(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('completed', 'uncompleted')),
    actor_source TEXT NOT NULL CHECK (actor_source IN ('user', 'panel')),
    actor_user_id TEXT,
    actor_child_id INTEGER REFERENCES children(id),
    occurred_at TEXT NOT NULL,
    was_on_time INTEGER CHECK (
        was_on_time IS NULL
        OR (typeof(was_on_time) = 'integer' AND was_on_time IN (0, 1))
    ),
    CHECK (
        (actor_source = 'user' AND actor_user_id IS NOT NULL)
        OR (actor_source = 'panel' AND actor_user_id IS NULL)
    ),
    CHECK (
        (actor_source = 'user' AND actor_child_id IS NULL)
        OR (actor_source = 'panel' AND actor_child_id IS NOT NULL)
    ),
    CHECK (
        (event_type = 'completed' AND was_on_time IS NOT NULL)
        OR (event_type = 'uncompleted')
    )
)"""

SCHEMA_V1_COMPLETION_EVENTS_DDL: list[str] = [
    f"""
    CREATE TABLE IF NOT EXISTS completion_events {COMPLETION_EVENTS_TABLE_SQL}
    """,
]

SCHEMA_V1_STATEMENTS: list[str] = [
    *SCHEMA_V1_CHILDREN_DDL,
    *SCHEMA_V1_ADMIN_USERS_DDL,
    *SCHEMA_V1_SCHEDULE_RULES_DDL,
    *SCHEMA_V1_QUEST_DEFINITIONS_DDL,
    *SCHEMA_V1_QUEST_DEFINITION_ASSIGNEES_DDL,
    *SCHEMA_V1_QUEST_DEFINITION_WINDOWS_DDL,
    *SCHEMA_V1_PRESENCE_SCHEDULES_DDL,
    *SCHEMA_V1_PRESENCE_OVERRIDES_DDL,
    *SCHEMA_V1_QUEST_INSTANCES_DDL,
    *SCHEMA_V1_COMPLETION_EVENTS_DDL,
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