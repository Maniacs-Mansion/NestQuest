import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import DefinitionsTab from "./DefinitionsTab";
import { DEFINITION_ICONS, DefinitionIcon, normalizeDefinitionIconName } from "./definitionIcons";
import type { AdminChild, DefinitionRule, QuestDefinition } from "../api/definitions";
import { storeTokens } from "../auth/oidc";

function child(id: number, name: string, overrides: Partial<AdminChild> = {}): AdminChild {
  return {
    id,
    display_name: name,
    colour: null,
    avatar_ref: null,
    sort_order: id,
    is_active: true,
    ...overrides,
  };
}

const CHILDREN: AdminChild[] = [
  child(1, "Declan"),
  child(2, "Maeve"),
  child(3, "Rory"),
  child(4, "Old", { is_active: false }),
];

function rule(overrides: Partial<DefinitionRule> = {}): DefinitionRule {
  return {
    rule_type: "daily",
    interval: 1,
    weekday_set: null,
    day_of_month: null,
    nth_weekday: null,
    nth_weekday_weekday: null,
    month: null,
    start_date: "2026-01-01",
    end_date: null,
    ...overrides,
  };
}

const BRUSH: QuestDefinition = {
  id: 10,
  title: "Brush teeth",
  description: null,
  icon: "smile",
  is_active: true,
  skip_on_away: true,
  rule: rule(),
  assignees: [
    { id: 1, display_name: "Declan" },
    { id: 2, display_name: "Maeve" },
    { id: 3, display_name: "Rory" },
  ],
  windows: [
    { window: "morning", due_time: "07:30" },
    { window: "evening", due_time: null },
  ],
};

const BINS: QuestDefinition = {
  id: 11,
  title: "Take out bins",
  description: "Green bin",
  icon: null,
  is_active: true,
  skip_on_away: false,
  rule: rule({ rule_type: "weekly", interval: 2, weekday_set: [0, 3] }),
  assignees: [
    { id: 1, display_name: "Declan" },
    { id: 4, display_name: "Old" },
  ],
  windows: [{ window: "afternoon", due_time: "16:00" }],
};

const PIANO: QuestDefinition = {
  id: 12,
  title: "Piano practice",
  description: null,
  icon: null,
  is_active: false,
  skip_on_away: true,
  rule: rule({ rule_type: "monthly_day", day_of_month: 15 }),
  assignees: [{ id: 2, display_name: "Maeve" }],
  windows: [{ window: "afternoon", due_time: null }],
};

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

const PREVIEW_PATH = "/api/v1/admin/quest-definitions/occurrences-preview";

/** Answers an occurrence-preview request; the default serves no dates. */
type PreviewHandler = (body: { rule: DefinitionRule; count?: number }) => Promise<Response>;

/**
 * A stub of the admin API: serves the list and children, records writes, and
 * lets a test queue a response for the next write. Occurrence previews are
 * reads (recorded, never counted as writes) answered by `setPreview`.
 */
function fakeApi(initial: QuestDefinition[]) {
  let definitions = [...initial];
  const calls: Call[] = [];
  let nextWrite: Response | null = null;
  let preview: PreviewHandler = async () => jsonResponse({ dates: [] });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init.method ?? "GET";
    const body = typeof init.body === "string" ? JSON.parse(init.body) : null;
    calls.push({ method, path, body });
    if (method === "POST" && path === PREVIEW_PATH) return preview(body);
    if (method === "GET" && path === "/api/v1/admin/quest-definitions") {
      return jsonResponse({ definitions });
    }
    if (method === "GET" && path === "/api/v1/admin/children") {
      return jsonResponse({ children: CHILDREN });
    }
    if (nextWrite) {
      const response = nextWrite;
      nextWrite = null;
      return response;
    }
    if (method === "POST" && path === "/api/v1/admin/quest-definitions") {
      const created: QuestDefinition = {
        id: 99,
        title: body.title,
        description: null,
        icon: body.icon ?? null,
        is_active: true,
        skip_on_away: body.skip_on_away,
        rule: body.rule,
        assignees: CHILDREN.filter((c) => body.assignee_child_ids.includes(c.id)).map((c) => ({
          id: c.id,
          display_name: c.display_name,
        })),
        windows: body.windows.map(([window, due_time]: [string, string | null]) => ({
          window,
          due_time,
        })),
      };
      definitions = [...definitions, created];
      return jsonResponse(created, 201);
    }
    const match = /^\/api\/v1\/admin\/quest-definitions\/(\d+)$/.exec(path);
    if (method === "PATCH" && match) {
      const id = Number(match[1]);
      definitions = definitions.map((d) =>
        d.id === id
          ? {
              ...d,
              title: body.title ?? d.title,
              icon: "icon" in body ? body.icon : d.icon,
              skip_on_away: body.skip_on_away ?? d.skip_on_away,
              rule: body.rule ?? d.rule,
              // Like the API: a sent list replaces the whole set; an absent one keeps it.
              assignees:
                "assignee_child_ids" in body
                  ? CHILDREN.filter((c) => body.assignee_child_ids.includes(c.id)).map((c) => ({
                      id: c.id,
                      display_name: c.display_name,
                    }))
                  : d.assignees,
            }
          : d,
      );
      return jsonResponse(definitions.find((d) => d.id === id));
    }
    return jsonResponse({ detail: "unexpected" }, 500);
  });
  return {
    fetchMock,
    calls,
    writes: () => calls.filter((c) => c.method !== "GET" && c.path !== PREVIEW_PATH),
    previews: () => calls.filter((c) => c.path === PREVIEW_PATH),
    setPreview: (handler: PreviewHandler) => {
      preview = handler;
    },
    listFetches: () =>
      calls.filter((c) => c.method === "GET" && c.path === "/api/v1/admin/quest-definitions")
        .length,
    failNextWrite: (response: Response) => {
      nextWrite = response;
    },
  };
}

