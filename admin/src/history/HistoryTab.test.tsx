import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import HistoryTab, { FOOTER_NOTE, computeStats } from "./HistoryTab";
import type { HistoryFilter, HistoryRow } from "../api/history";
import { storeTokens } from "../auth/oidc";

const TODAY = "2026-09-23";

function row(overrides: Partial<HistoryRow>): HistoryRow {
  return {
    occurred_at: null,
    event_type: "completed",
    child_name: "Declan",
    child_id: 1,
    quest_title: "Brush teeth",
    instance_id: 1,
    window: "morning",
    due_date: TODAY,
    due_time: null,
    actor: "panel (Declan)",
    was_on_time: true,
    ...overrides,
  };
}

// America/Los_Angeles is UTC-7 in September.
const BRUSH = row({
  instance_id: 1,
  occurred_at: "2026-09-23T14:04:00Z", // 7:04 AM
  due_time: "07:30",
});
const BED_DONE = row({
  instance_id: 2,
  quest_title: "Make bed",
  child_name: "Maeve",
  child_id: 2,
  occurred_at: "2026-09-23T14:50:00Z", // 7:50 AM
  actor: "panel (Maeve)",
});
const BED_UNDONE = row({
  instance_id: 2,
  event_type: "uncompleted",
  quest_title: "Make bed",
  child_name: "Maeve",
  child_id: 2,
  occurred_at: "2026-09-23T15:10:00Z", // 8:10 AM
  actor: "joshua (admin)",
  was_on_time: null,
});
const CAT_LATE = row({
  instance_id: 3,
  quest_title: "Feed cat",
  due_date: "2026-09-22",
  due_time: "07:00",
  occurred_at: "2026-09-22T14:22:00Z", // 7:22 AM, 22 min after due
  was_on_time: false,
});
// 7:30 PM local on Sep 22 — already Sep 23 in UTC.
const HOMEWORK_LATE = row({
  instance_id: 4,
  quest_title: "Homework",
  child_name: "Rory",
  child_id: 3,
  due_date: "2026-09-22",
  due_time: null,
  occurred_at: "2026-09-23T02:30:00Z",
  actor: "panel (Rory)",
  was_on_time: false,
});
const PLANTS_MISSED = row({
  instance_id: 5,
  event_type: "missed",
  quest_title: "Water plants",
  child_name: "Rory",
  child_id: 3,
  due_date: "2026-09-21",
  due_time: "18:00",
  actor: "nightly sweep",
  was_on_time: null,
});

