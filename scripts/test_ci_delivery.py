"""Regression coverage for exact-commit delivery without an ingress migration."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_native_builds_do_not_block_the_production_runner() -> None:
    jobs = workflow()["jobs"]
    build = jobs["build-platform"]
    assert build["runs-on"] == "${{ matrix.runner }}"  # noqa: S101
    assert build["strategy"]["matrix"]["include"] == [  # noqa: S101
        {"arch": "amd64", "runner": "ubuntu-24.04"},
        {"arch": "arm64", "runner": "ubuntu-24.04-arm"},
    ]
    assert build["concurrency"]["cancel-in-progress"] is True  # noqa: S101
    assert "matrix.arch" in build["concurrency"]["group"]  # noqa: S101
    assert jobs["publish"]["runs-on"] == "ubuntu-24.04"  # noqa: S101
    assert jobs["deploy"]["concurrency"]["cancel-in-progress"] is False  # noqa: S101
    assert not any("setup-qemu-action" in s.get("uses", "") for s in build["steps"])  # noqa: S101


def test_deploy_uses_the_run_commit_and_preserves_the_cutover_gate() -> None:
    jobs = workflow()["jobs"]
    steps = jobs["deploy"]["steps"]
    checkout = steps[0]
    assert checkout["with"]["ref"] == "${{ github.sha }}"  # noqa: S101
    deploy = next(s for s in steps if s.get("id") == "deploy")
    script = deploy["run"]
    assert "git checkout --detach FETCH_HEAD" not in script  # noqa: S101
    assert "cd ~/news-dashboard" not in script  # noqa: S101
    assert "deploy-image-only.sh" in script  # noqa: S101
    assert script.index("origin/main") < script.index("deploy-image-only.sh")  # noqa: S101
    assert script.index("production_cutover_enabled") < script.index('helm "${helm_args[@]}"')  # noqa: S101
    assert "live release unchanged" not in script  # noqa: S101
    assert "GITHUB_STEP_SUMMARY" in script  # noqa: S101
    smoke = next(s for s in steps if s.get("name") == "Smoke test public TLS Ingress")
    assert "verify-deployed-build.py" in smoke["run"]  # noqa: S101


def test_build_identity_is_baked_before_both_platform_builds() -> None:
    jobs = workflow()["jobs"]
    prep = jobs["prepare-image"]
    bake = next(
        s
        for s in prep["steps"]
        if s.get("name") == "Bake version + changelog into the build context"
    )
    assert "public/build-info.json" in bake["run"]  # noqa: S101
    assert bake["env"]["BUILD_REVISION"] == "${{ github.sha }}"  # noqa: S101
    assert "prepare-image" in jobs["build-platform"]["needs"]  # noqa: S101
    assert any(  # noqa: S101
        s.get("uses", "").startswith("actions/download-artifact@")
        for s in jobs["build-platform"]["steps"]
    )


@pytest.mark.parametrize("fail_rollout", [False, True])
def test_legacy_deploy_only_changes_images_and_rolls_back_on_failure(
    tmp_path: Path, fail_rollout: bool
) -> None:
    log = tmp_path / "calls"
    kubectl = tmp_path / "kubectl"
    kubectl.write_text("""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as f:
    f.write(" ".join(args) + "\\n")
if "get" in args:
    print("old-image:stable")
if "rollout" in args and os.environ["FAIL_ROLLOUT"] == "true":
    sys.exit(1)
""")
    kubectl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CALL_LOG": str(log),
        "FAIL_ROLLOUT": str(fail_rollout).lower(),
        "IMG": "ghcr.io/lihor-hub/news-dashboard",
        "IMAGE_DIGEST": DIGEST,
    }
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts/deploy-image-only.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is not fail_rollout, result.stderr  # noqa: S101
    calls = log.read_text()
    assert f'"image":"ghcr.io/lihor-hub/news-dashboard@{DIGEST}"' in calls  # noqa: S101
    assert "startupProbe" in calls  # noqa: S101
    assert "--timeout=600s" in calls  # noqa: S101
    assert "ingest=" in calls  # noqa: S101
    for forbidden in ("secret", "service/", "statefulset"):
        assert forbidden not in calls  # noqa: S101
    if fail_rollout:
        assert "news-dashboard=old-image:stable" in calls  # noqa: S101
        assert "ingest=old-image:stable" in calls  # noqa: S101


@pytest.mark.parametrize("digest", ["latest", "sha256:bad", "", "sha256:" + "G" * 64])
def test_legacy_deploy_rejects_mutable_or_invalid_images(digest: str) -> None:
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts/deploy-image-only.sh")],
        env={**os.environ, "IMG": "ghcr.io/lihor-hub/news-dashboard", "IMAGE_DIGEST": digest},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0  # noqa: S101
    assert "IMAGE_DIGEST" in result.stderr  # noqa: S101


def test_verification_rejects_a_healthy_but_old_build(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_build", ROOT / "scripts/verify-deployed-build.py"
    )
    assert spec  # noqa: S101
    assert spec.loader  # noqa: S101
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.matches_build(json.dumps({"revision": SHA, "version": "1.2.3"}), SHA, "1.2.3")  # noqa: S101
    assert not module.matches_build(  # noqa: S101
        json.dumps({"revision": "c" * 40, "version": "1.2.3"}), SHA, "1.2.3"
    )
    assert not module.matches_build("<html>SPA fallback</html>", SHA, "1.2.3")  # noqa: S101
    assert not module.matches_build('{"status":"ok"}', SHA, "1.2.3")  # noqa: S101
    assert not module.matches_build(  # noqa: S101
        json.dumps({"revision": SHA, "version": "1.2.2"}), SHA, "1.2.3"
    )
    import io
    from urllib.request import Request

    def healthy_old_build(request: Request, timeout: int) -> io.BytesIO:
        assert timeout == 15  # noqa: S101
        assert request.get_header("Cache-control") == "no-cache"  # noqa: S101
        return io.BytesIO(json.dumps({"revision": "c" * 40, "version": "1.2.3"}).encode())

    monkeypatch.setattr(module, "urlopen", healthy_old_build)
    with pytest.raises(RuntimeError, match="did not serve expected build"):
        module.verify("https://news.example", SHA, "1.2.3", attempts=1)

    def correct_build(request: Request, timeout: int) -> io.BytesIO:
        assert timeout == 15  # noqa: S101
        assert request.full_url.endswith(f"/build-info.json?revision={SHA}")  # noqa: S101
        return io.BytesIO(json.dumps({"revision": SHA, "version": "1.2.3"}).encode())

    monkeypatch.setattr(module, "urlopen", correct_build)
    module.verify("https://news.example", SHA, "1.2.3", attempts=1)
