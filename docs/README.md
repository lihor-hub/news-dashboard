# Documentation index

Technical documentation for News Dashboard. For end-user documentation (how to
use the app day to day), see the [User Guide](https://docs.lihor.ro/docs/user-guide) instead.

Architecture, product spec, authentication, HTTPS, Postgres backup, CI runner,
contributing, API reference, development guides, and end-user guides are
published at **[docs.lihor.ro](https://docs.lihor.ro)** (source in
[`website/docs/`](../website/docs)).

Two sections there are the usual starting points when working on the code:

- **[API reference](../website/docs/api/)** — authentication, response and
  error conventions, and the endpoint surface by area.
- **[Development](../website/docs/development/)** — environment setup, the
  codebase map, the feature-module convention, testing, and releases.

| Doc | Description |
|-----|--------------|
| [Self-Hosting](https://docs.lihor.ro/docs/self-hosting) | Canonical deployment and operations guide; [source](../website/docs/self-hosting/index.md). |
| [pr-previews.md](pr-previews.md) | PR preview deployments and the `stage.news.lihor.ro` demo backend: Helm values, operator runbook, security notes. |
| [a2a.md](a2a.md) | Opt-in A2A (Agent2Agent) endpoint exposing the assistant to external agents. |
| [knowledge-graph.md](knowledge-graph.md) | Neo4j knowledge graph architecture, data flow, backfill commands, and degraded behavior. |
| [learning-agent-roadmap.md](learning-agent-roadmap.md) | Lesson-first Learning Agent roadmap, child implementation slices, and AI generation guardrails. |
| [Python 3.15 compatibility report](python315-compatibility-2026-10-16.md) | Dated audit, platform evidence, reproduction commands and remaining migration gates; supported runtime remains Python 3.14. |
| [Python 3.15 development container](python315-devcontainer.md) | Build, open, rebuild and validate the isolated development environment. |
| [adr/](adr/README.md) | Architecture Decision Records — context and rationale behind significant technical decisions. |
| [User guide source](../website/docs/user-guide/index.md) | Canonical source for the [published end-user guide](https://docs.lihor.ro/docs/user-guide). |
