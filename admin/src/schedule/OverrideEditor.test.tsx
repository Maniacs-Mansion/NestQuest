import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import ScheduleTab from "./ScheduleTab";
import { CONSEQUENCE_DEBOUNCE_MS, isIsoDate, isValidRange } from "./OverrideEditor";
import type { AdminChild } from "../api/definitions";
import type { PresenceOverride, PresenceSchedule } from "../api/presence";
import { storeTokens } from "../auth/oidc";

function child(id: number, display_name: string, sort_order: number): AdminChild {
  return { id, display_name, colour: null, avatar_ref: null, sort_order, is_active: true };
}

const CHILDREN = [child(1, "Declan", 1), child(2, "Maeve", 2), child(3, "Rory", 3)];

const DECLAN: PresenceSchedule = {
  child_id: 1,
  cycle_length_weeks: 2,
  anchor_date: "2026-09-07",
  pattern: { "0": [0, 1, 2, 3, 4, 5, 6], "1": [5, 6] },
};

const INITIAL_OVERRIDES: PresenceOverride[] = [
  { id: 41, child_id: 1, start_date: "2026-09-10", end_date: "2026-09-12", is_present: false, note: "Dentist trip" },
];

const TODAY = "2026-09-23";
const OVERRIDES_PATH = "/api/v1/admin/presence-overrides";
const CONSEQUENCE_PATH = `${OVERRIDES_PATH}/consequence`;

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

let overrides: PresenceOverride[];
let consequence: (body: Record<string, unknown>) => Response | Promise<Response>;
let createResponse: (body: Record<string, unknown>) => Response;
let fetchMock: ReturnType<typeof vi.fn>;

function calls(): Call[] {
  return fetchMock.mock.calls.map(([url, init]: [string, RequestInit | undefined]) => ({
    method: init?.method ?? "GET",
    path: new URL(String(url), "http://x").pathname,
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  }));
}

function consequenceBodies(): unknown[] {
  return calls()
    .filter((c) => c.path === CONSEQUENCE_PATH)
    .map((c) => c.body);
}

async function routeFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const path = new URL(url, "http://x").pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : undefined;
  if (path === CONSEQUENCE_PATH && method === "POST") return consequence(body);
  if (path === OVERRIDES_PATH && method === "POST") return createResponse(body);
  const deleteMatch = /\/presence-overrides\/(\d+)$/.exec(path);
  if (deleteMatch && method === "DELETE") {
    overrides = overrides.filter((o) => o.id !== Number(deleteMatch[1]));
    return jsonResponse({ status: "ok" });
  }
  if (path.endsWith("/admin/children")) return jsonResponse({ children: CHILDREN });
  const scheduleMatch = /\/children\/(\d+)\/presence-schedule$/.exec(path);
  if (scheduleMatch) {
    return jsonResponse({ schedule: Number(scheduleMatch[1]) === 1 ? DECLAN : null });
  }
  if (path === OVERRIDES_PATH) return jsonResponse({ overrides });
  return jsonResponse({ detail: "unexpected" }, 500);
}

function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const pastDebounce = () => new Promise((r) => setTimeout(r, CONSEQUENCE_DEBOUNCE_MS + 150));

function headline(): string {
  return screen.getByTestId("override-consequence-headline").textContent ?? "";
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Save override" }) as HTMLButtonElement;
}

