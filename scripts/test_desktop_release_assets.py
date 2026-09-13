"""Exercise desktop artifact collection without platform build tools."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_desktop_assets.sh"
ASSETS = {
    "mac": [
        "News Dashboard.dmg",
        "News Dashboard.zip",
        "News Dashboard.dmg.blockmap",
        "News Dashboard.zip.blockmap",
        "latest-mac.yml",
    ],
    "linux": ["News Dashboard.AppImage", "latest-linux.yml"],
    "win": ["News Dashboard Setup.exe", "News Dashboard Setup.exe.blockmap", "latest.yml"],
}


class TestDesktopReleaseAssets(unittest.TestCase):
    def test_collects_installers_and_update_metadata(self) -> None:
        for platform, names in ASSETS.items():
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                dist = Path(temp) / "dist"
                dist.mkdir()
                for name in [*names, "builder-debug.yml"]:
                    (dist / name).write_text("artifact")
                output = Path(temp) / "assets"
                result = subprocess.run(  # noqa: S603 — repository script and temporary fixtures
                    ["/bin/bash", str(SCRIPT), platform, str(dist), str(output)], check=False
                )
                if result.returncode != 0 or {p.name for p in output.iterdir()} != set(names):
                    self.fail(f"Incorrect asset collection for {platform}")

    def test_rejects_each_missing_required_artifact(self) -> None:
        for platform, names in ASSETS.items():
            for missing in names:
                with (
                    self.subTest(platform=platform, missing=missing),
                    tempfile.TemporaryDirectory() as temp,
                ):
                    dist = Path(temp) / "dist"
                    dist.mkdir()
                    for name in names:
                        if name != missing:
                            (dist / name).write_text("artifact")
                    result = subprocess.run(  # noqa: S603 — repository script and temporary fixtures
                        ["/bin/bash", str(SCRIPT), platform, str(dist), str(Path(temp) / "assets")],
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode == 0:
                        self.fail(f"Accepted incomplete {platform} build without {missing}")


if __name__ == "__main__":
    unittest.main()