let api: ReturnType<typeof fakeApi>;

async function renderReady(initial: QuestDefinition[] = [BRUSH, BINS, PIANO]) {
  api = fakeApi(initial);
  vi.stubGlobal("fetch", api.fetchMock);
  render(<DefinitionsTab />);
  await screen.findByText("Brush teeth");
}

function meta(row: HTMLElement): string {
  return (row.querySelector(".defs-row-meta") as HTMLElement).textContent ?? "";
}

function sheet(): HTMLElement {
  return screen.getByRole("dialog");
}

describe("DefinitionsTab", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("header counts definitions and active children", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: "Tasks" })).toBeTruthy();
    expect(screen.getByText("3 definitions · 3 children")).toBeTruthy();
    const [url, init] = api.fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/admin\/quest-definitions$/);
    expect((init as RequestInit & { headers: Record<string, string> }).headers.Authorization).toBe(
      "Bearer at-123",
    );
  });

  it("rows show `<assignees> · <recurrence> · <windows>` meta", async () => {
    await renderReady();
    const brush = screen.getByTestId("definition-10");
    expect(within(brush).getByText("Brush teeth")).toBeTruthy();
    expect(meta(brush)).toBe("All three · Daily · Morning, Evening");
    expect(meta(screen.getByTestId("definition-11"))).toBe(
      "Declan, Old · Every 2 weeks on Mon, Thu · Afternoon",
    );
    expect(brush.className).not.toContain("defs-row--inactive");
  });

  it("an inactive definition is styled inactive with `· inactive`", async () => {
    await renderReady();
    const piano = screen.getByTestId("definition-12");
    expect(meta(piano)).toBe("Maeve · Monthly on day 15 · Afternoon · inactive");
    expect(piano.className).toContain("defs-row--inactive");
  });

  it("filter chips filter by child", async () => {
    await renderReady();
    const chips = screen.getByRole("group", { name: "Filter by child" });
    expect(
      within(chips)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["All", "Declan", "Maeve", "Rory"]);
    expect(within(chips).getByRole("button", { name: "All" }).className).toContain(
      "defs-chip--active",
    );

    fireEvent.click(within(chips).getByRole("button", { name: "Maeve" }));
    expect(within(chips).getByRole("button", { name: "Maeve" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.queryByTestId("definition-10")).toBeTruthy();
    expect(screen.queryByTestId("definition-11")).toBeNull();
    expect(screen.queryByTestId("definition-12")).toBeTruthy();

    fireEvent.click(within(chips).getByRole("button", { name: "Rory" }));
    expect(screen.queryByTestId("definition-10")).toBeTruthy();
    expect(screen.queryByTestId("definition-12")).toBeNull();

    fireEvent.click(within(chips).getByRole("button", { name: "All" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("New opens the sheet and saving POSTs the exact body, then re-fetches", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 23, 9, 0)); // Wed 23 Sep 2026, local
    await renderReady();
    expect(api.listFetches()).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "New" }));
    const s = sheet();
    expect(within(s).getByRole("heading", { name: "New task" })).toBeTruthy();

    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "  Feed the cat " },
    });
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Declan" }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Rory" }));
    expect(within(s).getByRole("button", { name: /Assigned children/ }).textContent).toContain(
      "Declan, Rory",
    );

    fireEvent.change(within(s).getByRole("combobox", { name: "Repeats" }), {
      target: { value: "weekly" },
    });
    fireEvent.change(within(s).getByRole("spinbutton", { name: "Interval" }), {
      target: { value: "2" },
    });
    // Today (Wednesday) is preselected; add Saturday.
    expect(within(s).getByRole("button", { name: "Wednesday" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(within(s).getByRole("button", { name: "Saturday" }));

    fireEvent.click(within(s).getByRole("button", { name: "Evening" }));
    fireEvent.click(within(s).getByRole("button", { name: "Morning" }));
    fireEvent.change(within(s).getByLabelText("Morning due time"), {
      target: { value: "07:15" },
    });

    const toggle = within(s).getByRole("switch", { name: "Skip on away days" });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: "/api/v1/admin/quest-definitions",
        body: {
          title: "Feed the cat",
          icon: null,
          rule: {
            rule_type: "weekly",
            interval: 2,
            weekday_set: [2, 5],
            day_of_month: null,
            nth_weekday: null,
            nth_weekday_weekday: null,
            month: null,
            start_date: "2026-09-23",
            end_date: null,
          },
          assignee_child_ids: [1, 3],
          windows: [
            ["morning", "07:15"],
            ["evening", null],
          ],
          skip_on_away: false,
        },
      },
    ]);

    const created = await screen.findByTestId("definition-99");
    expect(meta(created)).toBe("Declan, Rory · Every 2 weeks on Wed, Sat · Morning, Evening");
    expect(api.listFetches()).toBe(2);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("4 definitions · 3 children")).toBeTruthy();
  });

  it("the weekday picker lists Sunday first and Sunday still stores 6", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 23, 9, 0)); // Wed 23 Sep 2026, local
    await renderReady();

    fireEvent.click(screen.getByRole("button", { name: "New" }));
    const s = sheet();
    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Feed the cat" },
    });
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Declan" }));
    fireEvent.change(within(s).getByRole("combobox", { name: "Repeats" }), {
      target: { value: "weekly" },
    });

    const days = within(s).getByRole("group", { name: "Days" });
    expect(
      within(days)
        .getAllByRole("button")
        .map((b) => b.getAttribute("aria-label")),
    ).toEqual(["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]);
    fireEvent.click(within(days).getByRole("button", { name: "Sunday" }));
    fireEvent.click(within(s).getByRole("button", { name: "Evening" }));

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    const body = api.writes()[0].body as { rule: DefinitionRule };
    expect(body.rule.weekday_set).toEqual([2, 6]);
    expect(meta(await screen.findByTestId("definition-99"))).toContain("on Sun, Wed");
  });

  it("tapping a row opens the sheet in editing state and saving PATCHes", async () => {
    await renderReady();
    const row = screen.getByTestId("definition-11");
    fireEvent.click(row);

    // §3.1 editing state on the row.
    expect(row.className).toContain("defs-row--editing");
    expect(meta(row)).toBe("Editing");
    expect(row.getAttribute("aria-expanded")).toBe("true");

    const s = sheet();
    expect(within(s).getByRole("heading", { name: "Edit task" })).toBeTruthy();
    expect((within(s).getByRole("textbox", { name: "Title" }) as HTMLInputElement).value).toBe(
      "Take out bins",
    );
    expect((within(s).getByRole("combobox", { name: "Repeats" }) as HTMLSelectElement).value).toBe(
      "weekly",
    );
    expect((within(s).getByLabelText("Afternoon due time") as HTMLInputElement).value).toBe(
      "16:00",
    );
    // The inactive child "Old" is shown locked, not offered as a checkbox.
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    expect(within(s).queryByRole("checkbox", { name: "Old" })).toBeNull();
    const locked = within(s).getByTestId("inactive-assignee-4");
    expect(locked.textContent).toContain("Old");
    expect(locked.textContent).toContain("Inactive");
    expect(locked.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(within(s).getByRole("checkbox", { name: "Maeve" }));

    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Take out the bins" },
    });
    fireEvent.change(within(s).getByRole("combobox", { name: "Repeats" }), {
      target: { value: "monthly" },
    });
    fireEvent.change(within(s).getByRole("spinbutton", { name: "Day of month" }), {
      target: { value: "3" },
    });
    fireEvent.change(within(s).getByRole("spinbutton", { name: "Interval" }), {
      target: { value: "1" },
    });
    fireEvent.change(within(s).getByLabelText("Afternoon due time"), {
      target: { value: "" },
    });
    fireEvent.click(within(s).getByRole("switch", { name: "Skip on away days" }));

    // Changing the selection would drop "Old": confirm before sending.
    fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    expect(api.writes()).toHaveLength(0);
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Unassign and save" }));
    });

    expect(api.writes()).toEqual([
      {
        method: "PATCH",
        path: "/api/v1/admin/quest-definitions/11",
        body: {
          title: "Take out the bins",
          icon: null,
          rule: {
            rule_type: "monthly_day",
            interval: 1,
            weekday_set: null,
            day_of_month: 3,
            nth_weekday: null,
            nth_weekday_weekday: null,
            month: null,
            start_date: "2026-01-01",
            end_date: null,
          },
          assignee_child_ids: [1, 2],
          windows: [["afternoon", null]],
          skip_on_away: true,
        },
      },
    ]);
    await screen.findByText("Take out the bins");
    expect(api.listFetches()).toBe(2);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("editing only the title omits assignee_child_ids and keeps an inactive assignee", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    expect(within(s).getByText(/Also assigned \(inactive\): Old\./)).toBeTruthy();
    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Bins out" },
    });

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect(screen.queryByTestId("unassign-confirm")).toBeNull();
    expect(api.writes()).toHaveLength(1);
    const body = api.writes()[0].body as Record<string, unknown>;
    expect(api.writes()[0].method).toBe("PATCH");
    expect(body.title).toBe("Bins out");
    expect(body).not.toHaveProperty("assignee_child_ids");

    await screen.findByText("Bins out");
    expect(meta(screen.getByTestId("definition-11"))).toBe(
      "Declan, Old · Every 2 weeks on Mon, Thu · Afternoon",
    );
  });

  it("changing the active selection with an inactive assignee asks first", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Rory" }));

    fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    const confirm = within(s).getByTestId("unassign-confirm");
    expect(confirm.textContent).toContain("Saving will unassign Old.");
    expect(document.activeElement).toBe(confirm);
    expect(api.writes()).toHaveLength(0);

    // Going back sends nothing and restores the normal footer.
    fireEvent.click(within(confirm).getByRole("button", { name: "Go back" }));
    expect(within(s).queryByTestId("unassign-confirm")).toBeNull();
    expect(api.writes()).toHaveLength(0);

    fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Unassign and save" }));
    });
    expect(api.writes()).toHaveLength(1);
    expect((api.writes()[0].body as { assignee_child_ids: number[] }).assignee_child_ids).toEqual([
      1, 3,
    ]);
  });

  it("reverting the selection to the original omits assignee_child_ids without asking", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Rory" }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Rory" }));

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect(screen.queryByTestId("unassign-confirm")).toBeNull();
    expect(api.writes()).toHaveLength(1);
    expect(api.writes()[0].body).not.toHaveProperty("assignee_child_ids");
  });

  it("focus moves into the sheet on open and returns to the row on Escape", async () => {
    await renderReady();
    const row = screen.getByTestId("definition-10");
    row.focus();
    fireEvent.click(row);
    const s = sheet();
    expect(document.activeElement).toBe(within(s).getByRole("heading", { name: "Edit task" }));

    fireEvent.keyDown(s, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(row);
    expect(api.writes()).toHaveLength(0);
  });

  it("Tab and Shift+Tab wrap within the sheet", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    const s = sheet();
    const title = within(s).getByRole("textbox", { name: "Title" });
    const save = within(s).getByRole("button", { name: "Save changes" });

    save.focus();
    fireEvent.keyDown(s, { key: "Tab" });
    expect(document.activeElement).toBe(title);

    fireEvent.keyDown(s, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(save);
  });

  it("Escape does not close the sheet while saving", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    let release: (response: Response) => void = () => {};
    api.fetchMock.mockImplementationOnce(
      () => new Promise<Response>((resolve) => (release = resolve)),
    );
    const s = sheet();
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    fireEvent.keyDown(s, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeTruthy();

    await act(async () => {
      release(jsonResponse(BRUSH));
    });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("the skip-on-away toggle reflects and persists a false value", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    const toggle = within(s).getByRole("switch", { name: "Skip on away days" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(toggle.className).not.toContain("defs-switch--on");
    expect(within(s).getByText("No instance when the child is absent")).toBeTruthy();

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect(api.writes()).toHaveLength(1);
    expect((api.writes()[0].body as { skip_on_away: boolean }).skip_on_away).toBe(false);
  });

  it("a 422 from save shows the API's detail and keeps the sheet open", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    api.failNextWrite(jsonResponse({ detail: "interval must be >= 1, got 0" }, 422));

    await act(async () => {
      fireEvent.click(within(sheet()).getByRole("button", { name: "Save changes" }));
    });

    expect(screen.getByTestId("sheet-error").textContent).toBe("interval must be >= 1, got 0");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(api.listFetches()).toBe(1);
    // Save is usable again after the failure.
    expect(
      (within(sheet()).getByRole("button", { name: "Save changes" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("a 403 from save shows the admin-group refusal", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    api.failNextWrite(jsonResponse({ detail: "Forbidden" }, 403));

    await act(async () => {
      fireEvent.click(within(sheet()).getByRole("button", { name: "Save changes" }));
    });
    expect(screen.getByTestId("sheet-error").textContent).toBe(
      "Your account is not in the nestquest-admins group.",
    );
  });

  it("guards against a double submit", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    const save = within(sheet()).getByRole("button", { name: "Save changes" });
    await act(async () => {
      fireEvent.click(save);
      fireEvent.click(save);
    });
    expect(api.writes()).toHaveLength(1);
  });

  it("an incomplete new task is not submitted", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "New" }));
    fireEvent.click(within(sheet()).getByRole("button", { name: "Save changes" }));
    expect(screen.getByTestId("sheet-error").textContent).toBe("Give the task a title.");
    expect(api.writes()).toHaveLength(0);
  });

  it("Cancel closes the sheet without writing", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    fireEvent.click(within(sheet()).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(meta(screen.getByTestId("definition-10"))).toBe("All three · Daily · Morning, Evening");
    expect(api.writes()).toHaveLength(0);
  });

  it("a 403 on load renders the refusal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "Forbidden" }, 403)),
    );
    render(<DefinitionsTab />);
    expect((await screen.findByTestId("definitions-error")).textContent).toContain(
      "Your account is not in the nestquest-admins group.",
    );
  });

  it("scroll column carries the 92px bottom padding", async () => {
    await renderReady();
    expect(screen.getByTestId("definitions-scroll").style.paddingBottom).toBe("92px");
  });
});

