/**
 * Minimal path-based routing without react-router-dom: the app only needs two
 * paths (`/` shell and `/auth/callback`), so a tiny window.location switch is
 * enough and keeps the bundle small. Change screens listen to popstate.
 */
import { useEffect, useState } from "react";
import { ConfigError, config } from "./config";
import {
  AuthError,
  buildAuthorizeUrl,
  clearAuth,
  handleCallback,
  isAuthenticated,
} from "./auth/oidc";
import { ApiForbiddenError, ApiUnauthorizedError, apiFetch } from "./api/client";
import AdminShell from "./App";

type Screen =
  | { kind: "loading" }
  | { kind: "login" }
  | { kind: "config-error"; message: string }
  | { kind: "auth-error"; message: string }
  | { kind: "refusal"; message: string }
  | { kind: "probe-error"; message: string }
  | { kind: "app" };

function currentPath(): string {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

const ADMIN_PROBE_PATH = "/api/v1/admin/ping";

async function probeApi(setScreen: (screen: Screen) => void) {
  // The admin plane's authorization probe: only a 2xx enters the shell, so a
  // non-admin (403) sees the explicit refusal and any other failure an error.
  try {
    const response = await apiFetch(ADMIN_PROBE_PATH, {}, config);
    if (response.ok) {
      setScreen({ kind: "app" });
      return;
    }
    setScreen({
      kind: "probe-error",
      message: `The admin API answered ${response.status}. The admin console cannot load.`,
    });
  } catch (error) {
    if (error instanceof ConfigError) {
      setScreen({ kind: "config-error", message: error.message });
      return;
    }
    if (error instanceof ApiForbiddenError) {
      setScreen({ kind: "refusal", message: error.message });
      return;
    }
    if (error instanceof ApiUnauthorizedError) {
      // apiFetch has already started the login redirect.
      setScreen({ kind: "login" });
      return;
    }
    setScreen({
      kind: "probe-error",
      message: "The admin API could not be reached. Check your connection and try again.",
    });
  }
}

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  return (
    <div className="admin-login" data-testid="login-screen">
      <h1 className="admin-title">NestQuest Admin</h1>
      <p className="admin-subline">Sign in to continue</p>
      <button type="button" className="admin-login-button" onClick={onLogin}>
        Sign in with Authentik
      </button>
    </div>
  );
}

export default function AppRoutes() {
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });

  useEffect(() => {
    // Re-evaluate on navigation (popstate) — routing is path based.
    const onPop = () => setScreen({ kind: "loading" });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const path = currentPath();

    if (!config.clientId) {
      setScreen({
        kind: "config-error",
        message:
          "Missing VITE_AUTHENTIK_CLIENT_ID configuration. Set it in your .env before building the admin PWA.",
      });
      return;
    }

    if (path === "/auth/callback") {
      (async () => {
        try {
          await handleCallback(window.location.search, config);
          if (cancelled) return;
          window.history.replaceState({}, "", "/");
          await probeApi((next) => !cancelled && setScreen(next));
        } catch (error) {
          if (cancelled) return;
          const message =
            error instanceof AuthError || error instanceof Error
              ? error.message
              : "Authentication failed.";
          setScreen({ kind: "auth-error", message });
        }
      })();
      return () => {
        cancelled = true;
      };
    }

    if (isAuthenticated()) {
      void probeApi((next) => !cancelled && setScreen(next));
    } else {
      setScreen({ kind: "login" });
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startLogin = async () => {
    try {
      const url = await buildAuthorizeUrl(config);
      window.location.assign(url);
    } catch (error) {
      setScreen({
        kind: "config-error",
        message: error instanceof Error ? error.message : "Login failed.",
      });
    }
  };

  switch (screen.kind) {
    case "loading":
      return (
        <div className="admin-loading" role="status" data-testid="loading-screen">
          Loading…
        </div>
      );
    case "login":
      return <LoginScreen onLogin={startLogin} />;
    case "config-error":
      return (
        <div className="admin-error" role="alert" data-testid="config-error-screen">
          <h1>Configuration error</h1>
          <p>{screen.message}</p>
        </div>
      );
    case "auth-error":
      return (
        <div className="admin-error" role="alert" data-testid="auth-error-screen">
          <h1>Sign-in failed</h1>
          <p>{screen.message}</p>
          <button
            type="button"
            onClick={() => {
              clearAuth();
              window.history.replaceState({}, "", "/");
              setScreen({ kind: "loading" });
            }}
          >
            Try again
          </button>
        </div>
      );
    case "refusal":
      return (
        <div className="admin-refusal" role="alert" data-testid="refusal-screen">
          <h1>Access refused</h1>
          <p>{screen.message}</p>
          <button type="button" onClick={() => { clearAuth(); window.history.replaceState({}, "", "/"); setScreen({ kind: "login" }); }}>
            Sign out
          </button>
        </div>
      );
    case "probe-error":
      return (
        <div className="admin-error" role="alert" data-testid="probe-error-screen">
          <h1>Admin console unavailable</h1>
          <p>{screen.message}</p>
          <button
            type="button"
            onClick={() => {
              setScreen({ kind: "loading" });
              void probeApi(setScreen);
            }}
          >
            Retry
          </button>
          <button type="button" onClick={() => { clearAuth(); window.history.replaceState({}, "", "/"); setScreen({ kind: "login" }); }}>
            Sign out
          </button>
        </div>
      );
    case "app":
      return <AdminShell />;
  }
}
