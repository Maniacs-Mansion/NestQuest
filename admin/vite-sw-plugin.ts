/* Build-time service worker injection. After Vite writes the bundle, the
   hashed asset URLs referenced by dist/index.html and a content-derived
   revision are written into dist/sw.js, so the offline shell is complete right
   after install and every release ships a new worker with fresh caches.
   Build tooling only — never imported by the app bundle. */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Plugin } from "vite";

export const REVISION_MARKER = "__NQ_BUILD_REVISION__";
const PRECACHE_PLACEHOLDER = "const PRECACHE_ASSETS = [];";

// Every same-origin URL an index.html loads via <script src> or <link href>,
// normalised to an absolute path, in document order and without duplicates.
export function extractShellAssets(indexHtml: string): string[] {
  const tags = indexHtml.match(/<(?:script|link)\b[^>]*>/gi) ?? [];
  const urls = tags.flatMap((tag) => {
    const attr = /\b(?:src|href)\s*=\s*["']([^"']+)["']/i.exec(tag);
    if (!attr) return [];
    const url = new URL(attr[1], "https://same-origin.invalid/");
    return url.origin === "https://same-origin.invalid" ? [url.pathname] : [];
  });
  return [...new Set(urls)];
}

// Returns swSource with the precache list and the build revision filled in.
export function injectServiceWorker(indexHtml: string, swSource: string): string {
  if (!swSource.includes(PRECACHE_PLACEHOLDER) || !swSource.includes(REVISION_MARKER)) {
    throw new Error("sw.js is missing the PRECACHE_ASSETS placeholder or revision marker");
  }
  const assets = extractShellAssets(indexHtml);
  const revision = createHash("sha256")
    .update(indexHtml)
    .update(swSource)
    .digest("hex")
    .slice(0, 12);
  return swSource
    .replace(PRECACHE_PLACEHOLDER, `const PRECACHE_ASSETS = ${JSON.stringify(assets)};`)
    .replaceAll(REVISION_MARKER, revision);
}

export function serviceWorkerInjectPlugin(): Plugin {
  let outDir = "";
  return {
    name: "nestquest-sw-inject",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    writeBundle() {
      const swPath = resolve(outDir, "sw.js");
      const indexHtml = readFileSync(resolve(outDir, "index.html"), "utf8");
      writeFileSync(swPath, injectServiceWorker(indexHtml, readFileSync(swPath, "utf8")));
    },
  };
}