/* ── Occurrence preview ─────────────────────────────────────────────── */

/** Past the sheet's 300 ms preview debounce. */
function settleDebounce(): Promise<void> {
  return act(() => new Promise<void>((resolve) => setTimeout(resolve, 400)));
}

function previewText(): string | null {
  return screen.queryByTestId("occurrence-preview")?.textContent ?? null;
}

/** BINS' rule (every 2 weeks on Mon, Thu) from 2026-10-05. */
const BINS_DATES = ["2026-10-05", "2026-10-08", "2026-10-19", "2026-10-22", "2026-11-02"];
/** The same rule on Tuesdays only. */
const TUESDAY_DATES = ["2026-10-06", "2026-10-20", "2026-11-03", "2026-11-17", "2026-12-01"];

function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("DefinitionsTab occurrence preview", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("previews a weekly rule's next dates in plain language from the API", async () => {
    await renderReady();
    api.setPreview(async () => jsonResponse({ dates: BINS_DATES }));
    fireEvent.click(screen.getByTestId("definition-11"));

    await waitFor(() =>
      expect(previewText()).toBe(
        "Next: Mon 5 Oct · Thu 8 Oct · Mon 19 Oct · Thu 22 Oct · Mon 2 Nov · …",
      ),
    );
    expect(api.previews()).toEqual([
      {
        method: "POST",
        path: "/api/v1/admin/quest-definitions/occurrences-preview",
        body: { rule: BINS.rule, count: 5 },
      },
    ]);
  });

  it("re-requests once per rule change, debounced, and not for non-rule edits", async () => {
    await renderReady();
    api.setPreview(async ({ rule }) =>
      jsonResponse({ dates: rule.weekday_set?.includes(0) ? BINS_DATES : TUESDAY_DATES }),
    );
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    await waitFor(() => expect(previewText()).toContain("Mon 5 Oct"));

    // A title edit leaves the rule alone: no new request.
    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Bins" },
    });
    // Three rule edits in quick succession collapse into one request.
    const days = within(s).getByRole("group", { name: "Days" });
    fireEvent.click(within(days).getByRole("button", { name: "Monday" }));
    fireEvent.click(within(days).getByRole("button", { name: "Thursday" }));
    fireEvent.click(within(days).getByRole("button", { name: "Tuesday" }));

    await waitFor(() =>
      expect(previewText()).toBe(
        "Next: Tue 6 Oct · Tue 20 Oct · Tue 3 Nov · Tue 17 Nov · Tue 1 Dec · …",
      ),
    );
    await settleDebounce();
    expect(api.previews()).toHaveLength(2);
    expect(api.previews()[1].body).toEqual({
      rule: { ...BINS.rule, weekday_set: [1] },
      count: 5,
    });

    // An interval change is a rule change too.
    fireEvent.change(within(s).getByRole("spinbutton", { name: "Interval" }), {
      target: { value: "1" },
    });
    await waitFor(() => expect(api.previews()).toHaveLength(3));
    expect((api.previews()[2].body as { rule: DefinitionRule }).rule.interval).toBe(1);
  });

  it("window and assignee edits never request, and a rule edit waits out the debounce", async () => {
    await renderReady();
    api.setPreview(async () => jsonResponse({ dates: BINS_DATES }));
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    await waitFor(() => expect(previewText()).toContain("Mon 5 Oct"));
    expect(api.previews()).toHaveLength(1);

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    // Windows and assignees are not part of the rule.
    fireEvent.click(within(s).getByRole("button", { name: "Morning" }));
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Maeve" }));
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(api.previews()).toHaveLength(1);
    expect(previewText()).toContain("Mon 5 Oct");

    // A rule edit is not requested until the 300 ms debounce elapses.
    const days = within(s).getByRole("group", { name: "Days" });
    fireEvent.click(within(days).getByRole("button", { name: "Tuesday" }));
    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(api.previews()).toHaveLength(1);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(api.previews()).toHaveLength(2);
    expect((api.previews()[1].body as { rule: DefinitionRule }).rule.weekday_set).toEqual([
      0, 1, 3,
    ]);
  });

  it("a rule edit hides the previous rule's dates until its own response arrives", async () => {
    await renderReady();
    const pending: ReturnType<typeof deferred>[] = [];
    api.setPreview(() => {
      const next = deferred();
      pending.push(next);
      return next.promise;
    });
    fireEvent.click(screen.getByTestId("definition-11"));
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => {
      pending[0].resolve(jsonResponse({ dates: BINS_DATES }));
    });
    await waitFor(() => expect(previewText()).toContain("Mon 5 Oct"));

    const days = within(sheet()).getByRole("group", { name: "Days" });
    fireEvent.click(within(days).getByRole("button", { name: "Monday" }));
    // Within the debounce: the old dates are already gone.
    expect(previewText()).toBeNull();
    // Request in flight: still nothing shown for the new rule.
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(previewText()).toBeNull();

    await act(async () => {
      pending[1].resolve(jsonResponse({ dates: ["2026-10-08", "2026-10-22"] }));
    });
    await waitFor(() => expect(previewText()).toBe("Next: Thu 8 Oct · Thu 22 Oct"));
  });

  it("a rule edit hides the previous rule's error until its own response arrives", async () => {
    await renderReady();
    const pending: ReturnType<typeof deferred>[] = [];
    api.setPreview(() => {
      const next = deferred();
      pending.push(next);
      return next.promise;
    });
    fireEvent.click(screen.getByTestId("definition-11"));
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => {
      pending[0].resolve(jsonResponse({ detail: "rule rejected" }, 422));
    });
    await waitFor(() => expect(previewText()).toBe("Upcoming dates unavailable: rule rejected"));

    const days = within(sheet()).getByRole("group", { name: "Days" });
    fireEvent.click(within(days).getByRole("button", { name: "Monday" }));
    expect(previewText()).toBeNull();
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(previewText()).toBeNull();

    await act(async () => {
      pending[1].resolve(jsonResponse({ dates: ["2026-10-08"] }));
    });
    await waitFor(() => expect(previewText()).toBe("Next: Thu 8 Oct"));
  });

  it("a stale response resolving after a newer one does not overwrite it", async () => {
    await renderReady();
    const pending: ReturnType<typeof deferred>[] = [];
    api.setPreview(() => {
      const next = deferred();
      pending.push(next);
      return next.promise;
    });
    fireEvent.click(screen.getByTestId("definition-11"));
    await waitFor(() => expect(pending).toHaveLength(1));

    const days = within(sheet()).getByRole("group", { name: "Days" });
    fireEvent.click(within(days).getByRole("button", { name: "Monday" }));
    fireEvent.click(within(days).getByRole("button", { name: "Thursday" }));
    fireEvent.click(within(days).getByRole("button", { name: "Tuesday" }));
    await waitFor(() => expect(pending).toHaveLength(2));

    await act(async () => {
      pending[1].resolve(jsonResponse({ dates: TUESDAY_DATES }));
    });
    await waitFor(() => expect(previewText()).toContain("Tue 6 Oct"));
    await act(async () => {
      pending[0].resolve(jsonResponse({ dates: BINS_DATES }));
    });
    await settleDebounce();
    expect(previewText()).toBe(
      "Next: Tue 6 Oct · Tue 20 Oct · Tue 3 Nov · Tue 17 Nov · Tue 1 Dec · …",
    );
  });

  it("a failed preview shows a non-blocking message and the sheet still saves", async () => {
    await renderReady();
    api.setPreview(async () => jsonResponse({ detail: "rule rejected" }, 422));
    fireEvent.click(screen.getByTestId("definition-10"));

    await waitFor(() => expect(previewText()).toBe("Upcoming dates unavailable: rule rejected"));
    expect(screen.queryByTestId("sheet-error")).toBeNull();

    await act(async () => {
      fireEvent.click(within(sheet()).getByRole("button", { name: "Save changes" }));
    });
    expect(api.writes()).toHaveLength(1);
    expect(api.writes()[0].method).toBe("PATCH");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("an incomplete draft does not call the preview endpoint", async () => {
    await renderReady();
    api.setPreview(async () => jsonResponse({ dates: TUESDAY_DATES }));
    fireEvent.click(screen.getByRole("button", { name: "New" }));
    const s = sheet();
    fireEvent.change(within(s).getByRole("combobox", { name: "Repeats" }), {
      target: { value: "weekly" },
    });
    // Clear the default weekday: a weekly rule with no days is incomplete.
    const days = within(s).getByRole("group", { name: "Days" });
    for (const day of within(days).getAllByRole("button")) {
      if (day.getAttribute("aria-pressed") === "true") fireEvent.click(day);
    }
    await settleDebounce();
    expect(api.previews()).toHaveLength(0);
    expect(previewText()).toBeNull();

    // An unparseable interval is incomplete too.
    fireEvent.click(within(days).getByRole("button", { name: "Tuesday" }));
    fireEvent.change(within(s).getByRole("spinbutton", { name: "Interval" }), {
      target: { value: "" },
    });
    await settleDebounce();
    expect(api.previews()).toHaveLength(0);

    fireEvent.change(within(s).getByRole("spinbutton", { name: "Interval" }), {
      target: { value: "2" },
    });
    await waitFor(() => expect(previewText()).toContain("Tue 6 Oct"));
    expect(api.previews()).toHaveLength(1);
  });
});

