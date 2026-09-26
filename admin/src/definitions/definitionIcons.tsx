/**
 * The icons a definition's `icon` may name (ADMIN-SPEC §3.3): the curated
 * Lucide set, the curated Font Awesome Free solid subset, or an emoji. The
 * names, labels and path data come from the shared icon registry
 * (`src/icons/registry.generated.ts`, generated from
 * `tools/icons/curated-icons.json`) — no CDN, no runtime fetch. The stored
 * value is namespaced — `lucide:<name>`, `fa:<name>` or `emoji:<grapheme>` —
 * and a legacy bare `<kebab-name>` still names the same Lucide entry.
 */
import { GlyphSvg } from "../icons/GlyphSvg";
import { FA_ICONS, LUCIDE_ICONS, resolveIcon, type GlyphIcon } from "../icons/registry.generated";
import { TaskGlyph } from "./glyphs";

export type DefinitionIconEntry = GlyphIcon;

export const DEFINITION_ICONS: readonly DefinitionIconEntry[] = LUCIDE_ICONS;

export const FA_DEFINITION_ICONS: readonly DefinitionIconEntry[] = FA_ICONS;

const LUCIDE_PREFIX = "lucide:";
const FA_PREFIX = "fa:";
const EMOJI_PREFIX = "emoji:";

/** The canonical stored key for a Lucide choice, e.g. `lucide:dog`. */
export function lucideIconKey(name: string): string {
  return `${LUCIDE_PREFIX}${name}`;
}

/** The canonical stored key for a Font Awesome choice, e.g. `fa:dog`. */
export function faIconKey(name: string): string {
  return `${FA_PREFIX}${name}`;
}

/**
 * The stored key for typed emoji text, e.g. `emoji:🐶`. Edge whitespace is
 * trimmed; the rest must pass the registry's emoji check (1-8 code points,
 * no whitespace, control characters or `<`, `>`, `&`), else null.
 */
export function emojiIconKey(text: string): string | null {
  const key = `${EMOJI_PREFIX}${text.trim()}`;
  return resolveIcon(key).kind === "emoji" ? key : null;
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

/** The Font Awesome name an `fa:<name>` value refers to; anything else gives null. */
export function faIconName(value: string | null): string | null {
  return value?.startsWith(FA_PREFIX) ? value.slice(FA_PREFIX.length) : null;
}

/** The emoji text an `emoji:<grapheme>` value holds; anything else gives "". */
export function emojiIconText(value: string | null): string {
  return value?.startsWith(EMOJI_PREFIX) ? value.slice(EMOJI_PREFIX.length) : "";
}

/**
 * The curated glyph (Lucide or Font Awesome) an icon value resolves to via
 * the shared parser; emoji, unknown and null values give null.
 */
export function findDefinitionIcon(value: string | null): DefinitionIconEntry | null {
  const icon = resolveIcon(value);
  return icon.kind === "lucide" || icon.kind === "fa" ? icon : null;
}

/**
 * A definition's icon: a Lucide or Font Awesome glyph, an emoji drawn as
 * text, or — for no icon or an unknown value — the generic task glyph.
 */
export function DefinitionIcon({ name, size = 17 }: { name: string | null; size?: number }) {
  const icon = resolveIcon(name);
  if (icon.kind === "fallback") return <TaskGlyph size={size} />;
  if (icon.kind === "emoji") {
    return (
      <span className="defs-emoji" style={{ fontSize: size }} aria-hidden="true" data-emoji={icon.text}>
        {icon.text}
      </span>
    );
  }
  return <GlyphSvg icon={icon} size={size} />;
}
