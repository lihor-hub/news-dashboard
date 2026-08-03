# Documentation index

Technical documentation for News Dashboard. For end-user documentation (how to
use the app day to day), see the [User Guide](user-guide/README.md) instead.

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
| [SELF_HOSTING.md](SELF_HOSTING.md) | Running your own instance of News Dashboard. |
| [a2a.md](a2a.md) | Opt-in A2A (Agent2Agent) endpoint exposing the assistant to external agents. |
| [knowledge-graph.md](knowledge-graph.md) | Neo4j knowledge graph architecture, data flow, backfill commands, and degraded behavior. |
| [learning-agent-roadmap.md](learning-agent-roadmap.md) | Lesson-first Learning Agent roadmap, child implementation slices, and AI generation guardrails. |
| [adr/](adr/README.md) | Architecture Decision Records — context and rationale behind significant technical decisions. |
| [user-guide/](user-guide/README.md) | Markdown mirror of the end-user guide; the published version lives at [docs.lihor.ro/docs/user-guide](https://docs.lihor.ro/docs/user-guide). |
