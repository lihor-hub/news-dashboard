# Bootstrapping TypeScript tooling in a project that has none

Read this only when a project has **no** frontend lint/type/test setup and
you've been asked to establish one. If config already exists, follow it — don't
overwrite a working setup.

Target stack (what this repo proved out): **ESLint flat config** with
`typescript-eslint` + `react-hooks` + `react-refresh`, **Prettier**, **strict
`tsc`** with project references, **vitest** + Testing Library for units,
**Playwright** for e2e.

## tsconfig

Enable strictness from day one:

```jsonc
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "moduleResolution": "bundler"
  }
}
```

## package.json scripts

```jsonc
{
  "typecheck": "tsc -b --noEmit",
  "lint": "eslint . --max-warnings 0",
  "lint:fix": "eslint . --fix",
  "format": "prettier --write src",
  "format:check": "prettier --check src",
  "test": "vitest run",
  "test:coverage": "vitest run --coverage"
}
```

`--max-warnings 0` is the point: it makes warnings block CI, so they get fixed
instead of accumulating.

## ESLint flat config

Compose `@eslint/js` recommended + `typescript-eslint` recommended +
`eslint-plugin-react-hooks` + `eslint-plugin-react-refresh`, and put
`eslint-config-prettier` **last** so Prettier owns formatting.

## pre-commit + pre-push

Run eslint, prettier `--check`, and tsc as local `system` hooks on commit; run
the test suite at the **pre-push** stage so tests gate the push without slowing
commits:

```yaml
  - repo: local
    hooks:
      - id: vitest
        name: vitest
        entry: npm run test --silent
        language: system
        files: \.(ts|tsx)$
        pass_filenames: false
        stages: [pre-push]
```

Install both hook types:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Start strict and relax only with reason — loosening later is cheap, retrofitting
types and tests onto a loose codebase is not.