describe("DefinitionsTab icon picker", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  /** The Lucide name a row renders, or null for the generic fallback glyph. */
  function rowIcon(row: HTMLElement): string | null {
    const svg = row.querySelector(".defs-row-glyph svg");
    expect(svg).not.toBeNull();
    return svg!.getAttribute("data-icon");
  }

  function iconRadio(s: HTMLElement, label: string): HTMLElement {
    return within(within(s).getByRole("radiogroup", { name: "Icon" })).getByRole("radio", {
      name: label,
    });
  }

  it("ships the curated subset, and every entry renders an SVG", () => {
    expect(DEFINITION_ICONS.map((entry) => entry.name)).toEqual([
      "bed",
      "bath",
      "shower-head",
      "toilet",
      "brush",
      "smile",
      "shirt",
      "washing-machine",
      "utensils",
      "cooking-pot",
      "apple",
      "brush-cleaning",
      "spray-can",
      "trash-2",
      "recycle",
      "sofa",
      "house",
      "backpack",
      "book-open",
      "pencil",
      "music",
      "dog",
      "cat",
      "fish",
      "sprout",
      "droplets",
      "bike",
      "volleyball",
      "gamepad-2",
      "star",
      "heart",
      "sun",
      "moon",
      "clock",
      "calendar",
      "list-checks",
    ]);
    expect(DEFINITION_ICONS.length).toBeGreaterThanOrEqual(24);
    expect(DEFINITION_ICONS.length).toBeLessThanOrEqual(40);
    for (const { name } of DEFINITION_ICONS) {
      const { container, unmount } = render(<DefinitionIcon name={name} />);
      const svg = container.querySelector("svg");
      expect(svg, name).not.toBeNull();
      expect(svg!.getAttribute("data-icon")).toBe(name);
      expect(svg!.querySelectorAll("path, circle, rect, line, polyline, ellipse").length).toBeGreaterThan(0);
      unmount();
    }
  });

  it("a chosen icon is POSTed for a new task and renders on its row", async () => {
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "New" }));
    const s = sheet();
    expect(iconRadio(s, "No icon").getAttribute("aria-checked")).toBe("true");

    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Make the bed" },
    });
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Declan" }));
    fireEvent.click(within(s).getByRole("button", { name: "Morning" }));
    fireEvent.click(iconRadio(s, "Bed"));
    expect(iconRadio(s, "Bed").getAttribute("aria-checked")).toBe("true");
    expect(iconRadio(s, "Bed").className).toContain("defs-icon--on");
    expect(iconRadio(s, "No icon").getAttribute("aria-checked")).toBe("false");

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect(api.writes()).toHaveLength(1);
    expect(api.writes()[0].method).toBe("POST");
    expect((api.writes()[0].body as { icon: string }).icon).toBe("lucide:bed");
    expect(rowIcon(await screen.findByTestId("definition-99"))).toBe("bed");
  });

  it("a chosen icon is PATCHed for an existing task without breaking the assignee omit", async () => {
    await renderReady();
    expect(rowIcon(screen.getByTestId("definition-11"))).toBeNull();
    fireEvent.click(screen.getByTestId("definition-11"));
    const s = sheet();
    expect(iconRadio(s, "No icon").getAttribute("aria-checked")).toBe("true");
    fireEvent.click(iconRadio(s, "Bins"));

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect(screen.queryByTestId("unassign-confirm")).toBeNull();
    expect(api.writes()).toHaveLength(1);
    const { method, path, body } = api.writes()[0];
    expect(method).toBe("PATCH");
    expect(path).toBe("/api/v1/admin/quest-definitions/11");
    expect((body as { icon: string }).icon).toBe("lucide:trash-2");
    // Inactive "Old" stays assigned: the unchanged selection is still omitted.
    expect(body).not.toHaveProperty("assignee_child_ids");
    await waitFor(() => expect(rowIcon(screen.getByTestId("definition-11"))).toBe("trash-2"));
  });

  it("an unchanged icon is still sent on edit and shows as selected", async () => {
    await renderReady();
    expect(rowIcon(screen.getByTestId("definition-10"))).toBe("smile");
    fireEvent.click(screen.getByTestId("definition-10"));
    const s = sheet();
    expect(iconRadio(s, "Smile").getAttribute("aria-checked")).toBe("true");
    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Brush teeth well" },
    });

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect((api.writes()[0].body as { icon: string }).icon).toBe("smile");
  });

  it("an unknown legacy icon falls back to the generic glyph and is kept on save", async () => {
    const legacy: QuestDefinition = { ...BRUSH, id: 20, icon: "rocket-ship-9000" };
    await renderReady([legacy]);
    const row = screen.getByTestId("definition-20");
    expect(rowIcon(row)).toBeNull();

    fireEvent.click(row);
    const s = sheet();
    const group = within(s).getByRole("radiogroup", { name: "Icon" });
    for (const radio of within(group).getAllByRole("radio")) {
      expect(radio.getAttribute("aria-checked")).toBe("false");
    }

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });

    expect((api.writes()[0].body as { icon: string }).icon).toBe("rocket-ship-9000");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(rowIcon(screen.getByTestId("definition-20"))).toBeNull();
  });
});

