/**
 * Inline stroke glyphs for the Today tab (Lucide-style 24px grid). The
 * shipped Lucide subset is task b50b048f; these keep this screen CDN-free
 * until then.
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

export function SettingsGlyph({ size = 18 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
    </Glyph>
  );
}

export function InfoGlyph({ size = 16 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </Glyph>
  );
}

export function AlertCircleGlyph({ size = 18 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" />
    </Glyph>
  );
}

export function CheckCircleGlyph({ size = 18 }: { size?: number }) {
  return (
    <Glyph size={size}>
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </Glyph>
  );
}