// The API's order: due_date, then instance, then event id.
const ROWS: Record<HistoryFilter, HistoryRow[]> = {
  all: [CAT_LATE, HOMEWORK_LATE, BRUSH, BED_DONE, BED_UNDONE],
  reversals: [BED_UNDONE],
  missed: [PLANTS_MISSED],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function routeFetch(url: string): Response {
  const parsed = new URL(url, "http://x");
  if (!parsed.pathname.endsWith("/api/v1/admin/history")) {
    return jsonResponse({ detail: "unexpected" }, 500);
  }
  const filter = parsed.searchParams.get("filter") as HistoryFilter;
  const rows = ROWS[filter];
  return jsonResponse({
    filter,
    start: parsed.searchParams.get("start"),
    end: parsed.searchParams.get("end"),
    count: rows.length,
    rows,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function historyCalls(): URL[] {
  return fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://x"));
}

function metas(section: HTMLElement): string[] {
  return within(section)
    .getAllByTestId("history-meta")
    .map((el) => el.textContent ?? "");
}

async function renderReady() {
  render(<HistoryTab today={TODAY} />);
  await screen.findByTestId("stat-on-time");
}

describe("HistoryTab", () => {
  beforeAll(() => {
    vi.stubEnv("TZ", "America/Los_Angeles");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    fetchMock = vi.fn((url: string) => Promise.resolve(routeFetch(url)));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the header and queries the last 14 days with the Bearer token", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: "History" })).toBeTruthy();
    expect(screen.getByText("Append-only event log · last 14 days")).toBeTruthy();

    const calls = historyCalls();
    expect(calls.length).toBeGreaterThan(0);
    for (const url of calls) {
      expect(url.pathname).toBe("/api/v1/admin/history");
      expect(url.searchParams.get("start")).toBe("2026-09-10");
      expect(url.searchParams.get("end")).toBe(TODAY);
    }
    expect(calls.map((url) => url.searchParams.get("filter")).sort()).toEqual(["all", "missed"]);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer at-123");
  });

  it("stat row shows On time %, Completed and Missed for the period", async () => {
    await renderReady();
    // 4 completions (2 on time) in `all`; 1 derived missed row.
    expect(screen.getByTestId("stat-on-time").textContent).toBe("50%On time");
    expect(screen.getByTestId("stat-completed").textContent).toBe("4Completed");
    expect(screen.getByTestId("stat-missed").textContent).toBe("1Missed");
  });

  it("On time shows — when the period has no completions", () => {
    expect(computeStats([BED_UNDONE], [])).toEqual({ onTimePct: null, completed: 0, missed: 0 });
  });

  it("groups rows by local day, newest first, with event type, actor and on-time meta", async () => {
    await renderReady();

    const today = screen.getByTestId(`day-${TODAY}`);
    expect(within(today).getByRole("heading").textContent).toBe("Today");
    expect(metas(today)).toEqual([
      "uncompleted · joshua (admin)",
      "completed · panel (Maeve) · on time",
      "completed · panel (Declan) · on time",
    ]);
    expect(within(today).getAllByText("Make bed · Maeve")).toHaveLength(2);
    expect(within(today).getByText("8:10 AM")).toBeTruthy();

    // The 7:30 PM completion is Sep 23 in UTC but Sep 22 locally.
    const yesterday = screen.getByTestId("day-2026-09-22");
    expect(within(yesterday).getByRole("heading").textContent).toBe("Yesterday");
    expect(metas(yesterday)).toEqual([
      "completed · panel (Rory) · late",
      "completed · panel (Declan) · late 22 min",
    ]);
    expect(within(yesterday).getByText("7:30 PM")).toBeTruthy();

    const dots = screen.getAllByTestId("history-dot").map((el) => el.className);
    expect(dots[0]).toContain("history-dot--uncompleted");
    expect(dots[1]).toContain("history-dot--completed");
  });

  it("each filter chip re-queries the API with its filter and re-renders", async () => {
    await renderReady();

    fireEvent.click(screen.getByRole("button", { name: "Reversals" }));
    await waitFor(() =>
      expect(historyCalls().some((url) => url.searchParams.get("filter") === "reversals")).toBe(true),
    );
    await waitFor(() => expect(screen.getAllByTestId("history-row")).toHaveLength(1));
    expect(screen.getByTestId("history-meta").textContent).toBe("uncompleted · joshua (admin)");
    expect(screen.getByRole("button", { name: "Reversals" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Missed" }));
    const missedDay = await screen.findByTestId("day-2026-09-21");
    expect(within(missedDay).getByRole("heading").textContent).toBe("Mon, Sep 21");
    expect(metas(missedDay)).toEqual(["missed · nightly sweep"]);
    expect(within(missedDay).getByTestId("history-dot").className).toContain("history-dot--missed");
    expect(within(missedDay).getByText("6:00 PM")).toBeTruthy();
    // Stats stay the period's numbers whichever chip is selected.
    expect(screen.getByTestId("stat-completed").textContent).toBe("4Completed");

    fetchMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "All events" }));
    await screen.findByTestId(`day-${TODAY}`);
    expect(historyCalls().map((url) => url.searchParams.get("filter"))).toContain("all");
    expect(screen.getAllByTestId("history-row")).toHaveLength(5);
  });

  it("shows the append-only footer and an inert CSV button", async () => {
    await renderReady();
    expect(FOOTER_NOTE).toBe("Events are never edited or deleted. A reversal is its own row.");
    expect(screen.getByTestId("history-footer").textContent).toBe(FOOTER_NOTE);

    const csv = screen.getByRole("button", { name: "CSV" });
    const before = fetchMock.mock.calls.length;
    fireEvent.click(csv);
    expect(fetchMock.mock.calls.length).toBe(before);
  });

  it("rows are read-only: no row carries a control", async () => {
    await renderReady();
    for (const el of screen.getAllByTestId("history-row")) {
      expect(within(el).queryByRole("button")).toBeNull();
    }
  });

  it("a failed fetch shows the error state and Try again reloads", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ detail: "boom" }, 500)));
    render(<HistoryTab today={TODAY} />);

    const error = await screen.findByTestId("history-error");
    expect(error.textContent).toContain("The history could not be loaded");
    expect(screen.getByTestId("history-footer")).toBeTruthy();

    fetchMock.mockImplementation((url: string) => Promise.resolve(routeFetch(url)));
    fireEvent.click(within(error).getByRole("button", { name: "Try again" }));
    await screen.findByTestId("stat-on-time");
    expect(screen.queryByTestId("history-error")).toBeNull();
  });

  it("the scroll column ends with 92px bottom padding", async () => {
    await renderReady();
    expect(screen.getByTestId("history-scroll").style.paddingBottom).toBe("92px");
  });
});
