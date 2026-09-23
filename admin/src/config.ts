/**
 * Runtime configuration, read from Vite env (import.meta.env).
 * See .env.example for the variables and their defaults.
 */

export interface AppConfig {
  issuer: string;
  clientId: string | undefined;
  apiBaseUrl: string;
  authorizeEndpoint: string;
  tokenEndpoint: string;
  userinfoEndpoint: string;
  endSessionEndpoint: string;
  redirectUri: string;
}

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
    authorizeEndpoint: "https://auth.cubecraftlabs.com/application/o/authorize/",
    tokenEndpoint: "https://auth.cubecraftlabs.com/application/o/token/",
    userinfoEndpoint: "https://auth.cubecraftlabs.com/application/o/userinfo/",
    endSessionEndpoint: `${issuer}/end-session/`,
    redirectUri: `${window.location.origin}/auth/callback`,
  };
}

export const config: AppConfig = readConfig();
