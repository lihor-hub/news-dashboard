"""Verify ci.yml is wired for a GitHub merge queue (issue #566).

A merge queue tests each PR on a temporary ``merge_group`` ref before it lands
on ``main``. For the required checks to mean anything in the queue, CI must:

1. trigger on ``merge_group`` events, and
2. actually run the test lanes on those events — otherwise ``test-backend`` /
   ``test-frontend`` skip and the ``Test & build`` rollup (``if: always()``)
   reports a hollow green, merging untested code.

Note: PyYAML (YAML 1.1) parses the bare mapping key ``on:`` as the boolean
``True``, so the triggers live under ``data[True]``, not ``data["on"]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).parent.parent.parent
CI_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Jobs that must run the suite when GitHub builds a merge group.
_TEST_JOBS = ("test-backend", "test-frontend")


def _load_ci() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(CI_FILE.read_text())
    return data


def _triggers(ci: dict[Any, Any]) -> dict[Any, Any]:
    """Return the ``on:`` mapping, tolerating PyYAML's ``on`` -> ``True`` quirk."""
    on = ci.get("on", ci.get(True))
    assert isinstance(on, dict), f"ci.yml `on:` is not a mapping: {on!r}"
    return on


def test_ci_file_exists() -> None:
    assert CI_FILE.exists(), f"ci.yml not found at {CI_FILE}"


def test_ci_triggers_on_merge_group() -> None:
    """The queue cannot run required checks unless CI listens for merge_group."""
    on = _triggers(_load_ci())
    assert "merge_group" in on, (
        "ci.yml does not trigger on `merge_group`; a merge queue would never run "
        "its required checks. Triggers present: " + ", ".join(map(str, on))
    )


def test_test_jobs_run_on_merge_group() -> None:
    """test-backend/test-frontend must execute on merge_group, not skip.

    If they skip, the `Test & build` rollup (`if: always()`) goes green without
    running any tests — the queue would merge untested code.
    """
    jobs = _load_ci().get("jobs", {})
    for job_name in _TEST_JOBS:
        assert job_name in jobs, f"job `{job_name}` missing from ci.yml"
        condition = str(jobs[job_name].get("if", ""))
        assert "merge_group" in condition, (
            f"job `{job_name}` does not run on merge_group events "
            f"(its `if:` is {condition!r}); the merge queue would report a "
            "hollow green for `Test & build`."
        )


def test_vite_config_coverage_reporter() -> None:
    """vite.config.ts must output lcov format for the CI artifact download to succeed."""
    config_path = REPO_ROOT / "vite.config.ts"
    assert config_path.exists(), f"vite.config.ts not found at {config_path}"
    content = config_path.read_text()
    assert "reporter:" in content, "reporter not found in vite.config.ts"
    assert "lcov" in content, "lcov reporter is missing from vite.config.ts coverage settings"


def test_codecov_upload_specifies_token_and_flags() -> None:
    """All codecov-action steps in ci.yml must specify a token and flags."""
    ci = _load_ci()
    jobs = ci.get("jobs", {})
    found_codecov = False
    for job_name, job_data in jobs.items():
        steps = job_data.get("steps", [])
        for step in steps:
            uses = step.get("uses", "")
            if "codecov/codecov-action" in uses:
                found_codecov = True
                with_data = step.get("with", {})
                assert "token" in with_data, (
                    f"Job `{job_name}` has step `{step.get('name')}` using "
                    f"codecov-action but missing a token"
                )
                assert "flags" in with_data, (
                    f"Job `{job_name}` has step `{step.get('name')}` using "
                    f"codecov-action but missing the flags parameter"
                )
    assert found_codecov, "No codecov/codecov-action steps found in ci.yml"
