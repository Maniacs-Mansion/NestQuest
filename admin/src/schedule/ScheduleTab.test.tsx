import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import ScheduleTab from "./ScheduleTab";
import type { AdminChild } from "../api/definitions";
import type { PresenceOverride, PresenceSchedule } from "../api/presence";
import { storeTokens } from "../auth/oidc";

function child(id: number, display_name: string, sort_order: number, is_active = true): AdminChild {
  return { id, display_name, colour: null, avatar_ref: null, sort_order, is_active };
}

const CHILDREN = [
  child(3, "Rory", 3),
  child(1, "Declan", 1),
  child(2, "Maeve", 2),
  child(9, "Former", 4, false),
];

// Declan: anchor Monday 2026-09-07; cycle week 0 home every day, week 1 Sat/Sun.
// Keys arrive as JSON strings, exactly as the API serializes them.
const DECLAN: PresenceSchedule = {
  child_id: 1,
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { "0": [0, 1, 2, 3, 4, 5, 6], "1": [5, 6] },
};

const MAEVE: PresenceSchedule = {
  child_id: 2,
  cycle_length_weeks: 4,
  anchor_date: "2026-09-07",
  pattern: { "0": [0, 1, 2, 3, 4, 5, 6], "1": [], "2": [0, 1, 2, 3, 4, 5, 6], "3": [] },
};

const OVERRIDES: PresenceOverride[] = [
  { id: 41, child_id: 1, start_date: "2026-09-10", end_date: "2026-09-12", is_present: false, note: "Dentist trip" },
  { id: 42, child_id: 1, start_date: "2026-09-16", end_date: "2026-09-16", is_present: true, note: null },
  { id: 43, child_id: 2, start_date: "2026-09-28", end_date: "2026-10-02", is_present: false, note: "Camp" },
];

const TODAY = "2026-09-23";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
let putResponse: (body: unknown) => Response;

function routeFetch(url: string, init: RequestInit = {}): Response {
  const path = new URL(url, "http://x").pathname;
  if (init.method === "PUT") return putResponse(JSON.parse(String(init.body)));
  if (path.endsWith("/admin/children")) return jsonResponse({ children: CHILDREN });
  const match = /\/children\/(\d+)\/presence-schedule$/.exec(path);
  if (match) {
    const id = Number(match[1]);
    return jsonResponse({ schedule: id === 1 ? DECLAN : id === 2 ? MAEVE : null });
  }
  if (path.endsWith("/presence-overrides")) return jsonResponse({ overrides: OVERRIDES });
  return jsonResponse({ detail: "unexpected" }, 500);
}

function day(date: string): HTMLElement {
  const cell = document.querySelector<HTMLElement>(`[data-date="${date}"]`);
  if (!cell) throw new Error(`no cell for ${date}`);
  return cell;
}

async function renderReady() {
  render(<ScheduleTab today={TODAY} />);
  await screen.findByTestId("pattern-1");
}

