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
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PR_TIMING_FILE = WORKFLOWS_DIR / "pr-timing.yml"

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


def test_coverage_upload_runs_for_prs_and_merge_groups() -> None:
    """Coverage upload must run where PR authors and the queue need feedback."""
    coverage_job = _load_ci().get("jobs", {}).get("coverage-upload")
    assert coverage_job is not None, "coverage-upload job missing from ci.yml"

    condition = str(coverage_job.get("if", ""))
    for event_name in ("pull_request", "push", "merge_group"):
        assert event_name in condition, (
            f"coverage-upload job condition does not include {event_name!r}: {condition!r}"
        )


def test_codecov_upload_uses_current_action_major() -> None:
    """Pin the reviewed Codecov action major so accidental downgrades fail tests."""
    ci = _load_ci()
    codecov_uses = [
        step.get("uses", "")
        for job_data in ci.get("jobs", {}).values()
        for step in job_data.get("steps", [])
        if "codecov/codecov-action" in step.get("uses", "")
    ]
    assert codecov_uses, "No codecov/codecov-action steps found in ci.yml"
    assert all(uses == "codecov/codecov-action@v5" for uses in codecov_uses)


def test_codecov_uploads_are_guarded_by_report_existence() -> None:
    """Path-filtered PRs must not call Codecov when one report is absent."""
    coverage_job = _load_ci().get("jobs", {}).get("coverage-upload")
    assert coverage_job is not None, "coverage-upload job missing from ci.yml"

    steps = coverage_job.get("steps", [])
    check_steps = {
        step.get("id"): step
        for step in steps
        if step.get("id") in {"backend-coverage", "frontend-coverage"}
    }
    assert set(check_steps) == {"backend-coverage", "frontend-coverage"}
    assert "coverage-backend" in str(check_steps["backend-coverage"].get("run", ""))
    assert "coverage-frontend" in str(check_steps["frontend-coverage"].get("run", ""))

    upload_steps = {
        step.get("with", {}).get("flags"): step
        for step in steps
        if "codecov/codecov-action" in step.get("uses", "")
    }
    assert set(upload_steps) == {"backend", "frontend"}
    assert upload_steps["backend"].get("if") == "steps.backend-coverage.outputs.exists == 'true'"
    assert upload_steps["frontend"].get("if") == "steps.frontend-coverage.outputs.exists == 'true'"


def test_workflows_do_not_queue_pull_requests_for_auto_merge() -> None:
    """GitHub Actions must not enable auto-merge for pull requests."""
    forbidden_patterns = (
        "automerge",
        "auto-merge",
        "enable-auto-merge",
        "gh pr merge --auto",
    )
    offenders: list[str] = []
    for workflow_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        content = workflow_path.read_text()
        lower_content = content.lower()
        offenders.extend(
            f"{workflow_path.relative_to(REPO_ROOT)} contains {pattern!r}"
            for pattern in forbidden_patterns
            if pattern in lower_content
        )

    assert not offenders, (
        "GitHub Actions workflows must not queue PRs for auto-merge:\n" + "\n".join(offenders)
    )


def test_pr_timing_workflow_does_not_collect_coverage() -> None:
    """pr-timing.yml (issue #708) must be timing-only; Codecov owns coverage.

    Running two full-suite coverage collections per PR (once for the head,
    once for the base) duplicated Codecov's job and produced a second,
    potentially conflicting coverage comment. The workflow should measure
    wall-clock time only.
    """
    assert PR_TIMING_FILE.exists(), f"pr-timing.yml not found at {PR_TIMING_FILE}"
    content = PR_TIMING_FILE.read_text()
    forbidden = ("--cov", "coverage.reporter", "cov-backend.json", "coverage-summary.json")
    offenders = [pattern for pattern in forbidden if pattern in content]
    assert not offenders, f"pr-timing.yml still collects coverage: {offenders}"


def test_pr_timing_workflow_comment_has_no_coverage_table() -> None:
    """The sticky comment body must not render a coverage table.

    PRs should have one clear source of coverage feedback (Codecov); this
    workflow's comment should be timing-only.
    """
    content = PR_TIMING_FILE.read_text()
    assert "covRow" not in content, "pr-timing.yml comment still renders a coverage table"
    assert "backend_cov" not in content, "pr-timing.yml metrics still include backend_cov"
    assert "pr-test-timing" in content, "pr-timing.yml sticky comment marker is missing"
