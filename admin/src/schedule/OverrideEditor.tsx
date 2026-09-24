/**
 * Presence override editor — the pushed screen of design/ADMIN-SPEC.md §6.
 *
 * The consequence warning is counted by the API (POST
 * /presence-overrides/consequence) before anything is saved; Save stays off
 * until that count is on screen. Saving only ever sends the create request:
 * the API never removes an instance that already has a completion event (D-005).
 */
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { ApiForbiddenError } from "../api/client";
import { ApiRequestError, type AdminChild } from "../api/definitions";
import {
  createPresenceOverride,
  previewOverrideConsequence,
  type PresenceOverride,
  type PresenceOverrideBody,
} from "../api/presence";
import { dayNumber, isoFromDayNumber } from "./cycle";
import { dateRange } from "./format";
import { AlertCircleGlyph, ChevronLeftGlyph } from "./glyphs";
import "./OverrideEditor.css";

/** How long the form must sit still before the consequence is recounted. */
export const CONSEQUENCE_DEBOUNCE_MS = 300;

/** Strict "YYYY-MM-DD" naming a real calendar day (no 2026-02-30). */
export function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return isoFromDayNumber(dayNumber(value)) === value;
}

export function isValidRange(start: string, end: string): boolean {
  return isIsoDate(start) && isIsoDate(end) && start <= end;
}

type Consequence =
  | { kind: "invalid" }
  | { kind: "counting" }
  | { kind: "ready"; removed: number }
  | { kind: "error"; message: string };

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiForbiddenError) return error.message;
  if (error instanceof ApiRequestError && error.detail) return error.detail;
  return fallback;
}

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * Make everything outside `root` inert (siblings of each ancestor up to
 * <body>), so the tab bar behind the pushed screen cannot take focus.
 * Returns the undo.
 */
function inertOutside(root: HTMLElement): () => void {
  const made: HTMLElement[] = [];
  for (let node: HTMLElement = root; node.parentElement && node !== document.body; node = node.parentElement) {
    for (const sibling of Array.from(node.parentElement.children)) {
      if (sibling === node || !(sibling instanceof HTMLElement) || sibling.hasAttribute("inert")) continue;
      sibling.setAttribute("inert", "");
      sibling.setAttribute("aria-hidden", "true");
      made.push(sibling);
    }
  }
  return () => {
    for (const el of made) {
      el.removeAttribute("inert");
      el.removeAttribute("aria-hidden");
    }
  };
}

function tasksPhrase(count: number): string {
  return `${count} upcoming ${count === 1 ? "task" : "tasks"}`;
}

export interface OverrideEditorProps {
  /** Active children, in display order. */
  childOptions: AdminChild[];
  initialChildId: number;
  /** "YYYY-MM-DD"; the date fields start here. */
  today: string;
  onCancel: () => void;
  onSaved: (override: PresenceOverride) => void;
}

