/**
 * Lit rendering for the shared icon registry (`registry.generated.ts`,
 * generated from tools/icons/curated-icons.json). The glyph path data is
 * bundled — no CDN and no runtime fetch.
 */
import { html, svg, type TemplateResult } from "lit";

import { resolveIcon } from "./registry.generated";

/**
 * A stored definition icon (`lucide:<name>`, `fa:<name>`, `emoji:<grapheme>`
 * or a legacy bare Lucide name) as a template; anything that resolves to the
 * registry fallback renders `fallback` instead.
 */
export function renderQuestIcon(
  value: string | null,
  fallback: TemplateResult
): TemplateResult {
  const icon = resolveIcon(value);
  switch (icon.kind) {
    case "lucide":
      return html`<svg
        viewBox=${icon.viewBox}
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
        data-icon=${icon.key}
      >
        ${icon.paths.map((d) => svg`<path d=${d}></path>`)}
      </svg>`;
    case "fa":
      return html`<svg
        viewBox=${icon.viewBox}
        fill="currentColor"
        aria-hidden="true"
        data-icon=${icon.key}
      >
        ${icon.paths.map((d) => svg`<path d=${d}></path>`)}
      </svg>`;
    case "emoji":
      return html`<span class="emoji" data-icon=${icon.key}>${icon.text}</span>`;
    case "fallback":
      return fallback;
  }
}
