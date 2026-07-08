"""Unit tests for humanize_commits.py — stdlib only, no pytest required.

Run:  python3 -m unittest scripts/test_humanize_commits.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from humanize_commits import humanize_commits, sanitize_release_notes

_INTERNAL_ONLY = """- chore: make API docs exposure configurable (#646) (#817)
- ci: generate SBOM and build provenance for releases (#814)
- docs: rewrite the contributing guide
- test: add coverage for the parser
- refactor: extract helper
- build(deps): bump some-lib from 1 to 2
- style: reformat files"""


class TestHumanizeCommits(unittest.TestCase):
    def test_internal_only_collapses_to_stability_bullet(self):
        # A release with nothing user-facing must never leak "chore:"/"ci:" etc.
        out = humanize_commits(_INTERNAL_ONLY)
        self.assertEqual(out, "- Stability and performance improvements.")

    def test_empty_input_is_stability_bullet(self):
        self.assertEqual(humanize_commits(""), "- Stability and performance improvements.")
        self.assertEqual(humanize_commits("   \n  \n"), "- Stability and performance improvements.")

    def test_strips_conventional_prefix_and_pr_refs(self):
        out = humanize_commits("- feat: add dark mode (#123)")
        self.assertEqual(out, "- Add dark mode")

    def test_strips_scoped_prefix(self):
        out = humanize_commits("- fix(reader): stop losing your place when you rotate")
        self.assertEqual(out, "- Stop losing your place when you rotate")

    def test_keeps_user_facing_drops_internal(self):
        commits = """- feat: share articles with friends (#301)
- chore: bump deps
- fix: correct the relevance score (#310)
- ci: tweak the pipeline"""
        out = humanize_commits(commits)
        self.assertEqual(
            out,
            "- Share articles with friends\n- Correct the relevance score",
        )

    def test_accepts_lines_without_leading_dash(self):
        out = humanize_commits("feat: brand new inbox")
        self.assertEqual(out, "- Brand new inbox")

    def test_capitalizes_first_letter(self):
        out = humanize_commits("- feat: lowercase start stays readable")
        self.assertTrue(out.startswith("- Lowercase"))


class TestSanitizeReleaseNotes(unittest.TestCase):
    def test_clean_bullets_pass_through_unchanged(self):
        notes = "- Add dark mode (#123)\n- [See the docs](https://example.com)"
        self.assertEqual(sanitize_release_notes(notes), notes)

    def test_strips_fenced_code_block(self):
        notes = "```\n- Some code snippet\n```\n- Real bullet"
        self.assertEqual(sanitize_release_notes(notes), "- Real bullet")

    def test_strips_think_block_and_stray_tags(self):
        notes = "<think>reasoning about the release</think>\n- Add feature\n</think>"
        self.assertEqual(sanitize_release_notes(notes), "- Add feature")

    def test_drops_prompt_narration_lines(self):
        notes = (
            "The user wants me to write release notes for this commit.\n"
            "- Stability and performance improvements."
        )
        self.assertEqual(sanitize_release_notes(notes), "- Stability and performance improvements.")

    def test_reasoning_only_input_returns_none(self):
        notes = "The user wants me to summarize this release.\nI should keep it short."
        self.assertIsNone(sanitize_release_notes(notes))

    def test_empty_input_returns_none(self):
        self.assertIsNone(sanitize_release_notes(""))


if __name__ == "__main__":
    unittest.main()
