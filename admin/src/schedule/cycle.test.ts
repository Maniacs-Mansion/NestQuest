import { describe, expect, it } from "vitest";
import {
  cycleWeekIndex,
  dayState,
  monthDates,
  monthStart,
  presenceRule,
  resizePattern,
  togglePatternDay,
  weekdayOf,
} from "./cycle";
import type { PresenceOverride, PresenceScheduleBody } from "../api/presence";

// Anchor Monday 2026-09-07; week 0 home every day, week 1 home Sat/Sun only.
const SCHEDULE: PresenceScheduleBody = {
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { 0: [0, 1, 2, 3, 4, 5, 6], 1: [5, 6] },
};

describe("cycleWeekIndex", () => {
  it("follows the anchor across a month, wrapping every 2 weeks", () => {
    const expected: Record<string, number> = {};
    for (const date of monthDates("2026-09-01")) {
      const day = Number(date.slice(8));
      // Sep 7-13 week 0, 14-20 week 1, 21-27 week 0 (wrap), 28-30 week 1;
      // Sep 1-6 lie before the anchor and walk back into week 1.
      expected[date] = day < 7 ? 1 : Math.floor((day - 7) / 7) % 2;
    }
    for (const [date, week] of Object.entries(expected)) {
      expect(cycleWeekIndex(SCHEDULE.anchor_date, date, 2), date).toBe(week);
    }
    expect(cycleWeekIndex("2026-09-07", "2026-09-21", 2)).toBe(0);
    expect(cycleWeekIndex("2026-09-07", "2026-09-28", 2)).toBe(1);
  });

  it("walks the cycle backwards before the anchor (floor division)", () => {
    expect(cycleWeekIndex("2026-09-07", "2026-09-06", 2)).toBe(1); // day -1
    expect(cycleWeekIndex("2026-09-07", "2026-08-31", 2)).toBe(1); // day -7
    expect(cycleWeekIndex("2026-09-07", "2026-08-30", 2)).toBe(0); // day -8
    expect(cycleWeekIndex("2026-09-07", "2026-08-24", 2)).toBe(0); // day -14
    expect(cycleWeekIndex("2026-09-07", "2026-08-23", 2)).toBe(1); // day -15
    expect(cycleWeekIndex("2026-09-07", "2026-09-06", 3)).toBe(2); // last week of a 3-week cycle
  });

  it("ignores ISO week parity across a 53-week year", () => {
    // 2026-12-28 is ISO week 53 and 2027-01-04 ISO week 1 — both odd, so
    // parity would call them the same week. From the anchor they alternate.
    expect(cycleWeekIndex("2026-09-07", "2026-12-28", 2)).toBe(0);
    expect(cycleWeekIndex("2026-09-07", "2027-01-04", 2)).toBe(1);
  });
});

describe("calendar helpers", () => {
  it("weekdayOf is Monday=0", () => {
    expect(weekdayOf("2026-09-07")).toBe(0);
    expect(weekdayOf("2026-09-01")).toBe(1);
    expect(weekdayOf("2026-09-06")).toBe(6);
  });

  it("weekdayOf keeps the stored Monday=0 .. Sunday=6 numbering (display order is separate)", () => {
    // A full known week plus dates across month and year ends.
    expect(
      [
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
        "2026-09-12",
        "2026-09-13",
      ].map(weekdayOf),
    ).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(weekdayOf("2026-11-01")).toBe(6); // Sunday
    expect(weekdayOf("2027-01-01")).toBe(4); // Friday
    expect(weekdayOf("2024-02-29")).toBe(3); // Thursday
  });

  it("monthStart shifts across year ends", () => {
    expect(monthStart("2026-12-15", 1)).toBe("2027-01-01");
    expect(monthStart("2026-01-31", -1)).toBe("2025-12-01");
    expect(monthDates("2026-02-01")).toHaveLength(28);
  });
});

describe("dayState", () => {
  const overrides: PresenceOverride[] = [
    { id: 1, child_id: 1, start_date: "2026-09-10", end_date: "2026-09-12", is_present: false, note: null },
    { id: 2, child_id: 1, start_date: "2026-09-16", end_date: "2026-09-16", is_present: true, note: null },
  ];

  it("applies overrides first, then the anchor-based pattern", () => {
    expect(dayState(SCHEDULE, overrides, "2026-09-08")).toBe("home");
    expect(dayState(SCHEDULE, overrides, "2026-09-11")).toBe("override-away");
    expect(dayState(SCHEDULE, overrides, "2026-09-15")).toBe("away");
    expect(dayState(SCHEDULE, overrides, "2026-09-16")).toBe("override-home");
    expect(dayState(SCHEDULE, overrides, "2026-09-19")).toBe("home");
    expect(dayState(SCHEDULE, overrides, "2026-09-01")).toBe("away");
    expect(dayState(SCHEDULE, overrides, "2026-09-05")).toBe("home");
  });

  it("treats a child with no schedule as home every day", () => {
    expect(dayState(null, [], "2026-09-15")).toBe("home");
  });
});

describe("pattern editing and rule text", () => {
  it("toggles one weekday of one cycle week", () => {
    expect(togglePatternDay(SCHEDULE.pattern, 1, 1)).toEqual({
      0: [0, 1, 2, 3, 4, 5, 6],
      1: [1, 5, 6],
    });
    expect(togglePatternDay(SCHEDULE.pattern, 1, 5)[1]).toEqual([6]);
  });

  it("resizes the pattern to the cycle length", () => {
    expect(resizePattern(SCHEDULE.pattern, 1)).toEqual({ 0: [0, 1, 2, 3, 4, 5, 6] });
    expect(resizePattern(SCHEDULE.pattern, 3)[2]).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("describes the presence rule in plain language", () => {
    expect(presenceRule(null)).toBe("Every day");
    expect(presenceRule({ ...SCHEDULE, pattern: { 0: [0, 1, 2, 3, 4, 5, 6], 1: [0, 1, 2, 3, 4, 5, 6] } })).toBe(
      "Every day",
    );
    expect(presenceRule(SCHEDULE)).toBe("Weeks 1 & 2 of cycle");
    expect(
      presenceRule({ cycle_length_weeks: 4, anchor_date: "2026-09-07", pattern: { 0: [0], 1: [], 2: [3], 3: [] } }),
    ).toBe("Weeks 1 & 3 of cycle");
    expect(presenceRule({ ...SCHEDULE, pattern: { 0: [1], 1: [] } })).toBe("Week 1 of cycle");
    expect(presenceRule({ ...SCHEDULE, pattern: { 0: [], 1: [] } })).toBe("Never home");
  });
});
