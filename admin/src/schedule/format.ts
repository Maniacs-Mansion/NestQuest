/**
 * Date labels for the Schedule tab. Calendar dates are formatted in UTC from
 * their components, so the printed day never shifts with the viewer's offset.
 */
import { dayNumber } from "./cycle";

const LOCALE = "en-US";

function utcDate(iso: string): Date {
  return new Date(dayNumber(iso) * 86_400_000);
}

function format(iso: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(LOCALE, { ...options, timeZone: "UTC" }).format(utcDate(iso));
}

/** "Tuesday, Sep 1" */
export function anchorLabel(iso: string): string {
  return `${format(iso, { weekday: "long" })}, ${format(iso, { month: "short", day: "numeric" })}`;
}

/** "September 2026" */
export function monthLabel(iso: string): string {
  return format(iso, { month: "long", year: "numeric" });
}

/** "Sep 4" */
export function shortDate(iso: string): string {
  return format(iso, { month: "short", day: "numeric" });
}

/** "Sep 4 – 7", "Sep 28 – Oct 2", or "Sep 4" for a single day. */
export function dateRange(start: string, end: string): string {
  if (start === end) return shortDate(start);
  const sameMonth = start.slice(0, 7) === end.slice(0, 7);
  return `${shortDate(start)} – ${sameMonth ? Number(end.slice(8)) : shortDate(end)}`;
}
