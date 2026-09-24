/**
 * Presence pattern editor — a pushed screen like the override editor.
 *
 * Adds a pattern to the child's collection (POST) or edits one in place
 * (PATCH with only the changed fields). The weekday numbering sent to the
 * API stays Monday=0 .. Sunday=6; only the display is Sunday-first.
 */
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { AdminChild } from "../api/definitions";
import {
  createPresencePattern,
  updatePresencePattern,
  type PatternKind,
  type PatternWeeks,
  type PresencePattern,
  type PresencePatternBody,
} from "../api/presence";
import {
  DISPLAY_WEEKDAYS,
  WEEKDAY_SHORT,
  dayNumber,
  emptyPattern,
  isoFromDayNumber,
  resizePattern,
  togglePatternDay,
} from "./cycle";
import { anchorLabel, shortDate } from "./format";
import { ChevronLeftGlyph } from "./glyphs";
import { errorMessage, inertOutside, isIsoDate, trapTab } from "./OverrideEditor";
import "./OverrideEditor.css";

export const CYCLE_LENGTH_CHOICES = [1, 2, 3, 4];

const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** The fields of `next` that differ from the stored pattern. */
export function changedFields(
  stored: PresencePatternBody,
  next: PresencePatternBody,
): Partial<PresencePatternBody> {
  const changes: Partial<PresencePatternBody> = {};
  if (next.name !== stored.name) changes.name = next.name;
  if (next.kind !== stored.kind) changes.kind = next.kind;
  if (next.cycle_length_weeks !== stored.cycle_length_weeks) {
    changes.cycle_length_weeks = next.cycle_length_weeks;
  }
  if (next.anchor_date !== stored.anchor_date) changes.anchor_date = next.anchor_date;
  const samePattern = Array.from({ length: next.cycle_length_weeks }, (_, week) => week).every(
    (week) =>
      JSON.stringify([...(stored.pattern[week] ?? [])].sort()) ===
      JSON.stringify([...(next.pattern[week] ?? [])].sort()),
  );
  if (!samePattern || changes.cycle_length_weeks !== undefined) changes.pattern = next.pattern;
  return changes;
}

export interface PatternEditorProps {
  child: AdminChild;
  /** The pattern being edited, or null to add a new one. */
  pattern: PresencePattern | null;
  /** "YYYY-MM-DD"; a new pattern's anchor starts here. */
  today: string;
  onCancel: () => void;
  onSaved: (pattern: PresencePattern) => void;
}

export default function PatternEditor({ child, pattern, today, onCancel, onSaved }: PatternEditorProps) {
  const [name, setName] = useState(pattern?.name ?? "");
  const [kind, setKind] = useState<PatternKind>(pattern?.kind ?? "away");
  const [cycleLength, setCycleLength] = useState(pattern?.cycle_length_weeks ?? 1);
  const [anchor, setAnchor] = useState(pattern?.anchor_date ?? today);
  const [weeks, setWeeks] = useState<PatternWeeks>(pattern?.pattern ?? emptyPattern(1));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const screenRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

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
    trapTab(event, screenRef.current);
  }

  const body: PresencePatternBody = {
    name: name.trim(),
    kind,
    cycle_length_weeks: cycleLength,
    anchor_date: anchor,
    pattern: resizePattern(weeks, cycleLength),
  };
  const changes = pattern ? changedFields(pattern, body) : body;
  const coversADay = Object.values(body.pattern).some((days) => days.length > 0);
  const canSave =
    body.name !== "" && isIsoDate(anchor) && coversADay && Object.keys(changes).length > 0 && !saving;

  function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    const request = pattern
      ? updatePresencePattern(pattern.id, changes)
      : createPresencePattern(child.id, body);
    request.then(onSaved).catch((err: unknown) => {
      setError(errorMessage(err, "The pattern could not be saved. Check your connection and try again."));
      setSaving(false);
    });
  }

  const title = pattern ? "Edit pattern" : "New pattern";
  return (
    <div
      ref={screenRef}
      className="override-screen"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pattern-title"
      onKeyDown={onKeyDown}
    >
      <header className="override-header">
        <button type="button" className="override-back" aria-label="Back" onClick={onCancel}>
          <ChevronLeftGlyph size={20} />
        </button>
        <div>
          <h2 className="override-title" id="pattern-title" ref={titleRef} tabIndex={-1}>
            {title}
          </h2>
          <p className="override-sub">Repeating presence for {child.display_name}</p>
        </div>
      </header>

      <div className="override-scroll">
        <section className="override-card" aria-label="Pattern details">
          <label className="override-field">
            <span className="override-label">Name</span>
            <input
              className="override-input"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <div className="override-field">
            <span className="override-label" id="pattern-label-kind">
              Covered days are
            </span>
            <div className="override-segments override-segments--2" role="group" aria-labelledby="pattern-label-kind">
              {(["away", "home"] as PatternKind[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  className="override-segment override-segment--ink"
                  aria-pressed={kind === value}
                  onClick={() => setKind(value)}
                >
                  {value === "away" ? "Away" : "Home"}
                </button>
              ))}
            </div>
          </div>

          <div className="override-dates">
            <label className="override-field">
              <span className="override-label">Cycle length</span>
              <select
                className="override-input"
                value={cycleLength}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setCycleLength(next);
                  setWeeks((current) => resizePattern(current, next));
                }}
              >
                {CYCLE_LENGTH_CHOICES.map((count) => (
                  <option key={count} value={count}>
                    {count} {count === 1 ? "week" : "weeks"}
                  </option>
                ))}
              </select>
            </label>
            <label className="override-field">
              <span className="override-label">Anchor date</span>
              <input
                className="override-input override-date"
                type="date"
                value={anchor}
                onChange={(event) => setAnchor(event.target.value)}
              />
            </label>
          </div>

          {Array.from({ length: cycleLength }, (_, week) => {
            const days = body.pattern[week];
            const from = isIsoDate(anchor)
              ? shortDate(isoFromDayNumber(dayNumber(anchor) + week * 7))
              : null;
            return (
              <div key={week} className="override-field">
                <span className="override-label" id={`pattern-label-week-${week}`}>
                  Week {week + 1}
                  {from ? ` · from ${from}` : ""}
                </span>
                <div
                  className="override-segments override-segments--7"
                  role="group"
                  aria-labelledby={`pattern-label-week-${week}`}
                >
                  {DISPLAY_WEEKDAYS.map((weekday) => (
                    <button
                      key={weekday}
                      type="button"
                      className="override-segment override-segment--ink"
                      aria-pressed={days.includes(weekday)}
                      aria-label={WEEKDAY_NAMES[weekday]}
                      onClick={() => setWeeks((current) => togglePatternDay(current, week, weekday))}
                    >
                      {WEEKDAY_SHORT[weekday].slice(0, 2)}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          <p className="override-sub">
            {isIsoDate(anchor)
              ? `Week 1 starts ${anchorLabel(anchor)}; the cycle repeats from there.`
              : "Choose an anchor date."}
          </p>
        </section>

        {error ? (
          <p className="override-error" role="alert" data-testid="pattern-error">
            {error}
          </p>
        ) : null}

        <div className="override-footer">
          <button type="button" className="override-cancel" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="override-save" onClick={save} disabled={!canSave}>
            {saving ? "Saving…" : "Save pattern"}
          </button>
        </div>
      </div>
    </div>
  );
}
