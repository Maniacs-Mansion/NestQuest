# Third-party notices

NestQuest bundles glyph data from the icon sets below. The curated names are listed in
`tools/icons/curated-icons.json`; `tools/icons/generate.mjs` reads each glyph's SVG path
data from the locally installed packages and generates it into both bundles
(`admin/src/icons/registry.generated.ts` and `frontend/src/icons/registry.generated.ts`).
Nothing is loaded from a CDN or fetched at runtime. The package versions used are recorded
in the header of each generated file.

## Font Awesome Free

- Project: <https://fontawesome.com> · repository: <https://github.com/FortAwesome/Font-Awesome>
- Package: `@fortawesome/free-solid-svg-icons`
- Licence: <https://fontawesome.com/license/free>
  - Icons: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
  - Fonts: [SIL OFL 1.1](https://openfontlicense.org)
  - Code: [MIT](https://opensource.org/licenses/MIT)
- Use in NestQuest: a curated subset of the Free **solid** icon set, embedded as SVG path
  data. No fonts are bundled.

Font Awesome Free by @fontawesome — https://fontawesome.com — icons licensed under CC BY 4.0.

## Lucide

- Project: <https://lucide.dev> · repository: <https://github.com/lucide-icons/lucide>
- Package: `lucide-react`
- Licence: [ISC](https://github.com/lucide-icons/lucide/blob/main/LICENSE)
- Use in NestQuest: a curated subset of Lucide icons, embedded as SVG path data.

Lucide icons are Copyright (c) Lucide Contributors, licensed under the ISC License.
Portions derived from Feather are Copyright (c) Cole Bemis, licensed under the MIT License.
