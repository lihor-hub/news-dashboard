"""Remove the unused bundled Selenium Manager from the production installation.

The application supplies its own driver path via webdriver-manager. Selenium's
separate Rust-based manager is therefore unnecessary; removing its executables
and their SBOM/notices avoids shipping their vulnerable dependency tree. Keep
the Selenium Python bindings and webdriver-manager itself intact.
"""

from __future__ import annotations

import sysconfig
from pathlib import Path


def prune(common: Path) -> None:
    if not common.is_dir():
        message = f"Selenium common directory not found: {common}"
        raise FileNotFoundError(message)
    for path in common.rglob("selenium-manager*"):
        if path.is_file():
            path.unlink()


if __name__ == "__main__":
    prune(Path(sysconfig.get_path("purelib")) / "selenium/webdriver/common")
