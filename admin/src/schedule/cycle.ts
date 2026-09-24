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
import type { PresenceOverride, PresencePattern, PresenceScheduleBody } from "../api/presence";

const MS_PER_DAY = 86_400_000;

export const ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

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

/** Present every day for every week of the cycle (the no-schedule case). */
export function fullPattern(cycleLengthWeeks: number): PresencePattern {
  const pattern: PresencePattern = {};
  for (let week = 0; week < cycleLengthWeeks; week += 1) pattern[week] = [...ALL_WEEKDAYS];
  return pattern;
}

export type DayState = "home" | "away" | "override-home" | "override-away";

export function patternIncludes(
  schedule: PresenceScheduleBody,
  date: string,
): boolean {
  const week = cycleWeekIndex(schedule.anchor_date, date, schedule.cycle_length_weeks);
  return (schedule.pattern[week] ?? []).includes(weekdayOf(date));
}

/**
 * A date's state for one child: an override covering the date wins;
 * otherwise the schedule's pattern decides (no schedule = home every day).
 */
export function dayState(
  schedule: PresenceScheduleBody | null,
  overrides: PresenceOverride[],
  date: string,
): DayState {
  const override = overrides.find((o) => o.start_date <= date && date <= o.end_date);
  if (override) return override.is_present ? "override-home" : "override-away";
  if (!schedule) return "home";
  return patternIncludes(schedule, date) ? "home" : "away";
}

/** Flip `weekday` in `week` of the pattern; returns a new pattern. */
export function togglePatternDay(
  pattern: PresencePattern,
  week: number,
  weekday: number,
): PresencePattern {
  const days = pattern[week] ?? [];
  const next = days.includes(weekday)
    ? days.filter((d) => d !== weekday)
    : [...days, weekday].sort((a, b) => a - b);
  return { ...pattern, [week]: next };
}

/** Fit the pattern to a new cycle length; added weeks start present every day. */
export function resizePattern(pattern: PresencePattern, cycleLengthWeeks: number): PresencePattern {
  const next: PresencePattern = {};
  for (let week = 0; week < cycleLengthWeeks; week += 1) {
    next[week] = pattern[week] ? [...pattern[week]] : [...ALL_WEEKDAYS];
  }
  return next;
}

function joinWeeks(weeks: number[]): string {
  if (weeks.length === 1) return String(weeks[0]);
  return `${weeks.slice(0, -1).join(", ")} & ${weeks[weeks.length - 1]}`;
}

/** Plain-language rule: `Every day`, `Weeks 1 & 3 of cycle`, `Never home`. */
export function presenceRule(schedule: PresenceScheduleBody | null): string {
  if (!schedule) return "Every day";
  const weeks: number[] = [];
  let full = true;
  for (let week = 0; week < schedule.cycle_length_weeks; week += 1) {
    const days = schedule.pattern[week] ?? [];
    if (days.length > 0) weeks.push(week + 1);
    if (days.length < 7) full = false;
  }
  if (full) return "Every day";
  if (weeks.length === 0) return "Never home";
  return `${weeks.length === 1 ? "Week" : "Weeks"} ${joinWeeks(weeks)} of cycle`;
}
