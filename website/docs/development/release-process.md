---
title: Release process
sidebar_position: 6
---

# Release process

How a version number is decided, where it comes from at runtime, and why you
should not hardcode one.

## Git tags are the source of truth

Versions are **derived from git tags**, not stored in a file that gets bumped
by hand. `scripts/next_version.sh` computes the next semantic version from the
latest `v*` tag plus the Conventional Commits since it, and falls back to the
`VERSION` file only when no tags exist.

It is stateless — nothing is committed. It prints:

```
version=1.2.3
code=1002003
tag=v1.2.3
bumped=true|false
```

`bumped=false` means only `ci`, `docs`, `test`, or `chore` commits have landed
since the last tag, so no release is warranted.

The same script is shared by `ci.yml` (which bakes the version into the image)
and `release.yml` (which tags and builds artifacts), so CI builds and releases
can never disagree about what version they are.

This is why [commit conventions](../contributing/index.md) matter mechanically
rather than stylistically: a `feat:` commit and a `fix:` commit produce
different version bumps.

## The `VERSION` file

`VERSION` at the repository root is the single source of truth *for the running
application*.

It is intentionally **not** committed with a bumped value between releases —
it is written at release time. Do not bump it by hand in a feature PR.
`pyproject.toml`'s `version` field is synced to it at release time.

## How the version reaches runtime

The backend reads `VERSION` once at startup
(`news_dashboard.main._read_app_version`) and uses it for the FastAPI
`app.version`. That single value drives:

- the OpenAPI `info.version` shown at `/docs`
- the `/api/version` endpoint

Because they share one source, the documented version and the reported version
cannot drift apart.

:::warning Never hardcode a version literal
Read `VERSION`, or `app.version` at runtime. A hardcoded literal is exactly the
drift this arrangement exists to prevent.
:::

## Release workflow

`release.yml` handles tagging, image build, and publication. `ci.yml` bakes the
computed version into the image it builds, using the same script.

Supporting scripts:

| Script | Role |
|--------|------|
| `next_version.sh` | Compute the next version from tags + commits. |
| `bump_version.py` | Decide the bump type from Conventional Commits. |
| `inject_app_version.sh` | Inject the version into build artifacts. |
| `update_changelog.py` | Update `CHANGELOG.md`. |
| `humanize_commits.py` | Turn commit subjects into readable release notes. |

Each has a `scripts/test_*.py` counterpart. If you change release behavior,
expect to update the corresponding test — `test_bump_version.py`,
`test_release_sync_workflow.py`, `test_update_changelog.py`.

## Changelog

`CHANGELOG.md` is generated from commit history at release time. Write commit
subjects as the line you would want to read in release notes — they become
exactly that.

The running instance exposes its own release notes at `/api/changelog`.