describe("DefinitionsTab namespaced icons", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function rowIcon(row: HTMLElement): string | null {
    const svg = row.querySelector(".defs-row-glyph svg");
    expect(svg).not.toBeNull();
    return svg!.getAttribute("data-icon");
  }

  function iconRadio(s: HTMLElement, label: string): HTMLElement {
    return within(within(s).getByRole("radiogroup", { name: "Icon" })).getByRole("radio", {
      name: label,
    });
  }

  it("normalizes lucide-namespaced and legacy bare values to one Lucide name", () => {
    expect(normalizeDefinitionIconName("lucide:dog")).toBe("dog");
    expect(normalizeDefinitionIconName("dog")).toBe("dog");
    expect(normalizeDefinitionIconName("fa:dog")).toBeNull();
    expect(normalizeDefinitionIconName("emoji:🐶")).toBeNull();
    expect(normalizeDefinitionIconName("mystery:dog")).toBeNull();
    expect(normalizeDefinitionIconName(null)).toBeNull();
  });

  for (const icon of ["lucide:dog", "dog"]) {
    it(`renders and selects the Dog glyph for ${icon}`, async () => {
      await renderReady([{ ...BRUSH, id: 30, icon }]);
      const row = screen.getByTestId("definition-30");
      expect(rowIcon(row)).toBe("dog");

      fireEvent.click(row);
      const s = sheet();
      expect(iconRadio(s, "Dog").getAttribute("aria-checked")).toBe("true");
      expect(iconRadio(s, "Dog").className).toContain("defs-icon--on");
      expect(iconRadio(s, "No icon").getAttribute("aria-checked")).toBe("false");
    });
  }

  for (const icon of ["fa:dog", "emoji:🐶", "mystery:dog"]) {
    it(`renders the fallback tile and selects nothing for ${icon}`, async () => {
      await renderReady([{ ...BRUSH, id: 31, icon }]);
      const row = screen.getByTestId("definition-31");
      expect(rowIcon(row)).toBeNull();

      fireEvent.click(row);
      const s = sheet();
      const group = within(s).getByRole("radiogroup", { name: "Icon" });
      for (const radio of within(group).getAllByRole("radio")) {
        expect(radio.getAttribute("aria-checked")).toBe("false");
      }
    });
  }

  it("tapping a Lucide choice on a namespaced task PATCHes lucide:<name>, and No icon clears it", async () => {
    await renderReady([{ ...BRUSH, id: 32, icon: "lucide:dog" }]);
    fireEvent.click(screen.getByTestId("definition-32"));
    let s = sheet();
    fireEvent.click(iconRadio(s, "Cat"));
    expect(iconRadio(s, "Cat").getAttribute("aria-checked")).toBe("true");
    expect(iconRadio(s, "Dog").getAttribute("aria-checked")).toBe("false");

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect((api.writes()[0].body as { icon: string }).icon).toBe("lucide:cat");
    await waitFor(() => expect(rowIcon(screen.getByTestId("definition-32"))).toBe("cat"));

    fireEvent.click(screen.getByTestId("definition-32"));
    s = sheet();
    expect(iconRadio(s, "Cat").getAttribute("aria-checked")).toBe("true");
    fireEvent.click(iconRadio(s, "No icon"));
    expect(iconRadio(s, "No icon").getAttribute("aria-checked")).toBe("true");
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect((api.writes()[1].body as { icon: string | null }).icon).toBeNull();
  });
});

