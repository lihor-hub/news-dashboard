#!/usr/bin/env python3
"""Turn raw git commit subjects into user-facing "What's new" bullets.

This is the *fallback* for the release changelog: the CI/release pipeline first
asks an LLM to write friendly notes from the commits, but if that call fails or
returns nothing we must still produce something a non-developer can read — never
raw Conventional Commit subjects like "chore: bump deps" or "ci: fix pipeline".

The transform is deliberately conservative:
  - Commits whose type has no visible effect for users (chore, ci, test, docs,
    refactor, build, style, perf-infra, etc.) are dropped.
  - Remaining commits keep only their human part: the "type(scope): " prefix and
    trailing PR/issue references like " (#123)" are stripped, and the first
    letter is capitalized.
  - If nothing user-facing survives, we emit a single reassuring bullet rather
    than an empty changelog.

Stdlib only: this runs on the CI runner's system python3 with no dependencies,
matching update_changelog.py.

CLI usage:
    git log --pretty='- %s' RANGE | python3 scripts/humanize_commits.py
"""

from __future__ import annotations

import re

_STABILITY_BULLET = "- Stability and performance improvements."

# Conventional Commit types that carry no user-visible change.
_INTERNAL_TYPES = frozenset(
    {"chore", "ci", "test", "tests", "docs", "doc", "refactor", "build", "style"}
)

# "type" or "type(scope)" followed by "!" (breaking) and a colon, at line start.
_PREFIX_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?!?:\s*")
# Trailing " (#123)" / " (#123) (#456)" PR or issue references.
_PR_REF_RE = re.compile(r"(?:\s*\(#\d+\))+\s*$")


def _clean_subject(subject: str) -> str | None:
    """Return a user-facing bullet body for ``subject``, or ``None`` to drop it.

    ``subject`` is a single commit subject, optionally with a leading "- ".
    """
    text = subject.strip()
    if text.startswith("- "):
        text = text[2:].strip()
    if not text:
        return None

    match = _PREFIX_RE.match(text)
    if match:
        if match.group("type") in _INTERNAL_TYPES:
            return None
        text = text[match.end() :]

    text = _PR_REF_RE.sub("", text).strip()
    if not text:
        return None

    return text[0].upper() + text[1:]


def humanize_commits(commits: str) -> str:
    """Return markdown bullet lines summarizing ``commits`` for end users.

    ``commits`` is newline-separated commit subjects (each optionally prefixed
    with "- "). Internal commits are dropped and prefixes/PR refs stripped; if
    nothing user-facing remains, a single stability bullet is returned.
    """
    bullets = [
        f"- {body}" for line in commits.splitlines() if (body := _clean_subject(line)) is not None
    ]
    if not bullets:
        return _STABILITY_BULLET
    return "\n".join(bullets)


# ── Sanitizer for LLM-generated release notes ────────────────────────────────
#
# The release pipeline asks an LLM to write the changelog/GitHub-release
# prose. Occasionally the model leaks its reasoning instead of (or alongside)
# the requested bullets: <think> blocks, prompt narration ("The user wants
# me to..."), or stray markdown code fences. That text must never reach
# CHANGELOG.md or a published GitHub Release.

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)
_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_STRAY_FENCE_RE = re.compile(r"^```.*$", re.MULTILINE)

# Prefixes (checked against the start of a bullet's body, lowercased) that
# mark model reasoning/narration rather than a genuine release note.
_NARRATION_PREFIXES = (
    "the user wants",
    "i'll ",
    "i should",
    "i need to",
    "let me ",
    "as an ai",
    "according to the rules",
    "according to the instructions",
)


def _is_narration(bullet_body: str) -> bool:
    lowered = bullet_body.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _NARRATION_PREFIXES)


def sanitize_release_notes(text: str) -> str | None:
    """Return ``text`` reduced to safe user-facing bullet lines, or ``None``.

    Only lines that look like a genuine "- " bullet and don't open with a
    known reasoning marker survive. ``None`` means nothing usable remained —
    the caller should fall back to a deterministic summary rather than
    publish raw model output.
    """
    if not text:
        return None

    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _FENCED_BLOCK_RE.sub("", cleaned)
    cleaned = _STRAY_FENCE_RE.sub("", cleaned)

    bullets = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if _is_narration(stripped[2:]):
            continue
        bullets.append(stripped)

    if not bullets:
        return None
    return "\n".join(bullets)


def main() -> None:
    import sys

    if "--sanitize" in sys.argv:
        sanitized = sanitize_release_notes(sys.stdin.read())
        print(sanitized if sanitized is not None else "")
        return

    print(humanize_commits(sys.stdin.read()))


if __name__ == "__main__":
    main()