describe("ScheduleTab", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    putResponse = (body) => jsonResponse({ child_id: 1, ...(body as object) });
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads active children, their schedules and the overrides", async () => {
    await renderReady();
    const urls = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://x").pathname);
    expect(urls).toContain("/api/v1/admin/children");
    expect(urls).toContain("/api/v1/admin/children/1/presence-schedule");
    expect(urls).toContain("/api/v1/admin/children/2/presence-schedule");
    expect(urls).toContain("/api/v1/admin/children/3/presence-schedule");
    expect(urls).not.toContain("/api/v1/admin/children/9/presence-schedule");
    expect(urls).toContain("/api/v1/admin/presence-overrides");
    const chips = within(screen.getByRole("group", { name: "Child" })).getAllByRole("button");
    expect(chips.map((chip) => chip.textContent)).toEqual(["Declan", "Maeve", "Rory"]);
    expect(chips[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("header shows the cycle length and anchor", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: "Schedule" })).toBeTruthy();
    expect(screen.getByText("2-week cycle · anchor Monday, Sep 7")).toBeTruthy();
  });

  it("month grid renders home, away, override and today states from the anchor", async () => {
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
    expect(grid.children[7].tagName).toBe("SPAN");
    expect(grid.children[8].tagName).toBe("SPAN");
    expect(grid.children[9].getAttribute("data-date")).toBe("2026-09-01");

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Home",
      "Away",
      "Override · away",
      "Override · home",
      "Today",
    ]);
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

  it("presence pattern card shows a rule per child", async () => {
    await renderReady();
    expect(within(screen.getByTestId("pattern-1")).getByText("Weeks 1 & 2 of cycle")).toBeTruthy();
    expect(within(screen.getByTestId("pattern-2")).getByText("Weeks 1 & 3 of cycle")).toBeTruthy();
    expect(within(screen.getByTestId("pattern-3")).getByText("Every day")).toBeTruthy();
  });

  it("overrides card lists the selected child's overrides with inert actions", async () => {
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
    expect(screen.getByText("4-week cycle · anchor Monday, Sep 7")).toBeTruthy();
  });

  it("a child with no schedule is home every day and defaults to a 2-week cycle", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Rory" }));
    expect(screen.getByText("2-week cycle · anchor Tuesday, Sep 1")).toBeTruthy();
    expect(day("2026-09-15").dataset.state).toBe("home");
    expect(screen.getByText("No overrides for Rory.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save pattern" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("editing a day and saving PUTs the pattern; the grid reflects the saved schedule", async () => {
    await renderReady();
    expect(day("2026-09-01").dataset.state).toBe("away");
    fireEvent.click(day("2026-09-01")); // cycle week 1 (pre-anchor), Tuesday

    // The draft already shows the edit, and every other week-1 Tuesday follows.
    expect(day("2026-09-01").dataset.state).toBe("home");
    expect(day("2026-09-15").dataset.state).toBe("home");
    expect(day("2026-09-08").dataset.state).toBe("home");

    fireEvent.click(screen.getByRole("button", { name: "Save pattern" }));
    expect(await screen.findByText("Pattern saved.")).toBeTruthy();

    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(put).toBeTruthy();
    const [url, init] = put!;
    expect(new URL(String(url), "http://x").pathname).toBe("/api/v1/admin/children/1/presence-schedule");
    expect(init.headers.Authorization).toBe("Bearer at-123");
    expect(JSON.parse(init.body)).toEqual({
      cycle_length_weeks: 2,
      anchor_date: "2026-09-07",
      pattern: { "0": [0, 1, 2, 3, 4, 5, 6], "1": [1, 5, 6] },
    });

    expect(day("2026-09-15").dataset.state).toBe("home");
    expect(day("2026-09-29").dataset.state).toBe("home");
    expect(day("2026-09-30").dataset.state).toBe("away");
    expect((screen.getByRole("button", { name: "Save pattern" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("saves an edited anchor date and cycle length", async () => {
    await renderReady();
    fireEvent.change(screen.getByLabelText("Anchor date"), { target: { value: "2026-09-14" } });
    fireEvent.change(screen.getByLabelText("Cycle length"), { target: { value: "3" } });
    expect(screen.getByText("3-week cycle · anchor Monday, Sep 14")).toBeTruthy();
    // Anchor moved a week: Sep 7-13 is now the last week of the cycle (full, added).
    fireEvent.click(screen.getByRole("button", { name: "Save pattern" }));
    await screen.findByText("Pattern saved.");
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(init.body)).toEqual({
      cycle_length_weeks: 3,
      anchor_date: "2026-09-14",
      pattern: {
        "0": [0, 1, 2, 3, 4, 5, 6],
        "1": [5, 6],
        "2": [0, 1, 2, 3, 4, 5, 6],
      },
    });
  });

  it("a 422 shows the API detail and keeps the draft", async () => {
    putResponse = () => jsonResponse({ detail: "anchor_date must be a Monday" }, 422);
    await renderReady();
    fireEvent.click(day("2026-09-01"));
    fireEvent.click(screen.getByRole("button", { name: "Save pattern" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("anchor_date must be a Monday");
    expect(day("2026-09-01").dataset.state).toBe("home");
    expect((screen.getByRole("button", { name: "Save pattern" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    // The saved rule is unchanged.
    expect(within(screen.getByTestId("pattern-1")).getByText("Weeks 1 & 2 of cycle")).toBeTruthy();
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
