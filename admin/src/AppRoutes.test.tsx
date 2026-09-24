import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  function probeCalls(fetchMock: ReturnType<typeof vi.fn>): string[] {
    return fetchMock.mock.calls
      .map(([url]) => String(url))
      .filter((url) => url.includes("/api/"));
  }

  it("probes exactly GET /api/v1/admin/ping and no non-admin path", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByTestId("probe-error-screen")).toBeTruthy();
    });
    const calls = probeCalls(fetchMock);
    expect(calls).toEqual([`${config.apiBaseUrl}/api/v1/admin/ping`]);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method ?? "GET").toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer at-123");
    for (const url of calls) {
      expect(new URL(url, "http://localhost").pathname.startsWith("/api/v1/admin/")).toBe(true);
    }
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
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `${config.apiBaseUrl}/api/v1/admin/ping`,
    );
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
    expect(screen.queryByRole("tab", { name: "Today" })).toBeNull();
  });

  it("keeps the login flow when the probe answers 401", async () => {
    storeTokens({ access_token: "stale", expires_in: 600 });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      String(url).includes("/api/v1/admin/ping")
        ? new Response("", { status: 401 })
        : jsonResponse({
            issuer: config.issuer,
            authorization_endpoint: "https://auth.example.com/authorize/",
            token_endpoint: "https://auth.example.com/token/",
            userinfo_endpoint: "https://auth.example.com/userinfo/",
            end_session_endpoint: "https://auth.example.com/end-session/",
            jwks_uri: "https://auth.example.com/jwks/",
          }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByTestId("login-screen")).toBeTruthy();
    });
    expect(assign).toHaveBeenCalledTimes(1);
    const redirect = new URL(assign.mock.calls[0][0] as string);
    expect(redirect.origin + redirect.pathname).toBe("https://auth.example.com/authorize/");
    expect(probeCalls(fetchMock)).toEqual([`${config.apiBaseUrl}/api/v1/admin/ping`]);
    expect(screen.queryByRole("tab", { name: "Today" })).toBeNull();
    expect(screen.queryByTestId("probe-error-screen")).toBeNull();
  });

  for (const status of [404, 500]) {
    it(`shows the error screen, not the shell, when the probe answers ${status}`, async () => {
      storeTokens({ access_token: "at-123", expires_in: 600 });
      const fetchMock = vi.fn().mockResolvedValue(new Response("", { status }));
      vi.stubGlobal("fetch", fetchMock);

      render(<AppRoutes />);

      await waitFor(() => {
        expect(screen.getByTestId("probe-error-screen")).toBeTruthy();
      });
      expect(screen.getByText(new RegExp(`answered ${status}`))).toBeTruthy();
      expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
      expect(screen.queryByRole("tab", { name: "Today" })).toBeNull();
      expect(screen.queryByTestId("refusal-screen")).toBeNull();
    });
  }

  it("shows the error screen, not the shell, when the probe request fails", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByTestId("probe-error-screen")).toBeTruthy();
    });
    expect(screen.getByText(/could not be reached/i)).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "Today" })).toBeNull();
  });

  it("re-probes on retry and enters the shell once the probe succeeds", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    // After the retry the ping succeeds; the shell's own tab loads stay pending.
    let pings = 0;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (!String(url).endsWith("/api/v1/admin/ping")) return new Promise(() => {});
      pings += 1;
      return Promise.resolve(new Response("", { status: pings === 1 ? 500 : 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AppRoutes />);

    await waitFor(() => {
      expect(screen.getByTestId("probe-error-screen")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Today" })).toBeTruthy();
    });
    expect(String(fetchMock.mock.calls[1][0])).toBe(
      `${config.apiBaseUrl}/api/v1/admin/ping`,
    );
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
