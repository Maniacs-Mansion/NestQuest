/**
 * Schedule tab — the presence month grid (design/ADMIN-SPEC.md §4).
 *
 * Every day's cycle position comes from the anchor date (./cycle.ts), never
 * from ISO week numbers or week parity (D-004).
 */
import { useEffect, useRef, useState } from "react";
import { ApiForbiddenError } from "../api/client";
import { ApiRequestError, fetchChildren, type AdminChild } from "../api/definitions";
import {
  deletePresenceOverride,
  fetchPresenceOverrides,
  fetchPresenceSchedule,
  savePresenceSchedule,
  type PresenceOverride,
  type PresenceSchedule,
  type PresenceScheduleBody,
} from "../api/presence";
import {
  cycleWeekIndex,
  dayState,
  fullPattern,
  localTodayIso,
  monthDates,
  monthStart,
  patternIncludes,
  presenceRule,
  resizePattern,
  togglePatternDay,
  weekdayOf,
  type DayState,
} from "./cycle";
import { anchorLabel, dateRange, monthLabel, shortDate } from "./format";
import {
  CalendarCheckGlyph,
  CalendarXGlyph,
  ChevronLeftGlyph,
  ChevronRightGlyph,
  Trash2Glyph,
} from "./glyphs";
import OverrideEditor from "./OverrideEditor";
import "./ScheduleTab.css";

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

export const DEFAULT_CYCLE_LENGTH_WEEKS = 2;
const CYCLE_LENGTH_CHOICES = [1, 2, 3, 4];
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
  schedules: Record<number, PresenceSchedule | null>;
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

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

async function loadSchedule(): Promise<Loaded> {
  const children = (await fetchChildren())
    .filter((child) => child.is_active)
    .sort((a, b) => a.sort_order - b.sort_order);
  const [schedules, overrides] = await Promise.all([
    Promise.all(children.map((child) => fetchPresenceSchedule(child.id))),
    fetchPresenceOverrides(),
  ]);
  return {
    children,
    schedules: Object.fromEntries(children.map((child, i) => [child.id, schedules[i]])),
    overrides,
  };
}

function loadErrorMessage(error: unknown): string {
  return error instanceof ApiForbiddenError
    ? error.message
    : "The schedule could not be loaded. Check your connection and try again.";
}

function saveErrorMessage(
  error: unknown,
  fallback = "The pattern could not be saved. Check your connection and try again.",
): string {
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
  schedule: PresenceScheduleBody;
  /** Null when the child has no saved schedule and no edits: home every day. */
  effective: PresenceScheduleBody | null;
  overrides: PresenceOverride[];
  onMonth: (delta: number) => void;
  onToggle: (date: string) => void;
}

