/**
 * Draws a registry glyph (`registry.generated.ts`) as an inline SVG — the
 * path data is bundled, so there is no CDN and no runtime fetch. Lucide
 * glyphs are stroked on their 24px grid; Font Awesome glyphs are filled.
 */
import type { GlyphIcon } from "./registry.generated";

export function GlyphSvg({ icon, size }: { icon: GlyphIcon; size: number }) {
  const stroked = icon.kind === "lucide";
  return (
    <svg
      width={size}
      height={size}
      viewBox={icon.viewBox}
      fill={stroked ? "none" : "currentColor"}
      stroke={stroked ? "currentColor" : undefined}
      strokeWidth={stroked ? 2 : undefined}
      strokeLinecap={stroked ? "round" : undefined}
      strokeLinejoin={stroked ? "round" : undefined}
      aria-hidden="true"
      focusable="false"
      data-icon={icon.name}
    >
      {icon.paths.map((d, index) => (
        <path key={index} d={d} />
      ))}
    </svg>
  );
}
