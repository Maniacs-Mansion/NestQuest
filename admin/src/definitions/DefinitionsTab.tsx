/**
 * Definitions ("Tasks") tab — list + edit sheet with icon picker
 * (design/ADMIN-SPEC.md §3.1–3.3).
 */
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { ApiForbiddenError } from "../api/client";
import {
  ApiRequestError,
  createDefinition,
  fetchChildren,
  fetchDefinitions,
  previewOccurrences,
  updateDefinition,
  type AdminChild,
  type DefinitionCreateBody,
  type DefinitionEditBody,
  type DefinitionRule,
  type QuestDefinition,
  type WindowEntry,
  type WindowName,
} from "../api/definitions";
import {
  MONTH_SHORT,
  WEEKDAY_DISPLAY_ORDER,
  WEEKDAY_SHORT,
  WINDOW_LABELS,
  WINDOW_ORDER,
  assigneeSummary,
  occurrenceLabel,
  recurrenceSummary,
  windowSummary,
} from "./format";
import {
  CheckGlyph,
  ChevronDownGlyph,
  ChevronRightGlyph,
  PlusGlyph,
  TaskGlyph,
} from "./glyphs";
import { DEFINITION_ICONS, DefinitionIcon } from "./definitionIcons";
import "./DefinitionsTab.css";

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

type Repeats = "daily" | "weekly" | "monthly" | "yearly" | "custom";

const REPEATS_OPTIONS: { value: Repeats; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "yearly", label: "Yearly" },
  { value: "custom", label: "Custom" },
];

const REPEATS_BY_RULE: Record<DefinitionRule["rule_type"], Repeats> = {
  daily: "daily",
  weekly: "weekly",
  monthly_day: "monthly",
  monthly_weekday: "monthly",
  yearly: "yearly",
  custom_days: "custom",
};

/** How many upcoming dates the edit sheet previews. */
const PREVIEW_COUNT = 5;

/** Quiet period after the last rule edit before the preview is requested. */
const PREVIEW_DEBOUNCE_MS = 300;

const WEEKDAY_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface Draft {
  title: string;
  /** A Lucide name; a legacy value outside the subset is kept until replaced. */
  icon: string | null;
  assigneeIds: number[];
  repeats: Repeats;
  interval: string;
  weekdays: number[];
  dayOfMonth: string;
  month: string;
  /** An existing "nth weekday" monthly rule, kept while Repeats stays Monthly. */
  monthlyWeekday: { nth: number; weekday: number } | null;
  windows: WindowName[];
  dueTimes: Record<WindowName, string>;
  skipOnAway: boolean;
  startDate: string;
  endDate: string | null;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; definitions: QuestDefinition[]; children: AdminChild[] };

/** `null` = closed, `"new"` = creating, a definition = editing it. */
type SheetTarget = null | "new" | QuestDefinition;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function localIsoDate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function emptyDueTimes(): Record<WindowName, string> {
  return { morning: "", afternoon: "", evening: "" };
}

function newDraft(activeChildren: AdminChild[]): Draft {
  const today = new Date();
  return {
    title: "",
    icon: null,
    assigneeIds: activeChildren.length === 1 ? [activeChildren[0].id] : [],
    repeats: "daily",
    interval: "1",
    weekdays: [(today.getDay() + 6) % 7],
    dayOfMonth: String(today.getDate()),
    month: String(today.getMonth() + 1),
    monthlyWeekday: null,
    windows: [],
    dueTimes: emptyDueTimes(),
    // Mirrors the API's create default: no instance on an away day.
    skipOnAway: true,
    startDate: localIsoDate(today),
    endDate: null,
  };
}

function draftFrom(definition: QuestDefinition, activeChildren: AdminChild[]): Draft {
  const { rule } = definition;
  const today = new Date();
  const active = new Set(activeChildren.map((child) => child.id));
  const dueTimes = emptyDueTimes();
  for (const w of definition.windows) dueTimes[w.window] = w.due_time ?? "";
  return {
    title: definition.title,
    icon: definition.icon,
    // Inactive children cannot be submitted (the API rejects them with 422).
    assigneeIds: definition.assignees.map((a) => a.id).filter((id) => active.has(id)),
    repeats: REPEATS_BY_RULE[rule.rule_type],
    interval: String(rule.interval),
    weekdays:
      rule.rule_type === "weekly" || rule.rule_type === "custom_days"
        ? [...(rule.weekday_set ?? [])]
        : [(today.getDay() + 6) % 7],
    dayOfMonth: String(rule.day_of_month ?? today.getDate()),
    month: String(rule.month ?? today.getMonth() + 1),
    monthlyWeekday:
      rule.rule_type === "monthly_weekday"
        ? { nth: rule.nth_weekday ?? 1, weekday: rule.nth_weekday_weekday ?? 0 }
        : null,
    windows: WINDOW_ORDER.filter((w) => definition.windows.some((d) => d.window === w)),
    dueTimes,
    skipOnAway: definition.skip_on_away,
    startDate: rule.start_date,
    endDate: rule.end_date,
  };
}

