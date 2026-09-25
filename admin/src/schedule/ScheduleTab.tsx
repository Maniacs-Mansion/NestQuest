/**
 * Schedule tab — the presence month grid (design/ADMIN-SPEC.md §4) and the
 * selected child's presence patterns and overrides.
 *
 * The grid shows the COMBINED presence of every pattern (./cycle.ts
 * `dayState`); each pattern's cycle position comes from its own anchor date,
 * never from ISO week numbers or week parity (D-004).
 */
import { useEffect, useRef, useState } from "react";
import { ApiForbiddenError } from "../api/client";
import { ApiRequestError, fetchChildren, type AdminChild } from "../api/definitions";
import {
  deletePresenceOverride,
  deletePresencePattern,
  fetchPresenceOverrides,
  fetchPresencePatterns,
  type PresenceOverride,
  type PresencePattern,
} from "../api/presence";
import {
  cycleLabel,
  dayState,
  localTodayIso,
  monthDates,
  monthStart,
  patternDaysLabel,
  weekdayOf,
  type DayState,
} from "./cycle";
import { dateRange, monthLabel, shortDate } from "./format";
import {
  CalendarCheckGlyph,
  CalendarXGlyph,
  ChevronLeftGlyph,
  ChevronRightGlyph,
  PencilGlyph,
  Trash2Glyph,
} from "./glyphs";
import OverrideEditor from "./OverrideEditor";
import PatternEditor from "./PatternEditor";
import "./ScheduleTab.css";

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

/** Sunday-first header; `weekdayOf` stays Monday=0. */
const WEEKDAY_INITIALS = ["S", "M", "T", "W", "T", "F", "S"];

export const STATE_LABELS: Record<DayState, string> = {
  home: "Home",
  away: "Away",
  "override-away": "Override · away",
  "override-home": "Override · home",
};

interface Loaded {
  children: AdminChild[];
  patterns: Record<number, PresencePattern[]>;
  overrides: PresenceOverride[];
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Loaded };

type DeleteState =
  | { kind: "idle" }
  | { kind: "confirming"; id: number }
  | { kind: "deleting"; id: number }
  | { kind: "error"; id: number; message: string };

type EditorState =
  | { kind: "closed" }
  | { kind: "override" }
  | { kind: "pattern"; pattern: PresencePattern | null };

async function loadSchedule(): Promise<Loaded> {
  const children = (await fetchChildren())
    .filter((child) => child.is_active)
    .sort((a, b) => a.sort_order - b.sort_order);
  const [patterns, overrides] = await Promise.all([
    Promise.all(children.map((child) => fetchPresencePatterns(child.id))),
    fetchPresenceOverrides(),
  ]);
  return {
    children,
    patterns: Object.fromEntries(children.map((child, i) => [child.id, patterns[i]])),
    overrides,
  };
}

function loadErrorMessage(error: unknown): string {
  return error instanceof ApiForbiddenError
    ? error.message
    : "The schedule could not be loaded. Check your connection and try again.";
}

function saveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiForbiddenError) return error.message;
  if (error instanceof ApiRequestError && error.detail) return error.detail;
  return fallback;
}

function ScreenHeader({ sub }: { sub: string }) {
  return (
    <header className="schedule-header">
      <h2 className="schedule-title">Schedule</h2>
      <p className="schedule-sub">{sub}</p>
    </header>
  );
}

interface MonthGridProps {
  month: string;
  today: string;
  /** Every pattern of the child; none means home every day. */
  patterns: PresencePattern[];
  overrides: PresenceOverride[];
  onMonth: (delta: number) => void;
}

