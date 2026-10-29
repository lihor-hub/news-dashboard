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

    def test_image_and_security_checks_keep_pruning_enforced(self) -> None:
        root = SCRIPT.parent.parent
        dockerfile = (root / "Dockerfile").read_text()
        if "&& python /tmp/prune_selenium_manager.py" not in dockerfile:
            self.fail("Production image must remove the unused manager payloads")
        for name in ("runtime-security.yml", "python-runtime.yml"):
            workflow = (root / ".github/workflows" / name).read_text()
            if "- 'scripts/prune_selenium_manager.py'" not in workflow:
                self.fail(f"Pruning changes must trigger {name}")
        security = (root / ".github/workflows/runtime-security.yml").read_text()
        check = 'assert not any(Path(selenium.__file__).parent.rglob("selenium-manager*"))'
        if check not in security:
            self.fail("Security validation must verify manager removal in the built image")

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
