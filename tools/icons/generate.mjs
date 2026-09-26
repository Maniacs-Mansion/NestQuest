/**
 * Offline generator for the shared quest-icon registry.
 *
 * Reads the curated names + labels in `curated-icons.json` (the one source of
 * truth), pulls each glyph's SVG path data from locally installed packages in
 * `admin/node_modules` (lucide-react and @fortawesome/free-solid-svg-icons —
 * no network), and writes the same TypeScript module into both bundles:
 *
 *   admin/src/icons/registry.generated.ts
 *   frontend/src/icons/registry.generated.ts
 *
 *   node tools/icons/generate.mjs          # write both artefacts
 *   node tools/icons/generate.mjs --check  # exit 1 if either artefact drifted
 *
 * Lucide circles, rects and lines are converted to path `d` strings so every
 * glyph is plain `{ viewBox, paths }` data any renderer can draw.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = join(HERE, "..", "..");
export const SOURCE_PATH = join(HERE, "curated-icons.json");
export const OUTPUT_PATHS = [
  join(REPO_ROOT, "admin", "src", "icons", "registry.generated.ts"),
  join(REPO_ROOT, "frontend", "src", "icons", "registry.generated.ts"),
];

const ADMIN_MODULES = join(REPO_ROOT, "admin", "node_modules");
const LUCIDE_ICON_DIR = join(ADMIN_MODULES, "lucide-react", "dist", "esm", "icons");
const requireFromAdmin = createRequire(join(REPO_ROOT, "admin", "package.json"));

function packageVersion(name) {
  const pkg = JSON.parse(readFileSync(join(ADMIN_MODULES, name, "package.json"), "utf8"));
  return pkg.version;
}

function num(value, what) {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(`${what}: not a number: ${value}`);
  return n;
}

/** One Lucide icon-node element as a path `d` string. */
function elementToPath(tag, attrs, icon) {
  const where = `lucide ${icon} <${tag}>`;
  const known = { path: ["d"], circle: ["cx", "cy", "r"], rect: ["x", "y", "width", "height", "rx", "ry"], line: ["x1", "y1", "x2", "y2"] };
  if (!(tag in known)) throw new Error(`${where}: unsupported element`);
  for (const attr of Object.keys(attrs)) {
    if (attr !== "key" && !known[tag].includes(attr)) throw new Error(`${where}: unsupported attribute ${attr}`);
  }
  if (tag === "path") return attrs.d;
  if (tag === "line") {
    return `M${num(attrs.x1, where)} ${num(attrs.y1, where)}L${num(attrs.x2, where)} ${num(attrs.y2, where)}`;
  }
  if (tag === "circle") {
    const [cx, cy, r] = [num(attrs.cx, where), num(attrs.cy, where), num(attrs.r, where)];
    return `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
  }
  const [x, y, w, h] = [num(attrs.x ?? 0, where), num(attrs.y ?? 0, where), num(attrs.width, where), num(attrs.height, where)];
  const rxRaw = attrs.rx ?? attrs.ry;
  const ryRaw = attrs.ry ?? attrs.rx;
  const rx = Math.min(rxRaw === undefined ? 0 : num(rxRaw, where), w / 2);
  const ry = Math.min(ryRaw === undefined ? 0 : num(ryRaw, where), h / 2);
  if (rx === 0 || ry === 0) return `M${x} ${y}h${w}v${h}h${-w}z`;
  const iw = w - 2 * rx;
  const ih = h - 2 * ry;
  return (
    `M${x + rx} ${y}h${iw}a${rx} ${ry} 0 0 1 ${rx} ${ry}v${ih}` +
    `a${rx} ${ry} 0 0 1 ${-rx} ${ry}h${-iw}a${rx} ${ry} 0 0 1 ${-rx} ${-ry}` +
    `v${-ih}a${rx} ${ry} 0 0 1 ${rx} ${-ry}z`
  );
}

/** A Lucide icon's node list; follows lucide-react's alias re-exports (smile → face-slightly-smiling). */
async function lucideNode(name, seen = []) {
  if (seen.includes(name)) throw new Error(`lucide ${name}: alias cycle ${seen.join(" -> ")}`);
  const file = join(LUCIDE_ICON_DIR, `${name}.mjs`);
  const mod = await import(pathToFileURL(file).href);
  if (mod.__iconData) return mod.__iconData.node;
  const alias = /export \{ default \} from '\.\/([a-z0-9-]+)\.mjs';/.exec(readFileSync(file, "utf8"));
  if (!alias) throw new Error(`lucide ${name}: no icon data in ${file}`);
  return lucideNode(alias[1], [...seen, name]);
}

function faExportName(name) {
  return "fa" + name.split("-").map((part) => part[0].toUpperCase() + part.slice(1)).join("");
}

function checkCurated(list, namespace) {
  const seen = new Set();
  for (const { name, label } of list) {
    if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name)) throw new Error(`${namespace}:${name}: not a kebab name`);
    if (typeof label !== "string" || !label.trim()) throw new Error(`${namespace}:${name}: missing label`);
    if (seen.has(name)) throw new Error(`${namespace}:${name}: duplicate`);
    seen.add(name);
  }
}

async function buildEntries() {
  const curated = JSON.parse(readFileSync(SOURCE_PATH, "utf8"));
  checkCurated(curated.lucide, "lucide");
  checkCurated(curated.fa, "fa");

  const lucide = [];
  for (const { name, label } of curated.lucide) {
    const node = await lucideNode(name);
    const paths = node.map(([tag, attrs]) => elementToPath(tag, attrs, name));
    lucide.push({ kind: "lucide", key: `lucide:${name}`, name, label, viewBox: "0 0 24 24", paths });
  }

  const faPackage = requireFromAdmin("@fortawesome/free-solid-svg-icons");
  const fa = [];
  for (const { name, label } of curated.fa) {
    const definition = faPackage[faExportName(name)];
    if (!definition || definition.iconName !== name) throw new Error(`fa ${name}: not in @fortawesome/free-solid-svg-icons`);
    const [width, height, , , pathData] = definition.icon;
    const paths = Array.isArray(pathData) ? pathData.filter(Boolean) : [pathData];
    fa.push({ kind: "fa", key: `fa:${name}`, name, label, viewBox: `0 0 ${width} ${height}`, paths });
  }
  return { lucide, fa };
}

const RESOLVER = `
export const FALLBACK_ICON: FallbackIcon = { kind: "fallback", key: null };

/** Mirrors core/icons.py EMOJI_MAX_CODE_POINTS. */
export const EMOJI_MAX_CODE_POINTS = 8;

const LUCIDE_BY_NAME: ReadonlyMap<string, GlyphIcon> = new Map(LUCIDE_ICONS.map((icon) => [icon.name, icon]));
const FA_BY_NAME: ReadonlyMap<string, GlyphIcon> = new Map(FA_ICONS.map((icon) => [icon.name, icon]));

function isEmojiPayload(text: string): boolean {
  const codePoints = [...text];
  if (codePoints.length === 0 || codePoints.length > EMOJI_MAX_CODE_POINTS) return false;
  return !codePoints.some((char) => /[\\s<>&]|\\p{Cc}/u.test(char));
}

/**
 * The renderable icon for a stored definition \`icon\` value.
 *
 * \`lucide:<name>\` and a legacy bare \`<name>\` resolve against the curated
 * Lucide set, \`fa:<name>\` against the curated Font Awesome set, and
 * \`emoji:<grapheme>\` to its text. Like the backend's
 * normalize_icon_for_read, nothing here throws: null, empty, an unknown
 * namespace or name, or a malformed emoji all resolve to FALLBACK_ICON.
 */
export function resolveIcon(value: string | null | undefined): ResolvedIcon {
  if (!value || !value.trim()) return FALLBACK_ICON;
  const colon = value.indexOf(":");
  if (colon === -1) return LUCIDE_BY_NAME.get(value) ?? FALLBACK_ICON;
  const namespace = value.slice(0, colon);
  const name = value.slice(colon + 1);
  if (namespace === "lucide") return LUCIDE_BY_NAME.get(name) ?? FALLBACK_ICON;
  if (namespace === "fa") return FA_BY_NAME.get(name) ?? FALLBACK_ICON;
  if (namespace === "emoji" && isEmojiPayload(name)) return { kind: "emoji", key: value, text: name };
  return FALLBACK_ICON;
}
`;

/** The generated module's full text (identical for both bundles). */
export async function renderRegistry() {
  const { lucide, fa } = await buildEntries();
  const source = relative(REPO_ROOT, SOURCE_PATH);
  return `// GENERATED by tools/icons/generate.mjs from ${source} — do not edit.
// Regenerate with \`node tools/icons/generate.mjs\` (the drift tests fail if this
// file differs from a fresh generation).
//
// Glyph path data is embedded at generation time; nothing is fetched at runtime.
// Lucide glyphs: lucide-react ${packageVersion("lucide-react")} (ISC licence).
// Font Awesome glyphs: @fortawesome/free-solid-svg-icons ${packageVersion("@fortawesome/free-solid-svg-icons")}
// (Font Awesome Free, icons under CC BY 4.0).

/** A vector glyph: draw each path in \`paths\` inside an <svg viewBox>. Lucide
 *  glyphs are stroked (fill none, stroke-width 2, round caps and joins);
 *  Font Awesome glyphs are filled. */
export interface GlyphIcon {
  kind: "lucide" | "fa";
  key: string;
  name: string;
  label: string;
  viewBox: string;
  paths: readonly string[];
}

/** An emoji icon; render \`text\` as text. */
export interface EmojiIcon {
  kind: "emoji";
  key: string;
  text: string;
}

/** No usable icon: the caller draws its own default glyph. */
export interface FallbackIcon {
  kind: "fallback";
  key: null;
}

export type ResolvedIcon = GlyphIcon | EmojiIcon | FallbackIcon;

export const LUCIDE_ICONS: readonly GlyphIcon[] = ${JSON.stringify(lucide, null, 2)};

export const FA_ICONS: readonly GlyphIcon[] = ${JSON.stringify(fa, null, 2)};
${RESOLVER}`;
}

async function main() {
  const check = process.argv.includes("--check");
  const text = await renderRegistry();
  let drifted = false;
  for (const path of OUTPUT_PATHS) {
    const shown = relative(REPO_ROOT, path);
    if (check) {
      let current = null;
      try {
        current = readFileSync(path, "utf8");
      } catch {
        // missing counts as drift
      }
      if (current !== text) {
        drifted = true;
        console.error(`drift: ${shown} differs from a fresh generation`);
      }
    } else {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, text);
      console.log(`wrote ${shown}`);
    }
  }
  if (drifted) {
    console.error("run `node tools/icons/generate.mjs` and commit the result");
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
