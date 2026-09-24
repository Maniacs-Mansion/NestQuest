import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  REVISION_MARKER,
  STATIC_PRECACHE_FILES,
  injectServiceWorker,
} from "../../vite-sw-plugin";
import { registerServiceWorker } from "./register";

const adminRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const adminPath = (rel: string) => resolve(adminRoot, rel);
const publicPath = (urlPath: string) => adminPath(`public${urlPath}`);

interface ManifestIcon {
  src: string;
  sizes: string;
  type: string;
  purpose?: string;
}

const manifest = JSON.parse(readFileSync(publicPath("/manifest.webmanifest"), "utf8"));
const icons: ManifestIcon[] = manifest.icons;
const swSource = readFileSync(publicPath("/sw.js"), "utf8");

const sizeOf = (icon: ManifestIcon) => Number(icon.sizes.split("x")[0]);
const purposes = (icon: ManifestIcon) => (icon.purpose ?? "any").split(/\s+/);

describe("web app manifest", () => {
  it("meets the installability criteria", () => {
    expect(manifest.name).toBe("NestQuest Admin");
    expect(manifest.short_name).toBe("NestQuest");
    expect(manifest.start_url).toBe("/");
    expect(manifest.scope).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i);
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i);

    const any = icons.filter((i) => purposes(i).includes("any"));
    expect(any.some((i) => sizeOf(i) >= 192)).toBe(true);
    expect(any.some((i) => sizeOf(i) >= 512)).toBe(true);
    expect(icons.some((i) => purposes(i).includes("maskable"))).toBe(true);
  });

  it("uses the admin design token colours", () => {
    const css = readFileSync(adminPath("src/index.css"), "utf8");
    expect(css).toContain(`--nq-brand-blue: ${manifest.theme_color};`);
    expect(css).toContain(`--nq-a-page: ${manifest.background_color};`);
  });

  it.each(icons.map((i) => [i.src, i] as const))(
    "icon %s is a real PNG of its declared size",
    (_src, icon) => {
      const path = publicPath(icon.src);
      expect(existsSync(path)).toBe(true);
      const png = readFileSync(path);
      expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
      expect(png.toString("ascii", 12, 16)).toBe("IHDR");
      const [w, h] = icon.sizes.split("x").map(Number);
      expect(png.readUInt32BE(16)).toBe(w);
      expect(png.readUInt32BE(20)).toBe(h);
      expect(icon.type).toBe("image/png");
    },
  );
});

describe("index.html and entry point", () => {
  const html = readFileSync(adminPath("index.html"), "utf8");

  it("links the manifest, theme colour and apple touch icon", () => {
    expect(html).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
    expect(html).toContain(`<meta name="theme-color" content="${manifest.theme_color}" />`);
    expect(html).toContain('<link rel="apple-touch-icon" href="/icons/icon-192.png" />');
  });

  it("main.tsx registers the service worker", () => {
    const main = readFileSync(adminPath("src/main.tsx"), "utf8");
    expect(main).toMatch(/import \{ registerServiceWorker \} from "\.\/pwa\/register"/);
    expect(main).toMatch(/registerServiceWorker\(\)/);
  });
});

