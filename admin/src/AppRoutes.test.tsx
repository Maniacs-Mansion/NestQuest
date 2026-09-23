import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import AppRoutes from "./AppRoutes";
import { storeTokens } from "./auth/oidc";
import { config } from "./config";

// The bundled config reads real env at import time; seed the shared module's
// clientId directly so AppRoutes sees a configured app in these tests.
(config as { clientId: string | undefined }).clientId = "test-client-id";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("AppRoutes auth gating", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.history.replaceState({}, "", "/");
  });

  it("renders the login screen when unauthenticated at /", () => {
    render(<AppRoutes />);
    expect(screen.getByTestId("login-screen")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /sign in with authentik/i }),
    ).toBeTruthy();
  });

  it("renders the four-tab shell after a successful authenticated probe", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "NestQuest Admin" })).toBeTruthy();
    });
    for (const label of ["Today", "Tasks", "Schedule", "History"]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
  });

  it("renders the explicit refusal when the API answers 403", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByTestId("refusal-screen")).toBeTruthy();
    });
    expect(screen.getByText(/not in the nestquest-admins group/i)).toBeTruthy();
  });

  it("shows the configuration error screen when the client id is missing", () => {
    const original = config.clientId;
    (config as { clientId: string | undefined }).clientId = undefined;
    try {
      render(<AppRoutes />);
      expect(screen.getByTestId("config-error-screen")).toBeTruthy();
    } finally {
      (config as { clientId: string | undefined }).clientId = original;
    }
  });
});
