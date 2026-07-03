---
name: release
description: >-
  Runbook for how releases, versioning, and the changelog work in this repo,
  and how to check or troubleshoot what is deployed.
disable-model-invocation: true
---

# Release runbook

There is no manual release step: **merging to `main` is the release.** Use
this runbook to answer "how do I cut/check/troubleshoot a release".

## How a release happens

On every push to `main`, `.github/workflows/release.yml`:

1. Computes the next semantic version from the latest `v*` tag plus the
   Conventional Commits since it (`scripts/next_version.sh` →
   `scripts/bump_version.py`). Nothing is committed — the version lives in git
   tags only; the tracked `VERSION` file is just the no-tags fallback.
   Only `feat`/`fix`/breaking commits bump; ci/docs/test/chore-only pushes
   create no tag.
2. Pushes the tag ref (never the protected `main` branch), generates release
   notes with AI from the commit log, and creates the GitHub Release.
3. On a new tag, the `android` and `desktop` jobs build and attach the
   signed artifacts (version injected at build time by
   `scripts/inject_app_version.sh`, not committed).

Separately, `ci.yml` bakes the same computed version into the Docker image, so
the deployed app's `/api/version` and `/api/changelog` track `main` without a
post-merge bump commit.

## The changelog

The in-app "What's New" popup reads `/api/changelog`. Entries are AI-written
at build time; `scripts/humanize_commits.py` is the fallback that strips
Conventional-Commit jargon for customers. `scripts/update_changelog.py`
inserts entries idempotently. Treat all of it as generated output — never
hand-edit an entry and expect it to survive.

## Common operations

- **Force a release run**: `gh workflow run release.yml` (workflow_dispatch).
  If the computed tag already exists, the run is a no-op by design.
- **Check what version is deployed**: `curl <instance>/api/version` and
  compare with `git tag --list 'v*' --sort=-version:refname | head -1`.
- **Why didn't my merge release?** Check whether the commits since the last
  tag are all non-bumping types (`bumped=false` from
  `scripts/next_version.sh`), and check the release run logs:
  `gh run list --workflow release.yml`.
- **Version math looks wrong**: `bash scripts/next_version.sh` locally prints
  `version=/code=/tag=/bumped=` — the same values CI uses.

## Guardrails

- Never push a `v*` tag by hand; the workflow owns the tag namespace.
- Never commit a version bump or hand-edit `CHANGELOG.md` to "fix" a release.
- Changes to release behavior go through the scripts and their tests
  (`scripts/test_bump_version.py`, `scripts/test_update_changelog.py`,
  `scripts/test_humanize_commits.py`) via `tdd-ship`, like any other change.
