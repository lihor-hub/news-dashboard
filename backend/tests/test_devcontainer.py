"""Development-container isolation and lifecycle contracts (runtime verified in CI)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML ships no inline typing.

ROOT = Path(__file__).resolve().parents[2]


def test_devcontainer_isolates_interpreter_and_frontend_dependencies() -> None:
    compose = yaml.safe_load(
        (ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8")
    )
    app = compose["services"]["app"]
    assert "devcontainer-venv:/workspace/.venv" in app["volumes"]
    assert "devcontainer-node-modules:/workspace/node_modules" in app["volumes"]
    assert "ports" not in compose["services"]["db"]
    assert app["depends_on"]["db"]["condition"] == "service_healthy"


def test_devcontainer_rebuild_recovers_stale_venv_without_touching_host() -> None:
    config = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8"))
    script = ROOT / ".devcontainer/post-create.sh"
    assert config["postCreateCommand"] == "bash .devcontainer/post-create.sh"
    content = script.read_text(encoding="utf-8")
    assert content.index("mountpoint -q .venv") < content.index("venv --clear .venv")
    assert "/usr/local/bin/python -m venv --clear .venv" in content
    assert "--hook-type pre-push" in content
    assert config["remoteUser"] == "vscode"
    assert config["customizations"]["vscode"]["settings"]["python.defaultInterpreterPath"] == (
        "/workspace/.venv/bin/python"
    )
    compose = yaml.safe_load(
        (ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8")
    )
    assert compose["services"]["app"]["environment"]["PGOPTIONS"] == (
        "-c max_parallel_workers_per_gather=0"
    )
    assert config["features"]["ghcr.io/devcontainers/features/node:1"]["version"] == "26"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_push_hook_preserves_container_database_environment(tmp_path: Path, exit_code: int) -> None:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(
        hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == "pytest"
    )
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://localhost:55432/host_test\n"
        "TEST_DATABASE_URL=postgresql://localhost:55432/host_test\n"
        "PGOPTIONS=host-only\n",
        encoding="utf-8",
    )
    # Probe the real hook entry without running a nested database test suite.
    probe = tmp_path / "pytest"
    probe.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "assert os.environ['DATABASE_URL'] == 'postgresql://db:5432/dev'\n"
        "assert os.environ['TEST_DATABASE_URL'] == 'postgresql://db:5432/test'\n"
        "assert os.environ['PGOPTIONS'] == '-c max_parallel_workers_per_gather=0'\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    probe.chmod(0o755)
    result = subprocess.run(  # noqa: S603 - repository-owned hook, isolated probe executable.
        shlex.split(hook["entry"]),
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "DATABASE_URL": "postgresql://db:5432/dev",
            "TEST_DATABASE_URL": "postgresql://db:5432/test",
            "PGOPTIONS": "-c max_parallel_workers_per_gather=0",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == exit_code, result.stderr
