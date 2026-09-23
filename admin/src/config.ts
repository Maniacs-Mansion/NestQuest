/**
 * Runtime configuration, read from Vite env (import.meta.env).
 * See .env.example for the variables and their defaults.
 *
 * OIDC endpoints are NOT hardcoded here. They are resolved lazily from the
 * issuer's OIDC discovery document (see resolveEndpoints), because Authentik
 * serves authorize/token/userinfo OUTSIDE the application-specific issuer
 * path (issuer is /application/o/<slug>/, authorize is /application/o/authorize/).
 * Both hardcoding the production host and naively concatenating onto the
 * issuer would break non-default issuers; discovery is the only correct way.
 */

export interface AppConfig {
  issuer: string;
  clientId: string | undefined;
  apiBaseUrl: string;
  /** Resolved from the issuer's OIDC discovery document — see resolveEndpoints(). */
  authorizeEndpoint?: string;
  tokenEndpoint?: string;
  userinfoEndpoint?: string;
  endSessionEndpoint?: string;
  jwksUri?: string;
  redirectUri: string;
}

/** AppConfig whose OIDC endpoints have been filled in by resolveEndpoints(). */
export type ResolvedAppConfig = AppConfig &
  Required<
    Pick<
      AppConfig,
      "authorizeEndpoint" | "tokenEndpoint" | "userinfoEndpoint" | "endSessionEndpoint"
    >
  >;

export interface DiscoveredEndpoints {
  issuer: string;
  authorizeEndpoint: string;
  tokenEndpoint: string;
  userinfoEndpoint: string;
  endSessionEndpoint: string;
  jwksUri: string;
}

/** Raised when OIDC discovery fails or the configuration is unusable. */
export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

const REQUIRED_ENDPOINT_NAMES = [
  "authorizeEndpoint",
  "tokenEndpoint",
  "userinfoEndpoint",
  "endSessionEndpoint",
] as const;

export function readConfig(env: Record<string, string | undefined> = import.meta.env as any): AppConfig {
  const issuer = (
    env.VITE_AUTHENTIK_ISSUER || "https://auth.cubecraftlabs.com/application/o/nestquest/"
  ).replace(/\/$/, "");
  const clientId = env.VITE_AUTHENTIK_CLIENT_ID;
  const apiBaseUrl = env.VITE_API_BASE_URL || "https://nestquest.cubecraftlabs.com";

  return {
    issuer,
    // No default: a missing client id must surface as a configuration error
    // screen, not a broken redirect to Authentik.
    clientId: clientId || undefined,
    apiBaseUrl,
    // authorize/token/userinfo/end-session endpoints are resolved from the
    // issuer's discovery document at runtime — never hardcoded here.
    redirectUri: `${window.location.origin}/auth/callback`,
  };
}

export const config: AppConfig = readConfig();

interface DiscoveryDocument {
  issuer?: unknown;
  authorization_endpoint?: unknown;
  token_endpoint?: unknown;
  userinfo_endpoint?: unknown;
  end_session_endpoint?: unknown;
  jwks_uri?: unknown;
}

