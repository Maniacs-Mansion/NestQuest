import { describe, expect, it } from "vitest";
import {
  cycleLabel,
  cycleWeekIndex,
  dayState,
  emptyPattern,
  monthDates,
  monthStart,
  patternDaysLabel,
  patternIncludes,
  resizePattern,
  togglePatternDay,
  weekdayOf,
} from "./cycle";
import type { PatternCycle, PatternKind, PresenceOverride } from "../api/presence";

type KindedCycle = PatternCycle & { kind: PatternKind };

// The migrated single schedule: anchor Monday 2026-09-07; week 0 home every
// day, week 1 home Sat/Sun only.
const SCHEDULE: KindedCycle = {
  kind: "home",
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { 0: [0, 1, 2, 3, 4, 5, 6], 1: [5, 6] },
};

// The owner scenario: away Thu+Fri every week, away weekends every 2 weeks.
const THU_FRI: KindedCycle = {
  kind: "away",
  cycle_length_weeks: 1,
  anchor_date: "2026-09-07",
  pattern: { 0: [3, 4] },
};
const ALTERNATE_WEEKENDS: KindedCycle = {
  kind: "away",
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { 0: [5, 6], 1: [] },
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

  it("a home-only child: overrides first, then absent on days no home pattern covers", () => {
    const patterns = [SCHEDULE];
    expect(dayState(patterns, overrides, "2026-09-08")).toBe("home");
    expect(dayState(patterns, overrides, "2026-09-11")).toBe("override-away");
    expect(dayState(patterns, overrides, "2026-09-15")).toBe("away");
    expect(dayState(patterns, overrides, "2026-09-16")).toBe("override-home");
    expect(dayState(patterns, overrides, "2026-09-19")).toBe("home");
    expect(dayState(patterns, overrides, "2026-09-01")).toBe("away");
    expect(dayState(patterns, overrides, "2026-09-05")).toBe("home");
  });

  it("combines the owner's two away patterns; every other day is home", () => {
    const patterns = [THU_FRI, ALTERNATE_WEEKENDS];
    const expected: Record<string, string> = {};
    for (const date of monthDates("2026-09-01")) {
      const weekday = weekdayOf(date);
      const onWeek = cycleWeekIndex("2026-09-07", date, 2) === 0;
      const away = weekday === 3 || weekday === 4 || (onWeek && weekday >= 5);
      expected[date] = away ? "away" : "home";
    }
    for (const [date, state] of Object.entries(expected)) {
      expect(dayState(patterns, [], date), date).toBe(state);
    }
    // Spot checks: Thu/Fri every week; weekends alternate from the anchor.
    expect(dayState(patterns, [], "2026-09-10")).toBe("away"); // Thu, week 0
    expect(dayState(patterns, [], "2026-09-18")).toBe("away"); // Fri, week 1
    expect(dayState(patterns, [], "2026-09-12")).toBe("away"); // Sat, week 0
    expect(dayState(patterns, [], "2026-09-20")).toBe("home"); // Sun, week 1
    expect(dayState(patterns, [], "2026-09-27")).toBe("away"); // Sun, week 0
    expect(dayState(patterns, [], "2026-09-15")).toBe("home"); // Tue
  });

  it("away beats home when both cover a date; a home pattern makes uncovered days away", () => {
    const patterns = [SCHEDULE, THU_FRI];
    expect(dayState(patterns, [], "2026-09-10")).toBe("away"); // home week 0 Thu, but away wins
    expect(dayState(patterns, [], "2026-09-08")).toBe("home"); // home covers, away does not
    expect(dayState(patterns, [], "2026-09-15")).toBe("away"); // no home pattern covers it
    // An override still beats every pattern.
    expect(
      dayState(patterns, [{ ...overrides[1], start_date: "2026-09-10", end_date: "2026-09-10" }], "2026-09-10"),
    ).toBe("override-home");
  });

  it("treats a child with no patterns as home every day", () => {
    expect(dayState([], [], "2026-09-15")).toBe("home");
  });
});

describe("pattern editing and labels", () => {
  it("patternIncludes reads the date's cycle week from the anchor", () => {
    expect(patternIncludes(ALTERNATE_WEEKENDS, "2026-09-12")).toBe(true);
    expect(patternIncludes(ALTERNATE_WEEKENDS, "2026-09-19")).toBe(false);
    expect(patternIncludes(ALTERNATE_WEEKENDS, "2026-09-05")).toBe(false); // pre-anchor week 1
  });

  it("toggles one weekday of one cycle week", () => {
    expect(togglePatternDay(SCHEDULE.pattern, 1, 1)).toEqual({
      0: [0, 1, 2, 3, 4, 5, 6],
      1: [1, 5, 6],
    });
    expect(togglePatternDay(SCHEDULE.pattern, 1, 5)[1]).toEqual([6]);
  });

  it("resizes the pattern to the cycle length; added weeks cover no day", () => {
    expect(resizePattern(SCHEDULE.pattern, 1)).toEqual({ 0: [0, 1, 2, 3, 4, 5, 6] });
    expect(resizePattern(SCHEDULE.pattern, 3)[2]).toEqual([]);
    expect(emptyPattern(2)).toEqual({ 0: [], 1: [] });
  });

  it("describes the cycle and the weekday set in plain language", () => {
    expect(cycleLabel(1)).toBe("Every week");
    expect(cycleLabel(2)).toBe("Every 2 weeks");
    expect(patternDaysLabel(THU_FRI)).toBe("Thu, Fri");
    expect(patternDaysLabel(ALTERNATE_WEEKENDS)).toBe("Week 1: Sat, Sun · Week 2: No days");
    expect(patternDaysLabel(SCHEDULE)).toBe("Week 1: Every day · Week 2: Sat, Sun");
    // Listed Monday-first by weekday number, whatever order they were stored in.
    expect(patternDaysLabel({ ...THU_FRI, pattern: { "0": [6, 0] } })).toBe("Mon, Sun");
  });
});
