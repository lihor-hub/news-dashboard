---
name: typescript-dev
description: >-
  TypeScript/React standards and verification gate for this repo. Use when
  editing .ts/.tsx files, Vite/ESLint/tsconfig, npm dependencies, frontend tests,
  or investigating eslint, prettier, tsc, vitest, Playwright, or build failures.
---

# TypeScript development in this repo

The frontend is React + Vite + Tailwind in `frontend/src/`. Unit tests use
vitest + Testing Library; end-to-end tests use Playwright in `e2e/`.

## 0. Detect before you act

Prefer `npm` scripts and `make` targets; they are what CI runs. Confirm what exists:

```bash
cat package.json | sed -n '/"scripts"/,/}/p'
grep -E '^(lint|typecheck|test|check):' Makefile 2>/dev/null
```

Key scripts here: `lint`, `lint:fix`, `format`, `format:check`, `typecheck`
(`tsc -b --noEmit`), `build` (`tsc -b && vite build`), `test:frontend`
(`vitest run`). At repo level, `make lint typecheck test` covers both stacks.

Run `npm install` if `node_modules` is stale. If you're in a *different* project
with no frontend tooling at all, read
[references/bootstrap.md](references/bootstrap.md).

## 1. While writing code — clear the gates by construction

ESLint uses `--max-warnings 0`; a warning is a failure. `tsc` is strict. Common
traps:

- **No `any`.** Type props, hooks, and API payloads. Prefer `unknown` + a
  narrowing check over `any`; derive types from Zod/response shapes where they
  exist rather than hand-rolling drift.
- **Rules of Hooks** (`react-hooks`): hooks at top level only; complete
  dependency arrays in `useEffect`/`useMemo`/`useCallback`. Don't silence the
  exhaustive-deps warning — fix the dependency or restructure.
- **react-refresh:** a component file should export only components (move
  constants/helpers out) so fast-refresh stays intact.
- **No stray `console.log`** in committed code; remove debugging output.
- **Prettier owns formatting** (`eslint-config-prettier` disables conflicting
  lint rules). Don't hand-format — run `npm run format`.
- Honor `.prettierrc.json` / `.editorconfig`; don't override style inline.

When a rule genuinely doesn't apply, use
`// eslint-disable-next-line <rule> -- reason`. Never file-disable or loosen
`eslint.config.mjs`/`tsconfig.json` to pass.

## 2. Project guardrails (don't regress these)

- This is a **PWA** (`vite-plugin-pwa`) with a generated service worker and a
  `manifest.webmanifest`. Be careful with caching/offline behavior; don't break
  the SW registration or asset precaching.
- The app is served as an SPA behind the backend (`test_spa_static.py` asserts
  this) — keep client routing and the built asset paths consistent.
- UI primitives in `frontend/src/components/ui/*` follow the shadcn/Radix
  pattern. Reuse and extend them; don't fork a one-off button.
- `tsconfig`/`eslint`/`vite` config encode deliberate choices — raise issues
  rather than loosening them to go green.

## 3. Tests — unit vs e2e, and how to write each

Choose the cheapest test that proves the behavior:

- **vitest + Testing Library** (`*.test.tsx` near the component) for component
  logic, hooks, rendering, and state. Query by role/text like a user; assert on
  behavior, not implementation. `happy-dom`/`jsdom` are configured — no real
  browser needed. Use `@testing-library/user-event` for interaction.
- **Playwright** (`e2e/*.spec.ts`) only for real cross-page flows: navigation,
  keyboard shortcuts, command palette, PWA, auth — things unit tests can't cover.
  These are slower; don't push pure component logic into e2e.
- Mock network at the boundary (don't hit live services); a fix without a test
  for the regression is incomplete. Read a neighboring test before writing a new
  one to match fixtures and conventions.

## 4. Dependencies — keep them clean

- Add deps with `npm install <pkg>` (or `-D` for dev) so `package.json` **and**
  `package-lock.json` update together; commit both. Don't hand-edit versions and
  leave the lockfile stale.
- Avoid `"latest"` for new deps — pin a caret range like the rest. (Some
  existing entries use `latest`; don't add more.)
- Run `npm audit` on dependency changes and flag serious CVEs instead of
  pulling them in silently. Prefer adding to an existing Radix/utility rather
  than introducing a redundant library.

## 5. Before you say "done" — run the gate

Do not report success on unverified code. Run, in order, and fix until clean:

```bash
npm run lint            # eslint --max-warnings 0
npm run format:check    # prettier
npm run typecheck       # tsc -b --noEmit
npm run test:frontend   # vitest run
npm run build           # tsc -b && vite build  (catches build-only breakage)
```

`npm run lint:fix` and `npm run format` auto-fix the first two. Quote real
output when reporting; if it fails, say so — don't claim green on red.

## 6. Before pushing

The full frontend test suite (`npm run test:frontend`) plus `npm run build`
must pass before any push. Tests are **not** in the pre-commit hook (too slow),
so a `pre-push` git hook backs this up
(`pre-commit install --hook-type pre-push`); if it isn't installed in this
clone, run them manually. Playwright e2e is heavier — run it when you touched
flows it covers or before a release. Never `--no-verify` past a failing gate.
