import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import HistoryTab, { FOOTER_NOTE, computeStats } from "./HistoryTab";
import type { HistoryFilter, HistoryRow } from "../api/history";
import { storeTokens } from "../auth/oidc";
import { TransitionsProvider } from "../api/useTransitions";
import { frame, testStream, type TestStream } from "../api/testStream";

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

const CSV_BODY = "occurred_at,event_type\n2026-09-23T14:04:00Z,completed\n";

function csvResponse(filter: string, start: string, end: string): Response {
  return new Response(`${filter}\n${CSV_BODY}`, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="nestquest-history-${start}-to-${end}.csv"`,
    },
  });
}

function routeFetch(url: string): Response {
  const parsed = new URL(url, "http://x");
  if (parsed.pathname.endsWith("/api/v1/admin/history.csv")) {
    return csvResponse(
      parsed.searchParams.get("filter") ?? "",
      parsed.searchParams.get("start") ?? "",
      parsed.searchParams.get("end") ?? "",
    );
  }
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

  it("shows the append-only footer", async () => {
    await renderReady();
    expect(FOOTER_NOTE).toBe("Events are never edited or deleted. A reversal is its own row.");
    expect(screen.getByTestId("history-footer").textContent).toBe(FOOTER_NOTE);
  });

  describe("CSV export", () => {
    let createObjectURL: ReturnType<typeof vi.fn>;
    let revokeObjectURL: ReturnType<typeof vi.fn>;
    let clicked: { href: string; download: string; attached: boolean }[];

    beforeEach(() => {
      createObjectURL = vi.fn(() => "blob:nestquest/csv-1");
      revokeObjectURL = vi.fn();
      // jsdom has no object URLs; install stubs and remove them afterwards.
      Object.assign(URL, { createObjectURL, revokeObjectURL });
      clicked = [];
      vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push({
          href: this.getAttribute("href") ?? "",
          download: this.download,
          attached: document.body.contains(this),
        });
      });
    });

    afterEach(() => {
      vi.restoreAllMocks();
      const stubbed = URL as unknown as Record<string, unknown>;
      delete stubbed.createObjectURL;
      delete stubbed.revokeObjectURL;
    });

    function csvCalls(): [URL, RequestInit][] {
      return fetchMock.mock.calls
        .map(([url, init]) => [new URL(String(url), "http://x"), init] as [URL, RequestInit])
        .filter(([url]) => url.pathname === "/api/v1/admin/history.csv");
    }

    it("requests the CSV for the active filter and displayed range with the Bearer token", async () => {
      await renderReady();
      fireEvent.click(screen.getByRole("button", { name: "CSV" }));
      await waitFor(() => expect(clicked).toHaveLength(1));

      const calls = csvCalls();
      expect(calls).toHaveLength(1);
      const [url, init] = calls[0];
      expect(url.searchParams.get("filter")).toBe("all");
      expect(url.searchParams.get("start")).toBe("2026-09-10");
      expect(url.searchParams.get("end")).toBe(TODAY);
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer at-123");
      // The token never travels in the URL.
      expect(url.toString()).not.toContain("at-123");
    });

    it("offers the returned CSV for download, then revokes the URL and removes the anchor", async () => {
      await renderReady();
      fireEvent.click(screen.getByRole("button", { name: "CSV" }));
      await waitFor(() => expect(clicked).toHaveLength(1));

      expect(createObjectURL).toHaveBeenCalledTimes(1);
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(await blob.text()).toBe(`all\n${CSV_BODY}`);
      expect(clicked[0]).toEqual({
        href: "blob:nestquest/csv-1",
        download: "nestquest-history-2026-09-10-to-2026-09-23.csv",
        attached: true,
      });
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:nestquest/csv-1");
      expect(document.querySelector("a[download]")).toBeNull();
      expect(screen.queryByTestId("history-export-error")).toBeNull();
    });

    it("falls back to the range filename without a Content-Disposition header", async () => {
      fetchMock.mockImplementation((url: string) =>
        Promise.resolve(
          new URL(url, "http://x").pathname.endsWith(".csv")
            ? new Response(CSV_BODY, { status: 200, headers: { "Content-Type": "text/csv" } })
            : routeFetch(url),
        ),
      );
      await renderReady();
      fireEvent.click(screen.getByRole("button", { name: "CSV" }));
      await waitFor(() => expect(clicked).toHaveLength(1));
      expect(clicked[0].download).toBe("nestquest-history-2026-09-10-to-2026-09-23.csv");
    });

    it("switching the filter chip then exporting uses the new filter", async () => {
      await renderReady();
      fireEvent.click(screen.getByRole("button", { name: "Reversals" }));
      await waitFor(() => expect(screen.getAllByTestId("history-row")).toHaveLength(1));

      fireEvent.click(screen.getByRole("button", { name: "CSV" }));
      await waitFor(() => expect(clicked).toHaveLength(1));
      const calls = csvCalls();
      expect(calls).toHaveLength(1);
      expect(calls[0][0].searchParams.get("filter")).toBe("reversals");
      expect(calls[0][0].searchParams.get("start")).toBe("2026-09-10");
      expect(calls[0][0].searchParams.get("end")).toBe(TODAY);
    });

    it("a failed export shows a non-blocking error and does not download", async () => {
      fetchMock.mockImplementation((url: string) =>
        Promise.resolve(
          new URL(url, "http://x").pathname.endsWith(".csv")
            ? jsonResponse({ detail: "boom" }, 500)
            : routeFetch(url),
        ),
      );
      await renderReady();
      fireEvent.click(screen.getByRole("button", { name: "CSV" }));

      const error = await screen.findByTestId("history-export-error");
      expect(error.textContent).toContain("The CSV export failed");
      expect(createObjectURL).not.toHaveBeenCalled();
      expect(clicked).toHaveLength(0);
      // The tab stays usable: rows remain, the button is re-enabled, chips still work.
      expect(screen.getAllByTestId("history-row")).toHaveLength(5);
      expect((screen.getByRole("button", { name: "CSV" }) as HTMLButtonElement).disabled).toBe(false);
      fireEvent.click(screen.getByRole("button", { name: "Reversals" }));
      await waitFor(() => expect(screen.getAllByTestId("history-row")).toHaveLength(1));

      fireEvent.click(within(error).getByRole("button", { name: "Dismiss" }));
      expect(screen.queryByTestId("history-export-error")).toBeNull();
    });

    it("the button is disabled while the request is in flight (no double-submit)", async () => {
      let release: (response: Response) => void = () => {};
      fetchMock.mockImplementation((url: string) =>
        new URL(url, "http://x").pathname.endsWith(".csv")
          ? new Promise<Response>((resolve) => {
              release = resolve;
            })
          : Promise.resolve(routeFetch(url)),
      );
      await renderReady();
      const csv = screen.getByRole("button", { name: "CSV" }) as HTMLButtonElement;
      fireEvent.click(csv);
      await waitFor(() => expect(csv.disabled).toBe(true));
      fireEvent.click(csv);
      expect(csvCalls()).toHaveLength(1);

      release(csvResponse("all", "2026-09-10", TODAY));
      await waitFor(() => expect(clicked).toHaveLength(1));
      await waitFor(() => expect(csv.disabled).toBe(false));
      expect(csvCalls()).toHaveLength(1);
    });
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

describe("HistoryTab live updates", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let streams: TestStream[];

  function historyRequests(): URL[] {
    return fetchMock.mock.calls
      .map(([url]) => new URL(String(url), "http://x"))
      .filter((url) => url.pathname === "/api/v1/admin/history");
  }

  const PAYLOAD = {
    child_id: 2,
    child_name: "Maeve",
    instance_id: 2,
    quest_title: "Make bed",
    window: "morning",
    due_date: TODAY,
    due_time: null,
    occurred_at: "2026-09-23T15:10:00Z",
  };

  beforeAll(() => {
    vi.stubEnv("TZ", "America/Los_Angeles");
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    streams = [];
    fetchMock = vi.fn((url: string) => {
      if (new URL(url, "http://x").pathname.endsWith("/api/v1/admin/events")) {
        const stream = testStream();
        streams.push(stream);
        return Promise.resolve(stream.response);
      }
      return Promise.resolve(routeFetch(url));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("a quest transition refetches the active filter; a day-complete does not", async () => {
    render(
      <TransitionsProvider>
        <HistoryTab today={TODAY} />
      </TransitionsProvider>,
    );
    await screen.findByTestId("stat-on-time");
    fireEvent.click(screen.getByRole("button", { name: "Reversals" }));
    await waitFor(() =>
      expect(historyRequests().some((u) => u.searchParams.get("filter") === "reversals")).toBe(true),
    );
    await screen.findByTestId("stat-on-time");
    await waitFor(() => expect(streams).toHaveLength(1));
    const before = historyRequests().length;

    streams[0].push(
      frame("nestquest_child_day_complete", {
        child_id: 2,
        child_name: "Maeve",
        quests_due: 4,
        quests_completed: 4,
        occurred_at: "2026-09-23T15:00:00Z",
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(historyRequests().length).toBe(before);

    streams[0].push(frame("nestquest_quest_uncompleted", PAYLOAD));

    await waitFor(() => expect(historyRequests().length).toBe(before + 3));
    const refetched = historyRequests().slice(before);
    // One refetch (reversals + the two stats queries), same range and filter.
    expect(refetched.map((u) => u.searchParams.get("filter")).sort()).toEqual([
      "all",
      "missed",
      "reversals",
    ]);
    for (const url of refetched) {
      expect(url.searchParams.get("start")).toBe("2026-09-10");
      expect(url.searchParams.get("end")).toBe(TODAY);
    }
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(historyRequests().length).toBe(before + 3);
    expect(screen.queryByTestId("history-loading")).toBeNull();
    expect(screen.getByRole("button", { name: "Reversals" }).getAttribute("aria-pressed")).toBe("true");
    // Rows stay read-only (D-005): no row carries a control.
    for (const row of screen.getAllByTestId("history-row")) {
      expect(within(row).queryByRole("button")).toBeNull();
    }
  });

  describe("a filter change interleaved with a quest transition", () => {
    // Both land before the load effect runs, so one load serves both.
    async function interleave(order: "sse-first" | "chip-first") {
      await act(async () => {
        const click = () => fireEvent.click(screen.getByRole("button", { name: "Reversals" }));
        if (order === "chip-first") click();
        streams[0].push(frame("nestquest_quest_uncompleted", PAYLOAD));
        await new Promise((resolve) => setTimeout(resolve, 30));
        if (order === "sse-first") click();
      });
    }

    async function renderLive() {
      render(
        <TransitionsProvider>
          <HistoryTab today={TODAY} />
        </TransitionsProvider>,
      );
      await screen.findByTestId("stat-on-time");
      await waitFor(() => expect(streams).toHaveLength(1));
      expect(screen.getAllByTestId("history-row")).toHaveLength(ROWS.all.length);
    }

    function titles(): string[] {
      return screen.getAllByTestId("history-row").map((el) => el.textContent ?? "");
    }

    for (const order of ["sse-first", "chip-first"] as const) {
      it(`${order}: shows loading, then only the active filter's rows`, async () => {
        let release!: () => void;
        const gate = new Promise<void>((resolve) => {
          release = resolve;
        });
        const route = fetchMock.getMockImplementation()!;
        await renderLive();
        fetchMock.mockImplementation((url: string) => {
          const parsed = new URL(url, "http://x");
          if (parsed.searchParams.get("filter") === "reversals") {
            return gate.then(() => route(url));
          }
          return route(url);
        });

        await interleave(order);
        expect(screen.getByRole("button", { name: "Reversals" }).getAttribute("aria-pressed")).toBe("true");
        // The previous filter's rows never show under the new chip.
        expect(screen.getByTestId("history-loading")).toBeTruthy();
        expect(screen.queryAllByTestId("history-row")).toHaveLength(0);

        release();
        await screen.findByTestId("stat-on-time");
        expect(titles()).toHaveLength(1);
        expect(titles()[0]).toContain("Make bed · Maeve");
        expect(screen.getAllByTestId("history-dot")[0].className).toContain("history-dot--uncompleted");
      });

      it(`${order}: a failed filter-change load shows the error state, not stale rows`, async () => {
        const route = fetchMock.getMockImplementation()!;
        await renderLive();
        fetchMock.mockImplementation((url: string) => {
          const parsed = new URL(url, "http://x");
          if (parsed.pathname === "/api/v1/admin/history") {
            return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
          }
          return route(url);
        });

        await interleave(order);
        const error = await screen.findByTestId("history-error");
        expect(error.textContent).toContain("The history could not be loaded");
        expect(screen.getByRole("button", { name: "Reversals" }).getAttribute("aria-pressed")).toBe("true");
        expect(screen.queryAllByTestId("history-row")).toHaveLength(0);
        expect(screen.queryByTestId("stat-on-time")).toBeNull();
      });
    }
  });

  it("a failed transition refresh keeps the active filter's rows on screen", async () => {
    render(
      <TransitionsProvider>
        <HistoryTab today={TODAY} />
      </TransitionsProvider>,
    );
    await screen.findByTestId("stat-on-time");
    await waitFor(() => expect(streams).toHaveLength(1));
    const route = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string) => {
      if (new URL(url, "http://x").pathname === "/api/v1/admin/history") {
        return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      }
      return route(url);
    });
    const before = historyRequests().length;

    streams[0].push(frame("nestquest_quest_uncompleted", PAYLOAD));
    // The "all" filter plus the missed stats query.
    await waitFor(() => expect(historyRequests().length).toBe(before + 2));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(screen.queryByTestId("history-error")).toBeNull();
    expect(screen.queryByTestId("history-loading")).toBeNull();
    expect(screen.getAllByTestId("history-row")).toHaveLength(ROWS.all.length);
  });
});
