"""Guard tests for repo-level metadata consistency.

Run: python3 -m unittest scripts/test_repo_metadata.py
"""

import re
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).parent.parent


class TestVersionConsistency(unittest.TestCase):
    def test_pyproject_version_matches_version_file(self) -> None:
        version_file = (ROOT / "VERSION").read_text().strip()
        pyproject = (ROOT / "pyproject.toml").read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        assert m is not None, "version field not found in pyproject.toml"
        assert m.group(1) == version_file, (
            f"pyproject.toml version ({m.group(1)}) does not match VERSION ({version_file})"
        )


class TestReadmeVersionBadge(unittest.TestCase):
    """The version lives in git tags, never committed (see scripts/next_version.sh).

    A hardcoded ``version-X.Y.Z`` shields badge in the README therefore goes stale
    on the next push to main. Require the badge to be the dynamic tag-based image
    so it can never drift from the actual released version.
    """

    def test_readme_has_no_hardcoded_version_badge(self) -> None:
        readme = (ROOT / "README.md").read_text()
        m = re.search(r"img\.shields\.io/badge/version-\d+\.\d+\.\d+", readme)
        assert m is None, (
            "README.md pins a hardcoded version badge "
            f"({m.group(0) if m else ''}); use the dynamic github/v/tag badge instead"
        )

    def test_readme_uses_dynamic_tag_badge(self) -> None:
        readme = (ROOT / "README.md").read_text()
        assert "img.shields.io/github/v/tag/lihor-hub/news-dashboard" in readme, (
            "README.md should use the dynamic github/v/tag version badge"
        )
        assert "filter=v*" in readme, (
            "README version badge must filter to v* tags (exclude android-/desktop- tags)"
        )


class TestNoPrivatePersonalPhrases(unittest.TestCase):
    _FORBIDDEN: ClassVar[list[str]] = ["private personal", "for Ioachim"]
    _EXTENSIONS: ClassVar[set[str]] = {".py", ".md", ".toml", ".ts", ".tsx", ".txt", ".rst"}

    def test_no_forbidden_phrases_in_tracked_files(self) -> None:
        this_file = Path(__file__).resolve()
        violations: list[str] = []
        for ext in self._EXTENSIONS:
            for path in ROOT.rglob(f"*{ext}"):
                if path.resolve() == this_file:
                    continue
                if any(part.startswith(".") for part in path.parts):
                    continue
                text = path.read_text(errors="replace")
                violations.extend(
                    f"{path.relative_to(ROOT)}: contains '{phrase}'"
                    for phrase in self._FORBIDDEN
                    if phrase.lower() in text.lower()
                )
        assert not violations, "Forbidden phrases found:\n" + "\n".join(violations)


if __name__ == "__main__":
    unittest.main()