function normalizeIssuer(issuer: string): string {
  return issuer.replace(/\/+$/, "");
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/** Discovery document location for an issuer, tolerant of a trailing slash. */
export function discoveryUrlForIssuer(issuer: string): string {
  return `${normalizeIssuer(issuer)}/.well-known/openid-configuration`;
}

async function fetchDiscoveredEndpoints(
  issuer: string,
  fetchImpl: typeof fetch,
): Promise<DiscoveredEndpoints> {
  const normalizedIssuer = normalizeIssuer(issuer);
  const discoveryUrl = `${normalizedIssuer}/.well-known/openid-configuration`;

  let response: Response;
  try {
    response = await fetchImpl(discoveryUrl);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new ConfigError(
      `OIDC discovery request to ${discoveryUrl} failed (${reason}). ` +
        "Check VITE_AUTHENTIK_ISSUER and network reachability.",
    );
  }
  if (!response.ok) {
    throw new ConfigError(
      `OIDC discovery failed: ${discoveryUrl} returned HTTP ${response.status}. ` +
        "Check VITE_AUTHENTIK_ISSUER.",
    );
  }

  let doc: DiscoveryDocument;
  try {
    doc = (await response.json()) as DiscoveryDocument;
  } catch {
    throw new ConfigError(
      `OIDC discovery document at ${discoveryUrl} is not valid JSON. Check VITE_AUTHENTIK_ISSUER.`,
    );
  }

  const authorizationEndpoint = nonEmptyString(doc.authorization_endpoint);
  const tokenEndpoint = nonEmptyString(doc.token_endpoint);
  const userinfoEndpoint = nonEmptyString(doc.userinfo_endpoint);
  const endSessionEndpoint = nonEmptyString(doc.end_session_endpoint);
  const jwksUri = nonEmptyString(doc.jwks_uri);
  const discoveredIssuer = nonEmptyString(doc.issuer);

  const endpointFields: Array<[string, string | undefined]> = [
    ["authorization_endpoint", authorizationEndpoint],
    ["token_endpoint", tokenEndpoint],
    ["userinfo_endpoint", userinfoEndpoint],
    ["end_session_endpoint", endSessionEndpoint],
    ["jwks_uri", jwksUri],
  ];
  const missing = endpointFields.filter(([, value]) => !value).map(([name]) => name);
  if (missing.length > 0) {
    throw new ConfigError(
      `OIDC discovery document at ${discoveryUrl} is missing: ${missing.join(", ")}. ` +
        "The issuer must point at an OIDC provider that publishes these endpoints.",
    );
  }

  if (discoveredIssuer && normalizeIssuer(discoveredIssuer) !== normalizedIssuer) {
    throw new ConfigError(
      `OIDC discovery issuer mismatch: ${discoveryUrl} advertises "${discoveredIssuer}" ` +
        `but VITE_AUTHENTIK_ISSUER is "${normalizedIssuer}".`,
    );
  }

  return {
    issuer: normalizedIssuer,
    authorizeEndpoint: authorizationEndpoint!,
    tokenEndpoint: tokenEndpoint!,
    userinfoEndpoint: userinfoEndpoint!,
    endSessionEndpoint: endSessionEndpoint!,
    jwksUri: jwksUri!,
  };
}

/**
 * Session cache: one discovery fetch per issuer per SPA session. Failed
 * lookups are evicted so a transient network error can be retried instead of
 * poisoning the whole session.
 */
const discoveryCache = new Map<string, Promise<DiscoveredEndpoints>>();

export function resolveEndpointsFromDiscovery(
  issuer: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DiscoveredEndpoints> {
  const normalizedIssuer = normalizeIssuer(issuer);
  const cached = discoveryCache.get(normalizedIssuer);
  if (cached) return cached;

  const pending = fetchDiscoveredEndpoints(normalizedIssuer, fetchImpl);
  discoveryCache.set(normalizedIssuer, pending);
  pending.catch(() => {
    discoveryCache.delete(normalizedIssuer);
  });
  return pending;
}

/**
 * Return `app` with all OIDC endpoints filled in. When the config already
 * carries them (pre-resolved config, tests) this is a no-op; otherwise the
 * issuer's discovery document is fetched (cached for the session) and its
 * authorization/token/userinfo/end-session/jwks endpoints are used.
 */
export async function resolveEndpoints(
  app: AppConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<ResolvedAppConfig> {
  const missing = REQUIRED_ENDPOINT_NAMES.filter((name) => !app[name]);
  if (missing.length === 0) {
    return app as ResolvedAppConfig;
  }

  const discovered = await resolveEndpointsFromDiscovery(app.issuer, fetchImpl);
  return {
    ...app,
    authorizeEndpoint: discovered.authorizeEndpoint,
    tokenEndpoint: discovered.tokenEndpoint,
    userinfoEndpoint: discovered.userinfoEndpoint,
    endSessionEndpoint: discovered.endSessionEndpoint,
    jwksUri: discovered.jwksUri,
  };
}
