/**
 * Today tab — compact density (design/ADMIN-SPEC.md §2.1–2.3, §2.5–2.6).
 */
import { useEffect, useState } from "react";
import {
  fetchSnapshot,
  type AdminSnapshot,
  type SnapshotChild,
  type SnapshotInstance,
} from "../api/snapshot";
import { ApiForbiddenError } from "../api/client";
import {
  formatClockTime,
  formatDueTime,
  formatLongDate,
  formatShortDate,
} from "./format";
import {
  AlertCircleGlyph,
  CheckCircleGlyph,
  InfoGlyph,
  SettingsGlyph,
} from "./glyphs";
import "./TodayTab.css";

const CYCLE_LENGTH_DAYS = 14;

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

export const PERMISSION_NOTE =
  "Undo is admin-only. A panel tap can never reverse a completion.";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; snapshot: AdminSnapshot };

function isOverdueOpen(instance: SnapshotInstance): boolean {
  return instance.overdue && instance.state === "open";
}

function ScreenHeader({ sub }: { sub: string }) {
  return (
    <header className="today-header">
      <div>
        <h2 className="today-title">Today</h2>
        <p className="today-sub">{sub}</p>
      </div>
      {/* Settings screen is a later task; the control is not wired yet. */}
      <button type="button" className="today-icon-button" aria-label="Settings">
        <SettingsGlyph />
      </button>
    </header>
  );
}

function StatRow({ snapshot }: { snapshot: AdminSnapshot }) {
  const done = snapshot.children.reduce((sum, c) => sum + c.completed_today, 0);
  const remaining = snapshot.children.reduce((sum, c) => sum + c.remaining_today, 0);
  const overdue = snapshot.children.reduce(
    (sum, c) => sum + c.instances.filter(isOverdueOpen).length,
    0,
  );
  const stats = [
    { key: "done", label: "Done", value: done },
    { key: "remaining", label: "Remaining", value: remaining },
    { key: "overdue", label: "Overdue", value: overdue },
  ];
  return (
    <div className="today-stats">
      {stats.map((stat) => (
        <div key={stat.key} className="today-stat" data-testid={`stat-${stat.key}`}>
          <div className={`today-stat-value today-stat-value--${stat.key}`}>
            {stat.value}
          </div>
          <div className="today-stat-label">{stat.label}</div>
        </div>
      ))}
    </div>
  );
}

