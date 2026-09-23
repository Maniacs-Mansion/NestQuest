import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

describe("NestQuest Admin shell", () => {
  afterEach(cleanup);

  it("renders the title and all four tab labels", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "NestQuest Admin" })).toBeTruthy();
    for (const label of ["Today", "Tasks", "Schedule", "History"]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
  });

  it("starts on the Today placeholder and switches on tab click", () => {
    render(<App />);

    expect(screen.getByRole("tabpanel").textContent).toContain(
      "Today placeholder",
    );

    fireEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(screen.getByRole("tabpanel").textContent).toContain(
      "History placeholder",
    );
    expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });
});