function MonthGrid({ month, today, patterns, overrides, onMonth }: MonthGridProps) {
  const dates = monthDates(month);
  const leading = (weekdayOf(month) + 1) % 7;
  return (
    <>
      <div className="schedule-month-head">
        <span className="schedule-month-label" data-testid="month-label">
          {monthLabel(month)}
        </span>
        <div className="schedule-chevrons">
          <button
            type="button"
            className="schedule-chevron"
            aria-label="Previous month"
            onClick={() => onMonth(-1)}
          >
            <ChevronLeftGlyph />
          </button>
          <button
            type="button"
            className="schedule-chevron"
            aria-label="Next month"
            onClick={() => onMonth(1)}
          >
            <ChevronRightGlyph />
          </button>
        </div>
      </div>
      <div className="schedule-grid" role="group" aria-label="Month grid">
        {WEEKDAY_INITIALS.map((initial, i) => (
          <span key={`wd-${i}`} className="schedule-weekday" aria-hidden="true">
            {initial}
          </span>
        ))}
        {Array.from({ length: leading }, (_, i) => (
          <span key={`pad-${i}`} aria-hidden="true" />
        ))}
        {dates.map((date) => {
          const state = dayState(patterns, overrides, date);
          const isToday = date === today;
          let className = `schedule-day schedule-day--${state}`;
          if (isToday) className += " schedule-day--today";
          return (
            <span
              key={date}
              role="img"
              className={className}
              data-date={date}
              data-state={state}
              aria-label={`${shortDate(date)}${isToday ? " (today)" : ""}: ${STATE_LABELS[state]}`}
            >
              {Number(date.slice(8))}
            </span>
          );
        })}
      </div>
      <ul className="schedule-legend" aria-label="Legend">
        {(["home", "away", "override-away", "override-home"] as DayState[]).map((state) => (
          <li key={state} className="schedule-legend-item">
            <span className={`schedule-swatch schedule-day--${state}`} aria-hidden="true" />
            {STATE_LABELS[state]}
          </li>
        ))}
        <li className="schedule-legend-item">
          <span className="schedule-swatch schedule-day--today" aria-hidden="true" />
          Today
        </li>
      </ul>
      <p className="schedule-legend-note">
        Combined from every pattern: away beats home; overrides beat both.
      </p>
    </>
  );
}

interface PatternRowProps {
  pattern: PresencePattern;
  deletion: DeleteState;
  onEdit: () => void;
  onAskDelete: () => void;
  onKeep: () => void;
  onDelete: () => void;
}

function PatternRow({ pattern, deletion, onEdit, onAskDelete, onKeep, onDelete }: PatternRowProps) {
  const mine =
    (deletion.kind === "confirming" || deletion.kind === "deleting") && deletion.id === pattern.id;
  return (
    <li className="schedule-row" data-testid={`pattern-${pattern.id}`}>
      <span className="schedule-row-glyph">
        {pattern.kind === "home" ? <CalendarCheckGlyph /> : <CalendarXGlyph />}
      </span>
      <div className="schedule-row-text">
        <div className="schedule-row-title">{pattern.name}</div>
        <div className="schedule-row-meta">
          {pattern.kind === "home" ? "Home" : "Away"} · {cycleLabel(pattern.cycle_length_weeks)}
        </div>
        <div className="schedule-row-meta" data-testid={`pattern-days-${pattern.id}`}>
          {patternDaysLabel(pattern)}
        </div>
      </div>
      {mine ? (
        <div className="schedule-confirm" role="group" aria-label="Confirm delete">
          <span className="schedule-confirm-text">Delete pattern?</span>
          <button
            type="button"
            className="schedule-confirm-keep"
            onClick={onKeep}
            disabled={deletion.kind === "deleting"}
          >
            Keep
          </button>
          <button
            type="button"
            className="schedule-confirm-delete"
            onClick={onDelete}
            disabled={deletion.kind === "deleting"}
          >
            {deletion.kind === "deleting" ? "Deleting…" : "Delete"}
          </button>
        </div>
      ) : (
        <>
          <button
            type="button"
            className="schedule-icon-action schedule-icon-action--edit"
            aria-label={`Edit ${pattern.name}`}
            onClick={onEdit}
          >
            <PencilGlyph />
          </button>
          <button
            type="button"
            className="schedule-icon-action"
            aria-label={`Delete ${pattern.name}`}
            onClick={onAskDelete}
          >
            <Trash2Glyph />
          </button>
        </>
      )}
    </li>
  );
}

interface OverrideRowProps {
  override: PresenceOverride;
  childName: string;
  deletion: DeleteState;
  onAskDelete: () => void;
  onKeep: () => void;
  onDelete: () => void;
}

