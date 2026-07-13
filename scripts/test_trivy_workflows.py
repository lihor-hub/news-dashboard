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


class TestTrivyWorkflows(unittest.TestCase):
    def test_trivy_action_uses_resolvable_versioned_tag(self) -> None:
        workflow_texts = [path.read_text() for path in WORKFLOWS]
        combined = "\n".join(workflow_texts)

        if "aquasecurity/trivy-action@0.29.0" in combined:
            self.fail("Unresolvable Trivy action tag is still referenced")

        tags = re.findall(r"uses:\s+aquasecurity/trivy-action@(v\d+\.\d+\.\d+)", combined)
        if len(tags) != len(WORKFLOWS):
            self.fail(f"Expected one Trivy action tag per workflow, got {tags}")
        if set(tags) != {"v0.36.0"}:
            self.fail(f"Expected Trivy action v0.36.0 in all workflows, got {tags}")

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
        runtime_stage = dockerfile.split("FROM python:3.14-slim AS runtime", maxsplit=1)[1]

        for expected_command in (
            "apt-get update",
            "apt-get upgrade -y",
            "rm -rf /var/lib/apt/lists/*",
        ):
            if expected_command not in runtime_stage:
                self.fail(f"Runtime image is missing `{expected_command}`")


if __name__ == "__main__":
    unittest.main()
