import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
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
function loadServiceWorker(network: (url: string) => Promise<FakeResponse>) {
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
  new Function("self", "caches", "fetch", "Response", swSource)(self, caches, fetchFn, ResponseStub);

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
