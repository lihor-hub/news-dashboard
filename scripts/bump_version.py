#!/usr/bin/env python3
"""Determine next semantic version from Conventional Commits.

CLI usage:
    python3 scripts/bump_version.py --current 1.0.0 [--since-tag v1.0.0]

Prints three lines to stdout:
    bump=minor          # major | minor | patch | none
    next=1.1.0          # new version string
    code=1001000        # Android versionCode (major*1M + minor*1K + patch)

Bump rules (Conventional Commits spec):
    BREAKING CHANGE footer or ! after type  → major
    feat:                                   → minor
    fix: / perf:                            → patch
    ci: / docs: / test: / chore: / build:  → none (skipped)
    Any other / non-conventional commit     → patch (conservative)
"""

from __future__ import annotations

import re
import subprocess

_BREAKING_BANG = re.compile(r"^[a-z]+(\([^)]+\))?!:")
_FEAT = re.compile(r"^feat(\([^)]+\))?:")
_FIX_PERF = re.compile(r"^(fix|perf)(\([^)]+\))?:")
_SKIP = re.compile(r"^(ci|docs|test|chore|style|build|revert)(\([^)]+\))?:")


def determine_bump(messages: list[str]) -> str:
    """Return 'major', 'minor', 'patch', or 'none'."""
    has_breaking = False
    has_feat = False
    has_fix_or_perf = False
    has_other = False

    for msg in messages:
        first_line = msg.split("\n")[0].strip()

        if (
            "BREAKING CHANGE:" in msg
            or "BREAKING-CHANGE:" in msg
            or _BREAKING_BANG.match(first_line)
        ):
            has_breaking = True
        elif _FEAT.match(first_line):
            has_feat = True
        elif _FIX_PERF.match(first_line):
            has_fix_or_perf = True
        elif not _SKIP.match(first_line):
            has_other = True

    if has_breaking:
        return "major"
    if has_feat:
        return "minor"
    if has_fix_or_perf or has_other:
        return "patch"
    return "none"


def bump_version(version: str, bump: str) -> str:
    """Apply bump type and return new version string."""
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return version


def version_code(version: str) -> int:
    """Compute Android versionCode — always increases with semver increments."""
    major, minor, patch = (int(x) for x in version.split("."))
    return major * 1_000_000 + minor * 1_000 + patch


def _git_messages_since(since_tag: str | None) -> list[str]:
    cmd = ["git", "log", "--format=%B%x00"]
    if since_tag:
        cmd.append(f"{since_tag}..HEAD")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [m.strip() for m in result.stdout.split("\x00") if m.strip()]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compute next semantic version")
    parser.add_argument("--current", required=True, help="Current version, e.g. 1.0.0")
    parser.add_argument("--since-tag", help="Git tag to read commits from, e.g. v1.0.0")
    args = parser.parse_args()

    messages = _git_messages_since(args.since_tag)
    bump = determine_bump(messages)
    next_ver = bump_version(args.current, bump)
    code = version_code(next_ver)

    print(f"bump={bump}")
    print(f"next={next_ver}")
    print(f"code={code}")


if __name__ == "__main__":
    main()
