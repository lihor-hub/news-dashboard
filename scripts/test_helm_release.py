"""Verify packaged Helm releases and bounded image-publication waits."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestHelmRelease(unittest.TestCase):
    def test_injection_tracks_release_version_and_exact_image_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            shutil.copy(ROOT / "scripts/inject_app_version.sh", root / "scripts")
            shutil.copytree(ROOT / "helm", root / "helm")
            version = "2.3.4"
            image_tag = "a" * 40
            result = subprocess.run(  # noqa: S603 — repository script in an isolated fixture
                ["/bin/bash", str(root / "scripts/inject_app_version.sh"), "helm"],
                env={**os.environ, "VERSION": version, "IMAGE_TAG": image_tag},
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                self.fail(result.stderr)
            metadata = (root / "helm/news-dashboard/Chart.yaml").read_text()
            for expected in (f"version: {version}", f'appVersion: "{version}"'):
                if expected not in metadata:
                    self.fail(f"Injected chart missing {expected}")
            values = (root / "helm/news-dashboard/values.yaml").read_text()
            if f'tag: "{image_tag}"' not in values:
                self.fail("Packaged chart still targets the stale default application image")
            helm = shutil.which("helm")
            if helm is None:
                self.skipTest("Helm is required for package/render verification")
            subprocess.run(  # noqa: S603 — trusted Helm binary and temporary fixture
                [helm, "package", str(root / "helm/news-dashboard"), "--destination", str(root)],
                check=True,
                capture_output=True,
            )
            archive = root / f"news-dashboard-{version}.tgz"
            metadata = subprocess.check_output(  # noqa: S603 — locally generated chart archive
                [helm, "show", "chart", str(archive)],
                text=True,
            )
            if f"appVersion: {version}" not in metadata:
                self.fail("Packaged appVersion differs from the injected release")
            rendered = subprocess.check_output(  # noqa: S603 — offline Helm rendering
                [
                    helm,
                    "template",
                    "test",
                    str(archive),
                    "--set-string",
                    "app.auth.sessionSecret=render-only-session",
                    "--set-string",
                    "postgresql.password=render-only-postgres",
                    "--set-string",
                    "neo4j.auth.password=render-only-neo4j",
                ],
                text=True,
            )
            if f"ghcr.io/lihor-hub/news-dashboard:{image_tag}" not in rendered:
                self.fail("Packaged chart does not deploy the exact release commit image")

    def test_image_wait_retries_then_succeeds_and_times_out_when_absent(self) -> None:
        for available_after, expected_code in ((2, 0), (4, 1)):
            with (
                self.subTest(available_after=available_after),
                tempfile.TemporaryDirectory() as temp,
            ):
                root = Path(temp)
                docker = root / "docker"
                docker.write_text(
                    "#!/bin/bash\n"
                    'count=0; test ! -f "$PROBE_COUNT" || count=$(cat "$PROBE_COUNT")\n'
                    'count=$((count + 1)); echo "$count" > "$PROBE_COUNT"\n'
                    'test "$1" = manifest && test "$2" = inspect || exit 99\n'
                    'test "$count" -ge "$AVAILABLE_AFTER"\n'
                )
                docker.chmod(0o755)
                count = root / "count"
                result = subprocess.run(  # noqa: S603 — repository script and controlled fake Docker
                    [
                        "/bin/bash",
                        str(ROOT / "scripts/wait_for_release_image.sh"),
                        "ghcr.io/lihor-hub/news-dashboard:" + "a" * 40,
                    ],
                    env={
                        **os.environ,
                        "PATH": f"{root}:{os.environ['PATH']}",
                        "PROBE_COUNT": str(count),
                        "AVAILABLE_AFTER": str(available_after),
                        "IMAGE_WAIT_ATTEMPTS": "3",
                        "IMAGE_WAIT_SECONDS": "0",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != expected_code:
                    self.fail(f"Unexpected image wait result: {result.stderr}")
                if int(count.read_text()) != min(available_after, 3):
                    self.fail("Image wait did not honor its retry bound")
                if expected_code and "chart will not publish" not in result.stderr:
                    self.fail("Timeout does not explain publication is blocked")

    def test_workflow_checks_exact_image_before_packaging_and_pushing(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        if "  helm:\n" not in workflow:
            self.fail("Missing Helm release job")
        job = workflow.split("  helm:\n", 1)[1].split("\n  sync-version-files:", 1)[0]
        for expected in (
            "needs: release",
            "if: needs.release.outputs.released == 'true'",
            "ref: ${{ needs.release.outputs.tag }}",
            "packages: write",
            "timeout-minutes: 40",
            "git rev-parse HEAD",
        ):
            if expected not in job:
                self.fail(f"Helm release missing {expected}")
        commands = [
            "scripts/wait_for_release_image.sh",
            "scripts/inject_app_version.sh helm",
            "helm package",
            "helm push",
        ]
        positions = [job.index(command) for command in commands]
        if positions != sorted(positions):
            self.fail("Helm package can publish before its image is available")
        if "continue-on-error" in job:
            self.fail("Image publication failures must stop chart publication")


if __name__ == "__main__":
    unittest.main()
