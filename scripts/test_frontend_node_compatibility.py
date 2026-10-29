"""Guard Node 24 frontend compatibility and required CI failure propagation."""

from __future__ import annotations

import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def job(name: str) -> str:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", workflow, re.M | re.S)
    if match is None:
        message = f"Missing CI job: {name}"
        raise AssertionError(message)
    return match.group(1)


class TestFrontendNodeCompatibility(unittest.TestCase):
    def test_package_and_lockfile_agree_on_supported_lts_majors(self) -> None:
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        if package["engines"]["node"] != "^24.18.0 || ^26.0.0":
            self.fail("Frontend must support the tested Node 24 and 26 versions")
        if package["engines"] != lock["packages"][""]["engines"]:
            self.fail("Package and lockfile engine ranges must agree")

    def test_vercel_serves_the_actual_frontend_build_output(self) -> None:
        config = json.loads((ROOT / "vercel.json").read_text())
        if config.get("framework") != "vite" or config.get("buildCommand") != "npm run build":
            self.fail("Vercel must use the tested frontend build")
        output = config["outputDirectory"]
        if f"outDir: '{output}'" not in (ROOT / "vite.config.ts").read_text():
            self.fail("Vercel output directory must agree with Vite")

    def test_compatibility_lane_is_selected_and_runs_real_checks(self) -> None:
        detect = job("detect-changes")
        frontend_filter = detect.split("            frontend:\n", 1)[1].split(
            "            desktop:", 1
        )[0]
        for path in ("package.json", "package-lock.json", "scripts/**", ".github/workflows/ci.yml"):
            if f"- '{path}'" not in frontend_filter:
                self.fail(f"Frontend filter missing: {path}")
        lane = job("frontend-node24")
        for expected in (
            "needs: detect-changes",
            "github.event_name == 'push'",
            "github.event_name == 'merge_group'",
            "github.event_name == 'workflow_dispatch' && inputs.full_suite",
            (
                "github.event_name == 'pull_request' && "
                "needs.detect-changes.outputs.frontend == 'true'"
            ),
            "node-version: '24'",
            "npm ci --engine-strict",
            "npm run typecheck",
            "npm run test:frontend",
            "npm run build",
        ):
            if expected not in lane:
                self.fail(f"Compatibility lane missing: {expected}")
        if "continue-on-error" in lane:
            self.fail("Compatibility failures must not be ignored")
        if "node-version: '26'" not in job("test-frontend"):
            self.fail("Primary frontend lane must remain on Node 26")

    def test_required_rollup_rejects_node24_failure_and_cancellation(self) -> None:
        rollup = job("test")
        if not re.search(r"needs: \[[^\]]*\bfrontend-node24\b", rollup):
            self.fail("Required rollup must depend on Node 24 compatibility")
        if "if: always()" not in rollup:
            self.fail("Required rollup must run when a lane fails or skips")
        script = textwrap.dedent(rollup.split("run: |\n", 1)[1])
        for status in ("success", "skipped", "failure", "cancelled"):
            with self.subTest(status=status):
                rendered = script.replace("${{ needs.frontend-node24.result }}", status)
                rendered = re.sub(r"\$\{\{ needs\.[\w-]+\.result \}\}", "success", rendered)
                result = subprocess.run(  # noqa: S603 — repository workflow with fixed test statuses
                    ["/bin/bash", "-c", rendered], capture_output=True, check=False
                )
                expected_code = 0 if status in ("success", "skipped") else 1
                if result.returncode != expected_code:
                    self.fail(f"Node 24 {status} produced exit {result.returncode}")


if __name__ == "__main__":
    unittest.main()
