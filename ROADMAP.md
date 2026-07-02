# Roadmap

This is a lightweight, living snapshot of near-term direction for News
Dashboard. It's not a commitment or a schedule — see
[GOVERNANCE.md](GOVERNANCE.md) for how priorities actually get decided.

For granular, up-to-date status, the GitHub issue tracker is the source of
truth. This roadmap gives the high-level "why" behind the current epics.

## Now: OSS readiness

Tracked in [epic: OSS readiness](https://github.com/lihor-hub/news-dashboard/issues/640).
The project recently moved to the public `lihor-hub` org under the MIT
license, and the current focus is making it a genuinely welcoming,
self-hostable open source project:

- **Community health** — CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue/PR
  templates, CODEOWNERS, and this governance trio.
- **Documentation site** — a Docusaurus site at [docs.lihor.ro](https://docs.lihor.ro)
  with a Getting Started guide and user guide, replacing scattered `docs/`
  markdown.
- **Security & supply-chain CI** — CodeQL, dependency review, container
  scanning, and SBOM/provenance for releases.
- **Self-host adoption** — a publicly published container image, a
  production `docker-compose` quickstart, an operations guide, and a demo
  mode with seed data and a read-only guest account so people can try the
  app before self-hosting it.
- **Contributor onboarding** — Dev Containers/Codespaces, a curated `good
  first issue` backlog, and Architecture Decision Records for larger
  decisions.

## Later: beyond OSS readiness

Once the OSS-readiness epic is substantially done, expect the roadmap to
shift back toward product work — reader experience, AI-powered features, and
automation/delivery. Browse the `epic: *` labels
([reader-ux](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aissue+is%3Aopen+label%3A%22epic%3A+reader-ux%22),
[ai](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aissue+is%3Aopen+label%3A%22epic%3A+ai%22),
[automation](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aissue+is%3Aopen+label%3A%22epic%3A+automation%22),
[content](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aissue+is%3Aopen+label%3A%22epic%3A+content%22))
for the current backlog in each area — that's a more accurate picture than
anything a static roadmap file could promise.

## Proposing roadmap items

Roadmap direction is set the same way other proposals are, per
[GOVERNANCE.md](GOVERNANCE.md#how-proposals-are-made):

1. For a new epic or a significant shift in direction, open a
   [GitHub Discussion](https://github.com/lihor-hub/news-dashboard/discussions)
   to build consensus before filing issues.
2. For a specific, well-scoped feature or fix, open a
   [GitHub Issue](https://github.com/lihor-hub/news-dashboard/issues) directly.
3. If it's accepted as a near-term priority, it gets folded into this file
   (or a tracking epic issue) via a normal PR.

This file will be updated periodically as epics complete and new priorities
emerge — it does not need to track every issue, just the current "what and
why" at a glance.
