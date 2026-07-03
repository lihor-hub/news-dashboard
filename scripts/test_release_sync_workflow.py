"""Guard the release.yml job that syncs committed version files back to main.

The deployed version is derived from git tags (scripts/next_version.sh) and
baked into the image at build time, so the committed VERSION, pyproject.toml,
and CHANGELOG.md drift behind releases unless something proposes the catch-up.
release.yml must open a rolling sync PR after each release — and must never
push to the protected main branch or queue its own merge
(see scripts/test_auto_merge_workflow.py).

Run:  python3 -m unittest scripts/test_release_sync_workflow.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


class TestReleaseSyncJob(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = RELEASE.read_text()

    def test_sync_job_runs_only_after_a_new_tag(self) -> None:
        if "sync-version-files:" not in self.workflow:
            self.fail("release.yml is missing the sync-version-files job")
        if self.workflow.count("if: needs.release.outputs.released == 'true'") < 3:
            self.fail("sync-version-files must be gated on a new tag being created")

    def test_sync_job_updates_all_committed_version_files(self) -> None:
        for expected in (
            "> VERSION",
            'scripts/update_changelog.py --version "$V" --date "$DATE"',
            "pyproject.toml",
        ):
            if expected not in self.workflow:
                self.fail(f"release.yml sync job does not update {expected}")

    def test_sync_job_skips_when_rolling_pr_is_queued_for_merge(self) -> None:
        # A branch whose PR sits in the merge queue rejects pushes (GH006), and
        # the next release catches up anyway — the job must skip, not fail.
        if "isInMergeQueue" not in self.workflow:
            self.fail("sync job must check whether the rolling PR is in the merge queue")
        if "queued in the merge queue" not in self.workflow:
            self.fail("sync job must log why it skipped when the rolling PR is queued")

    def test_sync_job_opens_a_rolling_pr_instead_of_pushing_main(self) -> None:
        if "bot/sync-versioning" not in self.workflow:
            self.fail("sync job must push a rolling bot/sync-versioning branch")
        if "gh pr create" not in self.workflow:
            self.fail("sync job must open a PR for the version-file catch-up")
        for forbidden in ("git push origin main", "git push origin HEAD:main", "--admin"):
            if forbidden in self.workflow:
                self.fail(f"release.yml must not contain {forbidden!r}")


if __name__ == "__main__":
    unittest.main()
