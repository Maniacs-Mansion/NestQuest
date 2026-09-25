/**
 * List-row summaries for the Definitions tab (ADMIN-SPEC §3.1):
 * `<assignees> · <recurrence> · <windows>`.
 */
import type {
  AdminChild,
  DefinitionAssignee,
  DefinitionRule,
  DefinitionWindow,
  WindowName,
} from "../api/definitions";

export const WINDOW_ORDER: WindowName[] = ["morning", "afternoon", "evening"];

export const WINDOW_LABELS: Record<WindowName, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
};

/** Index 0 = Monday .. 6 = Sunday, the core's weekday numbering. */
export const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Display order for a week: Sunday first. The stored indices stay Monday=0. */
export const WEEKDAY_DISPLAY_ORDER = [6, 0, 1, 2, 3, 4, 5];

export const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const COUNT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

/**
 * `Declan`, `Declan, Maeve`, or `All three` when every active child (two or
 * more) is assigned.
 */
export function assigneeSummary(
  assignees: Pick<DefinitionAssignee, "id" | "display_name">[],
  activeChildren: AdminChild[],
): string {
  if (assignees.length === 0) return "Unassigned";
  const assigned = new Set(assignees.map((a) => a.id));
  const everyone =
    activeChildren.length > 1 &&
    assigned.size === activeChildren.length &&
    activeChildren.every((child) => assigned.has(child.id));
  if (everyone) {
    const word = COUNT_WORDS[activeChildren.length] ?? String(activeChildren.length);
    return `All ${word}`;
  }
  return assignees.map((a) => a.display_name).join(", ");
}

function weekdayList(days: number[] | null): string {
  return [...(days ?? [])]
    .sort((a, b) => WEEKDAY_DISPLAY_ORDER.indexOf(a) - WEEKDAY_DISPLAY_ORDER.indexOf(b))
    .map((day) => WEEKDAY_SHORT[day])
    .join(", ");
}

function ordinal(n: number): string {
  if (n === -1) return "last";
  const suffix = n === 1 ? "st" : n === 2 ? "nd" : n === 3 ? "rd" : "th";
  return `${n}${suffix}`;
}

function every(interval: number, one: string, unit: string): string {
  return interval === 1 ? one : `Every ${interval} ${unit}`;
}

export function recurrenceSummary(rule: DefinitionRule): string {
  const n = rule.interval;
  switch (rule.rule_type) {
    case "daily":
      return every(n, "Daily", "days");
    case "weekly":
      return `${every(n, "Weekly", "weeks")} on ${weekdayList(rule.weekday_set)}`;
    case "monthly_day":
      return `${every(n, "Monthly", "months")} on day ${rule.day_of_month}`;
    case "monthly_weekday":
      return `${every(n, "Monthly", "months")} on the ${ordinal(rule.nth_weekday ?? 1)} ${
        WEEKDAY_SHORT[rule.nth_weekday_weekday ?? 0]
      }`;
    case "yearly": {
      const month = MONTH_SHORT[(rule.month ?? 1) - 1];
      const when = rule.day_of_month ? `on ${month} ${rule.day_of_month}` : `in ${month}`;
      return `${every(n, "Yearly", "years")} ${when}`;
    }
    case "custom_days":
      return `Custom${n === 1 ? "" : ` every ${n} weeks`} (${weekdayList(rule.weekday_set)})`;
  }
}

export function windowSummary(windows: Pick<DefinitionWindow, "window">[]): string {
  const names = new Set(windows.map((w) => w.window));
  return WINDOW_ORDER.filter((w) => names.has(w))
    .map((w) => WINDOW_LABELS[w])
    .join(", ");
}

/**
 * "2026-10-06" -> "Tue 6 Oct". The calendar date is read by its components
 * and its weekday taken in UTC (as the Today tab does), so the printed day
 * never shifts with the viewer's offset — `new Date("YYYY-MM-DD")` would.
 */
export function occurrenceLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error(`Invalid calendar date: ${iso}`);
  const [, year, month, day] = match.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  // getUTCDay: 0 = Sunday; WEEKDAY_SHORT: 0 = Monday.
  return `${WEEKDAY_SHORT[(date.getUTCDay() + 6) % 7]} ${day} ${MONTH_SHORT[month - 1]}`;
}
