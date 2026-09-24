/**
 * Day grouping and row wording for the History tab.
 *
 * Calendar dates ("YYYY-MM-DD") are handled by their components (never
 * `new Date("YYYY-MM-DD")`, which is UTC midnight and reads as the previous
 * day in negative-offset zones); event stamps are UTC and shown in the
 * viewer's local time.
 */
import type { HistoryRow } from "../api/history";
import { dayNumber, isoFromDayNumber, localTodayIso } from "../schedule/cycle";
import { shortDate } from "../schedule/format";
import { formatClockTime, formatDueTime } from "../today/format";

const MS_PER_MINUTE = 60_000;

/** `iso` shifted by `days` calendar days. */
export function shiftIso(iso: string, days: number): string {
  return isoFromDayNumber(dayNumber(iso) + days);
}

/** The local calendar day an event belongs to (due_date for missed rows). */
export function rowDay(row: HistoryRow): string {
  return row.occurred_at ? localTodayIso(new Date(row.occurred_at)) : row.due_date;
}

/** The row's due moment as local wall-clock time, or null without a due time. */
function dueMoment(row: HistoryRow): Date | null {
  const match = /^(\d{2}):(\d{2})/.exec(row.due_time ?? "");
  if (!match) return null;
  const [year, month, day] = row.due_date.split("-").map(Number);
  return new Date(year, month - 1, day, Number(match[1]), Number(match[2]));
}

/** Newest first; a missed row sorts at its due moment (or the end of its day). */
function sortKey(row: HistoryRow): number {
  if (row.occurred_at) return Date.parse(row.occurred_at);
  const due = dueMoment(row);
  if (due) return due.getTime();
  const [year, month, day] = row.due_date.split("-").map(Number);
  return new Date(year, month - 1, day, 23, 59).getTime();
}

export interface DayGroup {
  day: string;
  rows: HistoryRow[];
}

/** Rows grouped by day, newest day first and newest row first within a day. */
export function groupByDay(rows: HistoryRow[]): DayGroup[] {
  const groups = new Map<string, HistoryRow[]>();
  for (const row of rows) {
    const day = rowDay(row);
    groups.set(day, [...(groups.get(day) ?? []), row]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, dayRows]) => ({
      day,
      // Stable sort: rows at the same moment keep the API's append order.
      rows: [...dayRows].sort((a, b) => sortKey(b) - sortKey(a)),
    }));
}

/** "Today", "Yesterday", else "Mon, Sep 21" (the CSS uppercases it). */
export function dayLabel(day: string, today: string): string {
  if (day === today) return "Today";
  if (day === shiftIso(today, -1)) return "Yesterday";
  const weekday = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" }).format(
    new Date(dayNumber(day) * 86_400_000),
  );
  return `${weekday}, ${shortDate(day)}`;
}

/** "on time", "late 22 min", or "late" when the lateness is not derivable. */
function onTimeFlag(row: HistoryRow): string | null {
  if (row.event_type !== "completed" || row.was_on_time === null) return null;
  if (row.was_on_time) return "on time";
  const due = dueMoment(row);
  if (!due || !row.occurred_at) return "late";
  const minutes = Math.round((Date.parse(row.occurred_at) - due.getTime()) / MS_PER_MINUTE);
  return minutes > 0 ? `late ${minutes} min` : "late";
}

/** `<event type> · <actor>` plus the on-time flag for completions. */
export function rowMeta(row: HistoryRow): string {
  const flag = onTimeFlag(row);
  return [row.event_type, row.actor, flag].filter(Boolean).join(" · ");
}

/** The event's local clock time; a missed row shows its due time, if any. */
export function rowTime(row: HistoryRow): string {
  if (row.occurred_at) return formatClockTime(row.occurred_at);
  return row.due_time ? formatDueTime(row.due_time) : "";
}
