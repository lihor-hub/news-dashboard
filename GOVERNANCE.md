# Governance

News Dashboard is a small, maintainer-led open source project. This document
describes how decisions are made today. It's intentionally lightweight and
will evolve as the project and contributor base grow — see
[MAINTAINERS.md](MAINTAINERS.md) for who currently holds this role.

## Decision model

The project currently follows a **maintainer-led (BDFL-style)** model: the
maintainer(s) listed in [MAINTAINERS.md](MAINTAINERS.md) have final say on
scope, direction, and what gets merged. In practice, most day-to-day
decisions happen through ordinary code review on pull requests — there's no
separate approval process for small or routine changes.

As more maintainers join, decisions will move toward lazy consensus among
them (see below), with the original maintainer as tie-breaker.

## How proposals are made

The right venue depends on the size of the change:

- **Bug fixes and small, well-scoped features** — open a
  [GitHub Issue](https://github.com/lihor-hub/news-dashboard/issues) (or pick
  up an existing one) and send a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Open-ended ideas, questions, or anything that needs discussion before
  code is written** — start a [GitHub Discussion](https://github.com/lihor-hub/news-dashboard/discussions).
  See [SUPPORT.md](SUPPORT.md) for how issues and Discussions are split.
- **Larger or architecturally significant changes** (new subsystems, breaking
  API/schema changes, changes that affect the PostgreSQL-only runtime rule in
  [CONTRIBUTING.md](CONTRIBUTING.md)) — open a Discussion or draft PR first so
  the approach can be agreed on before significant implementation work
  happens. There's no formal ADR (Architecture Decision Record) template yet;
  until one exists, capture the rationale in the Discussion/PR description
  and link it from the eventual PR.

Lazy consensus applies: a proposal is considered accepted if no maintainer
objects within a reasonable review window. Silence is not blocking; an
explicit maintainer objection is.

## Release and merge process

- All changes land on `main` through pull requests — no direct pushes.
- PRs require CI to pass (lint, type checks, backend and frontend test
  suites) before merge; see the `make check` gate in
  [CONTRIBUTING.md](CONTRIBUTING.md).
- PRs are reviewed and merged by a maintainer (or, for agent-authored PRs
  following the repo's autonomous-agent workflow, auto-merged once CI is
  green and the PR closes a `ready-for-agent`-labeled issue).
- Releases are versioned and recorded in [`CHANGELOG.md`](CHANGELOG.md);
  container images are published via the CI/CD pipeline on merge to `main`.
- Breaking changes (config, schema, API) must be called out explicitly in the
  PR description and the changelog entry.

## Code of Conduct

All participation — issues, Discussions, PRs, and reviews — is governed by
the [Code of Conduct](CODE_OF_CONDUCT.md). Report violations as described
there.

## Changing this document

Governance changes go through the normal PR process, reviewed by the current
maintainer(s). As the maintainer group grows, this document will be updated
to reflect a more formal consensus process.
