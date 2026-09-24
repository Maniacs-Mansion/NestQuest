import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ConfigError,
  discoveryUrlForIssuer,
  readConfig,
  resolveEndpoints,
  resolveEndpointsFromDiscovery,
  type AppConfig,
} from "./config";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Mirrors Authentik's layout: authorize/token/userinfo live OUTSIDE the
// application-specific issuer path, end-session/jwks under it.
function discoveryDocument(issuer: string) {
  const normalized = issuer.replace(/\/+$/, "");
  const origin = new URL(normalized).origin;
  return {
    issuer,
    authorization_endpoint: `${origin}/application/o/authorize/`,
    token_endpoint: `${origin}/application/o/token/`,
    userinfo_endpoint: `${origin}/application/o/userinfo/`,
    end_session_endpoint: `${normalized}/end-session/`,
    jwks_uri: `${normalized}/jwks/`,
  };
}

describe("config", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("readConfig keeps the production issuer as the default", () => {
    const cfg = readConfig({});
    expect(cfg.issuer).toBe("https://auth.cubecraftlabs.com/application/o/nestquest");
    expect(cfg.clientId).toBeUndefined();
  });

  it("readConfig normalizes a trailing slash off a custom issuer", () => {
    expect(
      readConfig({ VITE_AUTHENTIK_ISSUER: "https://sso.custom.example/application/o/custom/" })
        .issuer,
    ).toBe("https://sso.custom.example/application/o/custom");
  });

  it("readConfig hardcodes no OIDC endpoints — they come from discovery", () => {
    const cfg = readConfig({});
    expect(cfg.authorizeEndpoint).toBeUndefined();
    expect(cfg.tokenEndpoint).toBeUndefined();
    expect(cfg.userinfoEndpoint).toBeUndefined();
    expect(cfg.endSessionEndpoint).toBeUndefined();
    expect(cfg.jwksUri).toBeUndefined();
  });

  it("builds the discovery URL for issuers with and without a trailing slash", () => {
    expect(discoveryUrlForIssuer("https://sso.example.com/application/o/app/")).toBe(
      "https://sso.example.com/application/o/app/.well-known/openid-configuration",
    );
    expect(discoveryUrlForIssuer("https://sso.example.com/application/o/app")).toBe(
      "https://sso.example.com/application/o/app/.well-known/openid-configuration",
    );
  });

  it("resolves every endpoint from the discovery document of a non-default issuer", async () => {
    const issuer = "https://sso.other-host.example/application/o/other-app";
    const doc = discoveryDocument(issuer);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(doc));
    const app: AppConfig = {
      issuer,
      clientId: "client-id",
      apiBaseUrl: "https://api.example.com",
      redirectUri: "http://localhost:5173/auth/callback",
    };

    const resolved = await resolveEndpoints(app, fetchMock as unknown as typeof fetch);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://sso.other-host.example/application/o/other-app/.well-known/openid-configuration",
    );
    // Every endpoint comes verbatim from the (non-default) discovery document.
    expect(resolved.authorizeEndpoint).toBe(doc.authorization_endpoint);
    expect(resolved.tokenEndpoint).toBe(doc.token_endpoint);
    expect(resolved.userinfoEndpoint).toBe(doc.userinfo_endpoint);
    expect(resolved.endSessionEndpoint).toBe(doc.end_session_endpoint);
    expect(resolved.jwksUri).toBe(doc.jwks_uri);
    // Proves no hardcoded production host leaked into the resolved endpoints.
    for (const endpoint of [
      resolved.authorizeEndpoint,
      resolved.tokenEndpoint,
      resolved.userinfoEndpoint,
      resolved.endSessionEndpoint,
      resolved.jwksUri,
    ]) {
      expect(endpoint).not.toMatch(/cubecraftlabs/);
    }
  });

  it("resolves discovery for an issuer configured with a trailing slash", async () => {
    const issuer = "https://sso.slashy.example/application/o/slashy/";
    const doc = discoveryDocument(issuer);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(doc));

    const resolved = await resolveEndpointsFromDiscovery(issuer, fetchMock as any);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://sso.slashy.example/application/o/slashy/.well-known/openid-configuration",
    );
    expect(resolved.authorizeEndpoint).toBe(doc.authorization_endpoint);
    expect(resolved.endSessionEndpoint).toBe(doc.end_session_endpoint);
  });

  it("caches discovery per issuer for the session", async () => {
    const issuer = "https://sso.cached.example/application/o/cached";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(discoveryDocument(issuer)));

    const first = await resolveEndpointsFromDiscovery(issuer, fetchMock as any);
    const second = await resolveEndpointsFromDiscovery(issuer, fetchMock as any);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
  });

  it("surfaces a clear configuration error when discovery returns an HTTP error", async () => {
    const issuer = "https://sso.http-error.example/application/o/broken";
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 500 }));

    const error = await resolveEndpointsFromDiscovery(issuer, fetchMock as any).then(
      () => null,
      (error: unknown) => error,
    );

    expect(error).toBeInstanceOf(ConfigError);
    expect((error as Error).message).toContain(issuer);
    expect((error as Error).message).toContain("HTTP 500");
  });

  it("surfaces a clear configuration error when discovery is unreachable", async () => {
    const issuer = "https://sso.unreachable.example/application/o/unreachable";
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("network down"));

    await expect(
      resolveEndpointsFromDiscovery(issuer, fetchMock as any),
    ).rejects.toBeInstanceOf(ConfigError);
  });

  it("surfaces a clear configuration error when the discovery document is incomplete", async () => {
    const issuer = "https://sso.incomplete.example/application/o/incomplete";
    const doc = discoveryDocument(issuer) as Record<string, string>;
    delete doc.end_session_endpoint;
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(doc));

    await expect(
      resolveEndpointsFromDiscovery(issuer, fetchMock as any),
    ).rejects.toThrow(/end_session_endpoint/);
  });

  it("rejects a discovery document advertising a different issuer", async () => {
    const issuer = "https://sso.mismatch.example/application/o/mismatch";
    const doc = {
      ...discoveryDocument(issuer),
      issuer: "https://sso.elsewhere.example/application/o/elsewhere",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(doc));

    await expect(
      resolveEndpointsFromDiscovery(issuer, fetchMock as any),
    ).rejects.toThrow(/issuer mismatch/i);
  });

  it("the bundled config resolves its endpoints from discovery at runtime", async () => {
    const issuer = "https://sso.bundled.example/application/o/bundled";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(discoveryDocument(issuer)));
    const bundled = readConfig({ VITE_AUTHENTIK_ISSUER: `${issuer}/`, VITE_AUTHENTIK_CLIENT_ID: "bundled-client" });
    expect(bundled.authorizeEndpoint).toBeUndefined();

    const resolved = await resolveEndpoints(bundled, fetchMock as any);

    expect(resolved.authorizeEndpoint).toBe(
      "https://sso.bundled.example/application/o/authorize/",
    );
    expect(resolved.tokenEndpoint).toBe("https://sso.bundled.example/application/o/token/");
    expect(resolved.userinfoEndpoint).toBe(
      "https://sso.bundled.example/application/o/userinfo/",
    );
    expect(resolved.endSessionEndpoint).toBe(
      "https://sso.bundled.example/application/o/bundled/end-session/",
    );
    expect(resolved.jwksUri).toBe("https://sso.bundled.example/application/o/bundled/jwks/");
  });

  it("does not re-fetch discovery when the config already carries endpoints", async () => {
    const app: AppConfig = {
      issuer: "https://auth.example.com/application/o/nestquest",
      clientId: "client-id",
      apiBaseUrl: "https://api.example.com",
      authorizeEndpoint: "https://auth.example.com/application/o/authorize/",
      tokenEndpoint: "https://auth.example.com/application/o/token/",
      userinfoEndpoint: "https://auth.example.com/application/o/userinfo/",
      endSessionEndpoint: "https://auth.example.com/application/o/nestquest/end-session/",
      redirectUri: "http://localhost:5173/auth/callback",
    };
    const fetchMock = vi.fn();

    const resolved = await resolveEndpoints(app, fetchMock as any);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(resolved).toBe(app);
  });
});