function OverrideRow({ override, childName, deletion, onAskDelete, onKeep, onDelete }: OverrideRowProps) {
  const mine =
    (deletion.kind === "confirming" || deletion.kind === "deleting") && deletion.id === override.id;
  return (
    <li className="schedule-row" data-testid={`override-${override.id}`}>
      <span className="schedule-row-glyph">
        {override.is_present ? <CalendarCheckGlyph /> : <CalendarXGlyph />}
      </span>
      <div className="schedule-row-text">
        <div className="schedule-row-title">
          {childName} {override.is_present ? "home" : "away"} ·{" "}
          {dateRange(override.start_date, override.end_date)}
        </div>
        <div className="schedule-row-meta">{override.note || "No reason given"}</div>
      </div>
      {mine ? (
        <div className="schedule-confirm" role="group" aria-label="Confirm delete">
          <span className="schedule-confirm-text">Delete override?</span>
          <button
            type="button"
            className="schedule-confirm-keep"
            onClick={onKeep}
            disabled={deletion.kind === "deleting"}
          >
            Keep
          </button>
          <button
            type="button"
            className="schedule-confirm-delete"
            onClick={onDelete}
            disabled={deletion.kind === "deleting"}
          >
            {deletion.kind === "deleting" ? "Deleting…" : "Delete"}
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="schedule-icon-action"
          aria-label="Delete override"
          onClick={onAskDelete}
        >
          <Trash2Glyph />
        </button>
      )}
    </li>
  );
}

export interface ScheduleTabProps {
  /** "YYYY-MM-DD"; defaults to the viewer's local date. */
  today?: string;
}

