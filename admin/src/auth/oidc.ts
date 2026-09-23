/**
 * OIDC authorization-code + PKCE flow for a PUBLIC client.
 *
 * Never sends a client_secret anywhere. Tokens are stored in sessionStorage
 * (per-tab, cleared on tab close) — never localStorage.
 */
import { config, resolveEndpoints, type AppConfig, type ResolvedAppConfig } from "../config";
import {
  computeCodeChallenge,
  generateCodeVerifier,
  generateState,
} from "./pkce";

const STORAGE_KEYS = {
  accessToken: "nestquest.access_token",
  refreshToken: "nestquest.refresh_token",
  expiresAt: "nestquest.expires_at",
  idToken: "nestquest.id_token",
  state: "nestquest.oidc_state",
  codeVerifier: "nestquest.code_verifier",
} as const;

export class AuthError extends Error {}

export interface TokenResponse {
  access_token?: string;
  refresh_token?: string;
  id_token?: string;
  expires_in?: number;
  token_type?: string;
}

function makeScopes(): string {
  return "openid email profile";
}

/**
 * Build the Authentik authorization redirect URL, storing state + verifier in
 * sessionStorage so the callback can validate them. Endpoints are resolved
 * from the issuer's OIDC discovery document when not set on the config.
 */
export async function buildAuthorizeUrl(
  app: AppConfig = config,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  if (!app.clientId) {
    throw new AuthError(
      "Missing VITE_AUTHENTIK_CLIENT_ID configuration. Set it in your .env before building the admin PWA.",
    );
  }
  const resolved = await resolveEndpoints(app, fetchImpl);
  const state = generateState();
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await computeCodeChallenge(codeVerifier);

  sessionStorage.setItem(STORAGE_KEYS.state, state);
  sessionStorage.setItem(STORAGE_KEYS.codeVerifier, codeVerifier);

  const url = new URL(resolved.authorizeEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", app.clientId);
  url.searchParams.set("redirect_uri", app.redirectUri);
  url.searchParams.set("scope", makeScopes());
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  return url.toString();
}

/**
 * Handle the OAuth callback: validate state, exchange the code at the token
 * endpoint (PKCE, form-urlencoded, no client_secret), store tokens.
 */
export async function handleCallback(
  query: URLSearchParams | string = window.location.search,
  app: AppConfig = config,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const params =
    typeof query === "string" ? new URLSearchParams(query) : query;

  const providerError = params.get("error");
  if (providerError) {
    throw new AuthError(
      params.get("error_description") || `Provider returned error: ${providerError}`,
    );
  }

  const code = params.get("code");
  const state = params.get("state");
  if (!code || !state) {
    throw new AuthError("Callback is missing the code or state parameter.");
  }

  const storedState = sessionStorage.getItem(STORAGE_KEYS.state);
  const codeVerifier = sessionStorage.getItem(STORAGE_KEYS.codeVerifier);
  if (!storedState || storedState !== state || !codeVerifier) {
    throw new AuthError("State mismatch — possible CSRF; refusing to log in.");
  }

  if (!app.clientId) {
    throw new AuthError(
      "Missing VITE_AUTHENTIK_CLIENT_ID configuration. Set it in your .env before building the admin PWA.",
    );
  }

  const resolved: ResolvedAppConfig = await resolveEndpoints(app, fetchImpl);

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: app.redirectUri,
    client_id: app.clientId,
    code_verifier: codeVerifier,
  });

  const response = await fetchImpl(resolved.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!response.ok) {
    throw new AuthError(`Token exchange failed with HTTP ${response.status}`);
  }
  const tokens = (await response.json()) as TokenResponse;
  if (!tokens.access_token) {
    throw new AuthError("Token response did not include an access token.");
  }

  storeTokens(tokens);
  // One-time use values are consumed on success.
  sessionStorage.removeItem(STORAGE_KEYS.state);
  sessionStorage.removeItem(STORAGE_KEYS.codeVerifier);
}

export function storeTokens(tokens: TokenResponse): void {
  sessionStorage.setItem(STORAGE_KEYS.accessToken, tokens.access_token!);
  if (tokens.refresh_token) {
    sessionStorage.setItem(STORAGE_KEYS.refreshToken, tokens.refresh_token);
  }
  if (tokens.id_token) {
    sessionStorage.setItem(STORAGE_KEYS.idToken, tokens.id_token);
  }
  if (typeof tokens.expires_in === "number") {
    sessionStorage.setItem(
      STORAGE_KEYS.expiresAt,
      String(Date.now() + tokens.expires_in * 1000),
    );
  }
}

export function getToken(): string | undefined {
  return sessionStorage.getItem(STORAGE_KEYS.accessToken) ?? undefined;
}

export function getRefreshToken(): string | undefined {
  return sessionStorage.getItem(STORAGE_KEYS.refreshToken) ?? undefined;
}

export function getIdToken(): string | undefined {
  return sessionStorage.getItem(STORAGE_KEYS.idToken) ?? undefined;
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

/** True once the stored access token has passed its (approximate) expiry. */
export function isExpired(): boolean {
  const expiresAt = sessionStorage.getItem(STORAGE_KEYS.expiresAt);
  if (!expiresAt) return false;
  return Date.now() >= Number(expiresAt);
}

/**
 * Refresh the access token with the refresh token grant. Returns false when
 * no refresh token is stored or the grant fails (caller should re-login).
 */
export async function refreshAccessToken(
  app: AppConfig = config,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken || !app.clientId) return false;

  const resolved = await resolveEndpoints(app, fetchImpl);

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
    client_id: app.clientId,
  });

  const response = await fetchImpl(resolved.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!response.ok) return false;
  const tokens = (await response.json()) as TokenResponse;
  if (!tokens.access_token) return false;
  storeTokens(tokens);
  return true;
}

export function clearAuth(): void {
  for (const key of Object.values(STORAGE_KEYS)) {
    sessionStorage.removeItem(key);
  }
}

/** Sign out: clear local auth, then send the browser to the end-session endpoint. */
export async function logout(
  app: AppConfig = config,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const resolved = await resolveEndpoints(app, fetchImpl);
  const idTokenHint = getIdToken();
  clearAuth();
  const params = new URLSearchParams();
  if (idTokenHint) params.set("id_token_hint", idTokenHint);
  if (app.clientId) params.set("client_id", app.clientId);
  params.set("post_logout_redirect_uri", window.location.origin);
  window.location.assign(`${resolved.endSessionEndpoint}?${params.toString()}`);
}
