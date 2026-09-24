import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import ScheduleTab from "./ScheduleTab";
import type { AdminChild } from "../api/definitions";
import type { PresenceOverride, PresencePattern } from "../api/presence";
import { storeTokens } from "../auth/oidc";
import { cycleWeekIndex, monthDates, weekdayOf } from "./cycle";

function child(id: number, display_name: string, sort_order: number, is_active = true): AdminChild {
  return { id, display_name, colour: null, avatar_ref: null, sort_order, is_active };
}

const CHILDREN = [
  child(3, "Rory", 3),
  child(1, "Declan", 1),
  child(2, "Maeve", 2),
  child(9, "Former", 4, false),
];

// Declan: the migrated single schedule — one `home` pattern anchored Monday
// 2026-09-07; cycle week 0 home every day, week 1 Sat/Sun only. Keys arrive
// as JSON strings, exactly as the API serializes them.
const DECLAN_HOME: PresencePattern = {
  id: 1,
  child_id: 1,
  name: "Home weeks",
  kind: "home",
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { "0": [0, 1, 2, 3, 4, 5, 6], "1": [5, 6] },
};

// Maeve: the owner scenario — away Thursday+Friday every week, and away
// weekends every 2 weeks (the "on" week is cycle week 0 from Sep 7).
const MAEVE_THU_FRI: PresencePattern = {
  id: 2,
  child_id: 2,
  name: "Thursday+Friday",
  kind: "away",
  cycle_length_weeks: 1,
  anchor_date: "2026-09-07",
  pattern: { "0": [3, 4] },
};

const MAEVE_WEEKENDS: PresencePattern = {
  id: 3,
  child_id: 2,
  name: "Alternate weekends",
  kind: "away",
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { "0": [5, 6], "1": [] },
};

const OVERRIDES: PresenceOverride[] = [
  { id: 41, child_id: 1, start_date: "2026-09-10", end_date: "2026-09-12", is_present: false, note: "Dentist trip" },
  { id: 42, child_id: 1, start_date: "2026-09-16", end_date: "2026-09-16", is_present: true, note: null },
  { id: 43, child_id: 2, start_date: "2026-09-28", end_date: "2026-10-02", is_present: false, note: "Camp" },
];

const TODAY = "2026-09-23";
const PATTERNS_PATH = "/api/v1/admin/presence-patterns";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** The server's pattern store; POST/PATCH/DELETE mutate it like the API. */
let patterns: Record<number, PresencePattern[]>;
let nextId: number;
let writeFailure: Response | null;
let fetchMock: ReturnType<typeof vi.fn>;