export default function OverrideEditor({
  childOptions,
  initialChildId,
  today,
  onCancel,
  onSaved,
}: OverrideEditorProps) {
  const [childId, setChildId] = useState(initialChildId);
  const [isPresent, setIsPresent] = useState(false);
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [note, setNote] = useState("");
  const [consequence, setConsequence] = useState<Consequence>({ kind: "counting" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Every form change bumps the sequence; only the latest request may render.
  const requestSeq = useRef(0);
  const screenRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  // Modal focus: move in on open and keep the background out of reach. The
  // opener hands focus back to its Add control once this screen closes.
  useEffect(() => {
    titleRef.current?.focus();
    return screenRef.current ? inertOutside(screenRef.current) : undefined;
  }, []);

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!saving) onCancel();
      return;
    }
    if (event.key !== "Tab" || !screenRef.current) return;
    const focusable = Array.from(screenRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const current = document.activeElement;
    const outside = !focusable.includes(current as HTMLElement);
    if (event.shiftKey && (current === first || outside)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (current === last || outside)) {
      event.preventDefault();
      first.focus();
    }
  }

  const child = childOptions.find((c) => c.id === childId) ?? childOptions[0];
  const rangeValid = isValidRange(startDate, endDate);

  useEffect(() => {
    const seq = ++requestSeq.current;
    if (!rangeValid) {
      setConsequence({ kind: "invalid" });
      return;
    }
    if (isPresent) {
      // Keeping a child home removes nothing by definition.
      setConsequence({ kind: "ready", removed: 0 });
      return;
    }
    setConsequence({ kind: "counting" });
    const timer = setTimeout(() => {
      previewOverrideConsequence({
        child_id: childId,
        start_date: startDate,
        end_date: endDate,
        is_present: false,
      })
        .then((removed) => {
          if (seq === requestSeq.current) setConsequence({ kind: "ready", removed });
        })
        .catch((err: unknown) => {
          if (seq !== requestSeq.current) return;
          setConsequence({
            kind: "error",
            message: errorMessage(err, "The upcoming tasks could not be counted. Try again."),
          });
        });
    }, CONSEQUENCE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [childId, startDate, endDate, isPresent, rangeValid]);

  const canSave = rangeValid && consequence.kind === "ready" && !saving;

  function save() {
    if (!canSave) return;
    const body: PresenceOverrideBody = {
      child_id: childId,
      start_date: startDate,
      end_date: endDate,
      is_present: isPresent,
    };
    const reason = note.trim();
    if (reason) body.note = reason;
    setSaving(true);
    setError(null);
    createPresenceOverride(body)
      .then(onSaved)
      .catch((err: unknown) => {
        setError(errorMessage(err, "The override could not be saved. Check your connection and try again."));
        setSaving(false);
      });
  }

  let headline: string;
  let detail: string;
  const range = rangeValid ? dateRange(startDate, endDate) : "";
  if (consequence.kind === "invalid") {
    headline = "Choose a valid date range";
    detail = "Through must be on or after From.";
  } else if (consequence.kind === "counting") {
    headline = "Counting upcoming tasks…";
    detail = `${child.display_name} away ${range}. Completed days are untouched.`;
  } else if (consequence.kind === "error") {
    headline = "Upcoming tasks not counted";
    detail = consequence.message;
  } else {
    headline = `This removes ${tasksPhrase(consequence.removed)}`;
    detail = isPresent
      ? `${child.display_name} is home ${range}, so no tasks are removed. Completed days are untouched.`
      : `${child.display_name}'s open tasks ${range} are removed while away. Completed days are untouched.`;
  }

  return (
    <div
      ref={screenRef}
      className="override-screen"
      role="dialog"
      aria-modal="true"
      aria-labelledby="override-title"
      onKeyDown={onKeyDown}
    >
      <header className="override-header">
        <button type="button" className="override-back" aria-label="Back" onClick={onCancel}>
          <ChevronLeftGlyph size={20} />
        </button>
        <div>
          <h2 className="override-title" id="override-title" ref={titleRef} tabIndex={-1}>
            Presence override
          </h2>
          <p className="override-sub">Beats the custody pattern for these dates</p>
        </div>
      </header>

      <div className="override-scroll">
        <section className="override-card" aria-label="Override details">
          <div className="override-field">
            <span className="override-label" id="override-label-child">
              Child
            </span>
            <div className="override-segments override-segments--3" role="group" aria-labelledby="override-label-child">
              {childOptions.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="override-segment override-segment--gradient"
                  aria-pressed={c.id === childId}
                  onClick={() => setChildId(c.id)}
                >
                  {c.display_name}
                </button>
              ))}
            </div>
          </div>

          <div className="override-field">
            <span className="override-label" id="override-label-status">
              Status for these dates
            </span>
            <div className="override-segments override-segments--2" role="group" aria-labelledby="override-label-status">
              <button
                type="button"
                className="override-segment override-segment--ink"
                aria-pressed={!isPresent}
                onClick={() => setIsPresent(false)}
              >
                Away
              </button>
              <button
                type="button"
                className="override-segment override-segment--ink"
                aria-pressed={isPresent}
                onClick={() => setIsPresent(true)}
              >
                Home
              </button>
            </div>
          </div>

          <div className="override-dates">
            <label className="override-field">
              <span className="override-label">From</span>
              <input
                className="override-input override-date"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label className="override-field">
              <span className="override-label">Through</span>
              <input
                className="override-input override-date"
                type="date"
                value={endDate}
                min={isIsoDate(startDate) ? startDate : undefined}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
          </div>

          <label className="override-field">
            <span className="override-label">Reason (optional)</span>
            <input
              className="override-input"
              type="text"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
        </section>

        <section
          className="override-warning"
          aria-label="Consequence"
          aria-live="polite"
          data-testid="override-consequence"
          data-state={consequence.kind}
        >
          <span className="override-warning-glyph">
            <AlertCircleGlyph />
          </span>
          <div>
            <p className="override-warning-headline" data-testid="override-consequence-headline">
              {headline}
            </p>
            <p className="override-warning-body">{detail}</p>
          </div>
        </section>

        {error ? (
          <p className="override-error" role="alert" data-testid="override-error">
            {error}
          </p>
        ) : null}

        <div className="override-footer">
          <button type="button" className="override-cancel" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="override-save" onClick={save} disabled={!canSave}>
            {saving ? "Saving…" : "Save override"}
          </button>
        </div>
      </div>
    </div>
  );
}
