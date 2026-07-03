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

    def test_manual_desktop_build_never_publishes_and_uploads_update_manifest(self) -> None:
        workflow = DESKTOP.read_text()

        for expected in (
            "npm run build:mac -- --publish never",
            'find desktop/dist -name "latest-mac.yml"',
            "steps.dmg.outputs.manifest",
            "latest-mac-v${{ steps.version.outputs.version }}-manual",
        ):
            if expected not in workflow:
                self.fail(f"{DESKTOP.relative_to(ROOT)} is missing {expected}")

    def test_manual_artifacts_include_computed_version(self) -> None:
        expected_names = {
            ANDROID: (
                "news-dashboard-android-v${VERSION}-manual-${{ github.run_number }}.apk",
                "news-dashboard-apk-v${{ steps.version.outputs.version }}-manual",
            ),
            DESKTOP: ("news-dashboard-dmg-v${{ steps.version.outputs.version }}-manual",),
        }

        for path, expected_parts in expected_names.items():
            workflow = path.read_text()

            for expected in expected_parts:
                if expected not in workflow:
                    self.fail(f"{path.relative_to(ROOT)} is missing versioned artifact {expected}")


if __name__ == "__main__":
    unittest.main()
