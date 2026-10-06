# NestQuest brand icons in Home Assistant

## Where the icon comes from

Since Home Assistant 2026.3, a custom integration can ship its own brand
images in `custom_components/<domain>/brand/`, and Home Assistant serves them
ahead of the brands CDN (`brands.home-assistant.io`). NestQuest ships:

| File | Size |
|------|------|
| `custom_components/nestquest/brand/icon.png` | 256×256 |
| `custom_components/nestquest/brand/icon@2x.png` | 512×512 |
| `custom_components/nestquest/brand/logo.png` | 256×256 |
| `custom_components/nestquest/brand/logo@2x.png` | 512×512 |

HACS installs the whole `custom_components/nestquest/` directory, so these
images arrive with the integration. On Home Assistant 2026.3 or newer they
appear on the integrations page and the integration tile, through Home
Assistant's brand endpoint. Older Home Assistant versions ignore the directory
and show the generic placeholder icon.

The `custom_integrations` folder of the `home-assistant/brands` repository is
legacy for this purpose; NestQuest does not depend on it.

## Known caveat: the HACS store card

The HACS store card (the repository listing inside HACS, shown before and
after installing) is rendered by HACS itself, not by the integration. It may
still take its image from the brands CDN or fall back to the avatar of the
repository owner (the `Maniacs-Mansion` organization). Whether HACS reads the
local `brand/` directory for that card has not been verified, so that icon
may stay generic. The repository page inside HACS shows the README, which
embeds the logo from `design/logos/NestQuest-NoBG.png`.

## Regenerating

The PNGs are generated offline and deterministically (pure Node, zlib only)
from `design/logos/NestQuest-NoBG.png`, box-filter downscaled with
transparency kept. From the repository root:

```bash
node design/logos/generate-brand-icons.mjs          # write the four PNGs
node design/logos/generate-brand-icons.mjs --check  # exit 1 if any drifted
```

`tests/test_brand_icons.py` runs the `--check` and asserts the four files
exist with the expected sizes, so a missing or hand-edited image fails the
test suite.
