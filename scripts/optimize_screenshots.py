"""Convert captured PNG screenshots to size-capped WebP for docs/README use.

Run after scripts/capture-screenshots.spec.ts. Converts every *.png in
docs/screenshots/ to WebP, stepping quality down until the file is under the
300 KB budget, then removes the source PNG.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

MAX_BYTES = 300 * 1024
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def convert(png_path: Path) -> Path:
    webp_path = png_path.with_suffix(".webp")
    image = Image.open(png_path).convert("RGB")
    quality = 85
    while quality >= 40:
        image.save(webp_path, "WEBP", quality=quality, method=6)
        if webp_path.stat().st_size <= MAX_BYTES:
            break
        quality -= 15
    png_path.unlink()
    return webp_path


def main() -> None:
    pngs = sorted(SCREENSHOTS_DIR.glob("*.png"))
    if not pngs:
        print(f"no PNG files found in {SCREENSHOTS_DIR}", file=sys.stderr)
        sys.exit(1)
    for png_path in pngs:
        webp_path = convert(png_path)
        size_kb = webp_path.stat().st_size / 1024
        print(f"{webp_path.name}: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
