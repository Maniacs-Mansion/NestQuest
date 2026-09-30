/**
 * The stored application timezone, loaded once per signed-in shell.
 *
 * <AppTimezoneProvider> fetches the household settings and renders its
 * screens only once the zone is known (a failed load says so and offers a
 * retry), so no screen ever computes local time in a zone it will not keep.
 * The Settings screen publishes every zone it loads or saves, so a change
 * applies app-wide at once.
 *
 * Without a provider (a screen rendered on its own, e.g. in a test)
 * useAppTimezone() is "" — the documented unset value, i.e. browser-local.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiForbiddenError } from "../api/client";
import { fetchSettings } from "../api/settings";

interface ZoneHub {
  timeZone: string;
  publish(timeZone: string): void;
}

const AppTimezoneContext = createContext<ZoneHub | null>(null);

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; timeZone: string };

export function AppTimezoneProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchSettings()
      .then((settings) => {
        if (!cancelled) setState({ kind: "ready", timeZone: settings.timezone });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            error instanceof ApiForbiddenError
              ? error.message
              : "The application timezone could not be loaded. Check your connection and try again.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (state.kind === "loading") {
    return (
      <div className="admin-loading" role="status" data-testid="timezone-loading">
        Loading…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="admin-error" role="alert" data-testid="timezone-error">
        <p>{state.message}</p>
        <button type="button" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  const hub: ZoneHub = {
    timeZone: state.timeZone,
    publish: (timeZone) =>
      setState((prev) =>
        prev.kind === "ready" && prev.timeZone === timeZone ? prev : { kind: "ready", timeZone },
      ),
  };
  return <AppTimezoneContext.Provider value={hub}>{children}</AppTimezoneContext.Provider>;
}

/** The stored application timezone: an IANA name, or "" (browser-local). */
export function useAppTimezone(): string {
  return useContext(AppTimezoneContext)?.timeZone ?? "";
}

/** Publish a zone just loaded or saved; a no-op without a provider. */
export function usePublishAppTimezone(): (timeZone: string) => void {
  const hub = useContext(AppTimezoneContext);
  return (timeZone) => hub?.publish(timeZone);
}
