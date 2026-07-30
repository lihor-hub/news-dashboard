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
TRIVY_ACTION_REFERENCE = (
    "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0"
)
RUNTIME_STAGE = re.compile(
    r"^FROM python:3.14-slim@sha256:[0-9a-f]{64} AS runtime$",
    re.MULTILINE,
)


class TestTrivyWorkflows(unittest.TestCase):
    def test_trivy_action_uses_resolved_commit_with_version_comment(self) -> None:
        workflow_texts = [path.read_text() for path in WORKFLOWS]
        combined = "\n".join(workflow_texts)

        if "aquasecurity/trivy-action@0.29.0" in combined:
            self.fail("Unresolvable Trivy action tag is still referenced")

        if combined.count(TRIVY_ACTION_REFERENCE) != len(WORKFLOWS):
            self.fail("Expected one SHA-pinned Trivy v0.36.0 action per workflow")

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

    def test_runtime_image_applies_os_security_updates(self) -> None:
        dockerfile = DOCKERFILE.read_text()
        runtime_match = RUNTIME_STAGE.search(dockerfile)
        if runtime_match is None:
            self.fail("Runtime stage must use a digest-pinned Python image")
        runtime_stage = dockerfile[runtime_match.end() :]

        for expected_command in (
            "apt-get update",
            "apt-get upgrade -y",
            "rm -rf /var/lib/apt/lists/*",
        ):
            if expected_command not in runtime_stage:
                self.fail(f"Runtime image is missing `{expected_command}`")


if __name__ == "__main__":
    unittest.main()
