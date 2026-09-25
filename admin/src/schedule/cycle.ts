/**
 * Pure presence-cycle math for the Schedule tab.
 *
 * Cycle position comes from the anchor date ONLY, mirroring
 * core/presence.py `cycle_week_index`:
 * `((date - anchor).days // 7) % cycle_length_weeks` with floor division,
 * so dates before the anchor walk the cycle backwards. Never ISO week
 * numbers or week parity (D-004).
 *
 * Calendar dates are "YYYY-MM-DD" strings handled as whole UTC days, so no
 * viewer offset or DST change can shift a day.
 */
import type {
  PatternCycle,
  PatternKind,
  PatternWeeks,
  PresenceOverride,
} from "../api/presence";

const MS_PER_DAY = 86_400_000;

export const ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

/** Monday=0 weekday numbers in Sunday-first display order. */
export const DISPLAY_WEEKDAYS = [6, 0, 1, 2, 3, 4, 5];

/** Short names indexed by Monday=0 weekday number. */
export const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Days since 1970-01-01 for a "YYYY-MM-DD" calendar date. */
export function dayNumber(iso: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error(`Invalid calendar date: ${iso}`);
  const [, year, month, day] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day)) / MS_PER_DAY;
}

export function isoFromDayNumber(days: number): string {
  return new Date(days * MS_PER_DAY).toISOString().slice(0, 10);
}

/** Floor modulo: always in 0..divisor-1, like Python's `%`. */
function mod(value: number, divisor: number): number {
  return ((value % divisor) + divisor) % divisor;
}

/** 0 = Monday .. 6 = Sunday (1970-01-01 was a Thursday). */
export function weekdayOf(iso: string): number {
  return mod(dayNumber(iso) + 3, 7);
}

/** `((date - anchor).days // 7) % cycleLengthWeeks`, Python semantics. */
export function cycleWeekIndex(anchorDate: string, date: string, cycleLengthWeeks: number): number {
  const days = dayNumber(date) - dayNumber(anchorDate);
  return mod(Math.floor(days / 7), cycleLengthWeeks);
}

/** The viewer's local calendar date. */
export function localTodayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** "YYYY-MM-01" of the month containing `iso`, shifted by `delta` months. */
export function monthStart(iso: string, delta = 0): string {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + delta, 1));
  return date.toISOString().slice(0, 10);
}

/** Every date of the month starting at `firstIso`. */
export function monthDates(firstIso: string): string[] {
  const start = dayNumber(firstIso);
  const end = dayNumber(monthStart(firstIso, 1));
  const dates: string[] = [];
  for (let day = start; day < end; day += 1) dates.push(isoFromDayNumber(day));
  return dates;
}

/** Every week of the cycle covers no day yet (a new pattern). */
export function emptyPattern(cycleLengthWeeks: number): PatternWeeks {
  const pattern: PatternWeeks = {};
  for (let week = 0; week < cycleLengthWeeks; week += 1) pattern[week] = [];
  return pattern;
}

export type DayState = "home" | "away" | "override-home" | "override-away";

/** Does the pattern cover `date` (its cycle week lists the date's weekday)? */
export function patternIncludes(cycle: PatternCycle, date: string): boolean {
  const week = cycleWeekIndex(cycle.anchor_date, date, cycle.cycle_length_weeks);
  return (cycle.pattern[week] ?? []).includes(weekdayOf(date));
}

/**
 * A date's combined state for one child, mirroring core/presence.py
 * `is_present` — first match wins:
 * 1. an override covering the date;
 * 2. away when any `away` pattern covers it;
 * 3. home when any `home` pattern covers it;
 * 4. away when the child has at least one `home` pattern (a home pattern
 *    lists the days the child IS here), else home (no patterns, or only
 *    `away` ones).
 */
export function dayState(
  patterns: (PatternCycle & { kind: PatternKind })[],
  overrides: PresenceOverride[],
  date: string,
): DayState {
  const override = overrides.find((o) => o.start_date <= date && date <= o.end_date);
  if (override) return override.is_present ? "override-home" : "override-away";
  if (patterns.some((p) => p.kind === "away" && patternIncludes(p, date))) return "away";
  const homes = patterns.filter((p) => p.kind === "home");
  if (homes.some((p) => patternIncludes(p, date))) return "home";
  return homes.length > 0 ? "away" : "home";
}

/** Flip `weekday` in `week` of the pattern; returns a new pattern. */
export function togglePatternDay(
  pattern: PatternWeeks,
  week: number,
  weekday: number,
): PatternWeeks {
  const days = pattern[week] ?? [];
  const next = days.includes(weekday)
    ? days.filter((d) => d !== weekday)
    : [...days, weekday].sort((a, b) => a - b);
  return { ...pattern, [week]: next };
}

/** Fit the pattern to a new cycle length; added weeks start covering no day. */
export function resizePattern(pattern: PatternWeeks, cycleLengthWeeks: number): PatternWeeks {
  const next: PatternWeeks = {};
  for (let week = 0; week < cycleLengthWeeks; week += 1) {
    next[week] = pattern[week] ? [...pattern[week]] : [];
  }
  return next;
}

function daysLabel(days: number[]): string {
  if (days.length === 7) return "Every day";
  if (days.length === 0) return "No days";
  return [...days].sort((a, b) => a - b).map((d) => WEEKDAY_SHORT[d]).join(", ");
}

/**
 * Plain-language weekday set: `Thu, Fri` for a 1-week cycle, otherwise one
 * entry per cycle week, e.g. `Week 1: Sat, Sun · Week 2: No days`.
 */
export function patternDaysLabel(cycle: PatternCycle): string {
  if (cycle.cycle_length_weeks === 1) return daysLabel(cycle.pattern[0] ?? []);
  const weeks: string[] = [];
  for (let week = 0; week < cycle.cycle_length_weeks; week += 1) {
    weeks.push(`Week ${week + 1}: ${daysLabel(cycle.pattern[week] ?? [])}`);
  }
  return weeks.join(" · ");
}

/** `Every week`, `Every 2 weeks`. */
export function cycleLabel(cycleLengthWeeks: number): string {
  return cycleLengthWeeks === 1 ? "Every week" : `Every ${cycleLengthWeeks} weeks`;
}
