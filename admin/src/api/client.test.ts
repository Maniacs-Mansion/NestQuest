import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiForbiddenError,
  ApiUnauthorizedError,
  apiFetch,
} from "./client";
import { storeTokens } from "../auth/oidc";
import type { AppConfig } from "../config";

const app: AppConfig = {
  issuer: "https://auth.example.com/application/o/nestquest",
  clientId: "test-client-id",
  apiBaseUrl: "https://api.example.com",
  authorizeEndpoint: "https://auth.example.com/application/o/authorize/",
  tokenEndpoint: "https://auth.example.com/application/o/token/",
  userinfoEndpoint: "https://auth.example.com/application/o/userinfo/",
  endSessionEndpoint: "https://auth.example.com/application/o/nestquest/end-session/",
  redirectUri: "http://localhost:5173/auth/callback",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API client", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("attaches the Bearer token to API calls", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));

    await apiFetch("/api/v1/children", {}, app, fetchMock as any);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/api/v1/children");
    expect(init.headers.Authorization).toBe("Bearer at-123");
  });

  it("throws ApiForbiddenError on 403 (authenticated but refused)", async () => {
    storeTokens({ access_token: "at-123", expires_in: 600 });
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 403 }));

    await expect(
      apiFetch("/api/v1/children", {}, app, fetchMock as any),
    ).rejects.toBeInstanceOf(ApiForbiddenError);
  });

  it("triggers a login redirect on 401 with no refresh token", async () => {
    storeTokens({ access_token: "stale", expires_in: 600 });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 401 }));

    await expect(
      apiFetch("/api/v1/children", {}, app, fetchMock as any),
    ).rejects.toBeInstanceOf(ApiUnauthorizedError);
    expect(assign).toHaveBeenCalledTimes(1);
    const url = new URL(assign.mock.calls[0][0] as string);
    expect(url.origin + url.pathname).toBe(
      "https://auth.example.com/application/o/authorize/",
    );
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  });
});