/* ── Start date ─────────────────────────────────────────────────────── */

function startDateInput(s: HTMLElement): HTMLInputElement {
  return within(s).getByLabelText("Start date", { selector: "input" }) as HTMLInputElement;
}

describe("DefinitionsTab start date", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("a new task defaults to today and POSTs the chosen start date", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 23, 9, 0)); // Wed 23 Sep 2026, local
    await renderReady();

    fireEvent.click(screen.getByRole("button", { name: "New" }));
    const s = sheet();
    const input = startDateInput(s);
    expect(input.type).toBe("date");
    expect(input.value).toBe("2026-09-23");

    fireEvent.change(within(s).getByRole("textbox", { name: "Title" }), {
      target: { value: "Feed the cat" },
    });
    fireEvent.click(within(s).getByRole("button", { name: /Assigned children/ }));
    fireEvent.click(within(s).getByRole("checkbox", { name: "Declan" }));
    fireEvent.click(within(s).getByRole("button", { name: "Evening" }));
    fireEvent.change(input, { target: { value: "2026-10-15" } });

    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect(api.writes()).toHaveLength(1);
    expect(api.writes()[0].method).toBe("POST");
    expect((api.writes()[0].body as { rule: DefinitionRule }).rule.start_date).toBe("2026-10-15");
  });

  it("an edit pre-fills the definition's start date and PATCHes a changed one", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    const s = sheet();
    const input = startDateInput(s);
    expect(input.value).toBe("2026-01-01");

    fireEvent.change(input, { target: { value: "2026-11-02" } });
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect(api.writes()).toEqual([
      expect.objectContaining({
        method: "PATCH",
        path: "/api/v1/admin/quest-definitions/10",
        body: expect.objectContaining({ rule: rule({ start_date: "2026-11-02" }) }),
      }),
    ]);
  });

  it("the occurrence preview requests the chosen start date", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    const s = sheet();
    await waitFor(() => expect(api.previews()).toHaveLength(1));

    fireEvent.change(startDateInput(s), { target: { value: "2027-03-01" } });
    await settleDebounce();
    await waitFor(() => expect(api.previews()).toHaveLength(2));
    expect((api.previews()[1].body as { rule: DefinitionRule }).rule.start_date).toBe(
      "2027-03-01",
    );
  });

  it("a cleared start date is not submitted", async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId("definition-10"));
    const s = sheet();
    fireEvent.change(startDateInput(s), { target: { value: "" } });
    await act(async () => {
      fireEvent.click(within(s).getByRole("button", { name: "Save changes" }));
    });
    expect(api.writes()).toHaveLength(0);
    expect(within(s).getByText("Pick a start date.")).toBeTruthy();
  });
});
