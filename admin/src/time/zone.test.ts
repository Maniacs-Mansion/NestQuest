import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { isoDateIn, todayIn, wallClockInstant, zoneOption } from "./zone";
import { formatClockTime } from "../today/format";

// 13:00 UTC on Sep 23 is already 01:00 on Sep 24 in Auckland (NZST, UTC+12).
const NOW = new Date("2026-09-23T13:00:00Z");

describe("application timezone helpers (process in UTC)", () => {
  beforeAll(() => {
    vi.stubEnv("TZ", "UTC");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  it("a stored zone decides the calendar date; empty means the browser's zone", () => {
    expect(todayIn("Pacific/Auckland", NOW)).toBe("2026-09-24");
    expect(isoDateIn(NOW, "Pacific/Auckland")).toBe("2026-09-24");
    expect(todayIn("", NOW)).toBe("2026-09-23");
  });

  it("wall-clock time converts in the stored zone, across its DST change", () => {
    // NZST (UTC+12) before 27 Sep 2026, NZDT (UTC+13) after.
    expect(wallClockInstant("2026-09-24", 0, 10, "Pacific/Auckland")).toBe(
      Date.parse("2026-09-23T12:10:00Z"),
    );
    expect(wallClockInstant("2026-09-28", 7, 30, "Pacific/Auckland")).toBe(
      Date.parse("2026-09-27T18:30:00Z"),
    );
    expect(wallClockInstant("2026-09-24", 0, 10, "")).toBe(Date.parse("2026-09-24T00:10:00Z"));
  });

  it("the completion clock reads in the stored zone", () => {
    expect(formatClockTime("2026-09-23T11:04:00Z", "Pacific/Auckland")).toBe("11:04 PM");
    expect(formatClockTime("2026-09-23T11:04:00Z", "")).toBe("11:04 AM");
  });

  it("an invalid stored zone fails fast", () => {
    expect(zoneOption("")).toBeUndefined();
    expect(() => todayIn("Not/AZone", NOW)).toThrow(RangeError);
  });
});

describe("empty zone keeps browser-local behavior", () => {
  beforeAll(() => {
    vi.stubEnv("TZ", "America/Los_Angeles");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  it("matches the browser's own calendar and wall clock", () => {
    // 13:00 UTC is 06:00 PDT on Sep 23.
    expect(todayIn("", NOW)).toBe("2026-09-23");
    expect(wallClockInstant("2026-09-23", 7, 30, "")).toBe(new Date(2026, 8, 23, 7, 30).getTime());
    expect(formatClockTime("2026-09-23T14:04:00Z", "")).toBe("7:04 AM");
  });
});
