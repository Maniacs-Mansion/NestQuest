import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import TodayTab, { PERMISSION_NOTE } from "./TodayTab";
import type { AdminSnapshot, SnapshotInstance } from "../api/snapshot";
import { storeTokens } from "../auth/oidc";

function instance(overrides: Partial<SnapshotInstance>): SnapshotInstance {
  return {
    id: 0,
    definition_id: 1,
    child_id: 1,
    title: "Quest",
    icon: null,
    window: "morning",
    due_time: null,
    state: "open",
    overdue: false,
    completed_at: null,
    on_time: null,
    ...overrides,
  };
}

const SNAPSHOT: AdminSnapshot = {
  today_iso: "2026-09-23",
  cycle_day: 5,
  children: [
    {
      child_id: 1,
      child_name: "Declan",
      present: true,
      next_present: null,
      due_today: 7,
      completed_today: 3,
      remaining_today: 4,
      completion_pct: 43,
      instances: [
        instance({ id: 11, title: "Brush teeth", due_time: "07:30", overdue: true }),
        instance({
          id: 12,
          title: "Make bed",
          state: "completed",
          completed_at: "2026-09-23T11:04:00Z",
          on_time: true,
        }),
        instance({ id: 13, title: "Homework", window: "afternoon", due_time: "16:00" }),
        // Overdue but already completed: not counted as overdue.
        instance({
          id: 14,
          title: "Pack bag",
          state: "completed",
          overdue: true,
          completed_at: "2026-09-23T10:00:00Z",
          on_time: false,
        }),
      ],
    },
    {
      child_id: 2,
      child_name: "Maeve",
      present: true,
      next_present: null,
      due_today: 4,
      completed_today: 4,
      remaining_today: 0,
      completion_pct: 100,
      instances: [],
    },
    {
      child_id: 3,
      child_name: "Rory",
      present: false,
      next_present: "2026-10-01",
      due_today: 0,
      completed_today: 0,
      remaining_today: 0,
      completion_pct: 0,
      instances: [],
    },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

async function renderReady() {
  fetchMock.mockResolvedValue(jsonResponse(SNAPSHOT));
  render(<TodayTab />);
  await screen.findByText("Declan");
}

describe("TodayTab", () => {
  beforeAll(() => {
    // A negative-offset zone: `new Date("2026-09-23")` would read as Sep 22 here.
    vi.stubEnv("TZ", "America/Los_Angeles");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("fetches the admin snapshot with the Bearer token", async () => {
    await renderReady();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/admin\/snapshot$/);
    expect(init.headers.Authorization).toBe("Bearer at-123");
  });

  it("header shows the weekday, date and cycle day", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: "Today" })).toBeTruthy();
    expect(screen.getByText("Wednesday, September 23 · cycle day 5 of 14")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Settings" })).toBeTruthy();
  });

  it("stat row shows done, remaining and overdue totals", async () => {
    await renderReady();
    expect(screen.getByTestId("stat-done").textContent).toBe("7Done");
    expect(screen.getByTestId("stat-remaining").textContent).toBe("4Remaining");
    expect(screen.getByTestId("stat-overdue").textContent).toBe("1Overdue");
  });

  it("present child row shows progress meta and fill", async () => {
    await renderReady();
    const row = screen.getByTestId("child-1");
    expect(within(row).getByText("3 of 7 · 1 overdue")).toBeTruthy();
    const bar = within(row).getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("43");
    expect((bar.firstElementChild as HTMLElement).style.width).toBe("43%");
    expect(row.className).not.toContain("today-child--away");
  });

  it("all-done child renders the success state", async () => {
    await renderReady();
    const meta = within(screen.getByTestId("child-2")).getByText("4 of 4 · all done");
    expect(meta.className).toContain("today-child-meta--done");
  });

  it("away child shows the return date and the flat avatar", async () => {
    await renderReady();
    const row = screen.getByTestId("child-3");
    expect(within(row).getByText("Away · returns Oct 1")).toBeTruthy();
    expect(row.className).toContain("today-child--away");
    expect(within(row).getByTestId("child-avatar").textContent).toBe("R");
  });

  it("needs-attention lists overdue and completed rows with their actions", async () => {
    await renderReady();
    const list = screen.getByRole("list", { name: "Needs attention" });
    const overdue = within(list).getByTestId("attention-11");
    expect(within(overdue).getByText("Brush teeth · Declan")).toBeTruthy();
    expect(within(overdue).getByText("Overdue since 7:30 AM")).toBeTruthy();
    expect(within(overdue).getByRole("button", { name: "Mark done" })).toBeTruthy();

    const completed = within(list).getByTestId("attention-12");
    expect(within(completed).getByText("Make bed · Declan")).toBeTruthy();
    // 11:04Z is 4:04 AM in Los Angeles (PDT).
    expect(within(completed).getByText("Completed 4:04 AM")).toBeTruthy();
    expect(within(completed).getByRole("button", { name: "Undo" })).toBeTruthy();

    // Open, not-overdue instances do not need attention.
    expect(within(list).queryByTestId("attention-13")).toBeNull();
    // No actor in the payload, so no "from panel".
    expect(list.textContent).not.toContain("from panel");
  });

  it("permission note carries the exact copy", async () => {
    await renderReady();
    expect(PERMISSION_NOTE).toBe(
      "Undo is admin-only. A panel tap can never reverse a completion.",
    );
    expect(screen.getByTestId("permission-note").textContent).toBe(PERMISSION_NOTE);
  });

  it("scroll column ends with 92px bottom padding", async () => {
    await renderReady();
    expect(screen.getByTestId("today-scroll").style.paddingBottom).toBe("92px");
  });

  it("shows a loading state while the snapshot is in flight", () => {
    fetchMock.mockReturnValue(new Promise<Response>(() => {}));
    render(<TodayTab />);
    expect(screen.getByTestId("today-loading").textContent).toContain("Loading");
    expect(screen.getByTestId("today-scroll").style.paddingBottom).toBe("92px");
  });

  it("shows an error state on a failed fetch and retries", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    render(<TodayTab />);
    const error = await screen.findByTestId("today-error");
    expect(error.getAttribute("role")).toBe("alert");
    expect(error.textContent).toContain("could not be loaded");

    fetchMock.mockResolvedValueOnce(jsonResponse(SNAPSHOT));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Declan")).toBeTruthy();
  });

  it("shows the refusal message when the API answers 403", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 403 }));
    render(<TodayTab />);
    const error = await screen.findByTestId("today-error");
    expect(error.textContent).toContain("nestquest-admins");
  });
});
