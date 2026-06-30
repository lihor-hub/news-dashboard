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
