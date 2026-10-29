"""Verify image pruning removes manager payloads without breaking explicit drivers."""

from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("prune_selenium_manager.py")


class TestSeleniumManagerPruning(unittest.TestCase):
    def test_only_manager_payloads_and_matching_metadata_are_removed(self) -> None:
        prune = runpy.run_path(str(SCRIPT))["prune"]
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            removed = (
                "linux/selenium-manager",
                "macos/selenium-manager",
                "windows/selenium-manager.exe",
                "selenium-manager.cdx.json",
                "selenium-manager-THIRD-PARTY-NOTICES.txt",
            )
            kept = ("selenium_manager.py", "driver_finder.py", "linux/other-tool")
            for name in (*removed, *kept):
                path = common / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            prune(common)
            prune(common)  # Safe to run again.
            for name in removed:
                if (common / name).exists():
                    self.fail(f"Unused manager payload remains: {name}")
            for name in kept:
                if not (common / name).is_file():
                    self.fail(f"Required binding or unrelated file removed: {name}")

    def test_explicit_driver_does_not_invoke_selenium_manager(self) -> None:
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.driver_finder import DriverFinder

        with tempfile.TemporaryDirectory() as temporary:
            driver = Path(temporary) / "chromedriver"
            driver.touch()
            with patch("selenium.webdriver.common.driver_finder.SeleniumManager") as manager:
                finder = DriverFinder(Service(str(driver)), Options())
                if finder.get_driver_path() != str(driver):
                    self.fail("Explicit driver path was not preserved")
                manager.assert_not_called()


if __name__ == "__main__":
    unittest.main()
