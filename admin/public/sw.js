/* NestQuest Admin service worker — hand-written, served from the site root.
   Precaches the app shell, serves static assets cache-first, and falls back
   to the cached shell for navigations when offline. Only same-origin GET
   requests are handled; cross-origin requests (Authentik, the API host) are
   never intercepted or cached. */

const VERSION = "v1";
const SHELL_CACHE = `nestquest-admin-shell-${VERSION}`;
const RUNTIME_CACHE = `nestquest-admin-runtime-${VERSION}`;
const CURRENT_CACHES = [SHELL_CACHE, RUNTIME_CACHE];

const SHELL_URLS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
];

// Request destinations treated as static assets (cache-first). Anything else
// same-origin (e.g. API calls) goes straight to the network.
const STATIC_DESTINATIONS = ["script", "style", "image", "font", "manifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => !CURRENT_CACHES.includes(key)).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (new URL(request.url).origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/index.html", { cacheName: SHELL_CACHE }).then(
          (cached) => cached || Response.error(),
        ),
      ),
    );
    return;
  }

  if (STATIC_DESTINATIONS.includes(request.destination)) {
    event.respondWith(cacheFirst(request));
  }
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok && response.type === "basic") {
    const cache = await caches.open(RUNTIME_CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}
