/**
 * Inline stroke glyphs for the Definitions tab (Lucide-style 24px grid),
 * CDN-free like the Today tab's. Definition icons arrive with the icon
 * picker task; until then every row carries the generic task glyph.
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

export function TaskGlyph({ size = 17 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="m9 14 2 2 4-4" />
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

export function ChevronRightGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="m9 18 6-6-6-6" />
    </Glyph>
  );
}

export function ChevronDownGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="m6 9 6 6 6-6" />
    </Glyph>
  );
}

export function CheckGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="M20 6 9 17l-5-5" />
    </Glyph>
  );
}
