/**
 * Inline stroke glyphs for the History tab (Lucide-style 24px grid),
 * CDN-free like the other tabs' glyphs.
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

export function DownloadGlyph({ size = 15 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </Glyph>
  );
}

export function LockGlyph({ size = 15 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </Glyph>
  );
}
