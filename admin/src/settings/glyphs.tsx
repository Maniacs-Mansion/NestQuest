/**
 * Inline stroke glyphs for the Settings screen (Lucide-style 24px grid),
 * CDN-free like the tabs' glyphs.
 */
import type { ReactNode } from "react";

function Glyph({ size, children }: { size: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function ChevronLeftGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="m15 18-6-6 6-6" />
    </Glyph>
  );
}

export function ArrowUpGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="m5 12 7-7 7 7M12 19V5" />
    </Glyph>
  );
}

export function ArrowDownGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="M12 5v14M19 12l-7 7-7-7" />
    </Glyph>
  );
}

export function PlusGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="M12 5v14M5 12h14" />
    </Glyph>
  );
}
