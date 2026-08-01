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


class TestVultureWhitelistExists(unittest.TestCase):
    """`make lint` / `make dead-code` pass `backend/vulture_whitelist.py` on the
    vulture command line; if the file is deleted those commands break silently
    (vulture just sees fewer paths) instead of failing loudly.
    """

    def test_vulture_whitelist_file_exists(self) -> None:
        whitelist = ROOT / "backend" / "vulture_whitelist.py"
        assert whitelist.is_file(), (
            "backend/vulture_whitelist.py must exist for `make lint`/`make dead-code`"
        )


class TestDependabotNpmProjects(unittest.TestCase):
    _NPM_UPDATE = re.compile(
        r'^  - package-ecosystem: "npm"\n(?P<configuration>.*?)(?=^  - |\Z)',
        re.MULTILINE | re.DOTALL,
    )

    def test_expected_npm_projects_are_covered_exactly_once(self) -> None:
        dependabot = (ROOT / ".github" / "dependabot.yml").read_text()
        directories = [
            re.search(
                r'^    directory: "(?P<directory>[^"]+)"$',
                match.group("configuration"),
                re.MULTILINE,
            )["directory"]
            for match in self._NPM_UPDATE.finditer(dependabot)
        ]

        assert sorted(directories) == ["/", "/desktop", "/website"]


class TestNoDuplicateDocusaurusSourceFiles(unittest.TestCase):
    """A compiled/generated ``.js`` file checked in beside its ``.tsx`` source under
    ``website/src`` makes Docusaurus register the same page or component twice
    (e.g. a duplicate `/` route warning) because both files export a component
    for the same route or import path. Guard against that pairing recurring.
    """

    _SOURCE_DIRS: ClassVar[list[str]] = ["pages", "components"]
    _JS_EXTENSIONS: ClassVar[set[str]] = {".js", ".jsx"}
    _TS_EXTENSIONS: ClassVar[set[str]] = {".ts", ".tsx"}

    def test_no_js_and_ts_pair_share_a_basename(self) -> None:
        website_src = ROOT / "website" / "src"
        violations: list[str] = []
        for subdir in self._SOURCE_DIRS:
            base = website_src / subdir
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or path.suffix not in self._JS_EXTENSIONS:
                    continue
                stem_dir = path.parent
                for ts_ext in self._TS_EXTENSIONS:
                    ts_sibling = stem_dir / f"{path.stem}{ts_ext}"
                    if ts_sibling.is_file():
                        violations.append(
                            f"{path.relative_to(ROOT)} duplicates {ts_sibling.relative_to(ROOT)}"
                        )
        assert not violations, (
            "Docusaurus source files must not have both a compiled .js/.jsx and a "
            ".ts/.tsx file with the same name (causes duplicate route/component "
            "registration):\n" + "\n".join(violations)
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
