import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "../App";
import SettingsScreen, { SCROLL_BOTTOM_PADDING } from "./SettingsScreen";
import type { AdminChild } from "../api/definitions";
import type { HouseholdSettings } from "../api/settings";
import { storeTokens } from "../auth/oidc";

const CHILDREN_PATH = "/api/v1/admin/children";
const REORDER_PATH = `${CHILDREN_PATH}/reorder`;
const SETTINGS_PATH = "/api/v1/admin/settings";

const DEFAULT_SETTINGS: HouseholdSettings = {
  horizon_days: 14,
  day_rollover_time: "03:00",
  notify_target: "notify.family",
  morning_summary_time: "07:00",
  afternoon_reminder_time: "15:30",
  end_of_day_report_time: "20:00",
  morning_summary_enabled: true,
  afternoon_reminder_enabled: false,
  end_of_day_report_enabled: true,
  celebration_enabled: false,
  timezone: "America/Chicago",
};

function child(
  id: number,
  display_name: string,
  sort_order: number,
  extra: Partial<AdminChild> = {},
): AdminChild {
  return { id, display_name, colour: null, avatar_ref: null, sort_order, is_active: true, ...extra };
}

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

let children: AdminChild[];
let settings: HouseholdSettings;
/** Overrides the next write's response (the store is left untouched). */
let writeResponse: (() => Response) | null;
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

function childGets(): number {
  return calls().filter((c) => c.method === "GET" && c.path === CHILDREN_PATH).length;
}

async function routeFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const path = new URL(url, "http://x").pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : undefined;
  if (method !== "GET" && writeResponse) {
    const respond = writeResponse;
    writeResponse = null;
    return respond();
  }
  if (path === CHILDREN_PATH && method === "GET") return jsonResponse({ children });
  if (path === SETTINGS_PATH && method === "GET") return jsonResponse(settings);
  if (path === SETTINGS_PATH && method === "PATCH") {
    settings = { ...settings, ...body };
    return jsonResponse(settings);
  }
  if (path === CHILDREN_PATH && method === "POST") {
    const created = child(9, body.display_name, body.sort_order ?? 0, {
      colour: body.colour ?? null,
      avatar_ref: body.avatar_ref ?? null,
    });
    children = [...children, created];
    return jsonResponse(created, 201);
  }
  if (path === REORDER_PATH && method === "POST") {
    const ids = body.ordered_ids as number[];
    children = children.map((c) => ({ ...c, sort_order: ids.indexOf(c.id) + 1 }));
    return jsonResponse({ status: "ok" });
  }
  const activeMatch = /\/children\/(\d+)\/active$/.exec(path);
  if (activeMatch && method === "PATCH") {
    const id = Number(activeMatch[1]);
    children = children.map((c) => (c.id === id ? { ...c, is_active: body.is_active } : c));
    return jsonResponse(children.find((c) => c.id === id));
  }
  const editMatch = /\/children\/(\d+)$/.exec(path);
  if (editMatch && method === "PATCH") {
    const id = Number(editMatch[1]);
    children = children.map((c) => (c.id === id ? { ...c, ...body } : c));
    return jsonResponse(children.find((c) => c.id === id));
  }
  if (path.endsWith("/admin/snapshot")) {
    return jsonResponse({ today_iso: "2026-09-23", cycle_day: 5, children: [] });
  }
  return jsonResponse({ detail: "unexpected" }, 500);
}

function row(id: number) {
  return within(screen.getByTestId(`settings-child-${id}`));
}

function listNames(): string[] {
  return within(screen.getByRole("list", { name: "Children" }))
    .getAllByRole("listitem")
    .map((li) => li.querySelector(".settings-child-name")?.textContent ?? "");
}

function field(form: HTMLElement, label: string): HTMLInputElement {
  return within(form).getByLabelText(label) as HTMLInputElement;
}

async function renderScreen(onClose = vi.fn()) {
  render(<SettingsScreen onClose={onClose} />);
  await screen.findByTestId("settings-child-1");
  return onClose;
}

