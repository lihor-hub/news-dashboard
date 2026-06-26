"""Unit tests for update_changelog.py — stdlib only, no pytest required.

Run:  python3 -m unittest scripts/test_update_changelog.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from update_changelog import update_changelog

_EXISTING = """# Changelog

## 1.21.0
- You can now share articles with other users directly within the platform!

## 1.20.0
- Smarter recommendations.
"""


class TestUpdateChangelog(unittest.TestCase):
    def test_prepends_new_version(self):
        out = update_changelog(_EXISTING, "1.22.0", "- A shiny new feature.")
        # New entry sits at the top, right after the header.
        self.assertTrue(out.startswith("# Changelog\n\n## 1.22.0\n- A shiny new feature."))
        # Older entries are preserved.
        self.assertIn("## 1.21.0", out)
        self.assertIn("## 1.20.0", out)
        # Header appears exactly once.
        self.assertEqual(out.count("# Changelog"), 1)

    def test_idempotent_same_inputs(self):
        once = update_changelog(_EXISTING, "1.22.0", "- A shiny new feature.")
        twice = update_changelog(once, "1.22.0", "- A shiny new feature.")
        self.assertEqual(once, twice)
        # Version heading appears exactly once after re-applying.
        self.assertEqual(twice.count("## 1.22.0"), 1)

    def test_replaces_existing_version_body(self):
        first = update_changelog(_EXISTING, "1.22.0", "- Draft note.")
        updated = update_changelog(first, "1.22.0", "- Final note.")
        self.assertEqual(updated.count("## 1.22.0"), 1)
        self.assertIn("- Final note.", updated)
        self.assertNotIn("- Draft note.", updated)

    def test_replaces_top_version_in_place(self):
        # Re-bumping the newest version must not duplicate it.
        updated = update_changelog(_EXISTING, "1.21.0", "- Revised wording.")
        self.assertEqual(updated.count("## 1.21.0"), 1)
        self.assertTrue(updated.startswith("# Changelog\n\n## 1.21.0\n- Revised wording."))
        self.assertIn("## 1.20.0", updated)

    def test_bootstraps_empty_changelog(self):
        out = update_changelog("", "1.0.0", "- First release.")
        self.assertEqual(out, "# Changelog\n\n## 1.0.0\n- First release.\n")

    def test_bootstraps_header_only(self):
        out = update_changelog("# Changelog\n", "1.0.0", "- First release.")
        self.assertEqual(out, "# Changelog\n\n## 1.0.0\n- First release.\n")

    def test_multiline_body(self):
        body = "- First bullet.\n- Second bullet."
        out = update_changelog(_EXISTING, "1.22.0", body)
        self.assertIn("## 1.22.0\n- First bullet.\n- Second bullet.\n", out)

    def test_trailing_newline_normalized(self):
        out = update_changelog(_EXISTING, "1.22.0", "- Note.\n\n")
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