function setDate(label: "From" | "Through", value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function openEditor() {
  render(<ScheduleTab today={TODAY} />);
  await screen.findByTestId("pattern-1");
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await screen.findByRole("heading", { name: "Presence override" });
}

describe("OverrideEditor", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    overrides = [...INITIAL_OVERRIDES];
    consequence = () => jsonResponse({ removed: 4 });
    createResponse = (body) => {
      const created: PresenceOverride = {
        id: 50,
        child_id: body.child_id as number,
        start_date: body.start_date as string,
        end_date: body.end_date as string,
        is_present: body.is_present as boolean,
        note: (body.note as string | undefined) ?? null,
      };
      overrides = [...overrides, created];
      return jsonResponse(created, 201);
    };
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the pushed screen per ADMIN-SPEC §6", async () => {
    await openEditor();
    expect(screen.getByText("Beats the custody pattern for these dates")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back" })).toBeTruthy();
    const kids = within(screen.getByRole("group", { name: "Child" })).getAllByRole("button");
    expect(kids.map((b) => [b.textContent, b.getAttribute("aria-pressed")])).toEqual([
      ["Declan", "true"],
      ["Maeve", "false"],
      ["Rory", "false"],
    ]);
    const status = within(screen.getByRole("group", { name: "Status for these dates" }));
    expect(status.getByRole("button", { name: "Away" }).getAttribute("aria-pressed")).toBe("true");
    expect(status.getByRole("button", { name: "Home" }).getAttribute("aria-pressed")).toBe("false");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe(TODAY);
    expect((screen.getByLabelText("Through") as HTMLInputElement).value).toBe(TODAY);
    expect(screen.getByLabelText("Reason (optional)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  });

  it("shows the live consequence count from the API and recounts on every change", async () => {
    await openEditor();
    // Save is off until the count is on screen: the warning precedes saving.
    expect(saveButton().disabled).toBe(true);
    await waitFor(() => expect(headline()).toBe("This removes 4 upcoming tasks"));
    expect(consequenceBodies()).toEqual([
      { child_id: 1, start_date: TODAY, end_date: TODAY, is_present: false },
    ]);
    const warning = screen.getByTestId("override-consequence");
    expect(warning.textContent).toContain("Declan");
    expect(warning.textContent).toContain("Sep 23");
    expect(warning.textContent).toContain("Completed days are untouched.");
    expect(saveButton().disabled).toBe(false);

    consequence = () => jsonResponse({ removed: 9 });
    setDate("Through", "2026-09-27");
    await waitFor(() => expect(headline()).toBe("This removes 9 upcoming tasks"));
    expect(consequenceBodies()[1]).toEqual({
      child_id: 1,
      start_date: TODAY,
      end_date: "2026-09-27",
      is_present: false,
    });
    expect(warning.textContent).toContain("Sep 23 – 27");

    consequence = () => jsonResponse({ removed: 2 });
    fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
    await waitFor(() => expect(headline()).toBe("This removes 2 upcoming tasks"));
    expect(consequenceBodies()[2]).toEqual({
      child_id: 2,
      start_date: TODAY,
      end_date: "2026-09-27",
      is_present: false,
    });
    expect(warning.textContent).toContain("Maeve");

    // A Home override removes nothing by definition: no request, count 0.
    fireEvent.click(screen.getByRole("button", { name: "Home" }));
    expect(headline()).toBe("This removes 0 upcoming tasks");
    expect(warning.textContent).toContain("Completed days are untouched.");
    await pastDebounce();
    expect(consequenceBodies()).toHaveLength(3);
  });

  it("renders the API's count verbatim — completed instances are excluded server-side", async () => {
    // The range holds 3 open instances and 1 already completed. The API
    // excludes the completed one (D-005; proven by
    // tests/test_api_admin_presence_consequence.py::test_completed_instance_in_range_is_not_counted
    // and ::test_count_matches_a_direct_materialise_comparison), so it answers 3,
    // and the editor shows exactly that — it never counts days on its own.
    consequence = () => jsonResponse({ removed: 3 });
    await openEditor();
    setDate("Through", "2026-09-25");
    await waitFor(() => expect(headline()).toBe("This removes 3 upcoming tasks"));
    expect(screen.getByTestId("override-consequence").textContent).toContain(
      "Completed days are untouched.",
    );
  });

  it("a stale consequence response never overwrites a newer one", async () => {
    const first = deferred();
    const second = deferred();
    const pending = [first, second];
    consequence = () => pending.shift()!.promise;
    await openEditor();
    await waitFor(() => expect(consequenceBodies()).toHaveLength(1));

    setDate("Through", "2026-09-26");
    await waitFor(() => expect(consequenceBodies()).toHaveLength(2));

    second.resolve(jsonResponse({ removed: 5 }));
    await waitFor(() => expect(headline()).toBe("This removes 5 upcoming tasks"));
    first.resolve(jsonResponse({ removed: 99 }));
    await pastDebounce();
    expect(headline()).toBe("This removes 5 upcoming tasks");
  });

  it("debounces rapid edits into one request for the final range", async () => {
    await openEditor();
    await waitFor(() => expect(consequenceBodies()).toHaveLength(1));
    setDate("Through", "2026-09-24");
    setDate("Through", "2026-09-25");
    setDate("Through", "2026-09-26");
    await pastDebounce();
    expect(consequenceBodies().slice(1)).toEqual([
      { child_id: 1, start_date: TODAY, end_date: "2026-09-26", is_present: false },
    ]);
  });

  it("an incomplete or reversed range sends no consequence request and cannot be saved", async () => {
    await openEditor();
    await waitFor(() => expect(consequenceBodies()).toHaveLength(1));

    setDate("Through", "");
    expect(headline()).toBe("Choose a valid date range");
    expect(saveButton().disabled).toBe(true);
    await pastDebounce();
    expect(consequenceBodies()).toHaveLength(1);

    setDate("Through", "2026-09-20"); // before From
    expect(headline()).toBe("Choose a valid date range");
    await pastDebounce();
    expect(consequenceBodies()).toHaveLength(1);
    fireEvent.click(saveButton());
    expect(calls().some((c) => c.method === "POST" && c.path === OVERRIDES_PATH)).toBe(false);
  });

  it("Save sends the exact POST body, closes the editor and shows the new row", async () => {
    await openEditor();
    setDate("From", "2026-09-24");
    setDate("Through", "2026-09-26");
    fireEvent.change(screen.getByLabelText("Reason (optional)"), {
      target: { value: "  Trip with grandparents " },
    });
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    const before = calls().length;
    const schedulesBefore = calls().filter((c) => c.path.endsWith("/presence-schedule")).length;

    fireEvent.click(saveButton());
    const row = await screen.findByTestId("override-50");
    expect(row.textContent).toContain("Declan away · Sep 24 – 26");
    expect(row.textContent).toContain("Trip with grandparents");
    expect(screen.queryByRole("heading", { name: "Presence override" })).toBeNull();

    const after = calls().slice(before);
    const writes = after.filter((c) => c.method !== "GET");
    // D-005: saving sends ONLY the create request — never a delete of an
    // instance or an override. The API's regenerate path keeps completed
    // instances (tests/test_materialize.py::
    // test_regenerate_for_definition_rebuilds_horizon_and_preserves_completed).
    expect(writes).toEqual([
      {
        method: "POST",
        path: OVERRIDES_PATH,
        body: {
          child_id: 1,
          start_date: "2026-09-24",
          end_date: "2026-09-26",
          is_present: false,
          note: "Trip with grandparents",
        },
      },
    ]);
    expect(after.some((c) => c.method === "DELETE")).toBe(false);
    // The overrides and the presence schedules are refetched for the grid.
    expect(after.some((c) => c.method === "GET" && c.path === OVERRIDES_PATH)).toBe(true);
    expect(calls().filter((c) => c.path.endsWith("/presence-schedule")).length).toBeGreaterThan(
      schedulesBefore,
    );
    // The grid reflects the new override.
    expect(document.querySelector('[data-date="2026-09-25"]')?.getAttribute("data-state")).toBe(
      "override-away",
    );
  });

  it("omits an empty reason and saves a Home override", async () => {
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: "Home" }));
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    fireEvent.click(saveButton());
    await screen.findByTestId("override-50");
    const post = calls().find((c) => c.method === "POST" && c.path === OVERRIDES_PATH);
    expect(post?.body).toEqual({
      child_id: 1,
      start_date: TODAY,
      end_date: TODAY,
      is_present: true,
    });
  });

  it("a 422 shows the API detail and keeps the form", async () => {
    createResponse = () => jsonResponse({ detail: "overlaps an existing override" }, 422);
    await openEditor();
    setDate("Through", "2026-09-25");
    fireEvent.change(screen.getByLabelText("Reason (optional)"), { target: { value: "Camp" } });
    await waitFor(() => expect(saveButton().disabled).toBe(false));

    fireEvent.click(saveButton());
    const alert = await screen.findByTestId("override-error");
    expect(alert.textContent).toBe("overlaps an existing override");
    expect(screen.getByRole("heading", { name: "Presence override" })).toBeTruthy();
    expect((screen.getByLabelText("Through") as HTMLInputElement).value).toBe("2026-09-25");
    expect((screen.getByLabelText("Reason (optional)") as HTMLInputElement).value).toBe("Camp");
    expect(saveButton().disabled).toBe(false);
  });

  it("Cancel and Back close the editor without writing", async () => {
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByTestId("pattern-1");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("button", { name: "Back" }));
    await screen.findByTestId("pattern-1");
    expect(calls().some((c) => c.method === "POST" && c.path === OVERRIDES_PATH)).toBe(false);
  });

  it("Add opens the editor for the selected child", async () => {
    render(<ScheduleTab today={TODAY} />);
    await screen.findByTestId("pattern-1");
    fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const kids = within(await screen.findByRole("group", { name: "Child" }));
    expect(kids.getByRole("button", { name: "Maeve" }).getAttribute("aria-pressed")).toBe("true");
    await waitFor(() =>
      expect(consequenceBodies()).toEqual([
        { child_id: 2, start_date: TODAY, end_date: TODAY, is_present: false },
      ]),
    );
  });

  it("the trash button deletes the override only after confirm", async () => {
    render(<ScheduleTab today={TODAY} />);
    const row = await screen.findByTestId("override-41");

    fireEvent.click(within(row).getByRole("button", { name: "Delete override" }));
    fireEvent.click(within(row).getByRole("button", { name: "Keep" }));
    expect(calls().some((c) => c.method === "DELETE")).toBe(false);

    fireEvent.click(within(row).getByRole("button", { name: "Delete override" }));
    const confirm = within(row).getByRole("group", { name: "Confirm delete" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByTestId("override-41")).toBeNull());
    expect(calls().filter((c) => c.method === "DELETE")).toEqual([
      { method: "DELETE", path: `${OVERRIDES_PATH}/41`, body: undefined },
    ]);
    expect(screen.getByText("No overrides for Declan.")).toBeTruthy();
  });
});

describe("range validation", () => {
  it("accepts only strict ISO calendar dates in order", () => {
    expect(isIsoDate("2026-09-23")).toBe(true);
    expect(isIsoDate("2026-02-30")).toBe(false);
    expect(isIsoDate("2026-9-3")).toBe(false);
    expect(isIsoDate("")).toBe(false);
    expect(isValidRange("2026-09-23", "2026-09-23")).toBe(true);
    expect(isValidRange("2026-09-23", "2026-09-22")).toBe(false);
    expect(isValidRange("2026-09-23", "")).toBe(false);
  });
});