describe("SettingsScreen — children", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    children = [
      child(2, "Maeve", 2, { colour: "#16a34a" }),
      child(1, "Declan", 1, { colour: "#0ea5e9", avatar_ref: "fox" }),
      child(3, "Rory", 3, { is_active: false }),
    ];
    settings = { ...DEFAULT_SETTINGS };
    writeResponse = null;
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("lists each child with name, colour swatch, active state and order", async () => {
    await renderScreen();
    expect(listNames()).toEqual(["Declan", "Maeve", "Rory"]);
    expect(row(1).getByText("Order 1 · #0ea5e9")).toBeTruthy();
    expect(screen.getByTestId("settings-swatch-1").style.background).toBe("rgb(14, 165, 233)");
    expect(screen.getByTestId("settings-active-1").textContent).toBe("Active");
    expect(row(3).getByText("Order 3 · no colour")).toBeTruthy();
    expect(screen.getByTestId("settings-swatch-3").style.background).toBe("var(--nq-a-border)");
    expect(screen.getByTestId("settings-active-3").textContent).toBe("Inactive");
    expect(screen.getByTestId("settings-scroll").style.paddingBottom).toBe(SCROLL_BOTTOM_PADDING);
  });

  it("Add posts exactly the entered values, then shows the new child", async () => {
    await renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "Add child" }));
    const form = screen.getByRole("form", { name: "Add child" });
    expect(field(form, "Order").value).toBe("4");
    fireEvent.change(field(form, "Display name"), { target: { value: "  Nora " } });
    fireEvent.click(within(form).getByRole("button", { name: "Colour #7c3aed" }));
    fireEvent.change(field(form, "Avatar ref (optional)"), { target: { value: "owl" } });
    fireEvent.change(field(form, "Order"), { target: { value: "5" } });
    const gets = childGets();
    fireEvent.click(within(form).getByRole("button", { name: "Add child" }));

    await screen.findByTestId("settings-child-9");
    expect(writes()).toEqual([
      {
        method: "POST",
        path: CHILDREN_PATH,
        body: { display_name: "Nora", colour: "#7c3aed", avatar_ref: "owl", sort_order: 5 },
      },
    ]);
    expect(childGets()).toBe(gets + 1);
    expect(listNames()).toEqual(["Declan", "Maeve", "Rory", "Nora"]);
    expect(screen.queryByRole("form", { name: "Add child" })).toBeNull();
  });

  it("Add omits optional fields left blank and rejects a missing name", async () => {
    await renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "Add child" }));
    const form = screen.getByRole("form", { name: "Add child" });
    fireEvent.change(field(form, "Order"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add child" }));
    expect(screen.getByTestId("child-form-error").textContent).toBe("Enter a display name.");
    expect(writes()).toEqual([]);

    fireEvent.change(field(form, "Display name"), { target: { value: "Nora" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add child" }));
    await screen.findByTestId("settings-child-9");
    expect(writes()[0].body).toEqual({ display_name: "Nora" });
  });

  it("Edit patches only the changed fields", async () => {
    await renderScreen();
    fireEvent.click(row(1).getByRole("button", { name: "Edit Declan" }));
    const form = screen.getByRole("form", { name: "Edit Declan" });
    expect(field(form, "Display name").value).toBe("Declan");
    expect(field(form, "Colour").value).toBe("#0ea5e9");
    fireEvent.change(field(form, "Display name"), { target: { value: "Dec" } });
    fireEvent.change(field(form, "Colour"), { target: { value: "#FF8800" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save child" }));

    await waitFor(() => expect(row(1).getByText("Dec")).toBeTruthy());
    expect(writes()).toEqual([
      { method: "PATCH", path: `${CHILDREN_PATH}/1`, body: { display_name: "Dec", colour: "#FF8800" } },
    ]);
    expect(row(1).getByText("Order 1 · #FF8800")).toBeTruthy();
  });

  it("Edit refuses to clear a set colour instead of sending null", async () => {
    await renderScreen();
    fireEvent.click(row(1).getByRole("button", { name: "Edit Declan" }));
    const form = screen.getByRole("form", { name: "Edit Declan" });
    fireEvent.change(field(form, "Colour"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save child" }));
    expect(screen.getByTestId("child-form-error").textContent).toMatch(/cannot be removed/);
    expect(writes()).toEqual([]);
  });

  it("the active toggle patches /children/{id}/active with the new value", async () => {
    await renderScreen();
    fireEvent.click(row(1).getByRole("button", { name: "Deactivate Declan" }));
    await waitFor(() => expect(screen.getByTestId("settings-active-1").textContent).toBe("Inactive"));
    fireEvent.click(row(3).getByRole("button", { name: "Reactivate Rory" }));
    await waitFor(() => expect(screen.getByTestId("settings-active-3").textContent).toBe("Active"));
    expect(writes()).toEqual([
      { method: "PATCH", path: `${CHILDREN_PATH}/1/active`, body: { is_active: false } },
      { method: "PATCH", path: `${CHILDREN_PATH}/3/active`, body: { is_active: true } },
    ]);
  });

  it("reorder posts the complete ordered id list, then shows the new order", async () => {
    await renderScreen();
    expect((row(1).getByRole("button", { name: "Move Declan up" }) as HTMLButtonElement).disabled).toBe(true);
    expect((row(3).getByRole("button", { name: "Move Rory down" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(row(3).getByRole("button", { name: "Move Rory up" }));
    await waitFor(() => expect(listNames()).toEqual(["Declan", "Rory", "Maeve"]));
    expect(writes()).toEqual([{ method: "POST", path: REORDER_PATH, body: { ordered_ids: [1, 3, 2] } }]);
  });

  it("disables the write controls while a request is in flight (no double submit)", async () => {
    await renderScreen();
    let release!: () => void;
    writeResponse = () => jsonResponse({ status: "ok" });
    const gate = new Promise<void>((r) => {
      release = r;
    });
    fetchMock.mockImplementationOnce(async (url: string, init?: RequestInit) => {
      await gate;
      return routeFetch(url, init);
    });
    const up = row(2).getByRole("button", { name: "Move Maeve up" }) as HTMLButtonElement;
    fireEvent.click(up);
    fireEvent.click(up);
    await waitFor(() => expect(up.disabled).toBe(true));
    expect((row(1).getByRole("button", { name: "Deactivate Declan" }) as HTMLButtonElement).disabled).toBe(true);
    expect(writes()).toHaveLength(1);
    release();
    await waitFor(() => expect((row(1).getByRole("button", { name: "Edit Declan" }) as HTMLButtonElement).disabled).toBe(false));
    expect(writes()).toHaveLength(1);
  });

  it("a 422 shows the API detail and keeps the form and the screen open", async () => {
    const onClose = await renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "Add child" }));
    const form = screen.getByRole("form", { name: "Add child" });
    fireEvent.change(field(form, "Display name"), { target: { value: "Nora" } });
    writeResponse = () => jsonResponse({ detail: "display_name is required" }, 422);
    fireEvent.click(within(form).getByRole("button", { name: "Add child" }));

    const error = await screen.findByTestId("child-form-error");
    expect(error.textContent).toBe("The child could not be added: display_name is required");
    expect(screen.getByRole("form", { name: "Add child" })).toBeTruthy();
    expect(field(form, "Display name").value).toBe("Nora");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
  });

  it("a 403 on a row action shows the refusal message and keeps the screen open", async () => {
    const onClose = await renderScreen();
    writeResponse = () => jsonResponse({ detail: "forbidden" }, 403);
    fireEvent.click(row(1).getByRole("button", { name: "Deactivate Declan" }));
    const error = await screen.findByTestId("settings-action-error");
    expect(error.textContent).toContain("Your account is not in the nestquest-admins group.");
    expect(screen.getByTestId("settings-active-1").textContent).toBe("Active");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("a 403 on load shows the refusal message", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: "forbidden" }, 403));
    render(<SettingsScreen onClose={vi.fn()} />);
    const error = await screen.findByTestId("settings-error");
    expect(error.textContent).toContain("Your account is not in the nestquest-admins group.");
  });

  it("Escape and Back close the screen", async () => {
    const onClose = await renderScreen();
    fireEvent.keyDown(screen.getByRole("dialog", { name: "Settings" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("the Today Settings button opens the screen; closing restores focus and the background", async () => {
    render(<App />);
    const settings = await screen.findByRole("button", { name: "Settings" });
    settings.focus();
    fireEvent.click(settings);

    const dialog = await screen.findByRole("dialog", { name: "Settings" });
    await screen.findByTestId("settings-child-1");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Settings" }));
    const tabbar = document.querySelector("nav.admin-tabbar") as HTMLElement;
    expect(tabbar.hasAttribute("inert")).toBe(true);
    expect(dialog.closest("[inert]")).toBeNull();

    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Settings" })).toBeNull());
    expect(tabbar.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Settings" }));
  });
});

describe("SettingsScreen — preferences", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    children = [child(1, "Declan", 1)];
    settings = { ...DEFAULT_SETTINGS };
    writeResponse = null;
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function renderPreferences(onClose = vi.fn()) {
    render(<SettingsScreen onClose={onClose} />);
    await screen.findByTestId("settings-child-1");
    const form = await screen.findByRole("form", { name: "Preferences" });
    return { form, onClose };
  }

  function checkbox(form: HTMLElement, label: string): HTMLInputElement {
    return within(form).getByRole("checkbox", { name: label }) as HTMLInputElement;
  }

  function save(form: HTMLElement) {
    fireEvent.click(within(form).getByRole("button", { name: "Save preferences" }));
  }

  it("renders the current value of all eleven settings form fields", async () => {
    const { form } = await renderPreferences();
    expect(field(form, "Planning horizon (days)").value).toBe("14");
    expect(field(form, "Day rollover").value).toBe("03:00");
    expect(field(form, "Timezone").value).toBe("America/Chicago");
    expect(field(form, "Notify target").value).toBe("notify.family");
    expect(field(form, "Morning summary time").value).toBe("07:00");
    expect(field(form, "Afternoon reminder time").value).toBe("15:30");
    expect(field(form, "End-of-day report time").value).toBe("20:00");
    expect(checkbox(form, "Morning summary").checked).toBe(true);
    expect(checkbox(form, "Afternoon reminder").checked).toBe(false);
    expect(checkbox(form, "End-of-day report").checked).toBe(true);
    expect(checkbox(form, "Celebration").checked).toBe(false);
  });

  it("saving one changed field patches exactly that field", async () => {
    const { form } = await renderPreferences();
    fireEvent.change(field(form, "Planning horizon (days)"), { target: { value: "21" } });
    save(form);
    await screen.findByText("Preferences saved.");
    expect(writes()).toEqual([{ method: "PATCH", path: SETTINGS_PATH, body: { horizon_days: 21 } }]);
    const reloaded = screen.getByRole("form", { name: "Preferences" });
    expect(field(reloaded, "Planning horizon (days)").value).toBe("21");
  });

  it("saving several changed fields sends exactly those", async () => {
    const { form } = await renderPreferences();
    fireEvent.change(field(form, "Day rollover"), { target: { value: "04:15" } });
    fireEvent.change(field(form, "Notify target"), { target: { value: " notify.parents " } });
    fireEvent.change(field(form, "End-of-day report time"), { target: { value: "21:45" } });
    fireEvent.click(checkbox(form, "Afternoon reminder"));
    fireEvent.click(checkbox(form, "Celebration"));
    save(form);
    await screen.findByText("Preferences saved.");
    expect(writes()).toEqual([
      {
        method: "PATCH",
        path: SETTINGS_PATH,
        body: {
          day_rollover_time: "04:15",
          notify_target: "notify.parents",
          end_of_day_report_time: "21:45",
          afternoon_reminder_enabled: true,
          celebration_enabled: true,
        },
      },
    ]);
    const reloaded = screen.getByRole("form", { name: "Preferences" });
    expect(checkbox(reloaded, "Celebration").checked).toBe(true);
    expect(field(reloaded, "Notify target").value).toBe("notify.parents");
  });

  it("with nothing changed it says so and sends no request", async () => {
    const { form } = await renderPreferences();
    fireEvent.click(checkbox(form, "Celebration"));
    fireEvent.click(checkbox(form, "Celebration"));
    save(form);
    expect(screen.getByTestId("preferences-message").textContent).toBe("No changes to save.");
    expect(writes()).toEqual([]);
  });

  it("a 422 shows the API detail naming the field and keeps the edit", async () => {
    const { form, onClose } = await renderPreferences();
    fireEvent.change(field(form, "Notify target"), { target: { value: "notify.nobody" } });
    writeResponse = () => jsonResponse({ detail: "notify_target is not a notify service" }, 422);
    save(form);
    const message = await screen.findByTestId("preferences-message");
    expect(message.textContent).toBe(
      "The preferences could not be saved: notify_target is not a notify service",
    );
    expect(message.getAttribute("role")).toBe("alert");
    expect(field(form, "Notify target").value).toBe("notify.nobody");
    expect(writes()).toEqual([
      { method: "PATCH", path: SETTINGS_PATH, body: { notify_target: "notify.nobody" } },
    ]);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("a 403 on save shows the refusal message", async () => {
    const { form } = await renderPreferences();
    fireEvent.click(checkbox(form, "Celebration"));
    writeResponse = () => jsonResponse({ detail: "forbidden" }, 403);
    save(form);
    const message = await screen.findByTestId("preferences-message");
    expect(message.textContent).toContain("Your account is not in the nestquest-admins group.");
    expect(checkbox(form, "Celebration").checked).toBe(true);
  });

  it.each([
    ["empty", ""],
    ["zero", "0"],
    ["oversized (Infinity would serialize as null and reset the field)", "9".repeat(400)],
    ["past the safe-integer range", "123456789012345678901"],
  ])("a %s horizon is rejected before any request", async (_case, value) => {
    const { form } = await renderPreferences();
    fireEvent.change(field(form, "Planning horizon (days)"), { target: { value } });
    save(form);
    expect(screen.getByTestId("preferences-message").textContent).toBe(
      "Planning horizon must be a whole number of days, at least 1.",
    );
    expect(writes()).toEqual([]);
  });

  it("disables every write control while a save is in flight (no double submit)", async () => {
    const { form } = await renderPreferences();
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    fetchMock.mockImplementationOnce(async (url: string, init?: RequestInit) => {
      await gate;
      return routeFetch(url, init);
    });
    fireEvent.click(checkbox(form, "Celebration"));
    const button = within(form).getByRole("button", { name: "Save preferences" }) as HTMLButtonElement;
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(button.disabled).toBe(true));
    expect(checkbox(form, "Celebration").disabled).toBe(true);
    expect(field(form, "Planning horizon (days)").disabled).toBe(true);
    expect((row(1).getByRole("button", { name: "Edit Declan" }) as HTMLButtonElement).disabled).toBe(true);
    expect(writes()).toHaveLength(1);
    release();
    await screen.findByText("Preferences saved.");
    expect(writes()).toHaveLength(1);
  });

  it("a changed timezone patches exactly the timezone", async () => {
    const { form } = await renderPreferences();
    const input = field(form, "Timezone");
    expect(input.getAttribute("list")).toBe("settings-timezones");
    fireEvent.change(input, { target: { value: " Europe/London " } });
    save(form);
    await screen.findByText("Preferences saved.");
    expect(writes()).toEqual([{ method: "PATCH", path: SETTINGS_PATH, body: { timezone: "Europe/London" } }]);
    const reloaded = screen.getByRole("form", { name: "Preferences" });
    expect(field(reloaded, "Timezone").value).toBe("Europe/London");
  });

  it.each(["New York", "America/New York", "EST5EDT?", "/Chicago"])(
    "an invalid timezone %j is rejected before any request",
    async (value) => {
      const { form } = await renderPreferences();
      fireEvent.change(field(form, "Timezone"), { target: { value } });
      save(form);
      expect(screen.getByTestId("preferences-message").textContent).toBe(
        "Timezone must be an IANA zone like America/New_York, or UTC.",
      );
      expect(field(form, "Timezone").value).toBe(value);
      expect(writes()).toEqual([]);
    },
  );

  it("a 422 on an unknown timezone shows the API detail and keeps the edit", async () => {
    const { form } = await renderPreferences();
    fireEvent.change(field(form, "Timezone"), { target: { value: "Mars/Olympus_Mons" } });
    writeResponse = () =>
      jsonResponse({ detail: "timezone must be an IANA time zone name such as 'America/New_York'" }, 422);
    save(form);
    const message = await screen.findByTestId("preferences-message");
    expect(message.textContent).toBe(
      "The preferences could not be saved: timezone must be an IANA time zone name such as 'America/New_York'",
    );
    expect(field(form, "Timezone").value).toBe("Mars/Olympus_Mons");
    expect(field(form, "Timezone").disabled).toBe(false);
  });

  it("a failed load shows the reason and Try again refetches", async () => {
    let fail = true;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (fail && new URL(url, "http://x").pathname === SETTINGS_PATH) {
        return jsonResponse({ detail: "boom" }, 500);
      }
      return routeFetch(url, init);
    });
    render(<SettingsScreen onClose={vi.fn()} />);
    const error = await screen.findByTestId("preferences-error");
    expect(error.textContent).toContain("Preferences could not be loaded: boom");
    fail = false;
    fireEvent.click(within(error).getByRole("button", { name: "Try again" }));
    await screen.findByRole("form", { name: "Preferences" });
  });
});

describe("SettingsScreen — timezone auto-set", () => {
  let zoneSpy: ReturnType<typeof vi.spyOn> | null;

  function mockBrowserZone(timeZone: string | undefined) {
    const real = Intl.DateTimeFormat.prototype.resolvedOptions;
    zoneSpy = vi
      .spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions")
      .mockImplementation(function (this: Intl.DateTimeFormat) {
        return { ...real.call(this), timeZone } as Intl.ResolvedDateTimeFormatOptions;
      });
  }

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    children = [child(1, "Declan", 1)];
    settings = { ...DEFAULT_SETTINGS, timezone: "" };
    writeResponse = null;
    zoneSpy = null;
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => routeFetch(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    zoneSpy?.mockRestore();
    vi.unstubAllGlobals();
  });

  async function renderForm() {
    render(<SettingsScreen onClose={vi.fn()} />);
    await screen.findByTestId("settings-child-1");
    return screen.findByRole("form", { name: "Preferences" });
  }

  it("an unset timezone is set once, on load, to the browser's zone and shown", async () => {
    mockBrowserZone("America/New_York");
    const form = await renderForm();
    expect(field(form, "Timezone").value).toBe("America/New_York");
    expect(writes()).toEqual([
      { method: "PATCH", path: SETTINGS_PATH, body: { timezone: "America/New_York" } },
    ]);
    expect(settings.timezone).toBe("America/New_York");

    // A later save of another field does not re-send the timezone.
    fireEvent.change(field(form, "Planning horizon (days)"), { target: { value: "21" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save preferences" }));
    await screen.findByText("Preferences saved.");
    expect(writes()).toHaveLength(2);
    expect(writes()[1].body).toEqual({ horizon_days: 21 });
  });

  it("StrictMode's doubled effects still auto-set exactly once", async () => {
    mockBrowserZone("America/New_York");
    render(
      <StrictMode>
        <SettingsScreen onClose={vi.fn()} />
      </StrictMode>,
    );
    const form = await screen.findByRole("form", { name: "Preferences" });
    expect(field(form, "Timezone").value).toBe("America/New_York");
    expect(writes()).toEqual([
      { method: "PATCH", path: SETTINGS_PATH, body: { timezone: "America/New_York" } },
    ]);
  });

  it("an admin clearing the timezone is not re-set by the browser zone", async () => {
    mockBrowserZone("America/New_York");
    const form = await renderForm();
    fireEvent.change(field(form, "Timezone"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save preferences" }));
    await screen.findByText("Preferences saved.");
    expect(writes().map((w) => w.body)).toEqual([{ timezone: "America/New_York" }, { timezone: "" }]);
    const reloaded = screen.getByRole("form", { name: "Preferences" });
    expect(field(reloaded, "Timezone").value).toBe("");
  });

  it("a set timezone is shown and never overwritten by the browser zone", async () => {
    mockBrowserZone("America/New_York");
    settings = { ...DEFAULT_SETTINGS, timezone: "Europe/Dublin" };
    const form = await renderForm();
    expect(field(form, "Timezone").value).toBe("Europe/Dublin");
    expect(writes()).toEqual([]);
  });

  it.each([
    ["nothing", undefined],
    ["an empty zone", ""],
    ["an unknown zone", "Etc/Unknown"],
    ["a non-IANA zone", "not a zone"],
  ])("detection returning %s leaves the field empty and sends nothing", async (_case, zone) => {
    mockBrowserZone(zone);
    const form = await renderForm();
    expect(field(form, "Timezone").value).toBe("");
    expect(screen.queryByTestId("preferences-message")).toBeNull();
    expect(writes()).toEqual([]);
  });

  it("a rejected auto-set shows why and leaves the field empty for manual entry", async () => {
    mockBrowserZone("America/New_York");
    writeResponse = () => jsonResponse({ detail: "timezone is not known" }, 422);
    const form = await renderForm();
    expect(field(form, "Timezone").value).toBe("");
    expect(field(form, "Timezone").disabled).toBe(false);
    expect(screen.getByTestId("preferences-message").textContent).toBe(
      "The timezone could not be set to America/New_York: timezone is not known",
    );
    expect(writes()).toHaveLength(1);
  });
});
