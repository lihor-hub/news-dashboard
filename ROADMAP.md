# Roadmap

This is a lightweight, living snapshot of near-term direction for News
Dashboard. It's not a commitment or a schedule — see
[GOVERNANCE.md](GOVERNANCE.md) for how priorities actually get decided.

For granular, up-to-date status, the GitHub issue tracker is the source of
truth. This roadmap gives the high-level "why" behind the current epics.

## Now: growing the contributor community

The OSS-readiness push
([epic #640](https://github.com/lihor-hub/news-dashboard/issues/640)) is
done: the project is MIT-licensed, self-hostable from a published image,
documented at [docs.lihor.ro](https://docs.lihor.ro), covered by
security/supply-chain CI, and ready for Dev Containers/Codespaces. The
current focus is turning that foundation into an active contributor
community:

- **A curated, always-stocked backlog** — every
  [good first issue](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
  and [help wanted](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22help+wanted%22)
  item is grounded in the code with file references and acceptance
  criteria, so it can be picked up cold. Area labels (`frontend`,
  `backend`, `documentation`, `i18n`, `deploy`, `android`, `desktop`)
  let you filter by what you know.
- **Broadening the platforms** — help-wanted projects cover ARM64
  container images, Linux/Windows desktop builds, and a published Helm
  chart, so more self-hosters can run the app on their hardware.
- **Reaching more users** — more UI languages, RTL layout support, and
  closing the gaps between the app and its documentation.
- **Direction from real users** — the
  [contributor announcement](https://github.com/lihor-hub/news-dashboard/discussions/1331)
  asks self-hosters what would make them switch; that feedback feeds
  this roadmap.

## Later: product work

As the community grows, expect the roadmap to
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
