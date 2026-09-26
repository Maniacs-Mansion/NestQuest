/**
 * The curated Lucide set a definition's `icon` may name (ADMIN-SPEC §3.3).
 * The names, labels and path data come from the shared icon registry
 * (`src/icons/registry.generated.ts`, generated from
 * `tools/icons/curated-icons.json`) — no CDN, no runtime fetch. The stored
 * value is the namespaced `lucide:<kebab-name>`; a legacy bare
 * `<kebab-name>` still names the same Lucide entry.
 */
import { GlyphSvg } from "../icons/GlyphSvg";
import { LUCIDE_ICONS, resolveIcon, type GlyphIcon } from "../icons/registry.generated";
import { TaskGlyph } from "./glyphs";

export type DefinitionIconEntry = GlyphIcon;

export const DEFINITION_ICONS: readonly DefinitionIconEntry[] = LUCIDE_ICONS;

const LUCIDE_PREFIX = "lucide:";

/** The canonical stored key for a Lucide choice, e.g. `lucide:dog`. */
export function lucideIconKey(name: string): string {
  return `${LUCIDE_PREFIX}${name}`;
}

/**
 * The Lucide name an icon value refers to: `lucide:dog` and a legacy bare
 * `dog` both give `dog`. Any other namespace (`fa:`, `emoji:`, unknown) and
 * null give null — the admin has no Lucide entry for them.
 */
export function normalizeDefinitionIconName(value: string | null): string | null {
  if (value === null) return null;
  if (value.startsWith(LUCIDE_PREFIX)) return value.slice(LUCIDE_PREFIX.length);
  return value.includes(":") ? null : value;
}

/**
 * The curated Lucide entry an icon value resolves to via the shared parser.
 * The admin draws only Lucide glyphs for now; `fa:`, `emoji:`, unknown and
 * null values give null.
 */
export function findDefinitionIcon(value: string | null): DefinitionIconEntry | null {
  const icon = resolveIcon(value);
  return icon.kind === "lucide" ? icon : null;
}

/** A definition's glyph; no icon, or one outside the Lucide subset, gets the generic task glyph. */
export function DefinitionIcon({ name, size = 17 }: { name: string | null; size?: number }) {
  const entry = findDefinitionIcon(name);
  if (!entry) return <TaskGlyph size={size} />;
  return <GlyphSvg icon={entry} size={size} />;
}
