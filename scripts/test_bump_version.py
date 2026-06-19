"""Unit tests for bump_version.py — stdlib only, no pytest required.

Run:  python3 -m unittest scripts/test_bump_version.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from bump_version import bump_version, determine_bump, version_code


class TestDetermineBump(unittest.TestCase):
    # --- feat → minor ---

    def test_feat_is_minor(self):
        self.assertEqual(determine_bump(["feat: add search"]), "minor")

    def test_feat_with_scope(self):
        self.assertEqual(determine_bump(["feat(auth): add OAuth login"]), "minor")

    def test_feat_beats_fix(self):
        self.assertEqual(determine_bump(["fix: bug", "feat: feature"]), "minor")

    # --- fix / perf → patch ---

    def test_fix_is_patch(self):
        self.assertEqual(determine_bump(["fix: resolve crash"]), "patch")

    def test_fix_with_scope(self):
        self.assertEqual(determine_bump(["fix(api): handle 404"]), "patch")

    def test_perf_is_patch(self):
        self.assertEqual(determine_bump(["perf(db): add index"]), "patch")

    # --- BREAKING CHANGE → major ---

    def test_breaking_change_footer(self):
        self.assertEqual(
            determine_bump(["feat: rename API\n\nBREAKING CHANGE: /v1 removed"]),
            "major",
        )

    def test_breaking_bang_feat(self):
        self.assertEqual(determine_bump(["feat!: drop Python 3.11"]), "major")

    def test_breaking_bang_fix(self):
        self.assertEqual(determine_bump(["fix!: changed response shape"]), "major")

    def test_breaking_bang_with_scope(self):
        self.assertEqual(determine_bump(["feat(api)!: new auth scheme"]), "major")

    def test_breaking_beats_feat(self):
        self.assertEqual(determine_bump(["feat: new thing", "fix!: break api"]), "major")

    # --- skip types → none ---

    def test_ci_is_none(self):
        self.assertEqual(determine_bump(["ci: add cache step"]), "none")

    def test_docs_is_none(self):
        self.assertEqual(determine_bump(["docs: update README"]), "none")

    def test_test_is_none(self):
        self.assertEqual(determine_bump(["test: add coverage"]), "none")

    def test_chore_is_none(self):
        self.assertEqual(determine_bump(["chore: update deps"]), "none")

    def test_build_is_none(self):
        self.assertEqual(determine_bump(["build: upgrade webpack"]), "none")

    def test_revert_is_none(self):
        self.assertEqual(determine_bump(["revert: undo bad commit"]), "none")

    # --- mixed skip + meaningful → meaningful wins ---

    def test_ci_plus_fix_is_patch(self):
        self.assertEqual(determine_bump(["ci: skip", "fix: bug"]), "patch")

    def test_docs_plus_feat_is_minor(self):
        self.assertEqual(determine_bump(["docs: typo", "feat: new ui"]), "minor")

    # --- non-conventional commits → patch (conservative) ---

    def test_non_conventional_is_patch(self):
        self.assertEqual(determine_bump(["work"]), "patch")

    def test_codex_style_is_patch(self):
        self.assertEqual(determine_bump(["[codex] fix swipe actions"]), "patch")

    def test_empty_first_line_ignored(self):
        # Message with only a body (no first line prefix)
        self.assertEqual(determine_bump(["some random message"]), "patch")

    # --- edge cases ---

    def test_empty_list_is_none(self):
        self.assertEqual(determine_bump([]), "none")

    def test_only_skip_types_is_none(self):
        self.assertEqual(determine_bump(["ci: lint", "docs: readme", "test: coverage"]), "none")

    def test_multiline_commit_reads_first_line(self):
        # Body contains "feat:" but that should not trigger minor; only first line matters
        msg = "fix: crash in login\n\nSee also: feat: old note in body"
        self.assertEqual(determine_bump([msg]), "patch")


class TestBumpVersion(unittest.TestCase):
    def test_minor_from_initial(self):
        self.assertEqual(bump_version("1.0.0", "minor"), "1.1.0")

    def test_patch_from_initial(self):
        self.assertEqual(bump_version("1.0.0", "patch"), "1.0.1")

    def test_major_from_initial(self):
        self.assertEqual(bump_version("1.0.0", "major"), "2.0.0")

    def test_minor_resets_patch(self):
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")

    def test_major_resets_minor_and_patch(self):
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")

    def test_none_returns_same(self):
        self.assertEqual(bump_version("1.5.3", "none"), "1.5.3")

    def test_large_numbers(self):
        self.assertEqual(bump_version("10.20.30", "patch"), "10.20.31")


class TestVersionCode(unittest.TestCase):
    def test_initial(self):
        self.assertEqual(version_code("1.0.0"), 1_000_000)

    def test_minor_bump(self):
        self.assertEqual(version_code("1.1.0"), 1_001_000)

    def test_patch_bump(self):
        self.assertEqual(version_code("1.0.1"), 1_000_001)

    def test_major_bump(self):
        self.assertEqual(version_code("2.0.0"), 2_000_000)

    def test_always_increases_with_semver(self):
        # patch < minor < major for any reasonable version
        self.assertGreater(version_code("1.0.1"), version_code("1.0.0"))
        self.assertGreater(version_code("1.1.0"), version_code("1.0.99"))
        self.assertGreater(version_code("2.0.0"), version_code("1.999.999"))


if __name__ == "__main__":
    unittest.main()
