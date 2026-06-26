#!/usr/bin/env python3
"""Idempotently insert or replace a version entry in CHANGELOG.md.

The PR-time release job re-runs on every push to a pull request, so this must be
safe to apply repeatedly: re-applying the same version + body is a no-op, and a
changed body for an existing version replaces it rather than duplicating it.

CLI usage:
    python3 scripts/update_changelog.py --version 1.2.3 --body-file notes.md
    echo "- A bullet" | python3 scripts/update_changelog.py --version 1.2.3

Reads the body from --body-file, else stdin. Writes the result back to the file
named by --file (default: CHANGELOG.md).
"""

from __future__ import annotations

_HEADER = "# Changelog"


def update_changelog(text: str, version: str, body: str) -> str:
    """Return CHANGELOG text with ``version`` placed at the top.

    Any pre-existing section for ``version`` is removed first, so the result is
    stable under repeated application (idempotent for identical inputs).
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
    target = f"## {version}"
    sections = [s for s in sections if s[0].strip() != target]
    sections.insert(0, [target, *body.splitlines()])

    header = "\n".join(header_lines).rstrip() or _HEADER
    rendered = "\n\n".join("\n".join(s).rstrip() for s in sections)
    return f"{header}\n\n{rendered}\n"


def main() -> None:
    import argparse
    import pathlib
    import sys

    parser = argparse.ArgumentParser(description="Insert/replace a CHANGELOG entry")
    parser.add_argument("--version", required=True, help="Version, e.g. 1.2.3")
    parser.add_argument("--body-file", help="File with the entry body; else stdin")
    parser.add_argument("--file", default="CHANGELOG.md", help="Changelog path")
    args = parser.parse_args()

    body = pathlib.Path(args.body_file).read_text() if args.body_file else sys.stdin.read()

    path = pathlib.Path(args.file)
    text = path.read_text() if path.exists() else ""
    path.write_text(update_changelog(text, args.version, body))


if __name__ == "__main__":
    main()