export default function ScheduleTab({ today = localTodayIso() }: ScheduleTabProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [month, setMonth] = useState(() => monthStart(today));
  const [editor, setEditor] = useState<EditorState>({ kind: "closed" });
  const [deletion, setDeletion] = useState<DeleteState>({ kind: "idle" });
  const [patternDeletion, setPatternDeletion] = useState<DeleteState>({ kind: "idle" });
  const addRef = useRef<HTMLButtonElement>(null);
  const addPatternRef = useRef<HTMLButtonElement>(null);
  const openedEditor = useRef<EditorState["kind"]>("closed");

  // An editor replaces this screen, so the Add controls are remounted when
  // it closes; hand focus back to the one that belongs to that editor.
  useEffect(() => {
    if (editor.kind === "closed") {
      if (openedEditor.current === "override") addRef.current?.focus();
      if (openedEditor.current === "pattern") addPatternRef.current?.focus();
    }
    openedEditor.current = editor.kind;
  }, [editor.kind]);

  /** Reload children, patterns and overrides in place (no loading flash). */
  const refresh = () =>
    loadSchedule()
      .then((data) => setState({ kind: "ready", data }))
      .catch((error: unknown) => setState({ kind: "error", message: loadErrorMessage(error) }));

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    loadSchedule()
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ready", data });
        setSelectedId((current) => current ?? data.children[0]?.id ?? null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({ kind: "error", message: loadErrorMessage(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (editor.kind !== "closed" && state.kind === "ready" && state.data.children.length > 0) {
    const { children } = state.data;
    const current = children.find((c) => c.id === selectedId) ?? children[0];
    if (editor.kind === "pattern") {
      return (
        <PatternEditor
          child={current}
          pattern={editor.pattern}
          today={today}
          onCancel={() => setEditor({ kind: "closed" })}
          onSaved={() => {
            setEditor({ kind: "closed" });
            void refresh();
          }}
        />
      );
    }
    return (
      <OverrideEditor
        childOptions={children}
        initialChildId={current.id}
        today={today}
        onCancel={() => setEditor({ kind: "closed" })}
        onSaved={(override) => {
          setEditor({ kind: "closed" });
          setSelectedId(override.child_id);
          void refresh();
        }}
      />
    );
  }

  let sub = "";
  let body;
  if (state.kind === "loading") {
    body = (
      <div className="schedule-status" role="status" data-testid="schedule-loading">
        Loading schedule…
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div className="schedule-status schedule-status--error" role="alert" data-testid="schedule-error">
        <p>{state.message}</p>
        <button type="button" className="schedule-retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  } else if (state.data.children.length === 0) {
    body = <div className="schedule-card schedule-empty">No children yet.</div>;
  } else {
    const { data } = state;
    const child = data.children.find((c) => c.id === selectedId) ?? data.children[0];
    const patterns = data.patterns[child.id] ?? [];
    const childOverrides = data.overrides.filter((o) => o.child_id === child.id);
    sub =
      patterns.length === 0
        ? `${child.display_name} · no patterns, home every day`
        : `${child.display_name} · ${patterns.length} ${patterns.length === 1 ? "pattern" : "patterns"}`;

    const confirmDelete = (id: number) => {
      setDeletion({ kind: "deleting", id });
      deletePresenceOverride(id)
        .then(() => refresh())
        .then(() => setDeletion({ kind: "idle" }))
        .catch((error: unknown) =>
          setDeletion({
            kind: "error",
            id,
            message: saveErrorMessage(
              error,
              "The override could not be deleted. Check your connection and try again.",
            ),
          }),
        );
    };
    const confirmPatternDelete = (id: number) => {
      setPatternDeletion({ kind: "deleting", id });
      deletePresencePattern(id)
        .then(() => refresh())
        .then(() => setPatternDeletion({ kind: "idle" }))
        .catch((error: unknown) =>
          setPatternDeletion({
            kind: "error",
            id,
            message: saveErrorMessage(
              error,
              "The pattern could not be deleted. Check your connection and try again.",
            ),
          }),
        );
    };

    body = (
      <>
        <div className="schedule-children" role="group" aria-label="Child">
          {data.children.map((c) => (
            <button
              key={c.id}
              type="button"
              className="schedule-child-chip"
              aria-pressed={c.id === child.id}
              onClick={() => {
                setSelectedId(c.id);
                setPatternDeletion({ kind: "idle" });
              }}
            >
              {c.display_name}
            </button>
          ))}
        </div>

        <section className="schedule-card schedule-month" aria-label="Month grid card">
          <MonthGrid
            month={month}
            today={today}
            patterns={patterns}
            overrides={childOverrides}
            onMonth={(delta) => setMonth((m) => monthStart(m, delta))}
          />
        </section>

        <div className="schedule-section-head">
          <h3 className="schedule-section-label">Presence patterns</h3>
          <button
            ref={addPatternRef}
            type="button"
            className="schedule-text-action"
            aria-label="Add pattern"
            onClick={() => setEditor({ kind: "pattern", pattern: null })}
          >
            Add
          </button>
        </div>
        {patterns.length > 0 ? (
          <ul className="schedule-card schedule-list" aria-label="Presence patterns">
            {patterns.map((pattern) => (
              <PatternRow
                key={pattern.id}
                pattern={pattern}
                deletion={patternDeletion}
                onEdit={() => setEditor({ kind: "pattern", pattern })}
                onAskDelete={() => setPatternDeletion({ kind: "confirming", id: pattern.id })}
                onKeep={() => setPatternDeletion({ kind: "idle" })}
                onDelete={() => confirmPatternDelete(pattern.id)}
              />
            ))}
          </ul>
        ) : (
          <div className="schedule-card schedule-empty" data-testid="patterns-empty">
            No patterns for {child.display_name} — home every day.
          </div>
        )}
        {patternDeletion.kind === "error" ? (
          <p className="schedule-save-status schedule-save-status--error" role="alert">
            {patternDeletion.message}
          </p>
        ) : null}

        <div className="schedule-section-head">
          <h3 className="schedule-section-label">Overrides</h3>
          <button
            ref={addRef}
            type="button"
            className="schedule-text-action"
            onClick={() => setEditor({ kind: "override" })}
          >
            Add
          </button>
        </div>
        {childOverrides.length > 0 ? (
          <ul className="schedule-card schedule-list" aria-label="Overrides">
            {childOverrides.map((override) => (
              <OverrideRow
                key={override.id}
                override={override}
                childName={child.display_name}
                deletion={deletion}
                onAskDelete={() => setDeletion({ kind: "confirming", id: override.id })}
                onKeep={() => setDeletion({ kind: "idle" })}
                onDelete={() => confirmDelete(override.id)}
              />
            ))}
          </ul>
        ) : (
          <div className="schedule-card schedule-empty">No overrides for {child.display_name}.</div>
        )}
        {deletion.kind === "error" ? (
          <p className="schedule-save-status schedule-save-status--error" role="alert">
            {deletion.message}
          </p>
        ) : null}
      </>
    );
  }

  return (
    <div className="schedule-screen">
      <ScreenHeader sub={sub} />
      <div
        className="schedule-scroll"
        data-testid="schedule-scroll"
        style={{ paddingBottom: SCROLL_BOTTOM_PADDING }}
      >
        {body}
      </div>
    </div>
  );
}
