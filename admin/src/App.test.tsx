import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let settingsResponse: () => Promise<Response>;

describe("NestQuest Admin shell", () => {
  beforeEach(() => {
    settingsResponse = () => Promise.resolve(jsonResponse({ timezone: "" }));
    // The shell loads the stored application timezone; every tab's own
    // requests stay pending so the shell tests remain offline.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        String(url).endsWith("/api/v1/admin/settings")
          ? settingsResponse()
          : new Promise<Response>(() => {}),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the title and all four tab labels", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "NestQuest Admin" })).toBeTruthy();
    for (const label of ["Today", "Tasks", "Schedule", "History"]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
  });

  it("starts on the Today screen and switches on tab click", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Today" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(screen.getByRole("heading", { name: "History" })).toBeTruthy();
    expect(screen.getByRole("tabpanel").textContent).not.toContain("placeholder");
    expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("the Tasks tab renders the definitions screen", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));

    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeTruthy();
    expect(screen.getByRole("tabpanel").textContent).not.toContain("placeholder");
  });

  it("renders no screen until the stored application timezone is known", async () => {
    settingsResponse = () => new Promise<Response>(() => {});
    render(<App />);

    expect(screen.getByTestId("timezone-loading")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Today" })).toBeNull();
  });

  it("a failed timezone load says so and retries", async () => {
    settingsResponse = () => Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    render(<App />);

    await screen.findByTestId("timezone-error");
    expect(screen.queryByRole("heading", { name: "Today" })).toBeNull();

    settingsResponse = () => Promise.resolve(jsonResponse({ timezone: "Pacific/Auckland" }));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Today" })).toBeTruthy();
  });
});
