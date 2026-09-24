import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

describe("NestQuest Admin shell", () => {
  beforeEach(() => {
    // The Today tab fetches the admin snapshot; keep the shell tests offline.
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
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

  it("starts on the Today screen and switches on tab click", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Today" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(screen.getByRole("heading", { name: "History" })).toBeTruthy();
    expect(screen.getByRole("tabpanel").textContent).not.toContain("placeholder");
    expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("the Tasks tab renders the definitions screen", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));

    expect(screen.getByRole("heading", { name: "Tasks" })).toBeTruthy();
    expect(screen.getByRole("tabpanel").textContent).not.toContain("placeholder");
  });
});