function MonthGrid({ month, today, schedule, effective, overrides, onMonth, onToggle }: MonthGridProps) {
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
          const state = dayState(effective, overrides, date);
          const isToday = date === today;
          let className = `schedule-day schedule-day--${state}`;
          if (isToday) className += " schedule-day--today";
          return (
            <button
              key={date}
              type="button"
              className={className}
              data-date={date}
              data-state={state}
              aria-pressed={patternIncludes(schedule, date)}
              aria-label={`${shortDate(date)}${isToday ? " (today)" : ""}: ${STATE_LABELS[state]}`}
              onClick={() => onToggle(date)}
            >
              {Number(date.slice(8))}
            </button>
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
    </>
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
  const [drafts, setDrafts] = useState<Record<number, PresenceScheduleBody>>({});
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [editorOpen, setEditorOpen] = useState(false);
  const [deletion, setDeletion] = useState<DeleteState>({ kind: "idle" });
  const addRef = useRef<HTMLButtonElement>(null);
  const editorWasOpen = useRef(false);

  // The editor replaces this screen, so Add is remounted when it closes;
  // hand focus back to it then.
  useEffect(() => {
    if (editorWasOpen.current && !editorOpen) addRef.current?.focus();
    editorWasOpen.current = editorOpen;
  }, [editorOpen]);

  /** Reload children, schedules and overrides in place (no loading flash). */
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

  if (editorOpen && state.kind === "ready" && state.data.children.length > 0) {
    const { children } = state.data;
    return (
      <OverrideEditor
        childOptions={children}
        initialChildId={children.find((c) => c.id === selectedId)?.id ?? children[0].id}
        today={today}
        onCancel={() => setEditorOpen(false)}
        onSaved={(override) => {
          setEditorOpen(false);
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
    const saved = data.schedules[child.id] ?? null;
    const draft = drafts[child.id];
    // Edits start from the saved schedule, or — with none — from "home every
    // day" on a 2-week cycle anchored at the displayed month's 1st.
    const schedule: PresenceScheduleBody = draft ??
      saved ?? {
        cycle_length_weeks: DEFAULT_CYCLE_LENGTH_WEEKS,
        anchor_date: month,
        pattern: fullPattern(DEFAULT_CYCLE_LENGTH_WEEKS),
      };
    const effective = draft ?? saved;
    const childOverrides = data.overrides.filter((o) => o.child_id === child.id);
    sub = `${schedule.cycle_length_weeks}-week cycle · anchor ${anchorLabel(schedule.anchor_date)}`;

    const edit = (next: PresenceScheduleBody) => {
      setDrafts((all) => ({ ...all, [child.id]: next }));
      setSave({ kind: "idle" });
    };
    const toggle = (date: string) => {
      const week = cycleWeekIndex(schedule.anchor_date, date, schedule.cycle_length_weeks);
      edit({ ...schedule, pattern: togglePatternDay(schedule.pattern, week, weekdayOf(date)) });
    };
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
    const submit = () => {
      if (!draft) return;
      const childId = child.id;
      setSave({ kind: "saving" });
      const { cycle_length_weeks, anchor_date, pattern } = draft;
      savePresenceSchedule(childId, { cycle_length_weeks, anchor_date, pattern })
        .then((stored) => {
          setState((current) =>
            current.kind === "ready"
              ? {
                  kind: "ready",
                  data: {
                    ...current.data,
                    schedules: { ...current.data.schedules, [childId]: stored },
                  },
                }
              : current,
          );
          setDrafts((all) => {
            const rest = { ...all };
            delete rest[childId];
            return rest;
          });
          setSave({ kind: "saved" });
        })
        .catch((error: unknown) => setSave({ kind: "error", message: saveErrorMessage(error) }));
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
                setSave({ kind: "idle" });
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
            schedule={schedule}
            effective={effective}
            overrides={childOverrides}
            onMonth={(delta) => setMonth((m) => monthStart(m, delta))}
            onToggle={toggle}
          />
          <div className="schedule-controls">
            <label className="schedule-field">
              <span>Anchor date</span>
              <input
                type="date"
                value={schedule.anchor_date}
                onChange={(event) => {
                  if (event.target.value) edit({ ...schedule, anchor_date: event.target.value });
                }}
              />
            </label>
            <label className="schedule-field">
              <span>Cycle length</span>
              <select
                value={schedule.cycle_length_weeks}
                onChange={(event) => {
                  const weeks = Number(event.target.value);
                  edit({
                    ...schedule,
                    cycle_length_weeks: weeks,
                    pattern: resizePattern(schedule.pattern, weeks),
                  });
                }}
              >
                {CYCLE_LENGTH_CHOICES.map((weeks) => (
                  <option key={weeks} value={weeks}>
                    {weeks} {weeks === 1 ? "week" : "weeks"}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="schedule-save"
              disabled={!draft || save.kind === "saving"}
              onClick={submit}
            >
              {save.kind === "saving" ? "Saving…" : "Save pattern"}
            </button>
          </div>
          {save.kind === "error" ? (
            <p className="schedule-save-status schedule-save-status--error" role="alert">
              {save.message}
            </p>
          ) : save.kind === "saved" ? (
            <p className="schedule-save-status" role="status">
              Pattern saved.
            </p>
          ) : null}
        </section>

        <h3 className="schedule-section-label">Presence pattern</h3>
        <ul className="schedule-card schedule-list" aria-label="Presence pattern">
          {data.children.map((c) => (
            <li key={c.id} className="schedule-row" data-testid={`pattern-${c.id}`}>
              <div className="schedule-row-text">
                <div className="schedule-row-title">{c.display_name}</div>
              </div>
              <span className="schedule-rule">{presenceRule(data.schedules[c.id] ?? null)}</span>
            </li>
          ))}
        </ul>

        <div className="schedule-section-head">
          <h3 className="schedule-section-label">Overrides</h3>
          <button
            ref={addRef}
            type="button"
            className="schedule-text-action"
            onClick={() => setEditorOpen(true)}
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
