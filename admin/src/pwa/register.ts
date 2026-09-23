/**
 * Service worker registration for the installable admin PWA.
 * Registers /sw.js only in production builds, so dev servers and tests never
 * run a worker. Failures are logged, never thrown — the app works without it.
 */
export async function registerServiceWorker(): Promise<void> {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch (error) {
    console.error("Service worker registration failed:", error);
  }
}
