import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// The offline generator is the only writer of both registry artefacts.
import { OUTPUT_PATHS, REPO_ROOT, SOURCE_PATH, renderRegistry } from "../../../tools/icons/generate.mjs";
import { FALLBACK_ICON, FA_ICONS, LUCIDE_ICONS, resolveIcon } from "./registry.generated";

type Curated = { lucide: { name: string; label: string }[]; fa: { name: string; label: string }[] };

const curated = JSON.parse(readFileSync(SOURCE_PATH, "utf8")) as Curated;

describe("shared icon registry — one source of truth", () => {
  it("both committed artefacts are byte-identical to a fresh generation", async () => {
    const fresh = await renderRegistry();
    expect(OUTPUT_PATHS).toHaveLength(2);
    for (const path of OUTPUT_PATHS) {
      expect(readFileSync(path, "utf8"), `${path} drifted — run node tools/icons/generate.mjs`).toBe(fresh);
    }
  });

  it("the generated sets carry exactly the curated names and labels, in order", () => {
    expect(LUCIDE_ICONS.map(({ name, label }) => ({ name, label }))).toEqual(curated.lucide);
    expect(FA_ICONS.map(({ name, label }) => ({ name, label }))).toEqual(curated.fa);
    expect(curated.lucide).toHaveLength(36);
    expect(FA_ICONS.length).toBeGreaterThanOrEqual(15);
    expect(FA_ICONS.length).toBeLessThanOrEqual(25);
  });

  it("every glyph is plain data: a viewBox and at least one path", () => {
    for (const icon of LUCIDE_ICONS) {
      expect(icon.kind).toBe("lucide");
      expect(icon.key).toBe(`lucide:${icon.name}`);
      expect(icon.viewBox).toBe("0 0 24 24");
      expect(icon.paths.length, icon.name).toBeGreaterThan(0);
    }
    for (const icon of FA_ICONS) {
      expect(icon.kind).toBe("fa");
      expect(icon.key).toBe(`fa:${icon.name}`);
      expect(icon.viewBox).toMatch(/^0 0 \d+ 512$/);
      expect(icon.paths.length, icon.name).toBeGreaterThan(0);
    }
    for (const icon of [...LUCIDE_ICONS, ...FA_ICONS]) {
      for (const d of icon.paths) expect(d, icon.key).toMatch(/^[Mm][-0-9.,\sA-Za-z]+$/);
    }
  });
});

describe("resolveIcon", () => {
  it("resolves lucide:, fa: and emoji: keys", () => {
    const dog = resolveIcon("lucide:dog");
    expect(dog.kind).toBe("lucide");
    expect(dog).toBe(LUCIDE_ICONS.find((icon) => icon.name === "dog"));

    const broom = resolveIcon("fa:broom");
    expect(broom.kind).toBe("fa");
    expect(broom).toBe(FA_ICONS.find((icon) => icon.name === "broom"));

    expect(resolveIcon("emoji:🐶")).toEqual({ kind: "emoji", key: "emoji:🐶", text: "🐶" });
    expect(resolveIcon("emoji:👨‍👩‍👧")).toEqual({ kind: "emoji", key: "emoji:👨‍👩‍👧", text: "👨‍👩‍👧" });
  });

  it("reads a legacy bare name as Lucide", () => {
    expect(resolveIcon("dog")).toBe(resolveIcon("lucide:dog"));
    expect(resolveIcon("trash-2")).toBe(LUCIDE_ICONS.find((icon) => icon.name === "trash-2"));
  });

  it("falls back — never throws — for empty or unknown values", () => {
    for (const value of [
      null,
      undefined,
      "",
      "   ",
      "rocket-ship-9000",
      "lucide:",
      "lucide:rocket-ship-9000",
      "fa:",
      "fa:rocket-ship-9000",
      "fa:Dog",
      "mystery:dog",
      "emoji:",
      "emoji:<b>",
      "emoji:a b",
      "emoji:123456789",
    ]) {
      expect(resolveIcon(value), String(value)).toBe(FALLBACK_ICON);
    }
    expect(FALLBACK_ICON).toEqual({ kind: "fallback", key: null });
  });
});

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

describe("offline bundling", () => {
  const registryFiles = [SOURCE_PATH, join(REPO_ROOT, "tools", "icons", "generate.mjs"), ...OUTPUT_PATHS];

  it("the registry has no remote URL, CDN reference or data-lucide runtime", () => {
    for (const path of registryFiles) {
      const text = readFileSync(path, "utf8");
      expect(text, path).not.toMatch(/https?:\/\//i);
      expect(text, path).not.toMatch(/\/\/[a-z0-9.-]+\.[a-z]{2,}\//i);
      expect(text, path).not.toMatch(/\bcdn\b|jsdelivr|unpkg|cdnjs|kit\.fontawesome/i);
      expect(text, path).not.toContain("data-lucide");
      expect(text, path).not.toMatch(/\bfetch\s*\(/);
    }
  });

  it("no bundled source imports an icon package — only the curated generated data ships", () => {
    const sources = [join(REPO_ROOT, "admin", "src"), join(REPO_ROOT, "frontend", "src")]
      .flatMap(filesUnder)
      .filter((path) => /\.(ts|tsx)$/.test(path) && !path.endsWith(".test.ts") && !path.endsWith(".test.tsx"));
    expect(sources.length).toBeGreaterThan(0);
    for (const path of sources) {
      const text = readFileSync(path, "utf8");
      expect(text, path).not.toMatch(/from\s+["'](lucide|lucide-react|lucide-static|@fortawesome\/[^"']+)["']/);
    }
  });
});
