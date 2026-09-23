/**
 * Minimal fetch wrapper for the NestQuest API.
 *
 * - Attaches `Authorization: Bearer <access_token>` when a token is stored.
 * - 401: not authenticated (or token expired) -> trigger a new login.
 * - 403: authenticated but refused -> throws ApiForbiddenError so the UI can
 *   render an explicit refusal message.
 */
import { config, type AppConfig } from "../config";
import {
  buildAuthorizeUrl,
  getToken,
  isExpired,
  refreshAccessToken,
} from "../auth/oidc";

export class ApiForbiddenError extends Error {
  constructor(message = "Your account is not in the nestquest-admins group.") {
    super(message);
    this.name = "ApiForbiddenError";
  }
}

export class ApiUnauthorizedError extends Error {
  constructor(message = "Not authenticated.") {
    super(message);
    this.name = "ApiUnauthorizedError";
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
}

/**
 * Redirect the browser to Authentik to start a new login.
 * Exported for testing injection.
 */
export async function triggerLogin(app: AppConfig = config): Promise<void> {
  const url = await buildAuthorizeUrl(app);
  window.location.assign(url);
}

export async function apiFetch(
  path: string,
  options: ApiRequestOptions = {},
  app: AppConfig = config,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (isExpired() && (await refreshAccessToken(app, fetchImpl))) {
    // token renewed; fall through and use the fresh one
  }

  const token = getToken();
  const headers = {
    ...(options.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const response = await fetchImpl(`${app.apiBaseUrl}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Not authenticated: either no token or an unusable one.
    if (await refreshAccessToken(app, fetchImpl)) {
      const retryToken = getToken();
      const retryResponse = await fetchImpl(`${app.apiBaseUrl}${path}`, {
        ...options,
        headers: {
          ...(options.headers ?? {}),
          ...(retryToken ? { Authorization: `Bearer ${retryToken}` } : {}),
        },
      });
      if (retryResponse.status === 403) throw new ApiForbiddenError();
      if (retryResponse.ok) return retryResponse;
      throw new ApiUnauthorizedError();
    }
    await triggerLogin(app);
    throw new ApiUnauthorizedError();
  }

  if (response.status === 403) {
    // Authenticated, but Authentik's token does not belong to nestquest-admins.
    throw new ApiForbiddenError();
  }

  return response;
}
