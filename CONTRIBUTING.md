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

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add OPML export button to SourcesPage
fix: correct infinite-query snapshot in triage mutations
docs: add PRIVACY.md data-flow transparency
chore: upgrade vite to 6.x
```

Prefixes: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`, `refactor:`.

## Git workflow

- **Rebase on `origin/main`** before pushing. Resolve divergence by rebasing, not merging.
- **Do not use `git push --no-verify`** — pre-push hooks exist for a reason.
- Keep working branches fast-forwardable with `origin/main`.

## PostgreSQL-only runtime rule

Runtime database code **must** use PostgreSQL-specific SQL and `psycopg` parameter style (`%s` placeholders). Do not add SQLite runtime fallbacks, database-type sniffing, placeholder translation layers, or generic multi-database SQL.

SQLite may appear only in legacy import/migration tooling that reads an old SQLite database and writes into PostgreSQL.

## Opening a PR

1. Fork the repo and create a feature branch.
2. Make your changes, add tests.
3. Run `make check` — all targets must pass.
4. Open a PR with a Conventional Commit title and a clear description.
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
