"""Behavior of the repository-owned UTF-8 VERSION file."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from news_dashboard.version import read_app_version


@pytest.fixture
def version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "VERSION"
    monkeypatch.setattr("news_dashboard.version._VERSION_FILE", path)
    read_app_version.cache_clear()
    try:
        yield path
    finally:
        read_app_version.cache_clear()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("1.2.3", "1.2.3"),
        (" \t1.2.3\n", "1.2.3"),
        ("\u20031.2.3\u2003\n", "1.2.3"),
        ("", "unknown"),
        (" \t\n", "unknown"),
    ],
)
def test_read_app_version_from_utf8_file(version_file: Path, content: str, expected: str) -> None:
    version_file.write_bytes(content.encode("utf-8"))
    with patch("io.text_encoding", side_effect=lambda encoding, _stacklevel=2: encoding or "ascii"):
        assert read_app_version() == expected


def test_read_app_version_missing_file(version_file: Path) -> None:
    assert not version_file.exists()
    assert read_app_version() == "unknown"
