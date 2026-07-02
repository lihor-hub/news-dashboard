"""Guard against drift between .env.example and the env vars the backend reads (issue #616).

``.env.example`` is meant to be the single source of truth for configuration.
This scans ``backend/news_dashboard`` source (not tests) for
``os.environ.get("X")`` / ``os.getenv("X")`` calls with a literal name and
asserts every var found there is documented in ``.env.example``, and vice
versa (aside from a small, explicit allowlist of vars that are only read
dynamically or are intentionally undocumented).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"
SOURCE_DIR = REPO_ROOT / "backend" / "news_dashboard"

_ENV_VAR_PATTERN = re.compile(r"os\.(?:environ\.get|getenv)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")
_ENV_EXAMPLE_LINE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=")

# TOKEN_SECRET is read dynamically via a tuple loop in digest.py, so the
# literal-string scan below cannot discover it; it is still documented.
_DYNAMIC_ONLY_VARS = {"TOKEN_SECRET"}


def _vars_read_in_source() -> set[str]:
    found: set[str] = set()
    for path in SOURCE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(_ENV_VAR_PATTERN.findall(text))
    return found


def _vars_in_env_example() -> set[str]:
    documented: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = _ENV_EXAMPLE_LINE_PATTERN.match(line)
        if match:
            documented.add(match.group(1))
    return documented


def test_every_source_env_var_is_documented_in_env_example() -> None:
    source_vars = _vars_read_in_source()
    documented_vars = _vars_in_env_example()

    missing = source_vars - documented_vars
    assert not missing, f"env vars read in source but missing from .env.example: {sorted(missing)}"


def test_every_documented_env_var_is_used_or_allowlisted() -> None:
    source_vars = _vars_read_in_source()
    documented_vars = _vars_in_env_example()

    unused = documented_vars - source_vars - _DYNAMIC_ONLY_VARS
    assert not unused, f".env.example vars not read anywhere in backend source: {sorted(unused)}"