// Minimal service-worker global scope: runs public/sw.js against in-memory
// caches and a stubbed network, so handler behaviour is checked without I/O.
function loadServiceWorker(
  network: (url: string) => Promise<FakeResponse>,
  source: string = swSource,
) {
  const listeners: Record<string, (event: any) => void> = {};
  const stores = new Map<string, Map<string, FakeResponse>>();
  const openStore = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    return stores.get(name)!;
  };
  const keyOf = (req: string | { url: string }) =>
    new URL(typeof req === "string" ? req : req.url, "https://admin.test").href;
  const fetchFn = vi.fn((req: string | { url: string }) => network(keyOf(req)));

  const caches = {
    open: async (name: string) => {
      const store = openStore(name);
      return {
        addAll: async (urls: string[]) => {
          for (const u of urls) store.set(keyOf(u), await network(keyOf(u)));
        },
        put: async (req: { url: string }, res: FakeResponse) => void store.set(keyOf(req), res),
      };
    },
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async (req: string | { url: string }, opts?: { cacheName?: string }) => {
      const names = opts?.cacheName ? [opts.cacheName] : [...stores.keys()];
      for (const n of names) {
        const hit = stores.get(n)?.get(keyOf(req));
        if (hit) return hit;
      }
      return undefined;
    },
  };
  const self = {
    location: new URL("https://admin.test/"),
    addEventListener: (type: string, fn: (event: any) => void) => (listeners[type] = fn),
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined) },
  };
  const ResponseStub = { error: () => new FakeResponse("", false, "error") };
  new Function("self", "caches", "fetch", "Response", source)(self, caches, fetchFn, ResponseStub);

  const dispatch = async (type: string, init: object = {}) => {
    let pending: Promise<unknown> | undefined;
    const event = {
      ...init,
      waitUntil: (p: Promise<unknown>) => (pending = p),
      respondWith: (p: Promise<unknown>) => (pending = p),
    };
    listeners[type](event);
    return { responded: pending !== undefined, result: await pending };
  };
  return { listeners, stores, self, fetchFn, dispatch, openStore };
}

class FakeResponse {
  constructor(
    readonly body: string,
    readonly ok = true,
    readonly type = "basic",
  ) {}
  clone() {
    return new FakeResponse(this.body, this.ok, this.type);
  }
}

const request = (url: string, extra: object = {}) => ({
  url: new URL(url, "https://admin.test").href,
  method: "GET",
  mode: "cors",
  destination: "",
  ...extra,
});

