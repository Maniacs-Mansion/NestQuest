/**
 * Date/time formatting for the Today tab.
 *
 * Calendar dates ("YYYY-MM-DD") are parsed by their components and formatted
 * in UTC, so the printed day never shifts with the viewer's offset — unlike
 * `new Date("YYYY-MM-DD")`, which is UTC midnight and reads as the previous
 * day in negative-offset zones.
 */

const LOCALE = "en-US";

function calendarDate(iso: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error(`Invalid calendar date: ${iso}`);
  const [, year, month, day] = match;
  return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
}

function format(date: Date, options: Intl.DateTimeFormatOptions): string {
  // Newer ICU puts a narrow no-break space before AM/PM; normalise it.
  return new Intl.DateTimeFormat(LOCALE, options)
    .format(date)
    .replace(/ /g, " ");
}

/** "Wednesday, September 23" */
export function formatLongDate(iso: string): string {
  const date = calendarDate(iso);
  const weekday = format(date, { weekday: "long", timeZone: "UTC" });
  const monthDay = format(date, { month: "long", day: "numeric", timeZone: "UTC" });
  return `${weekday}, ${monthDay}`;
}

/** "Sep 23" */
export function formatShortDate(iso: string): string {
  return format(calendarDate(iso), { month: "short", day: "numeric", timeZone: "UTC" });
}

/** "09:00" -> "9:00 AM" (a wall-clock time, no zone conversion). */
export function formatDueTime(hhmm: string): string {
  const match = /^(\d{2}):(\d{2})/.exec(hhmm);
  if (!match) return hhmm;
  const date = new Date(Date.UTC(2000, 0, 1, Number(match[1]), Number(match[2])));
  return format(date, { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
}

/** A UTC ISO timestamp shown as the viewer's local time, "7:04 AM". */
export function formatClockTime(isoTimestamp: string): string {
  return format(new Date(isoTimestamp), { hour: "numeric", minute: "2-digit" });
}
