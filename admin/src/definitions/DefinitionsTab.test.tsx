import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import DefinitionsTab from "./DefinitionsTab";
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

/**
 * A stub of the admin API: serves the list and children, records writes, and
 * lets a test queue a response for the next write.
 */
function fakeApi(initial: QuestDefinition[]) {
  let definitions = [...initial];
  const calls: Call[] = [];
  let nextWrite: Response | null = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init.method ?? "GET";
    const body = typeof init.body === "string" ? JSON.parse(init.body) : null;
    calls.push({ method, path, body });
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
        icon: null,
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
    writes: () => calls.filter((c) => c.method !== "GET"),
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
    // The icon is never sent, so it is carried through unchanged.
    expect(api.writes()[0].body).not.toHaveProperty("icon");

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
