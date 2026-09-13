"""Guard desktop lane routing and propagation into the required CI status."""

from __future__ import annotations

import re
import subprocess
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def job(name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", WORKFLOW.read_text(), re.M | re.S)
    if match is None:
        message = f"Missing CI job: {name}"
        raise AssertionError(message)
    return match.group(1)


class TestDesktopCIWorkflow(unittest.TestCase):
    def test_desktop_lane_selects_changes_and_full_runs(self) -> None:
        detect = job("detect-changes")
        if "desktop: ${{ steps.filter.outputs.desktop }}" not in detect:
            self.fail("Desktop filter output is not exposed")
        if not re.search(r"desktop:\s*\n\s*- 'desktop/\*\*'", detect):
            self.fail("Desktop source changes do not select the lane")
        desktop = job("desktop")
        for expected in (
            "needs: detect-changes",
            "github.event_name == 'push'",
            "github.event_name == 'merge_group'",
            "github.event_name == 'workflow_dispatch'",
            "github.event_name == 'pull_request' && needs.detect-changes.outputs.desktop == 'true'",
            "working-directory: desktop",
            "cache-dependency-path: desktop/package-lock.json",
            "run: npm ci",
            "run: npm test",
        ):
            if expected not in desktop:
                self.fail(f"Desktop lane missing: {expected}")
        if "continue-on-error" in desktop:
            self.fail("Desktop failures must not be ignored")

    def test_required_rollup_rejects_failure_and_cancellation_but_accepts_skip(self) -> None:
        rollup = job("test")
        if not re.search(r"needs: \[[^\]]*\bdesktop\b", rollup):
            self.fail("Required rollup does not depend on desktop")
        if "if: always()" not in rollup:
            self.fail("Required rollup must run when a lane fails or skips")
        script = textwrap.dedent(rollup.split("run: |\n", 1)[1])
        for status in ("success", "skipped", "failure", "cancelled"):
            with self.subTest(status=status):
                rendered = script.replace("${{ needs.desktop.result }}", status)
                rendered = re.sub(r"\$\{\{ needs\.[\w-]+\.result \}\}", "success", rendered)
                result = subprocess.run(  # noqa: S603 — execute the repository workflow with fixed test statuses
                    ["/bin/bash", "-c", rendered], capture_output=True, check=False
                )
                expected_code = 0 if status in ("success", "skipped") else 1
                if result.returncode != expected_code:
                    self.fail(f"Desktop {status} produced exit {result.returncode}")


if __name__ == "__main__":
    unittest.main()
