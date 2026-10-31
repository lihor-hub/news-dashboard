from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "trivy-scan.yml",
]
DOCKERFILE = ROOT / "Dockerfile"
RUNTIME_STAGE = re.compile(
    r"^FROM python:3.15.0-slim-bookworm@sha256:[0-9a-f]{64} AS runtime$",
    re.MULTILINE,
)


class TestTrivyWorkflows(unittest.TestCase):
    def test_trivy_scan_policy_is_preserved(self) -> None:
        for path in WORKFLOWS:
            workflow = path.read_text()

            for expected_policy in (
                "format: sarif",
                "output: trivy-results.sarif",
                "exit-code: '1'",
                "ignore-unfixed: true",
                "severity: CRITICAL,HIGH",
            ):
                if expected_policy not in workflow:
                    self.fail(f"{path.relative_to(ROOT)} is missing {expected_policy}")

    def test_ci_uploads_failed_scans_only_when_a_report_exists(self) -> None:
        workflow = WORKFLOWS[0].read_text()
        scan = workflow[workflow.index("  trivy:\n") :]
        report_check = scan[scan.index("      - name: Check whether Trivy") :]
        for expected in (
            "if: ${{ !cancelled() }}",
            "if [ -s trivy-results.sarif ]; then",
            'echo "exists=true" >> "$GITHUB_OUTPUT"',
            "if: ${{ !cancelled() && steps.trivy-report.outputs.exists == 'true' }}",
        ):
            if expected not in report_check:
                self.fail(f"Trivy report preservation is missing {expected}")
        for unwanted in ("continue-on-error", "hashFiles"):
            if unwanted in scan:
                self.fail(f"Trivy failure handling must not use {unwanted}")

    def test_runtime_image_applies_os_security_updates(self) -> None:
        dockerfile = DOCKERFILE.read_text()
        runtime_match = RUNTIME_STAGE.search(dockerfile)
        if runtime_match is None:
            self.fail("Runtime stage must use a digest-pinned Python image")
        runtime_stage = dockerfile[runtime_match.end() :]

        for expected_command in (
            "apt-get update",
            "apt-get upgrade -y",
            "apt-get install -y --no-install-recommends tzdata",
            "rm -rf /var/lib/apt/lists/*",
        ):
            if expected_command not in runtime_stage:
                self.fail(f"Runtime image is missing `{expected_command}`")


if __name__ == "__main__":
    unittest.main()
