/**
 * Inline stroke glyphs for the Schedule tab (Lucide-style 24px grid),
 * CDN-free like the Today and Tasks tabs' glyphs.
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

export function ChevronRightGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="m9 18 6-6-6-6" />
    </Glyph>
  );
}

function CalendarFrame() {
  return (
    <>
      <path d="M8 2v4M16 2v4" />
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M3 10h18" />
    </>
  );
}

export function CalendarXGlyph({ size = 18 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <CalendarFrame />
      <path d="m14 14-4 4M10 14l4 4" />
    </Glyph>
  );
}

export function CalendarCheckGlyph({ size = 18 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <CalendarFrame />
      <path d="m9 16 2 2 4-4" />
    </Glyph>
  );
}

export function Trash2Glyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6" />
    </Glyph>
  );
}
