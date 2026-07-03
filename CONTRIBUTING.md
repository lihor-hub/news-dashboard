# Contributing to News Dashboard

Thanks for your interest! This guide covers how to set up, make changes, and land your first PR.

By participating in this project, you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Quick links

- **[Good first issues](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22good+first+issue%22)** — beginner-friendly tasks you can pick up cold.
- **[Help wanted](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22help+wanted%22)** — issues the maintainers would love help with.
- **[docs.lihor.ro](https://docs.lihor.ro)** — the published documentation site (source in `website/`, preview with `cd website && npm install && npm run start`).
- **[GOVERNANCE.md](GOVERNANCE.md)** — how decisions are made and how releases ship.
- **[MAINTAINERS.md](MAINTAINERS.md)** — who maintains this project and how to become one.
- **[ROADMAP.md](ROADMAP.md)** — near-term direction and how to propose roadmap items.

## Where to start

Not sure which part of the codebase to touch? Here is a quick map:

| I want to… | Where to look |
|---|---|
| Add a new feed source or scraper | `backend/news_dashboard/ingest/` |
| Work on the UI / React components | `frontend/src/` |
| Add or improve translations (i18n) | `frontend/src/locales/` |
| Write or fix backend tests | `backend/tests/` |
| Improve Helm or Docker packaging | `helm/`, `Dockerfile`, `docker-compose.yml` |
| Fix or expand the documentation | `website/docs/` |
| Improve CI or GitHub Actions | `.github/workflows/` |
| Work on the Android or desktop app | `android/`, `desktop/` |

For deeper orientation, see the [Architecture Decision Records](docs/adr/) and the [Project Layout](README.md#project-layout) in the README.

## Prerequisites

- Python 3.14+
- Node.js LTS
- PostgreSQL 16+
- A running PostgreSQL instance (see the local-dev section in the README)

## Development setup

The README covers the full local-development setup, configuration, and quality-check commands — start there:

→ [README — Local Development](README.md#local-development)

Tip: you can also use a pre-configured **Dev Container** or **GitHub Codespace** (see README) to skip manual setup.

## The `make check` gate

Before opening a PR, run the full quality gate:

```bash
make check
```

This runs lint, format check, type checking, and the test suites. CI runs the same checks — if `make check` passes locally, your PR will be green.

### Individual targets

| Target | What it does |
|---|---|
| `make lint` | Lint backend (ruff) + frontend (eslint) |
| `make format` | Auto-format everything |
| `make typecheck` | Static type checks (mypy, tsc) |
| `make test` | Backend (pytest) + frontend (vitest) unit tests |
| `make test-smoke` | Fast smoke tests |
| `make test-e2e` | End-to-end tests (Playwright) |
| `make helm-validate` | Lint and render the Helm chart |

## Commit conventions

Use either [Conventional Commits](https://www.conventionalcommits.org/) or
[Scoped Commits](https://scopedcommits.com/). Pick the style that best
communicates the change.

Conventional Commits use `<type>: <description>` or
`<type>(<scope>): <description>`:

```
feat: add OPML export button to SourcesPage
fix(api): handle missing source IDs
fix: correct infinite-query snapshot in triage mutations
docs: add PRIVACY.md data-flow transparency
chore: upgrade vite to 6.x
```

Scoped Commits use `<scope>: <description>`:

```
sources: add OPML export button
api: handle missing source IDs
docs: clarify local setup
```

Common Conventional Commit prefixes include `feat:`, `fix:`, `docs:`,
`chore:`, `ci:`, `test:`, and `refactor:`.

## Git workflow

- **Rebase on `origin/main`** before pushing. Resolve divergence by rebasing, not merging.
- **Do not use `git push --no-verify`** — pre-push hooks exist for a reason.
- Keep working branches fast-forwardable with `origin/main`.

## PostgreSQL-only runtime rule

Runtime database code **must** use PostgreSQL-specific SQL and `psycopg` parameter style (`%s` placeholders). Do not add SQLite runtime fallbacks, database-type sniffing, placeholder translation layers, or generic multi-database SQL.

SQLite may appear only in legacy import/migration tooling that reads an old SQLite database and writes into PostgreSQL.

## Versioning

The `VERSION` file at the repo root is the **single source of truth** for the app version:

- It is derived from git tags by `scripts/next_version.sh` and baked into the release image — it is intentionally **not** committed with a bumped value between releases (see `release.yml`).
- `pyproject.toml`'s `version` field is kept in sync with `VERSION` at release time.
- The backend reads `VERSION` once at startup (`news_dashboard.main._read_app_version`) and uses it for the FastAPI `app.version`, which in turn drives both the OpenAPI `info.version` (`/docs`) and the `/api/version` endpoint.

Don't hardcode a version literal anywhere else — read `VERSION` (or `app.version` at runtime) instead, so these values can't drift apart again.

## Opening a PR

1. Fork the repo and create a feature branch.
2. Make your changes, add tests.
3. Run `make check` — all targets must pass.
4. Open a PR with a Conventional Commit or Scoped Commit title and a clear description.
5. Link any related issue (`Closes #123`).

## Internationalization (i18n)

This project uses `react-i18next` for internationalization. All user-facing strings should be externalized for translation.

### Adding new translatable strings

1. Add a new key-value pair to `frontend/src/locales/en/translation.json`
   - Use descriptive, nested keys (e.g., `feature.action.label`)
   - Keep values concise and avoid concatenation
   - Use printf-style placeholders for dynamic values: `Hello {{name}}, you have {{count}} messages`

2. Use the `useTranslation` hook in your component:
   ```tsx
   import { useTranslation } from 'react-i18next';

   function MyComponent() {
     const { t } = useTranslation();
     return <button>{t('button.save')}</button>;
   }
   ```

3. For components without hooks, use the `Trans` component or `withTranslation` HOC

### Development

- The default language is English (`en`)
- To test other languages, you can temporarily change the lng in `src/lib/i18n.ts`
- Run `npm run test:frontend` to ensure translations work correctly

### Key organization

- Group related keys under common namespaces
- Use consistent naming: `feature.action.state`
- Keep keys short but descriptive
- Avoid duplicating similar strings

Good first issues often include adding new UI strings following this pattern.

## Good first issues

New to the project? Browse issues labeled [`good first issue`](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22good+first+issue%22) — these are small, well-scoped tasks that don't require deep codebase context. Each one has clear acceptance criteria so you can start immediately.

If you're unsure which to pick, leave a comment on the issue and a maintainer will help you get started.
