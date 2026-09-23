import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildAuthorizeUrl,
  clearAuth,
  getToken,
  handleCallback,
  logout,
  storeTokens,
} from "./oidc";
import type { AppConfig } from "../config";

function testApp(): AppConfig {
  return {
    issuer: "https://auth.example.com/application/o/nestquest",
    clientId: "test-client-id",
    apiBaseUrl: "https://api.example.com",
    authorizeEndpoint: "https://auth.example.com/application/o/authorize/",
    tokenEndpoint: "https://auth.example.com/application/o/token/",
    userinfoEndpoint: "https://auth.example.com/application/o/userinfo/",
    endSessionEndpoint: "https://auth.example.com/application/o/nestquest/end-session/",
    redirectUri: "http://localhost:5173/auth/callback",
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("OIDC flow", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("buildAuthorizeUrl carries all required params and stores state/verifier", async () => {
    const app = testApp();
    const url = new URL(await buildAuthorizeUrl(app));

    expect(url.origin + url.pathname).toBe(app.authorizeEndpoint);
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("client_id")).toBe("test-client-id");
    expect(url.searchParams.get("redirect_uri")).toBe(app.redirectUri);
    expect(url.searchParams.get("scope")).toBe("openid email profile");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(url.searchParams.get("state")).toMatch(/^[A-Za-z0-9_-]+$/);

    expect(sessionStorage.getItem("nestquest.oidc_state")).toBe(
      url.searchParams.get("state"),
    );
    expect(sessionStorage.getItem("nestquest.code_verifier")).toMatch(/^[A-Za-z0-9-._~]{43,128}$/);
  });

  it("handleCallback rejects a mismatched state", async () => {
    await buildAuthorizeUrl(testApp());
    sessionStorage.setItem("nestquest.oidc_state", "different-state");

    const fetchMock = vi.fn();
    await expect(
      handleCallback("?code=abc&state=tampered", testApp(), fetchMock as any),
    ).rejects.toThrow(/state mismatch/i);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getToken()).toBeUndefined();
  });

  it("handleCallback exchanges the code with the correct form body and stores the token", async () => {
    await buildAuthorizeUrl(testApp());
    const verifier = sessionStorage.getItem("nestquest.code_verifier")!;
    const state = sessionStorage.getItem("nestquest.oidc_state")!;

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        access_token: "at-123",
        refresh_token: "rt-456",
        id_token: "id-789",
        expires_in: 300,
      }),
    );
    await handleCallback(`?code=abc&state=${state}`, testApp(), fetchMock as any);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://auth.example.com/application/o/token/");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");

    const body = new URLSearchParams(init.body);
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code")).toBe("abc");
    expect(body.get("redirect_uri")).toBe(testApp().redirectUri);
    expect(body.get("client_id")).toBe("test-client-id");
    expect(body.get("code_verifier")).toBe(verifier);
    expect(body.has("client_secret")).toBe(false);

    expect(getToken()).toBe("at-123");
    // one-time values consumed
    expect(sessionStorage.getItem("nestquest.oidc_state")).toBeNull();
    expect(sessionStorage.getItem("nestquest.code_verifier")).toBeNull();
  });

  it("handleCallback surfaces provider errors", async () => {
    await expect(
      handleCallback("?error=access_denied&error_description=nope", testApp(), vi.fn() as any),
    ).rejects.toThrow(/nope|access_denied/);
  });

  it("clearAuth removes all stored auth data", () => {
    storeTokens({ access_token: "a", refresh_token: "r", expires_in: 60 });
    clearAuth();
    expect(getToken()).toBeUndefined();
    expect(sessionStorage.length).toBe(0);
  });

  it("logout clears auth and redirects to the end-session endpoint", async () => {
    storeTokens({ access_token: "a", id_token: "idt", expires_in: 60 });
    const assign = vi.fn();
    const original = window.location;
    vi.stubGlobal("location", { ...original, assign, origin: "http://localhost:5173" });

    await logout(testApp());

    expect(assign).toHaveBeenCalledTimes(1);
    const url = new URL(assign.mock.calls[0][0] as string);
    expect(url.toString()).toBe(
      "https://auth.example.com/application/o/nestquest/end-session/?id_token_hint=idt&client_id=test-client-id&post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A5173",
    );
    expect(getToken()).toBeUndefined();
    vi.unstubAllGlobals();
  });

  it("buildAuthorizeUrl resolves the authorize endpoint via discovery for a non-default issuer", async () => {
    const issuer = "https://sso.discovery.example/application/o/discovered";
    const discoveryDoc = {
      issuer,
      authorization_endpoint: "https://sso.discovery.example/application/o/authorize/",
      token_endpoint: "https://sso.discovery.example/application/o/token/",
      userinfo_endpoint: "https://sso.discovery.example/application/o/userinfo/",
      end_session_endpoint: `${issuer}/end-session/`,
      jwks_uri: `${issuer}/jwks/`,
    };
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        String(url).endsWith("/.well-known/openid-configuration")
          ? jsonResponse(discoveryDoc)
          : jsonResponse({}),
      ),
    );
    const app: AppConfig = {
      issuer,
      clientId: "test-client-id",
      apiBaseUrl: "https://api.example.com",
      redirectUri: "http://localhost:5173/auth/callback",
    };

    const url = new URL(await buildAuthorizeUrl(app, fetchMock as any));

    // The authorize endpoint comes from the discovery document — Authentik
    // serves it outside the app-specific issuer path, so it is NOT
    // `${issuer}/authorize/` and must never be a hardcoded production host.
    expect(url.origin + url.pathname).toBe(discoveryDoc.authorization_endpoint);
    expect(url.searchParams.get("client_id")).toBe("test-client-id");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `${issuer}/.well-known/openid-configuration`,
    );
  });
});