function calls(): Call[] {
  return fetchMock.mock.calls.map((args: unknown[]) => {
    const [url, init] = args as [string, RequestInit | undefined];
    return {
      method: init?.method ?? "GET",
      path: new URL(String(url), "http://x").pathname,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
  });
}

function writes(): Call[] {
  return calls().filter((c) => c.method !== "GET");
}

function findPattern(id: number): PresencePattern | undefined {
  return Object.values(patterns)
    .flat()
    .find((p) => p.id === id);
}

function routeFetch(url: string, init: RequestInit = {}): Response {
  const path = new URL(url, "http://x").pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : undefined;
  if (method !== "GET" && writeFailure) return writeFailure;
  if (path.endsWith("/admin/children")) return jsonResponse({ children: CHILDREN });
  const collection = /\/children\/(\d+)\/presence-patterns$/.exec(path);
  if (collection) {
    const childId = Number(collection[1]);
    if (method === "POST") {
      const stored: PresencePattern = { id: nextId++, child_id: childId, ...body };
      patterns[childId] = [...(patterns[childId] ?? []), stored];
      return jsonResponse(stored, 201);
    }
    return jsonResponse({ patterns: patterns[childId] ?? [] });
  }
  const single = /\/presence-patterns\/(\d+)$/.exec(path);
  if (single) {
    const id = Number(single[1]);
    const existing = findPattern(id);
    if (!existing) return jsonResponse({ detail: "Presence pattern not found" }, 404);
    if (method === "PATCH") {
      const updated = { ...existing, ...body };
      patterns[existing.child_id] = patterns[existing.child_id].map((p) => (p.id === id ? updated : p));
      return jsonResponse(updated);
    }
    if (method === "DELETE") {
      patterns[existing.child_id] = patterns[existing.child_id].filter((p) => p.id !== id);
      return jsonResponse({ status: "ok" });
    }
  }
  if (path.endsWith("/presence-overrides")) return jsonResponse({ overrides: OVERRIDES });
  return jsonResponse({ detail: "unexpected" }, 500);
}

function day(date: string): HTMLElement {
  const cell = document.querySelector<HTMLElement>(`[data-date="${date}"]`);
  if (!cell) throw new Error(`no cell for ${date}`);
  return cell;
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Save pattern" }) as HTMLButtonElement;
}

function weekGroup(week: number): HTMLElement {
  return screen.getByRole("group", { name: new RegExp(`^Week ${week}\\b`) });
}

async function renderReady() {
  render(<ScheduleTab today={TODAY} />);
  await screen.findByTestId("pattern-1");
}

async function selectMaeve() {
  await renderReady();
  fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
  await screen.findByTestId("pattern-3");
}

describe("ScheduleTab", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    patterns = { 1: [DECLAN_HOME], 2: [MAEVE_THU_FRI, MAEVE_WEEKENDS], 3: [] };
    nextId = 50;
    writeFailure = null;
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads active children, their patterns and the overrides", async () => {
    await renderReady();
    const urls = calls().map((c) => c.path);
    expect(urls).toContain("/api/v1/admin/children");
    expect(urls).toContain("/api/v1/admin/children/1/presence-patterns");
    expect(urls).toContain("/api/v1/admin/children/2/presence-patterns");
    expect(urls).toContain("/api/v1/admin/children/3/presence-patterns");
    expect(urls).not.toContain("/api/v1/admin/children/9/presence-patterns");
    expect(urls).toContain("/api/v1/admin/presence-overrides");
    const chips = within(screen.getByRole("group", { name: "Child" })).getAllByRole("button");
    expect(chips.map((chip) => chip.textContent)).toEqual(["Declan", "Maeve", "Rory"]);
    expect(chips[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("header names the child and how many patterns it has", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: "Schedule" })).toBeTruthy();
    expect(screen.getByText("Declan · 1 pattern")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
    expect(screen.getByText("Maeve · 2 patterns")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rory" }));
    expect(screen.getByText("Rory · no patterns, home every day")).toBeTruthy();
  });

  it("a home-pattern-only child is away on days no home pattern covers", async () => {
    await renderReady();
    expect(screen.getByTestId("month-label").textContent).toBe("September 2026");
    const states: Record<string, string> = {
      "2026-09-01": "away", // before the anchor: cycle week 1, Tuesday
      "2026-09-05": "home", // before the anchor: cycle week 1, Saturday
      "2026-09-07": "home", // anchor: week 0
      "2026-09-11": "override-away",
      "2026-09-15": "away", // week 1, Tuesday
      "2026-09-16": "override-home",
      "2026-09-19": "home", // week 1, Saturday
      "2026-09-22": "home", // wrap back to week 0
      "2026-09-29": "away", // week 1 again
    };
    for (const [date, state] of Object.entries(states)) {
      expect(day(date).dataset.state, date).toBe(state);
      expect(day(date).className).toContain(`schedule-day--${state}`);
      expect(day(date).className).not.toContain("schedule-day--today");
    }
    const today = day(TODAY);
    expect(today.className).toContain("schedule-day--today");
    expect(today.dataset.state).toBe("home");
    expect(today.getAttribute("aria-label")).toBe("Sep 23 (today): Home");
    // The grid is a read-out of the combined presence, not a set of toggles.
    expect(today.tagName).toBe("SPAN");
    // Sunday-first header; September 2026 starts on a Tuesday: two leading pads.
    const grid = screen.getByRole("group", { name: "Month grid" });
    expect(Array.from(grid.children, (c) => c.textContent).slice(0, 7)).toEqual([
      "S",
      "M",
      "T",
      "W",
      "T",
      "F",
      "S",
    ]);
    expect(grid.children[7].getAttribute("data-date")).toBeNull();
    expect(grid.children[8].getAttribute("data-date")).toBeNull();
    expect(grid.children[9].getAttribute("data-date")).toBe("2026-09-01");

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Home",
      "Away",
      "Override · away",
      "Override · home",
      "Today",
    ]);
    expect(screen.getByText(/Combined from every pattern/)).toBeTruthy();
  });

  it("the owner scenario: Thu/Fri away every week, Sat/Sun away only in the on week", async () => {
    await selectMaeve();
    for (const date of monthDates("2026-09-01")) {
      if (date >= "2026-09-28") continue; // Camp override, checked below
      const weekday = weekdayOf(date);
      const onWeek = cycleWeekIndex("2026-09-07", date, 2) === 0;
      const away = weekday === 3 || weekday === 4 || (weekday >= 5 && onWeek);
      expect(day(date).dataset.state, date).toBe(away ? "away" : "home");
    }
    // Explicit spot checks of that rule.
    expect(day("2026-09-03").dataset.state).toBe("away"); // Thu
    expect(day("2026-09-04").dataset.state).toBe("away"); // Fri
    expect(day("2026-09-05").dataset.state).toBe("home"); // Sat, off week (pre-anchor)
    expect(day("2026-09-12").dataset.state).toBe("away"); // Sat, on week
    expect(day("2026-09-13").dataset.state).toBe("away"); // Sun, on week
    expect(day("2026-09-19").dataset.state).toBe("home"); // Sat, off week
    expect(day("2026-09-20").dataset.state).toBe("home"); // Sun, off week
    expect(day("2026-09-26").dataset.state).toBe("away"); // Sat, on week again
    expect(day("2026-09-14").dataset.state).toBe("home"); // Mon
    expect(day("2026-09-28").dataset.state).toBe("override-away");
  });

  it("navigates months with the chevrons", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(screen.getByTestId("month-label").textContent).toBe("October 2026");
    // Oct 1 is day 24 from the anchor: cycle week 1, a Thursday — away.
    expect(day("2026-10-01").dataset.state).toBe("away");
    expect(day("2026-10-03").dataset.state).toBe("home"); // week 1, Saturday
    expect(day("2026-10-05").dataset.state).toBe("home"); // week 0 again
    fireEvent.click(screen.getByRole("button", { name: "Previous month" }));
    expect(screen.getByTestId("month-label").textContent).toBe("September 2026");
  });

  it("patterns list shows each pattern's name, kind, cycle and weekday set", async () => {
    await selectMaeve();
    const list = screen.getByRole("list", { name: "Presence patterns" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    const thuFri = within(list).getByTestId("pattern-2");
    expect(within(thuFri).getByText("Thursday+Friday")).toBeTruthy();
    expect(within(thuFri).getByText("Away · Every week")).toBeTruthy();
    expect(within(thuFri).getByText("Thu, Fri")).toBeTruthy();
    const weekends = within(list).getByTestId("pattern-3");
    expect(within(weekends).getByText("Alternate weekends")).toBeTruthy();
    expect(within(weekends).getByText("Away · Every 2 weeks")).toBeTruthy();
    expect(within(weekends).getByText("Week 1: Sat, Sun · Week 2: No days")).toBeTruthy();
    expect(within(weekends).getByRole("button", { name: "Edit Alternate weekends" })).toBeTruthy();
    expect(within(weekends).getByRole("button", { name: "Delete Alternate weekends" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Declan" }));
    const declan = screen.getByTestId("pattern-1");
    expect(within(declan).getByText("Home · Every 2 weeks")).toBeTruthy();
    expect(within(declan).getByText("Week 1: Every day · Week 2: Sat, Sun")).toBeTruthy();
  });

  it("a child with no patterns is home every day", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Rory" }));
    expect(screen.getByTestId("patterns-empty").textContent).toBe("No patterns for Rory — home every day.");
    for (const date of monthDates("2026-09-01")) expect(day(date).dataset.state, date).toBe("home");
    expect(screen.getByText("No overrides for Rory.")).toBeTruthy();
  });

  it("overrides card lists the selected child's overrides", async () => {
    await renderReady();
    const list = screen.getByRole("list", { name: "Overrides" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    const away = within(list).getByTestId("override-41");
    expect(within(away).getByText("Declan away · Sep 10 – 12")).toBeTruthy();
    expect(within(away).getByText("Dentist trip")).toBeTruthy();
    expect(within(away).getByRole("button", { name: "Delete override" })).toBeTruthy();
    expect(within(list).getByText("Declan home · Sep 16")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
    expect(screen.getByText("Maeve away · Sep 28 – Oct 2")).toBeTruthy();
  });

  it("Add POSTs a new pattern to the child's collection and refreshes the list from the API", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Rory" }));
    fireEvent.click(screen.getByRole("button", { name: "Add pattern" }));
    expect(await screen.findByRole("heading", { name: "New pattern" })).toBeTruthy();
    // Nothing named and no day covered yet.
    expect(saveButton().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  Dad's weekends " } });
    fireEvent.change(screen.getByLabelText("Cycle length"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Anchor date"), { target: { value: "2026-09-07" } });
    // Sunday-first buttons; the body keeps Monday=0 numbering.
    const week1 = weekGroup(1);
    expect(within(week1).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Su",
      "Mo",
      "Tu",
      "We",
      "Th",
      "Fr",
      "Sa",
    ]);
    fireEvent.click(within(week1).getByRole("button", { name: "Saturday" }));
    fireEvent.click(within(week1).getByRole("button", { name: "Sunday" }));
    expect(saveButton().disabled).toBe(false);

    const before = calls().length;
    fireEvent.click(saveButton());
    const row = await screen.findByTestId("pattern-50");
    expect(screen.queryByRole("heading", { name: "New pattern" })).toBeNull();

    expect(writes()).toEqual([
      {
        method: "POST",
        path: "/api/v1/admin/children/3/presence-patterns",
        body: {
          name: "Dad's weekends",
          kind: "away",
          cycle_length_weeks: 2,
          anchor_date: "2026-09-07",
          pattern: { "0": [5, 6], "1": [] },
        },
      },
    ]);
    const after = calls().slice(before);
    expect(after.some((c) => c.method === "GET" && c.path === "/api/v1/admin/children/3/presence-patterns")).toBe(
      true,
    );
    expect(within(row).getByText("Dad's weekends")).toBeTruthy();
    expect(within(row).getByText("Away · Every 2 weeks")).toBeTruthy();
    expect(day("2026-09-12").dataset.state).toBe("away");
    expect(day("2026-09-19").dataset.state).toBe("home");
    // Focus returns to the Add control of the patterns section.
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Add pattern" }));
  });

  it("Add can save a Home pattern", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Rory" }));
    fireEvent.click(screen.getByRole("button", { name: "Add pattern" }));
    await screen.findByRole("heading", { name: "New pattern" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "School nights" } });
    fireEvent.click(screen.getByRole("button", { name: "Home" }));
    fireEvent.click(within(weekGroup(1)).getByRole("button", { name: "Monday" }));
    fireEvent.click(saveButton());
    await screen.findByTestId("pattern-50");
    expect(writes()[0].body).toEqual({
      name: "School nights",
      kind: "home",
      cycle_length_weeks: 1,
      anchor_date: TODAY,
      pattern: { "0": [0] },
    });
    // A home pattern: uncovered days are now away.
    expect(day("2026-09-14").dataset.state).toBe("home"); // Monday
    expect(day("2026-09-15").dataset.state).toBe("away"); // Tuesday
  });

  it("Edit PATCHes only the changed fields to /presence-patterns/{id} and refreshes", async () => {
    await selectMaeve();
    fireEvent.click(screen.getByRole("button", { name: "Edit Alternate weekends" }));
    expect(await screen.findByRole("heading", { name: "Edit pattern" })).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Alternate weekends");
    expect((screen.getByLabelText("Cycle length") as HTMLSelectElement).value).toBe("2");
    expect((screen.getByLabelText("Anchor date") as HTMLInputElement).value).toBe("2026-09-07");
    expect(within(weekGroup(1)).getByRole("button", { name: "Saturday" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    // Unchanged: nothing to save.
    expect(saveButton().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Every other weekend" } });
    fireEvent.click(within(weekGroup(1)).getByRole("button", { name: "Sunday" }));
    const before = calls().length;
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Edit pattern" })).toBeNull());

    expect(writes()).toEqual([
      {
        method: "PATCH",
        path: `${PATTERNS_PATH}/3`,
        body: { name: "Every other weekend", pattern: { "0": [5], "1": [] } },
      },
    ]);
    const after = calls().slice(before);
    expect(after.some((c) => c.method === "GET" && c.path === "/api/v1/admin/children/2/presence-patterns")).toBe(
      true,
    );
    const row = await screen.findByText("Every other weekend");
    expect(within(row.closest("li")!).getByText("Week 1: Sat · Week 2: No days")).toBeTruthy();
    expect(day("2026-09-12").dataset.state).toBe("away"); // Sat, on week
    expect(day("2026-09-13").dataset.state).toBe("home"); // Sun no longer covered
  });

  it("Delete asks first, DELETEs /presence-patterns/{id} and refreshes the list", async () => {
    await selectMaeve();
    fireEvent.click(screen.getByRole("button", { name: "Delete Thursday+Friday" }));
    const confirm = within(screen.getByTestId("pattern-2")).getByRole("group", { name: "Confirm delete" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Keep" }));
    expect(writes()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Delete Thursday+Friday" }));
    fireEvent.click(within(screen.getByTestId("pattern-2")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByTestId("pattern-2")).toBeNull());
    expect(writes()).toEqual([{ method: "DELETE", path: `${PATTERNS_PATH}/2`, body: undefined }]);
    expect(screen.getByTestId("pattern-3")).toBeTruthy();
    expect(day("2026-09-17").dataset.state).toBe("home"); // Thursday, no longer away
    expect(day("2026-09-12").dataset.state).toBe("away"); // weekends pattern still applies
  });

  it("deleting the last pattern leaves the child with none: home every day", async () => {
    await renderReady();
    expect(day("2026-09-15").dataset.state).toBe("away");
    fireEvent.click(screen.getByRole("button", { name: "Delete Home weeks" }));
    fireEvent.click(within(screen.getByTestId("pattern-1")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByTestId("patterns-empty")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Presence patterns" })).toBeNull();
    expect(patterns[1]).toEqual([]);
    expect(day("2026-09-15").dataset.state).toBe("home");
    expect(day("2026-09-11").dataset.state).toBe("override-away"); // overrides still win
    expect(screen.getByText("Declan · no patterns, home every day")).toBeTruthy();
  });

  it("a 422 on save shows the API detail naming the field and keeps the editor open", async () => {
    writeFailure = jsonResponse({ detail: "name must not be empty" }, 422);
    await selectMaeve();
    fireEvent.click(screen.getByRole("button", { name: "Edit Thursday+Friday" }));
    await screen.findByRole("heading", { name: "Edit pattern" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Thu/Fri" } });
    fireEvent.click(saveButton());

    const alert = await screen.findByTestId("pattern-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.textContent).toBe("name must not be empty");
    expect(screen.getByRole("heading", { name: "Edit pattern" })).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Thu/Fri");
    expect(saveButton().disabled).toBe(false);
  });

  it("a 403 on add is surfaced as the refusal, not swallowed", async () => {
    writeFailure = new Response("", { status: 403 });
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Add pattern" }));
    await screen.findByRole("heading", { name: "New pattern" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Fridays" } });
    fireEvent.click(within(weekGroup(1)).getByRole("button", { name: "Friday" }));
    fireEvent.click(saveButton());
    const alert = await screen.findByTestId("pattern-error");
    expect(alert.textContent).toBe("Your account is not in the nestquest-admins group.");
    expect(patterns[1]).toEqual([DECLAN_HOME]);
  });

  it("a 403 on delete is surfaced and the pattern stays listed", async () => {
    writeFailure = new Response("", { status: 403 });
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Delete Home weeks" }));
    fireEvent.click(within(screen.getByTestId("pattern-1")).getByRole("button", { name: "Delete" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Your account is not in the nestquest-admins group.");
    expect(screen.getByTestId("pattern-1")).toBeTruthy();
  });

  it("a 422 on delete shows the API detail", async () => {
    writeFailure = jsonResponse({ detail: "pattern_id must be an integer" }, 422);
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Delete Home weeks" }));
    fireEvent.click(within(screen.getByTestId("pattern-1")).getByRole("button", { name: "Delete" }));
    expect((await screen.findByRole("alert")).textContent).toBe("pattern_id must be an integer");
  });

  it("Cancel closes the editor without any request", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Add pattern" }));
    await screen.findByRole("heading", { name: "New pattern" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("heading", { name: "New pattern" })).toBeNull();
    expect(writes()).toEqual([]);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Add pattern" }));
  });

  it("never calls the removed one-per-child /presence-schedule route", async () => {
    await selectMaeve();
    // Add, edit and delete: every pattern path the screen can take.
    fireEvent.click(screen.getByRole("button", { name: "Add pattern" }));
    await screen.findByRole("heading", { name: "New pattern" });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Mondays" } });
    fireEvent.click(within(weekGroup(1)).getByRole("button", { name: "Monday" }));
    fireEvent.click(saveButton());
    await screen.findByTestId("pattern-50");
    fireEvent.click(screen.getByRole("button", { name: "Edit Mondays" }));
    await screen.findByRole("heading", { name: "Edit pattern" });
    fireEvent.click(screen.getByRole("button", { name: "Home" }));
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Edit pattern" })).toBeNull());
    fireEvent.click(await screen.findByRole("button", { name: "Delete Mondays" }));
    fireEvent.click(within(screen.getByTestId("pattern-50")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByTestId("pattern-50")).toBeNull());

    expect(writes().map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /api/v1/admin/children/2/presence-patterns",
      `PATCH ${PATTERNS_PATH}/50`,
      `DELETE ${PATTERNS_PATH}/50`,
    ]);
    expect(calls().filter((c) => c.path.includes("presence-schedule"))).toEqual([]);
  });

  it("scroll column ends with 92px bottom padding", async () => {
    await renderReady();
    expect(screen.getByTestId("schedule-scroll").style.paddingBottom).toBe("92px");
  });

  it("shows an error state on a failed load and retries", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    render(<ScheduleTab today={TODAY} />);
    const error = await screen.findByTestId("schedule-error");
    expect(error.textContent).toContain("could not be loaded");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("pattern-1")).toBeTruthy();
  });
});
