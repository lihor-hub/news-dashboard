from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ANDROID = WORKFLOWS / "android.yml"
DESKTOP = WORKFLOWS / "desktop.yml"
RELEASE = WORKFLOWS / "release.yml"


class TestManualAppWorkflows(unittest.TestCase):
    def test_manual_workflows_compute_versions_from_git_history(self) -> None:
        for path in (ANDROID, DESKTOP):
            workflow = path.read_text()

            if "fetch-depth: 0" not in workflow:
                self.fail(f"{path.relative_to(ROOT)} does not fetch tag history")
            if 'bash scripts/next_version.sh >> "$GITHUB_OUTPUT"' not in workflow:
                self.fail(f"{path.relative_to(ROOT)} does not compute the tag-derived version")

    def test_workflows_use_shared_version_injection_script(self) -> None:
        expected_calls = {
            ANDROID: "bash scripts/inject_app_version.sh android",
            DESKTOP: "bash scripts/inject_app_version.sh desktop",
            RELEASE: "bash scripts/inject_app_version.sh",
        }

        for path, expected_call in expected_calls.items():
            workflow = path.read_text()

            if expected_call not in workflow:
                self.fail(f"{path.relative_to(ROOT)} is missing {expected_call}")

    def test_desktop_workflows_build_all_platforms_and_collect_updates(self) -> None:
        for path in (DESKTOP, RELEASE):
            workflow = path.read_text()
            for expected in (
                "os: macos-latest",
                "platform: mac",
                "os: ubuntu-latest",
                "platform: linux",
                "os: windows-latest",
                "platform: win",
                "shell: bash",
                "--publish never",
                "scripts/collect_desktop_assets.sh",
                "if-no-files-found: error",
            ):
                if expected not in workflow:
                    self.fail(f"{path.name} is missing {expected}")

    def test_release_publishes_once_after_all_desktop_builds(self) -> None:
        workflow = RELEASE.read_text()
        if "needs: [release, desktop]" not in workflow:
            self.fail("Desktop release must await all matrix builds")
        if workflow.count('gh release create "desktop-v$V"') != 1:
            self.fail("Desktop release must be created exactly once")

    def test_manual_artifacts_include_computed_version(self) -> None:
        expected_names = {
            ANDROID: (
                "news-dashboard-android-v${VERSION}-manual-${{ github.run_number }}.apk",
                "news-dashboard-apk-v${{ steps.version.outputs.version }}-manual",
            ),
            DESKTOP: (
                (
                    "news-dashboard-desktop-${{ matrix.platform }}-v"
                    "${{ steps.version.outputs.version }}-manual"
                ),
            ),
        }

        for path, expected_parts in expected_names.items():
            workflow = path.read_text()

            for expected in expected_parts:
                if expected not in workflow:
                    self.fail(f"{path.relative_to(ROOT)} is missing versioned artifact {expected}")


if __name__ == "__main__":
    unittest.main()
