"""Exercise container-smoke readiness against PostgreSQL's temporary server."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("eventually_ready", [True, False])
def test_smoke_waits_for_final_postgres_server(tmp_path: Path, eventually_ready: bool) -> None:
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state = Path(os.environ['SMOKE_TEST_STATE'])
if args[0] == 'exec' and 'pg_isready' in args:
    count = int(state.read_text()) if state.exists() else 0
    state.write_text(str(count + 1))
    if '-h' not in args:
        # The temporary Unix-socket server accepts once, then shuts down.
        sys.exit(0 if count == 0 else 1)
    # TCP is available only when the final server has started.
    sys.exit(0 if count > 0 and os.environ['SMOKE_TEST_READY'] == '1' else 1)
if args[0] == 'build':
    Path(os.environ['SMOKE_TEST_BUILD']).touch()
    sys.exit(23)  # Stop at the boundary before building an actual image.
if args[0] == 'logs':
    print('postgres startup logs', file=sys.stderr)
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleep.chmod(0o755)
    build = tmp_path / "build-started"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "SMOKE_TEST_STATE": str(tmp_path / "readiness-count"),
        "SMOKE_TEST_BUILD": str(build),
        "SMOKE_TEST_READY": "1" if eventually_ready else "0",
    }
    env.pop("MCP_SMOKE_IMAGE", None)
    result = subprocess.run(  # noqa: S603 -- repository script and controlled Docker fixture
        ["/bin/bash", str(ROOT / "scripts" / "smoke-mcp-container.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if eventually_ready:
        assert build.exists(), result.stderr  # noqa: S101 -- regression assertion
        assert result.returncode == 23  # noqa: S101 -- regression assertion
    else:
        assert not build.exists()  # noqa: S101 -- regression assertion
        assert result.returncode == 1  # noqa: S101 -- regression assertion
        assert "postgres startup logs" in result.stderr  # noqa: S101 -- regression assertion