describe("service worker (public/sw.js)", () => {
  it("is a static asset served from the site root", () => {
    expect(existsSync(publicPath("/sw.js"))).toBe(true);
    expect(swSource).toMatch(/const SHELL_CACHE = /);
    expect(swSource).toMatch(/addEventListener\("install"/);
    expect(swSource).toMatch(/addEventListener\("activate"/);
    expect(swSource).toMatch(/addEventListener\("fetch"/);
  });

  it("precaches the shell on install, prunes stale caches on activate", async () => {
    const sw = loadServiceWorker(async (url) => new FakeResponse(`net:${url}`));
    sw.openStore("nestquest-admin-shell-v0");

    await sw.dispatch("install");
    expect(sw.self.skipWaiting).toHaveBeenCalled();
    const precached = [...sw.stores.values()].flatMap((s) => [...s.keys()]);
    for (const path of ["/", "/index.html", "/manifest.webmanifest", ...icons.map((i) => i.src)]) {
      expect(precached).toContain(`https://admin.test${path}`);
    }

    await sw.dispatch("activate");
    expect(sw.stores.has("nestquest-admin-shell-v0")).toBe(false);
    expect(sw.self.clients.claim).toHaveBeenCalled();
  });

  it("serves the cached shell for navigations when offline", async () => {
    let online = true;
    const sw = loadServiceWorker(async (url) => {
      if (!online) throw new TypeError("Failed to fetch");
      return new FakeResponse(`net:${url}`);
    });
    await sw.dispatch("install");
    online = false;

    const { result } = await sw.dispatch("fetch", {
      request: request("/children/42", { mode: "navigate", destination: "document" }),
    });
    expect((result as FakeResponse).body).toBe("net:https://admin.test/index.html");
  });

  it("serves static assets cache-first and fills the runtime cache", async () => {
    const sw = loadServiceWorker(async (url) => new FakeResponse(`net:${url}`));
    const asset = request("/assets/index-abc123.js", { destination: "script" });

    const first = await sw.dispatch("fetch", { request: asset });
    expect((first.result as FakeResponse).body).toBe("net:https://admin.test/assets/index-abc123.js");
    expect(sw.fetchFn).toHaveBeenCalledTimes(1);

    const second = await sw.dispatch("fetch", { request: asset });
    expect((second.result as FakeResponse).body).toBe("net:https://admin.test/assets/index-abc123.js");
    expect(sw.fetchFn).toHaveBeenCalledTimes(1);
  });

  it("never handles cross-origin, non-GET or non-static requests", async () => {
    const sw = loadServiceWorker(async (url) => new FakeResponse(`net:${url}`));
    const cases = [
      request("https://auth.example.com/logo.png", { destination: "image" }),
      request("/assets/app.js", { destination: "script", method: "POST" }),
      request("/api/admin/children"),
    ];
    for (const req of cases) {
      const { responded } = await sw.dispatch("fetch", { request: req });
      expect(responded).toBe(false);
    }
    expect(sw.fetchFn).not.toHaveBeenCalled();
  });
});

// A Vite-style built index.html referencing hashed bundles.
const builtIndexHtml = (hash: string) => `<!doctype html>
<html lang="en">
  <head>
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="apple-touch-icon" href="/icons/icon-192.png" />
    <script type="module" crossorigin src="/assets/index-${hash}.js"></script>
    <link rel="modulepreload" crossorigin href="/assets/vendor-${hash}.js">
    <link rel="stylesheet" crossorigin href="/assets/index-${hash}.css">
    <link rel="preconnect" href="https://auth.example.com" />
  </head>
  <body><div id="root"></div></body>
</html>`;

// Same-origin script/link URLs of an HTML document, parsed independently of
// the build plugin so the regression check does not trust its own extractor.
const referencedAssets = (html: string) =>
  [...new DOMParser().parseFromString(html, "text/html").querySelectorAll("script[src], link[href]")]
    .map((el) => new URL(el.getAttribute("src") ?? el.getAttribute("href")!, "https://admin.test/"))
    .filter((url) => url.origin === "https://admin.test")
    .map((url) => url.href);

// The unhashed files the build hashes into the revision, read from public/.
const staticFiles = STATIC_PRECACHE_FILES.map((path) => ({
  path,
  bytes: readFileSync(publicPath(`/${path}`)),
}));
const revisionOf = (src: string) => /const REVISION = "([0-9a-f]+)";/.exec(src)?.[1];

describe("build-time service worker injection", () => {
  it("precaches every asset the cached index.html references on install (PWA-001)", async () => {
    const html = builtIndexHtml("Ab12Cd34");
    const built = injectServiceWorker(html, swSource, staticFiles);
    const sw = loadServiceWorker(async (url) =>
      new FakeResponse(url.endsWith("/index.html") ? html : `net:${url}`),
    built);

    await sw.dispatch("install");
    const shell = [...sw.stores.entries()].find(([name]) => name.startsWith("nestquest-admin-shell-"));
    expect(shell).toBeDefined();
    const [, shellStore] = shell!;

    const cachedHtml = shellStore.get("https://admin.test/index.html")!.body;
    const assets = referencedAssets(cachedHtml);
    expect(assets).toEqual(
      expect.arrayContaining([
        "https://admin.test/assets/index-Ab12Cd34.js",
        "https://admin.test/assets/vendor-Ab12Cd34.js",
        "https://admin.test/assets/index-Ab12Cd34.css",
      ]),
    );
    for (const asset of assets) expect([...shellStore.keys()]).toContain(asset);
    expect([...shellStore.keys()]).not.toContain("https://auth.example.com/");
  });

  it("derives a new revision for different index.html content (PWA-002)", () => {
    const a = injectServiceWorker(builtIndexHtml("aaaa1111"), swSource, staticFiles);
    const b = injectServiceWorker(builtIndexHtml("bbbb2222"), swSource, staticFiles);

    expect(a).not.toContain(REVISION_MARKER);
    expect(b).not.toContain(REVISION_MARKER);
    expect(revisionOf(a)).toMatch(/^[0-9a-f]{12}$/);
    expect(revisionOf(b)).toMatch(/^[0-9a-f]{12}$/);
    expect(revisionOf(a)).not.toBe(revisionOf(b));
    expect(injectServiceWorker(builtIndexHtml("aaaa1111"), swSource, staticFiles)).toBe(a);
  });

  it("derives a new revision when only a precached static file changes (PWA-002)", () => {
    const html = builtIndexHtml("aaaa1111");
    const base = revisionOf(injectServiceWorker(html, swSource, staticFiles));
    const withChanged = (path: string) =>
      staticFiles.map((f) =>
        f.path === path ? { path, bytes: Buffer.concat([f.bytes, Buffer.from([0])]) } : f,
      );

    expect(revisionOf(injectServiceWorker(html, swSource, [...staticFiles].reverse()))).toBe(base);
    for (const path of STATIC_PRECACHE_FILES) {
      const changed = revisionOf(injectServiceWorker(html, swSource, withChanged(path)));
      expect(changed, path).toMatch(/^[0-9a-f]{12}$/);
      expect(changed, path).not.toBe(base);
    }
  });

  it("hashes every unhashed URL sw.js precaches (PWA-002)", () => {
    const shellUrls = [...swSource.matchAll(/^\s*"(\/[^"]*)",$/gm)].map((m) => m[1]);
    const fixed = shellUrls.filter((url) => url !== "/" && url !== "/index.html");
    expect(fixed.map((url) => url.slice(1)).sort()).toEqual([...STATIC_PRECACHE_FILES].sort());
  });

  it("names both caches after the build revision (PWA-002)", async () => {
    const built = injectServiceWorker(builtIndexHtml("aaaa1111"), swSource, staticFiles);
    const revision = /const REVISION = "([0-9a-f]+)";/.exec(built)![1];
    const sw = loadServiceWorker(async (url) => new FakeResponse(`net:${url}`), built);

    await sw.dispatch("install");
    await sw.dispatch("fetch", { request: request("/assets/late.js", { destination: "script" }) });
    expect([...sw.stores.keys()].sort()).toEqual([
      `nestquest-admin-runtime-${revision}`,
      `nestquest-admin-shell-${revision}`,
    ]);
  });

  it("fails fast when sw.js lacks the placeholders", () => {
    expect(() => injectServiceWorker(builtIndexHtml("x"), "const SHELL_URLS = [];", staticFiles)).toThrow();
  });

  it("activation deletes only stale nestquest-admin caches (PWA-003)", async () => {
    const built = injectServiceWorker(builtIndexHtml("aaaa1111"), swSource, staticFiles);
    const sw = loadServiceWorker(async (url) => new FakeResponse(`net:${url}`), built);
    for (const name of [
      "nestquest-admin-shell-old",
      "nestquest-admin-runtime-old",
      "some-other-app-cache",
    ]) {
      sw.openStore(name);
    }

    await sw.dispatch("install");
    await sw.dispatch("activate");
    const names = [...sw.stores.keys()];
    expect(names).not.toContain("nestquest-admin-shell-old");
    expect(names).not.toContain("nestquest-admin-runtime-old");
    expect(names).toContain("some-other-app-cache");
    expect(names.some((n) => n.startsWith("nestquest-admin-shell-") && n !== "nestquest-admin-shell-old")).toBe(true);
  });
});

describe("registerServiceWorker", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const stubServiceWorker = (register: ReturnType<typeof vi.fn>) =>
    vi.stubGlobal("navigator", { ...navigator, serviceWorker: { register } });

  it("does not register outside production builds", async () => {
    const register = vi.fn();
    stubServiceWorker(register);
    expect(import.meta.env.PROD).toBe(false);
    await registerServiceWorker();
    expect(register).not.toHaveBeenCalled();
  });

  it("registers /sw.js in production", async () => {
    vi.stubEnv("PROD", true);
    const register = vi.fn().mockResolvedValue({});
    stubServiceWorker(register);
    await registerServiceWorker();
    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("logs instead of throwing when registration fails", async () => {
    vi.stubEnv("PROD", true);
    stubServiceWorker(vi.fn().mockRejectedValue(new Error("boom")));
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    await expect(registerServiceWorker()).resolves.toBeUndefined();
    expect(error).toHaveBeenCalled();
  });

  it("does nothing when the browser lacks service workers", async () => {
    vi.stubEnv("PROD", true);
    vi.stubGlobal("navigator", {});
    await expect(registerServiceWorker()).resolves.toBeUndefined();
  });
});
