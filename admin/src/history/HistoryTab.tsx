/**
 * History tab — the append-only event log (design/ADMIN-SPEC.md §5).
 *
 * Rows are read-only: events are never edited or deleted, and a reversal is
 * its own row (D-005).
 */
import { useEffect, useState } from "react";
import { ApiForbiddenError } from "../api/client";
import { fetchHistory, type HistoryFilter, type HistoryRow } from "../api/history";
import { localTodayIso } from "../schedule/cycle";
import { dayLabel, groupByDay, rowMeta, rowTime, shiftIso } from "./format";
import { DownloadGlyph, LockGlyph } from "./glyphs";
import "./HistoryTab.css";

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

export const RANGE_DAYS = 14;

export const FOOTER_NOTE = "Events are never edited or deleted. A reversal is its own row.";

export const FILTERS: { id: HistoryFilter; label: string }[] = [
  { id: "all", label: "All events" },
  { id: "reversals", label: "Reversals" },
  { id: "missed", label: "Missed" },
];

export interface HistoryStats {
  /** Whole percent, or null when the period has no completions. */
  onTimePct: number | null;
  completed: number;
  missed: number;
}

/** Per-period stats from the `all` rows (completions) and the `missed` rows. */
export function computeStats(allRows: HistoryRow[], missedRows: HistoryRow[]): HistoryStats {
  const completions = allRows.filter((row) => row.event_type === "completed");
  const onTime = completions.filter((row) => row.was_on_time === true).length;
  return {
    onTimePct: completions.length > 0 ? Math.round((onTime / completions.length) * 100) : null,
    completed: completions.length,
    missed: missedRows.filter((row) => row.event_type === "missed").length,
  };
}

interface Loaded {
  rows: HistoryRow[];
  stats: HistoryStats;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Loaded };

/**
 * The selected filter's rows plus the period stats. Stats always come from
 * the `all` and `missed` queries, whichever chip is selected, so switching
 * chips never changes the period's numbers.
 */
async function loadHistory(filter: HistoryFilter, start: string, end: string): Promise<Loaded> {
  const [selected, all, missed] = await Promise.all([
    fetchHistory(filter, start, end),
    filter === "all" ? null : fetchHistory("all", start, end),
    filter === "missed" ? null : fetchHistory("missed", start, end),
  ]);
  return {
    rows: selected.rows,
    stats: computeStats((all ?? selected).rows, (missed ?? selected).rows),
  };
}

function ScreenHeader() {
  return (
    <header className="history-header">
      <div>
        <h2 className="history-title">History</h2>
        <p className="history-sub">Append-only event log · last {RANGE_DAYS} days</p>
      </div>
      {/* TODO(e5133d0f): export the filtered range as CSV; inert until then. */}
      <button type="button" className="history-csv" data-testid="history-csv">
        <DownloadGlyph />
        CSV
      </button>
    </header>
  );
}

function StatRow({ stats }: { stats: HistoryStats }) {
  const items = [
    { key: "on-time", label: "On time", value: stats.onTimePct === null ? "—" : `${stats.onTimePct}%` },
    { key: "completed", label: "Completed", value: String(stats.completed) },
    { key: "missed", label: "Missed", value: String(stats.missed) },
  ];
  return (
    <div className="history-stats">
      {items.map((item) => (
        <div key={item.key} className="history-stat" data-testid={`stat-${item.key}`}>
          <div className={`history-stat-value history-stat-value--${item.key}`}>{item.value}</div>
          <div className="history-stat-label">{item.label}</div>
        </div>
      ))}
    </div>
  );
}

function EventRow({ row }: { row: HistoryRow }) {
  return (
    <li className="history-event" data-testid="history-row">
      <span
        className={`history-dot history-dot--${row.event_type}`}
        data-testid="history-dot"
        aria-hidden="true"
      />
      <div className="history-event-text">
        <div className="history-event-title">
          {row.quest_title} · {row.child_name}
        </div>
        <div className="history-event-meta" data-testid="history-meta">
          {rowMeta(row)}
        </div>
      </div>
      <span className="history-event-time">{rowTime(row)}</span>
    </li>
  );
}

function FooterNote() {
  return (
    <div className="history-note" data-testid="history-footer">
      <span className="history-note-glyph">
        <LockGlyph />
      </span>
      <span>{FOOTER_NOTE}</span>
    </div>
  );
}

export default function HistoryTab({ today = localTodayIso() }: { today?: string }) {
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const start = shiftIso(today, -(RANGE_DAYS - 1));

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    loadHistory(filter, start, today)
      .then((data) => {
        if (!cancelled) setState({ kind: "ready", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiForbiddenError
            ? error.message
            : "The history could not be loaded. Check your connection and try again.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [filter, start, today, attempt]);

  let body;
  if (state.kind === "loading") {
    body = (
      <div className="history-status" role="status" data-testid="history-loading">
        Loading history…
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div className="history-status history-status--error" role="alert" data-testid="history-error">
        <p>{state.message}</p>
        <button type="button" className="history-retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  } else {
    const groups = groupByDay(state.data.rows);
    body =
      groups.length > 0 ? (
        groups.map((group) => (
          <section key={group.day} className="history-day" data-testid={`day-${group.day}`}>
            <h3 className="history-section-label">{dayLabel(group.day, today)}</h3>
            <ul className="history-card history-list">
              {group.rows.map((row, index) => (
                <EventRow key={`${row.instance_id}-${row.event_type}-${row.occurred_at ?? ""}-${index}`} row={row} />
              ))}
            </ul>
          </section>
        ))
      ) : (
        <div className="history-card history-empty">No events in the last {RANGE_DAYS} days.</div>
      );
  }

  return (
    <div className="history-screen">
      <ScreenHeader />
      <div
        className="history-scroll"
        data-testid="history-scroll"
        style={{ paddingBottom: SCROLL_BOTTOM_PADDING }}
      >
        {state.kind === "ready" ? <StatRow stats={state.data.stats} /> : null}
        <div className="history-chips" role="group" aria-label="Filter events">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === filter ? "history-chip history-chip--active" : "history-chip"}
              aria-pressed={item.id === filter}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        {body}
        <FooterNote />
      </div>
    </div>
  );
}
