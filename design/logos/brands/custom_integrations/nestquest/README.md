# Home Assistant brands files for NestQuest

These files are prepared for a pull request to
[`github.com/home-assistant/brands`](https://github.com/home-assistant/brands),
placed at `custom_integrations/nestquest/`:

| File | Size |
|------|------|
| `icon.png` | 256×256 |
| `icon@2x.png` | 512×512 |
| `logo.png` | 256×256 |
| `logo@2x.png` | 512×512 |

Home Assistant and HACS load integration icons from `brands.home-assistant.io`,
which is built from that repository. Once the pull request is merged, the
NestQuest icon shows on the HACS card and on the Home Assistant integrations
page. Nothing in this repository can change that icon directly.

The alternative (HACS only) is to set the avatar of the GitHub
`Maniacs-Mansion` organization to the NestQuest logo; HACS falls back to the
repository owner's avatar when no brands icon exists.

## Regenerating

The PNGs are generated offline and deterministically (pure Node, zlib only)
from `design/logos/NestQuest-NoBG.png`, box-filter downscaled with
transparency kept. From the repository root:

```bash
node design/logos/brands/generate-brand-icons.mjs
```
