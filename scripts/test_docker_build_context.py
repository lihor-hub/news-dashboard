from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_script_inputs() -> set[str]:
    package = json.loads((ROOT / "package.json").read_text())
    build = package["scripts"]["build"]
    return set(re.findall(r"\bnode\s+(scripts/[^\s;&|]+)", build))


def _frontend_stage_sources() -> set[str]:
    dockerfile = (ROOT / "Dockerfile").read_text()
    frontend_stage = dockerfile.split("\nFROM ", maxsplit=1)[0]
    sources: set[str] = set()
    for line in frontend_stage.splitlines():
        tokens = shlex.split(line, comments=True)
        if not tokens or tokens[0].upper() != "COPY":
            continue
        sources.update(token for token in tokens[1:-1] if not token.startswith("--"))
    return sources


def test_frontend_docker_stage_contains_every_build_script_input() -> None:
    required = _build_script_inputs()
    copied = _frontend_stage_sources()

    assert required <= copied, (  # noqa: S101
        f"Docker frontend stage omits package build inputs: {sorted(required - copied)}"
    )