function parseWhole(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

/** Build the request rule from the draft, or return a message naming what to fix. */
function buildRule(draft: Draft): DefinitionRule | string {
  const interval = parseWhole(draft.interval, 1, 999);
  if (interval === null) return "Interval must be a whole number of at least 1.";
  const rule: DefinitionRule = {
    rule_type: "daily",
    interval,
    weekday_set: null,
    day_of_month: null,
    nth_weekday: null,
    nth_weekday_weekday: null,
    month: null,
    start_date: draft.startDate,
    end_date: draft.endDate,
  };
  switch (draft.repeats) {
    case "daily":
      return rule;
    case "weekly":
    case "custom":
      if (draft.weekdays.length === 0) return "Pick at least one day.";
      return {
        ...rule,
        rule_type: draft.repeats === "weekly" ? "weekly" : "custom_days",
        weekday_set: [...draft.weekdays].sort((a, b) => a - b),
      };
    case "monthly": {
      if (draft.monthlyWeekday) {
        return {
          ...rule,
          rule_type: "monthly_weekday",
          nth_weekday: draft.monthlyWeekday.nth,
          nth_weekday_weekday: draft.monthlyWeekday.weekday,
        };
      }
      const day = parseWhole(draft.dayOfMonth, 1, 31);
      if (day === null) return "Day of month must be 1 to 31.";
      return { ...rule, rule_type: "monthly_day", day_of_month: day };
    }
    case "yearly": {
      const month = parseWhole(draft.month, 1, 12);
      const day = parseWhole(draft.dayOfMonth, 1, 31);
      if (month === null || day === null) return "Pick a month and a day (1 to 31).";
      return { ...rule, rule_type: "yearly", month, day_of_month: day };
    }
  }
}

/**
 * `keepsAssignees`: an edit whose active selection is unchanged sends no
 * assignee list, so an empty selection is fine when inactive children remain.
 */
function buildBody(draft: Draft, keepsAssignees = false): DefinitionCreateBody | string {
  const title = draft.title.trim();
  if (!title) return "Give the task a title.";
  if (draft.assigneeIds.length === 0 && !keepsAssignees) return "Assign at least one child.";
  if (draft.windows.length === 0) return "Pick at least one window.";
  const rule = buildRule(draft);
  if (typeof rule === "string") return rule;
  const windows: WindowEntry[] = WINDOW_ORDER.filter((w) => draft.windows.includes(w)).map(
    (w) => [w, draft.dueTimes[w] || null],
  );
  return {
    title,
    icon: draft.icon,
    rule,
    assignee_child_ids: [...draft.assigneeIds],
    windows,
    skip_on_away: draft.skipOnAway,
  };
}

function saveErrorMessage(error: unknown): string {
  if (error instanceof ApiForbiddenError) return error.message;
  if (error instanceof ApiRequestError && error.detail) return error.detail;
  return "The task could not be saved. Check your connection and try again.";
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function sameIds(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/* ── List ───────────────────────────────────────────────────────────── */

function FilterChips({
  options,
  filter,
  onChange,
}: {
  options: AdminChild[];
  filter: number | "all";
  onChange: (filter: number | "all") => void;
}) {
  const chips: { key: number | "all"; label: string }[] = [
    { key: "all", label: "All" },
    ...options.map((child) => ({ key: child.id, label: child.display_name })),
  ];
  return (
    <div className="defs-chips" role="group" aria-label="Filter by child">
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          className={chip.key === filter ? "defs-chip defs-chip--active" : "defs-chip"}
          aria-pressed={chip.key === filter}
          onClick={() => onChange(chip.key)}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}

function DefinitionRow({
  definition,
  activeChildren,
  editing,
  onOpen,
}: {
  definition: QuestDefinition;
  activeChildren: AdminChild[];
  editing: boolean;
  onOpen: () => void;
}) {
  let meta = [
    assigneeSummary(definition.assignees, activeChildren),
    recurrenceSummary(definition.rule),
    windowSummary(definition.windows),
  ].join(" · ");
  if (!definition.is_active) meta += " · inactive";
  let className = "defs-row";
  if (!definition.is_active) className += " defs-row--inactive";
  if (editing) className += " defs-row--editing";
  return (
    <li>
      <button
        type="button"
        className={className}
        data-testid={`definition-${definition.id}`}
        aria-expanded={editing}
        onClick={onOpen}
      >
        <span className="defs-row-glyph">
          <DefinitionIcon name={definition.icon} />
        </span>
        <span className="defs-row-text">
          <span className="defs-row-title">{definition.title}</span>
          <span className="defs-row-meta">{editing ? "Editing" : meta}</span>
        </span>
        <span className="defs-row-chevron">
          {editing ? <ChevronDownGlyph /> : <ChevronRightGlyph />}
        </span>
      </button>
    </li>
  );
}

/* ── Edit sheet ─────────────────────────────────────────────────────── */

type PreviewState =
  | { kind: "idle" }
  | { kind: "ready"; ruleKey: string; dates: string[] }
  | { kind: "error"; ruleKey: string; message: string };

/**
 * The next few dates the backend would materialize for the draft's rule.
 * `ruleKey` is the built rule serialized (null while the draft is invalid), so
 * the request only goes out when the rule itself changes — debounced, and a
 * superseded request's late response is dropped by its effect's cleanup.
 * A result is tagged with the rule it answers and only shown while that rule
 * is still the draft's, so a changed rule never shows the previous dates.
 */
function OccurrencePreview({ ruleKey }: { ruleKey: string | null }) {
  const [preview, setPreview] = useState<PreviewState>({ kind: "idle" });

  useEffect(() => {
    if (ruleKey === null) {
      setPreview({ kind: "idle" });
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      previewOccurrences(JSON.parse(ruleKey) as DefinitionRule, { count: PREVIEW_COUNT })
        .then((dates) => {
          if (!cancelled) setPreview({ kind: "ready", ruleKey, dates });
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          const detail =
            error instanceof ApiForbiddenError ||
            (error instanceof ApiRequestError && error.detail)
              ? `: ${error.message}`
              : ".";
          setPreview({
            kind: "error",
            ruleKey,
            message: `Upcoming dates unavailable${detail}`,
          });
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [ruleKey]);

  if (preview.kind === "idle" || preview.ruleKey !== ruleKey) return null;
  if (preview.kind === "error") {
    return (
      <p className="defs-hint defs-preview defs-preview--error" data-testid="occurrence-preview">
        {preview.message}
      </p>
    );
  }
  let text: string;
  if (preview.dates.length === 0) {
    text = "No upcoming dates in the next year.";
  } else {
    const labels = preview.dates.map(occurrenceLabel);
    // A full page means the rule keeps going past the last shown date.
    if (preview.dates.length >= PREVIEW_COUNT) labels.push("…");
    text = `Next: ${labels.join(" · ")}`;
  }
  return (
    <p className="defs-hint defs-preview" data-testid="occurrence-preview" aria-live="polite">
      {text}
    </p>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="defs-field" role="group" aria-labelledby={id}>
      <span className="defs-label" id={id}>
        {label}
      </span>
      {children}
    </div>
  );
}

function EditSheet({
  target,
  activeChildren,
  onCancel,
  onSaved,
}: {
  target: "new" | QuestDefinition;
  activeChildren: AdminChild[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() =>
    target === "new" ? newDraft(activeChildren) : draftFrom(target, activeChildren),
  );
  // The active selection as loaded: while it is unchanged, the PATCH omits
  // assignee_child_ids, because the API replaces the whole set and inactive
  // children cannot be sent back.
  const [originalActiveIds] = useState(() => draft.assigneeIds);
  const inactiveAssignees =
    target === "new"
      ? []
      : target.assignees.filter((a) => !activeChildren.some((child) => child.id === a.id));
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A ref, not state: two taps in one frame must not both see `saving === false`.
  const inFlight = useRef(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const confirmRef = useRef<HTMLDivElement>(null);

  // Modal focus: move in on open, hand back to the trigger on close.
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    titleRef.current?.focus();
    return () => {
      if (trigger && trigger.isConnected) trigger.focus();
    };
  }, []);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!inFlight.current) onCancel();
      return;
    }
    if (event.key !== "Tab" || !sheetRef.current) return;
    const focusable = Array.from(sheetRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
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

  const update = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const selectedAssignees = activeChildren
    .filter((child) => draft.assigneeIds.includes(child.id))
    .map((child) => ({ id: child.id, display_name: child.display_name }));
  const orderedWindows = WINDOW_ORDER.filter((w) => draft.windows.includes(w));
  const previewRule = buildRule(draft);
  const previewKey = typeof previewRule === "string" ? null : JSON.stringify(previewRule);

  async function save(confirmed = false) {
    if (inFlight.current) return;
    const keepsAssignees = target !== "new" && sameIds(draft.assigneeIds, originalActiveIds);
    const body = buildBody(draft, keepsAssignees);
    if (typeof body === "string") {
      setError(body);
      setConfirming(false);
      return;
    }
    if (target !== "new" && !keepsAssignees && inactiveAssignees.length > 0 && !confirmed) {
      setError(null);
      setConfirming(true);
      return;
    }
    setConfirming(false);
    inFlight.current = true;
    setSaving(true);
    setError(null);
    try {
      if (target === "new") {
        await createDefinition(body);
      } else {
        const edit: DefinitionEditBody = { ...body };
        if (keepsAssignees) delete edit.assignee_child_ids;
        await updateDefinition(target.id, edit);
      }
      onSaved();
    } catch (err) {
      setError(saveErrorMessage(err));
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <div className="defs-sheet-layer">
      <div
        className="defs-scrim"
        data-testid="sheet-scrim"
        onClick={() => {
          if (!inFlight.current) onCancel();
        }}
      />
      <div
        ref={sheetRef}
        className="defs-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="defs-sheet-title"
        onKeyDown={onKeyDown}
      >
        <div className="defs-grabber" aria-hidden="true" />
        <h3 className="defs-sheet-title" id="defs-sheet-title" ref={titleRef} tabIndex={-1}>
          {target === "new" ? "New task" : "Edit task"}
        </h3>
        <div className="defs-fields">
          <Field label="Title" id="defs-label-title">
            <input
              className="defs-input"
              aria-labelledby="defs-label-title"
              value={draft.title}
              onChange={(e) => update({ title: e.target.value })}
            />
          </Field>

          <Field label="Icon" id="defs-label-icon">
            <div className="defs-icon-grid" role="radiogroup" aria-labelledby="defs-label-icon">
              <button
                type="button"
                role="radio"
                aria-checked={draft.icon === null}
                aria-label="No icon"
                className={draft.icon === null ? "defs-icon defs-icon--on" : "defs-icon"}
                onClick={() => update({ icon: null })}
              >
                <TaskGlyph size={18} />
              </button>
              {DEFINITION_ICONS.map(({ name, label, Icon }) => (
                <button
                  key={name}
                  type="button"
                  role="radio"
                  aria-checked={draft.icon === name}
                  aria-label={label}
                  data-icon-option={name}
                  className={draft.icon === name ? "defs-icon defs-icon--on" : "defs-icon"}
                  onClick={() => update({ icon: name })}
                >
                  <Icon size={18} aria-hidden="true" focusable="false" />
                </button>
              ))}
            </div>
          </Field>

          <Field label="Assigned children" id="defs-label-children">
            <button
              type="button"
              className="defs-select-row"
              aria-expanded={pickerOpen}
              aria-labelledby="defs-label-children defs-children-summary"
              onClick={() => setPickerOpen((open) => !open)}
            >
              <span id="defs-children-summary">
                {selectedAssignees.length > 0
                  ? assigneeSummary(selectedAssignees, activeChildren)
                  : "Choose children"}
              </span>
              {pickerOpen ? <ChevronDownGlyph /> : <ChevronRightGlyph />}
            </button>
            {pickerOpen ? (
              <ul className="defs-picker" aria-label="Children">
                {activeChildren.map((child) => {
                  const checked = draft.assigneeIds.includes(child.id);
                  return (
                    <li key={child.id}>
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={checked}
                        className="defs-picker-option"
                        onClick={() => update({ assigneeIds: toggle(draft.assigneeIds, child.id) })}
                      >
                        <span>{child.display_name}</span>
                        <span className="defs-picker-check">{checked ? <CheckGlyph /> : null}</span>
                      </button>
                    </li>
                  );
                })}
                {inactiveAssignees.map((assignee) => (
                  <li
                    key={assignee.id}
                    className="defs-picker-option defs-picker-option--locked"
                    aria-disabled="true"
                    data-testid={`inactive-assignee-${assignee.id}`}
                  >
                    <span>{assignee.display_name}</span>
                    <span className="defs-picker-note">Inactive</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {inactiveAssignees.length > 0 ? (
              <p className="defs-hint">
                Also assigned (inactive): {inactiveAssignees.map((a) => a.display_name).join(", ")}.
                Kept unless you change the selection.
              </p>
            ) : null}
          </Field>

          <Field label="Repeats" id="defs-label-repeats">
            <div className="defs-repeats">
              <select
                className="defs-input"
                aria-label="Repeats"
                value={draft.repeats}
                onChange={(e) =>
                  update({
                    repeats: e.target.value as Repeats,
                    // Leaving Monthly drops a carried nth-weekday rule for good.
                    monthlyWeekday: e.target.value === "monthly" ? draft.monthlyWeekday : null,
                  })
                }
              >
                {REPEATS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <label className="defs-interval">
                <span>Every</span>
                <input
                  className="defs-input"
                  type="number"
                  min={1}
                  aria-label="Interval"
                  value={draft.interval}
                  onChange={(e) => update({ interval: e.target.value })}
                />
              </label>
            </div>
            {draft.repeats === "weekly" || draft.repeats === "custom" ? (
              <div className="defs-weekdays" role="group" aria-label="Days">
                {WEEKDAY_DISPLAY_ORDER.map((day) => (
                  <button
                    key={day}
                    type="button"
                    aria-pressed={draft.weekdays.includes(day)}
                    aria-label={WEEKDAY_LONG[day]}
                    className={
                      draft.weekdays.includes(day) ? "defs-day defs-day--on" : "defs-day"
                    }
                    onClick={() => update({ weekdays: toggle(draft.weekdays, day) })}
                  >
                    {WEEKDAY_SHORT[day].charAt(0)}
                  </button>
                ))}
              </div>
            ) : null}
            {draft.repeats === "monthly" && draft.monthlyWeekday ? (
              <p className="defs-hint">
                {recurrenceSummary({
                  rule_type: "monthly_weekday",
                  interval: parseWhole(draft.interval, 1, 999) ?? 1,
                  weekday_set: null,
                  day_of_month: null,
                  nth_weekday: draft.monthlyWeekday.nth,
                  nth_weekday_weekday: draft.monthlyWeekday.weekday,
                  month: null,
                  start_date: draft.startDate,
                  end_date: draft.endDate,
                })}
              </p>
            ) : null}
            {draft.repeats === "yearly" ? (
              <select
                className="defs-input"
                aria-label="Month"
                value={draft.month}
                onChange={(e) => update({ month: e.target.value })}
              >
                {MONTH_SHORT.map((label, index) => (
                  <option key={label} value={String(index + 1)}>
                    {label}
                  </option>
                ))}
              </select>
            ) : null}
            {(draft.repeats === "monthly" && !draft.monthlyWeekday) || draft.repeats === "yearly" ? (
              <input
                className="defs-input"
                type="number"
                min={1}
                max={31}
                aria-label="Day of month"
                value={draft.dayOfMonth}
                onChange={(e) => update({ dayOfMonth: e.target.value })}
              />
            ) : null}
            <OccurrencePreview ruleKey={previewKey} />
          </Field>

          <Field label="Due time" id="defs-label-due">
            {orderedWindows.length === 0 ? (
              <p className="defs-hint">Pick a window to set its due time.</p>
            ) : (
              <div className="defs-due-times">
                {orderedWindows.map((w) => (
                  <label key={w} className="defs-due">
                    <span>{WINDOW_LABELS[w]}</span>
                    <input
                      className="defs-input"
                      type="time"
                      aria-label={`${WINDOW_LABELS[w]} due time`}
                      value={draft.dueTimes[w]}
                      onChange={(e) =>
                        update({ dueTimes: { ...draft.dueTimes, [w]: e.target.value } })
                      }
                    />
                  </label>
                ))}
              </div>
            )}
          </Field>

          <Field label="Window" id="defs-label-window">
            <div className="defs-segmented">
              {WINDOW_ORDER.map((w) => (
                <button
                  key={w}
                  type="button"
                  aria-pressed={draft.windows.includes(w)}
                  className={
                    draft.windows.includes(w) ? "defs-segment defs-segment--on" : "defs-segment"
                  }
                  onClick={() => update({ windows: toggle(draft.windows, w) })}
                >
                  {WINDOW_LABELS[w]}
                </button>
              ))}
            </div>
          </Field>

          <div className="defs-toggle-row">
            <div>
              <div className="defs-toggle-title" id="defs-label-skip">
                Skip on away days
              </div>
              <div className="defs-toggle-sub">No instance when the child is absent</div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={draft.skipOnAway}
              aria-labelledby="defs-label-skip"
              className={draft.skipOnAway ? "defs-switch defs-switch--on" : "defs-switch"}
              onClick={() => update({ skipOnAway: !draft.skipOnAway })}
            >
              <span className="defs-switch-knob" />
            </button>
          </div>
        </div>

        {error ? (
          <p className="defs-sheet-error" role="alert" data-testid="sheet-error">
            {error}
          </p>
        ) : null}

        {confirming ? (
          <div
            className="defs-confirm"
            role="group"
            aria-labelledby="defs-confirm-text"
            data-testid="unassign-confirm"
            ref={confirmRef}
            tabIndex={-1}
          >
            <p id="defs-confirm-text">
              Saving will unassign{" "}
              {inactiveAssignees.map((a) => a.display_name).join(", ")}. Inactive children can't be
              assigned again until they are reactivated.
            </p>
            <div className="defs-sheet-footer">
              <button type="button" className="defs-cancel" onClick={() => setConfirming(false)}>
                Go back
              </button>
              <button type="button" className="defs-save" onClick={() => save(true)}>
                Unassign and save
              </button>
            </div>
          </div>
        ) : (
          <div className="defs-sheet-footer">
            <button type="button" className="defs-cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="button" className="defs-save" onClick={() => save()} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Screen ─────────────────────────────────────────────────────────── */

export default function DefinitionsTab() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<number | "all">("all");
  const [sheet, setSheet] = useState<SheetTarget>(null);

  useEffect(() => {
    let cancelled = false;
    // Keep the list on screen during a post-save re-fetch; spin only on first load.
    setState((current) => (current.kind === "ready" ? current : { kind: "loading" }));
    Promise.all([fetchDefinitions(), fetchChildren()])
      .then(([definitions, children]) => {
        if (!cancelled) setState({ kind: "ready", definitions, children });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiForbiddenError
            ? error.message
            : "Tasks could not be loaded. Check your connection and try again.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const activeChildren =
    state.kind === "ready"
      ? [...state.children]
          .filter((child) => child.is_active)
          .sort((a, b) => a.sort_order - b.sort_order)
      : [];

  let sub = "";
  let body;
  if (state.kind === "loading") {
    body = (
      <div className="defs-status" role="status" data-testid="definitions-loading">
        Loading tasks…
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div className="defs-status defs-status--error" role="alert" data-testid="definitions-error">
        <p>{state.message}</p>
        <button type="button" className="defs-retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  } else {
    const { definitions } = state;
    sub = `${definitions.length} definitions · ${activeChildren.length} children`;
    const shown =
      filter === "all"
        ? definitions
        : definitions.filter((d) => d.assignees.some((a) => a.id === filter));
    const editingId = sheet !== null && sheet !== "new" ? sheet.id : null;
    body = (
      <>
        <FilterChips options={activeChildren} filter={filter} onChange={setFilter} />
        {shown.length > 0 ? (
          <ul className="defs-card defs-list" aria-label="Task definitions">
            {shown.map((definition) => (
              <DefinitionRow
                key={definition.id}
                definition={definition}
                activeChildren={activeChildren}
                editing={definition.id === editingId}
                onOpen={() => setSheet(definition)}
              />
            ))}
          </ul>
        ) : (
          <div className="defs-card defs-empty">No tasks yet.</div>
        )}
      </>
    );
  }

  return (
    <div className="defs-screen">
      <header className="defs-header">
        <div>
          <h2 className="defs-title">Tasks</h2>
          <p className="defs-sub">{sub}</p>
        </div>
        <button
          type="button"
          className="defs-new"
          disabled={state.kind !== "ready"}
          onClick={() => setSheet("new")}
        >
          <PlusGlyph />
          New
        </button>
      </header>
      <div
        className="defs-scroll"
        data-testid="definitions-scroll"
        style={{ paddingBottom: SCROLL_BOTTOM_PADDING }}
      >
        {body}
      </div>
      {sheet !== null && state.kind === "ready" ? (
        <EditSheet
          key={sheet === "new" ? "new" : sheet.id}
          target={sheet}
          activeChildren={activeChildren}
          onCancel={() => setSheet(null)}
          onSaved={() => {
            setSheet(null);
            setAttempt((n) => n + 1);
          }}
        />
      ) : null}
    </div>
  );
}
