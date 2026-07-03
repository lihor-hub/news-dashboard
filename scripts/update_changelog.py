#!/usr/bin/env python3
"""Idempotently insert or replace a version entry in CHANGELOG.md.

The PR-time release job re-runs on every push to a pull request, so this must be
safe to apply repeatedly: re-applying the same version + body is a no-op, and a
changed body for an existing version replaces it rather than duplicating it.

Entries are written as Keep a Changelog headings (``## [1.2.3] — 2026-07-03``)
when a date is supplied; the CLI defaults the date to today (UTC). Sections are
matched by version regardless of heading style, so a dated entry replaces a
legacy plain ``## 1.2.3`` one and vice versa.

CLI usage:
    python3 scripts/update_changelog.py --version 1.2.3 --body-file notes.md
    echo "- A bullet" | python3 scripts/update_changelog.py --version 1.2.3
"""

from __future__ import annotations

import re

_HEADER = "# Changelog"

# "## 1.2.3" or "## [1.2.3] — 2026-07-03" (em dash or hyphen) → the version.
_HEADING_VERSION = re.compile(r"^##\s+\[?([^\]\s]+)\]?")


def _heading_version(heading: str) -> str:
    m = _HEADING_VERSION.match(heading.strip())
    return m.group(1) if m else heading.strip()


def update_changelog(text: str, version: str, body: str, date: str | None = None) -> str:
    """Return CHANGELOG text with ``version`` placed at the top.

    Any pre-existing section for ``version`` — plain or Keep a Changelog style —
    is removed first, so the result is stable under repeated application
    (idempotent for identical inputs).
    """
    body = body.strip()
    lines = text.splitlines()

    # Split off the header: everything before the first "## " section heading.
    i = 0
    header_lines: list[str] = []
    while i < len(lines) and not lines[i].startswith("## "):
        header_lines.append(lines[i])
        i += 1

    # Group the remaining lines into sections, each starting at a "## " heading.
    sections: list[list[str]] = []
    current: list[str] | None = None
    for line in lines[i:]:
        if line.startswith("## "):
            current = [line]
            sections.append(current)
        elif current is not None:
            current.append(line)

    # Drop any existing section for this version, then prepend the fresh one.
    heading = f"## [{version}] — {date}" if date else f"## {version}"
    sections = [s for s in sections if _heading_version(s[0]) != version]
    sections.insert(0, [heading, *body.splitlines()])

    header = "\n".join(header_lines).rstrip() or _HEADER
    rendered = "\n\n".join("\n".join(s).rstrip() for s in sections)
    return f"{header}\n\n{rendered}\n"


def main() -> None:
    import argparse
    import datetime
    import pathlib
    import sys

    parser = argparse.ArgumentParser(description="Insert/replace a CHANGELOG entry")
    parser.add_argument("--version", required=True, help="Version, e.g. 1.2.3")
    parser.add_argument("--body-file", help="File with the entry body; else stdin")
    parser.add_argument("--file", default="CHANGELOG.md", help="Changelog path")
    parser.add_argument(
        "--date",
        default=datetime.datetime.now(datetime.UTC).date().isoformat(),
        help="Release date for the heading (YYYY-MM-DD, default: today UTC)",
    )
    args = parser.parse_args()

    body = pathlib.Path(args.body_file).read_text() if args.body_file else sys.stdin.read()

    path = pathlib.Path(args.file)
    text = path.read_text() if path.exists() else ""
    path.write_text(update_changelog(text, args.version, body, date=args.date))


if __name__ == "__main__":
    main()
