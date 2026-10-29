"""Guard Node 24 frontend compatibility and required CI failure propagation."""

from __future__ import annotations

import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

from scripts.test_desktop_ci_workflow import job

ROOT = Path(__file__).resolve().parents[1]


class TestFrontendNodeCompatibility(unittest.TestCase):
    def test_package_and_lockfile_agree_on_supported_lts_majors(self) -> None:
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        self.assertEqual(package["engines"]["node"], "^24.18.0 || ^26.0.0")
        self.assertEqual(package["engines"], lock["packages"][""]["engines"])

    def test_compatibility_lane_is_selected_and_runs_real_checks(self) -> None:
        detect = job("detect-changes")
        frontend_filter = detect.split("            frontend:\n", 1)[1].split("            desktop:", 1)[0]
        for path in ("package.json", "package-lock.json", "scripts/**", ".github/workflows/ci.yml"):
            self.assertIn(f"- '{path}'", frontend_filter)
        lane = job("frontend-node24")
        for expected in (
            "needs: detect-changes",
            "github.event_name == 'push'",
            "github.event_name == 'merge_group'",
            "github.event_name == 'workflow_dispatch' && inputs.full_suite",
            "github.event_name == 'pull_request' && needs.detect-changes.outputs.frontend == 'true'",
            "node-version: '24'",
            "npm ci --engine-strict",
            "npm run typecheck",
            "npm run test:frontend",
            "npm run build",
        ):
            self.assertIn(expected, lane)
        self.assertNotIn("continue-on-error", lane)
        self.assertIn("node-version: '26'", job("test-frontend"))

    def test_required_rollup_rejects_node24_failure_and_cancellation(self) -> None:
        rollup = job("test")
        self.assertRegex(rollup, r"needs: \[[^\]]*\bfrontend-node24\b")
        self.assertIn("if: always()", rollup)
        script = textwrap.dedent(rollup.split("run: |\n", 1)[1])
        for status in ("success", "skipped", "failure", "cancelled"):
            with self.subTest(status=status):
                rendered = script.replace("${{ needs.frontend-node24.result }}", status)
                rendered = re.sub(r"\$\{\{ needs\.[\w-]+\.result \}\}", "success", rendered)
                result = subprocess.run(  # noqa: S603 — repository workflow with fixed test statuses
                    ["/bin/bash", "-c", rendered], capture_output=True, check=False
                )
                self.assertEqual(result.returncode, 0 if status in ("success", "skipped") else 1)


if __name__ == "__main__":
    unittest.main()