function ChildRow({ child }: { child: SnapshotChild }) {
  const overdue = child.instances.filter(isOverdueOpen).length;
  const allDone = child.due_today > 0 && child.completed_today === child.due_today;
  let meta: string;
  let metaClass = "today-child-meta";
  if (!child.present) {
    meta = child.next_present
      ? `Away · returns ${formatShortDate(child.next_present)}`
      : "Away";
  } else if (allDone) {
    meta = `${child.completed_today} of ${child.due_today} · all done`;
    metaClass += " today-child-meta--done";
  } else {
    meta = `${child.completed_today} of ${child.due_today} · ${overdue} overdue`;
  }
  const pct = Math.max(0, Math.min(100, child.completion_pct));
  // ADMIN-SPEC §2.3 also asks for a lowercase `override` pill when an absence
  // comes from a presence override. The snapshot carries no field saying
  // where an absence came from, so the pill is omitted rather than guessed.
  return (
    <li
      className={child.present ? "today-child" : "today-child today-child--away"}
      data-testid={`child-${child.child_id}`}
    >
      <span className="today-avatar" data-testid="child-avatar" aria-hidden="true">
        {child.child_name.charAt(0).toUpperCase()}
      </span>
      <div className="today-child-text">
        <div className="today-child-name">{child.child_name}</div>
        <div className={metaClass}>{meta}</div>
      </div>
      <div
        className="today-progress"
        role="progressbar"
        aria-label={`${child.child_name} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className="today-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}

interface AttentionItem {
  instance: SnapshotInstance;
  childName: string;
}

function attentionItems(snapshot: AdminSnapshot): AttentionItem[] {
  const all = snapshot.children.flatMap((child) =>
    child.instances.map((instance) => ({ instance, childName: child.child_name })),
  );
  const overdue = all.filter((item) => isOverdueOpen(item.instance));
  const completed = all
    .filter((item) => item.instance.state === "completed" && item.instance.completed_at)
    .sort((a, b) =>
      (b.instance.completed_at ?? "").localeCompare(a.instance.completed_at ?? ""),
    );
  return [...overdue, ...completed];
}

function AttentionRow({ item }: { item: AttentionItem }) {
  const { instance, childName } = item;
  const overdue = isOverdueOpen(instance);
  // TODO(e57facc2): wire "Mark done" / "Undo" mutations and live updates.
  // The admin plane has no complete route yet, so both actions are inert here.
  return (
    <li className="today-event" data-testid={`attention-${instance.id}`}>
      <span
        className={overdue ? "today-event-glyph today-event-glyph--overdue" : "today-event-glyph"}
      >
        {overdue ? <AlertCircleGlyph /> : <CheckCircleGlyph />}
      </span>
      <div className="today-event-text">
        <div className="today-event-title">
          {instance.title} · {childName}
        </div>
        {overdue ? (
          <div className="today-event-meta today-event-meta--overdue">
            {instance.due_time
              ? `Overdue since ${formatDueTime(instance.due_time)}`
              : "Overdue"}
          </div>
        ) : (
          // The snapshot carries no completion actor, so "from panel" is not printed.
          <div className="today-event-meta">
            Completed {formatClockTime(instance.completed_at as string)}
          </div>
        )}
      </div>
      <button
        type="button"
        className={overdue ? "today-action today-action--done" : "today-action today-action--undo"}
      >
        {overdue ? "Mark done" : "Undo"}
      </button>
    </li>
  );
}

function PermissionNote() {
  return (
    <div className="today-note" data-testid="permission-note">
      <span className="today-note-glyph">
        <InfoGlyph />
      </span>
      <span>{PERMISSION_NOTE}</span>
    </div>
  );
}

export default function TodayTab() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchSnapshot()
      .then((snapshot) => {
        if (!cancelled) setState({ kind: "ready", snapshot });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiForbiddenError
            ? error.message
            : "Today's snapshot could not be loaded. Check your connection and try again.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  let sub = "";
  let body;
  if (state.kind === "loading") {
    body = (
      <div className="today-status" role="status" data-testid="today-loading">
        Loading today…
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div className="today-status today-status--error" role="alert" data-testid="today-error">
        <p>{state.message}</p>
        <button type="button" className="today-retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  } else {
    const { snapshot } = state;
    sub = `${formatLongDate(snapshot.today_iso)} · cycle day ${snapshot.cycle_day} of ${CYCLE_LENGTH_DAYS}`;
    const attention = attentionItems(snapshot);
    body = (
      <>
        <StatRow snapshot={snapshot} />
        <ul className="today-card today-list" aria-label="Children">
          {snapshot.children.map((child) => (
            <ChildRow key={child.child_id} child={child} />
          ))}
        </ul>
        <h3 className="today-section-label">Needs attention</h3>
        {attention.length > 0 ? (
          <ul className="today-card today-list" aria-label="Needs attention">
            {attention.map((item) => (
              <AttentionRow key={item.instance.id} item={item} />
            ))}
          </ul>
        ) : (
          <div className="today-card today-empty">Nothing needs attention.</div>
        )}
        <PermissionNote />
      </>
    );
  }

  return (
    <div className="today-screen">
      <ScreenHeader sub={sub} />
      <div
        className="today-scroll"
        data-testid="today-scroll"
        style={{ paddingBottom: SCROLL_BOTTOM_PADDING }}
      >
        {body}
      </div>
    </div>
  );
}
