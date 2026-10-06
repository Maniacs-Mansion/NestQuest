"""The integration's local brand images (Home Assistant 2026.3+).

``custom_components/nestquest/brand/`` ships through HACS with the
integration, and Home Assistant serves those images ahead of the brands CDN.
They are generated offline from ``design/logos/NestQuest-NoBG.png`` by
``design/logos/generate-brand-icons.mjs``; these checks fail if the directory
goes missing, changes shape, or drifts from a fresh generation.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BRAND_DIR = REPO_ROOT / "custom_components" / "nestquest" / "brand"
GENERATOR = REPO_ROOT / "design" / "logos" / "generate-brand-icons.mjs"
EXPECTED = {
    "icon.png": 256,
    "icon@2x.png": 512,
    "logo.png": 256,
    "logo@2x.png": 512,
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_brand_dir_holds_exactly_the_four_images() -> None:
    assert sorted(p.name for p in BRAND_DIR.iterdir()) == sorted(EXPECTED)


@pytest.mark.parametrize(("name", "size"), sorted(EXPECTED.items()))
def test_brand_image_is_square_rgba_png(name: str, size: int) -> None:
    data = (BRAND_DIR / name).read_bytes()
    assert data[:8] == PNG_SIGNATURE
    assert data[12:16] == b"IHDR"
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert (width, height) == (size, size)
    assert (depth, colour) == (8, 6)  # 8-bit RGBA keeps the transparency


def test_generator_reproduces_the_committed_images() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("needs node")
    result = subprocess.run(
        [node, str(GENERATOR), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
