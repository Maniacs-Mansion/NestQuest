import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "../App";
import ScheduleTab from "./ScheduleTab";
import { CONSEQUENCE_DEBOUNCE_MS, isIsoDate, isValidRange } from "./OverrideEditor";
import type { AdminChild } from "../api/definitions";
import type { PresenceOverride, PresencePattern } from "../api/presence";
import { storeTokens } from "../auth/oidc";

function child(id: number, display_name: string, sort_order: number): AdminChild {
  return { id, display_name, colour: null, avatar_ref: null, sort_order, is_active: true };
}

const CHILDREN = [child(1, "Declan", 1), child(2, "Maeve", 2), child(3, "Rory", 3)];

const DECLAN: PresencePattern = {
  id: 1,
  child_id: 1,
  name: "Home weeks",
  kind: "home",
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
  const patternsMatch = /\/children\/(\d+)\/presence-patterns$/.exec(path);
  if (patternsMatch) {
    return jsonResponse({ patterns: Number(patternsMatch[1]) === 1 ? [DECLAN] : [] });
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

function warningBody(): string {
  return screen.getByTestId("override-consequence").querySelector(".override-warning-body")?.textContent ?? "";
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
    expect(warningBody()).toBe(
      "Declan's open tasks Sep 23 are removed while away. Completed days are untouched.",
    );
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
    expect(warningBody()).toBe(
      "Declan's open tasks Sep 23 – 27 are removed while away. Completed days are untouched.",
    );

    consequence = () => jsonResponse({ removed: 2 });
    fireEvent.click(screen.getByRole("button", { name: "Maeve" }));
    await waitFor(() => expect(headline()).toBe("This removes 2 upcoming tasks"));
    expect(consequenceBodies()[2]).toEqual({
      child_id: 2,
      start_date: TODAY,
      end_date: "2026-09-27",
      is_present: false,
    });
    expect(warningBody()).toBe(
      "Maeve's open tasks Sep 23 – 27 are removed while away. Completed days are untouched.",
    );

    // A Home override removes nothing by definition: no request, count 0.
    fireEvent.click(screen.getByRole("button", { name: "Home" }));
    expect(headline()).toBe("This removes 0 upcoming tasks");
    expect(warningBody()).toBe(
      "Maeve is home Sep 23 – 27, so no tasks are removed. Completed days are untouched.",
    );
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
    expect(warningBody()).toBe(
      "Declan's open tasks Sep 23 – 25 are removed while away. Completed days are untouched.",
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

  it("a malformed From date sends no consequence request and cannot be saved", async () => {
    await openEditor();
    await waitFor(() => expect(consequenceBodies()).toHaveLength(1));

    setDate("From", "2026-02-30");
    expect(headline()).toBe("Choose a valid date range");
    expect(saveButton().disabled).toBe(true);
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
    const patternsBefore = calls().filter((c) => c.path.endsWith("/presence-patterns")).length;

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
    // The overrides and the presence patterns are refetched for the grid.
    expect(after.some((c) => c.method === "GET" && c.path === OVERRIDES_PATH)).toBe(true);
    expect(calls().filter((c) => c.path.endsWith("/presence-patterns")).length).toBeGreaterThan(
      patternsBefore,
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

describe("OverrideEditor focus", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    overrides = [...INITIAL_OVERRIDES];
    consequence = () => jsonResponse({ removed: 4 });
    createResponse = (body) => {
      const created = { id: 50, note: null, ...body } as PresenceOverride;
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

  function dialog(): HTMLElement {
    return screen.getByRole("dialog", { name: "Presence override" });
  }

  function addButton(): HTMLElement {
    return screen.getByRole("button", { name: "Add" });
  }

  it("moves focus into the editor on open", async () => {
    await openEditor();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Presence override" }));
    expect(dialog().contains(document.activeElement)).toBe(true);
  });

  it("keeps Tab and Shift+Tab inside the editor", async () => {
    await openEditor();
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    const back = screen.getByRole("button", { name: "Back" });

    saveButton().focus();
    fireEvent.keyDown(saveButton(), { key: "Tab" });
    expect(document.activeElement).toBe(back);

    fireEvent.keyDown(back, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(saveButton());

    // From the focused heading (not in the tab order) Shift+Tab wraps to the end.
    const title = screen.getByRole("heading", { name: "Presence override" });
    title.focus();
    fireEvent.keyDown(title, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(saveButton());
  });

  it("makes the tab bar inert while open and restores it on close", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    await screen.findByTestId("pattern-1");
    fireEvent.click(addButton());
    await screen.findByRole("heading", { name: "Presence override" });

    const tabbar = document.querySelector(".admin-tabbar") as HTMLElement;
    expect(tabbar.hasAttribute("inert")).toBe(true);
    expect(tabbar.getAttribute("aria-hidden")).toBe("true");
    expect(dialog().closest("[inert]")).toBeNull();

    fireEvent.keyDown(dialog(), { key: "Escape" });
    await screen.findByTestId("pattern-1");
    expect(tabbar.hasAttribute("inert")).toBe(false);
    expect(tabbar.hasAttribute("aria-hidden")).toBe(false);
  });

  it("Escape cancels without writing and returns focus to Add", async () => {
    await openEditor();
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Escape" });
    await screen.findByTestId("pattern-1");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(addButton());
    expect(calls().some((c) => c.method === "POST" && c.path === OVERRIDES_PATH)).toBe(false);
  });

  it("Escape does nothing while saving; focus returns to Add after the save", async () => {
    const gate = deferred();
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = new URL(url, "http://x").pathname;
      if (path === OVERRIDES_PATH && init?.method === "POST") await gate.promise;
      return routeFetch(url, init);
    });
    await openEditor();
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    fireEvent.click(saveButton());
    expect(screen.getByRole("button", { name: "Saving…" })).toBeTruthy();

    fireEvent.keyDown(dialog(), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeTruthy();

    gate.resolve(new Response(null));
    await screen.findByTestId("override-50");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(addButton());
  });

  it("Back and Cancel return focus to Add", async () => {
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await screen.findByTestId("pattern-1");
    expect(document.activeElement).toBe(addButton());

    fireEvent.click(addButton());
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await screen.findByTestId("pattern-1");
    expect(document.activeElement).toBe(addButton());
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
