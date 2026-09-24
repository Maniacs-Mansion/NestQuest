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
// Unhashed files sw.js precaches by fixed URL, relative to the build output.
export const STATIC_PRECACHE_FILES = [
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
];

export interface PrecacheFile {
  path: string;
  bytes: string | Uint8Array;
}

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

// Hash of every precached file, sorted by path; each entry is length-prefixed
// so no two different file sets hash the same concatenation.
export function computeRevision(files: PrecacheFile[]): string {
  const hash = createHash("sha256");
  for (const { path, bytes } of [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0))) {
    const data = typeof bytes === "string" ? Buffer.from(bytes, "utf8") : bytes;
    hash.update(`${path}\0${data.byteLength}\0`).update(data);
  }
  return hash.digest("hex").slice(0, 12);
}

// Returns swSource with the precache list and the build revision filled in.
// The revision covers index.html (and so the hashed bundles it names), the
// sw.js source and the bytes of every unhashed static file it precaches.
export function injectServiceWorker(
  indexHtml: string,
  swSource: string,
  staticFiles: PrecacheFile[],
): string {
  if (!swSource.includes(PRECACHE_PLACEHOLDER) || !swSource.includes(REVISION_MARKER)) {
    throw new Error("sw.js is missing the PRECACHE_ASSETS placeholder or revision marker");
  }
  const assets = extractShellAssets(indexHtml);
  const revision = computeRevision([
    { path: "index.html", bytes: indexHtml },
    { path: "sw.js", bytes: swSource },
    ...staticFiles,
  ]);
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
      const staticFiles = STATIC_PRECACHE_FILES.map((path) => ({
        path,
        bytes: readFileSync(resolve(outDir, path)),
      }));
      writeFileSync(
        swPath,
        injectServiceWorker(indexHtml, readFileSync(swPath, "utf8"), staticFiles),
      );
    },
  };
}
