import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import TodayTab, { PERMISSION_NOTE } from "./TodayTab";
import type { AdminSnapshot, SnapshotInstance } from "../api/snapshot";
import { TransitionsProvider } from "../api/useTransitions";
import { frame, testStream, type TestStream } from "../api/testStream";
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

/** SNAPSHOT after instance 12 ("Make bed") is reversed back to open. */
const AFTER_UNDO: AdminSnapshot = {
  ...SNAPSHOT,
  children: SNAPSHOT.children.map((child) =>
    child.child_id !== 1
      ? child
      : {
          ...child,
          completed_today: 2,
          remaining_today: 5,
          completion_pct: 29,
          instances: child.instances.map((i) =>
            i.id === 12 ? { ...i, state: "open" as const, completed_at: null, on_time: null } : i,
          ),
        },
  ),
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("TodayTab Undo and live updates", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let snapshots: AdminSnapshot[];
  let uncomplete: () => Promise<Response>;
  let streams: TestStream[];

  function calls(pathSuffix: string, method = "GET") {
    return fetchMock.mock.calls.filter(
      ([url, init]) =>
        new URL(String(url), "http://x").pathname.endsWith(pathSuffix) &&
        (init?.method ?? "GET") === method,
    );
  }

  beforeAll(() => {
    vi.stubEnv("TZ", "America/Los_Angeles");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    snapshots = [SNAPSHOT, AFTER_UNDO];
    uncomplete = () =>
      Promise.resolve(jsonResponse({ instance_id: 12, state: "open", appended: true }));
    streams = [];
    fetchMock = vi.fn((url: string) => {
      const path = new URL(url, "http://x").pathname;
      if (path.endsWith("/api/v1/admin/snapshot")) {
        const next = snapshots.length > 1 ? snapshots.shift()! : snapshots[0];
        return Promise.resolve(jsonResponse(next));
      }
      if (path.endsWith("/api/v1/admin/instances/12/uncomplete")) return uncomplete();
      if (path.endsWith("/api/v1/admin/events")) {
        const stream = testStream();
        streams.push(stream);
        return Promise.resolve(stream.response);
      }
      return Promise.resolve(jsonResponse({ detail: "unexpected" }, 500));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("Undo POSTs uncomplete for the completed instance and refetches the snapshot", async () => {
    render(<TodayTab />);
    const row = await screen.findByTestId("attention-12");
    fireEvent.click(within(row).getByRole("button", { name: "Undo" }));

    await waitFor(() => expect(screen.queryByTestId("attention-12")).toBeNull());
    const posts = calls("/api/v1/admin/instances/12/uncomplete", "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0][1].headers.Authorization).toBe("Bearer at-123");
    expect(calls("/api/v1/admin/snapshot")).toHaveLength(2);
    // The reversed instance is open again: one fewer done, one more remaining.
    expect(screen.getByTestId("stat-done").textContent).toBe("6Done");
    expect(screen.getByTestId("stat-remaining").textContent).toBe("5Remaining");
    expect(screen.queryByTestId("today-undo-error")).toBeNull();
  });

  it("disables Undo while the request is in flight (no double submit)", async () => {
    const pending = deferred<Response>();
    uncomplete = () => pending.promise;
    render(<TodayTab />);
    const row = await screen.findByTestId("attention-12");
    const button = within(row).getByRole("button", { name: "Undo" }) as HTMLButtonElement;

    fireEvent.click(button);
    await waitFor(() => expect(button.disabled).toBe(true));
    expect(button.textContent).toBe("Undoing…");
    // Every Undo is disabled while one reversal is in flight.
    const other = within(screen.getByTestId("attention-14")).getByRole("button", {
      name: "Undo",
    }) as HTMLButtonElement;
    expect(other.disabled).toBe(true);
    fireEvent.click(button);
    fireEvent.click(other);
    expect(calls("/api/v1/admin/instances/12/uncomplete", "POST")).toHaveLength(1);
    expect(calls("/uncomplete", "POST")).toHaveLength(1);

    pending.resolve(jsonResponse({ instance_id: 12, state: "open", appended: true }));
    await waitFor(() => expect(screen.queryByTestId("attention-12")).toBeNull());
    expect(other.disabled).toBe(false);
  });

  it("a failed Undo shows a message and leaves the view intact", async () => {
    uncomplete = () => Promise.resolve(jsonResponse({ detail: "instance 12 not found" }, 404));
    render(<TodayTab />);
    const row = await screen.findByTestId("attention-12");
    fireEvent.click(within(row).getByRole("button", { name: "Undo" }));

    const alert = await screen.findByTestId("today-undo-error");
    expect(alert.textContent).toContain("The completion could not be undone: instance 12 not found");
    // Still the original snapshot: nothing refetched, the row and its Undo remain usable.
    expect(calls("/api/v1/admin/snapshot")).toHaveLength(1);
    const button = within(screen.getByTestId("attention-12")).getByRole("button", {
      name: "Undo",
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(screen.getByTestId("stat-done").textContent).toBe("7Done");

    fireEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByTestId("today-undo-error")).toBeNull();
  });

  it("Mark done stays inert", async () => {
    render(<TodayTab />);
    const row = await screen.findByTestId("attention-11");
    fireEvent.click(within(row).getByRole("button", { name: "Mark done" }));
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it("a transition on the live stream refetches the snapshot without a reload", async () => {
    const { unmount } = render(
      <TransitionsProvider>
        <TodayTab />
      </TransitionsProvider>,
    );
    await screen.findByTestId("attention-12");
    await waitFor(() => expect(streams).toHaveLength(1));
    const [, init] = calls("/api/v1/admin/events")[0];
    expect(init.headers.Authorization).toBe("Bearer at-123");

    // An uncompletion made elsewhere, its frame split across two chunks.
    const text = frame("nestquest_quest_uncompleted", {
      child_id: 1,
      child_name: "Declan",
      instance_id: 12,
      quest_title: "Make bed",
      window: "morning",
      due_date: "2026-09-23",
      due_time: null,
      occurred_at: "2026-09-23T12:00:00Z",
    });
    streams[0].push(text.slice(0, 25));
    streams[0].push(text.slice(25));

    await waitFor(() => expect(calls("/api/v1/admin/snapshot")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByTestId("attention-12")).toBeNull());
    // Refreshed in place: the loading state never replaced the view.
    expect(screen.queryByTestId("today-loading")).toBeNull();

    const signal = init.signal as AbortSignal;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(streams[0].cancelled()).toBe(true));
  });
});
