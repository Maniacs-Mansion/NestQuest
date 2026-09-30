/**
 * Local time in the application timezone.
 *
 * The admin-saved zone (settings `timezone`, an IANA name) is the single
 * source of local-time truth for the whole application; the API publishes it
 * as `effective_timezone`, naming its host's own zone when none is stored.
 * "" means the API published no zone, and only then does the browser's own
 * zone apply. Every helper takes
 * that stored value as-is; an invalid zone name throws (Intl's RangeError).
 */

/** The `timeZone` option for Intl: the zone, or undefined (browser) for "". */
export function zoneOption(timeZone: string): string | undefined {
  return timeZone === "" ? undefined : timeZone;
}

interface WallClock {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

function wallClock(instant: number, timeZone: string): WallClock {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zoneOption(timeZone),
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(instant);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((p) => p.type === type)?.value);
  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
    hour: part("hour"),
    minute: part("minute"),
    second: part("second"),
  };
}

/** The "YYYY-MM-DD" calendar date of `instant` in the zone. */
export function isoDateIn(instant: Date, timeZone: string): string {
  const { year, month, day } = wallClock(instant.getTime(), timeZone);
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Today's calendar date in the zone. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  return isoDateIn(now, timeZone);
}

/** The zone's UTC offset in ms at `instant` (wall clock minus UTC). */
function offsetAt(instant: number, timeZone: string): number {
  const c = wallClock(instant, timeZone);
  const wholeSeconds = Math.floor(instant / 1000) * 1000;
  return Date.UTC(c.year, c.month - 1, c.day, c.hour, c.minute, c.second) - wholeSeconds;
}

/**
 * Epoch ms at which the zone's wall clock reads `hour:minute` on the
 * "YYYY-MM-DD" date. Two passes settle the offset across a DST change.
 */
export function wallClockInstant(
  iso: string,
  hour: number,
  minute: number,
  timeZone: string,
): number {
  const [year, month, day] = iso.split("-").map(Number);
  const asUtc = Date.UTC(year, month - 1, day, hour, minute);
  const guess = asUtc - offsetAt(asUtc, timeZone);
  return asUtc - offsetAt(guess, timeZone);
}
