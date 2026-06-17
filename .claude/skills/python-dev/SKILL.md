---
name: python-dev
description: >-
  Standards and verification gate for writing Python in this repository. Use
  this skill ANY time you create or edit a .py file, add or change a Python
  dependency, write or fix a pytest test, or are about to commit/push Python
  changes — even for a "small" edit. It tells you how to write code that passes
  this project's ruff + mypy(strict) + ty + pyrefly + pytest gates the first
  time, how to keep dependencies and lockfiles clean, what test patterns to
  follow, and which project-specific gotchas (PostgreSQL-only, tz-aware
  datetimes, no print) will otherwise bite you. Triggers on: Python, .py,
  FastAPI, pytest, ruff, mypy, ty, pyrefly, type checker, backend changes,
  "run the backend tests", "why does the type check fail".
---

# Python development in this repo

The backend lives in `backend/news_dashboard/`, tests in `backend/tests/`. The
toolchain is already configured and strict — your job is to write code that
clears it on the first try, not to reinvent or relax it.

## 0. Detect before you act

Never assume commands. This repo standardizes entry points in the `Makefile` —
**prefer those**, they're what CI runs (`make check`). Confirm what exists:

```bash
ls Makefile pyproject.toml uv.lock 2>/dev/null   # what governs the project
grep -E '^(lint|typecheck|test|check|format|install):' Makefile
```

- If `make` targets exist (they do here): use `make lint`, `make typecheck`,
  `make test`, `make check`.
- If you're in a *different* project with no Makefile, fall back to the raw
  tools you find configured (`ruff`, `mypy`, `pytest`), and read
  [references/bootstrap.md](references/bootstrap.md) only when a project has
  **no** Python tooling at all and you're setting it up from scratch.

Run `pip install -e '.[dev]'` (or `make install`) once if the tools aren't importable.

## 1. While writing code — clear the gates by construction

The ruff rule set here is large (see `[tool.ruff.lint]` in `pyproject.toml`) and
**three** type checkers must all pass: `mypy` (strict, `warn_unreachable`), `ty`
(Astral), and `pyrefly` (Meta) — configured under `[tool.mypy]`, `[tool.ty]`,
and `[tool.pyrefly]`. They overlap but each catches things the others miss (e.g.
pyrefly flags possibly-unbound locals, ty flags LSP-violating overrides), so
write code that satisfies all three rather than the most lenient. The patterns
that trip agents most often, and how to avoid them:

- **Type everything.** Strict mypy means every function needs annotated params
  and return type; no implicit `Any`. Public modules ship types (`py.typed`).
  Use `X | None`, not `Optional[X]`; built-in generics (`list[str]`), not `List`.
- **No `print` in library code** (`T20`). Use the module logger. Log with
  `%`-style lazy args, not f-strings (`G`): `log.info("loaded %s", n)`.
- **Datetimes must be timezone-aware** (`DTZ`). Use `datetime.now(timezone.utc)`.
  Note the repo deliberately keeps `timezone.utc` over `UTC` (`UP017` ignored) —
  don't "modernize" it.
- **Errors:** raise with a message assigned to a variable first if it's long
  (`EM`/`TRY` rules); custom exceptions over bare `Exception`; don't `log.error`
  and re-raise the same thing.
- **Security (`S`/bandit):** no `assert` in runtime code, no `shell=True`, no
  hardcoded secrets, parameterize SQL. The repo allows `S608` only for SQL built
  from trusted literal identifiers — match that bar, don't widen it.
- **Comprehensions/simplify (`C4`/`SIM`/`RET`/`PERF`):** prefer the idiom ruff
  wants; when it flags, take the suggestion rather than `# noqa`.

When you genuinely must suppress a finding, scope it to the one tool and one
rule, with a reason: ruff → `# noqa: <CODE>`, mypy → `# type: ignore[<code>]`,
ty → `# ty: ignore[<rule>]`, pyrefly → `# pyrefly: ignore[<rule>]`. Prefer
fixing the code over suppressing; reserve ignores for genuine third-party or
tool limitations (e.g. ty mis-resolving psycopg's overloaded `connect`). Never a
blanket ignore, and never edit `pyproject.toml` to disable a rule to pass.

## 2. Project guardrails (don't regress these)

These are decisions encoded in config/`AGENTS.md` that an unaware edit will undo:

- **PostgreSQL only.** Runtime code uses PostgreSQL SQL + psycopg param style.
  Do **not** add SQLite fallbacks, db-type sniffing, or placeholder-translation
  layers. SQLite appears only in legacy import/migration tooling.
- **Ruff `target-version = py313`** on a `requires-python >=3.14` project is
  intentional (avoids PEP 758 rewrites mypy can't parse). Leave it.
- **Lazy imports are deliberate** (`PLC0415` ignored) for optional deps / startup
  cost / cycles — keep them where they are.
- Config files (`pyproject.toml`, `.pre-commit-config.yaml`) are not yours to
  loosen to pass checks. If a rule seems wrong, raise it; don't silently flip it.

## 3. Tests — author them to this project's style

- Framework is **pytest** with `flake8-pytest-style` (`PT`) enforced. Use
  `pytest.raises`, parametrize with `@pytest.mark.parametrize`, name fixtures
  clearly. `assert` is allowed in tests (per-file ignore), not in app code.
- **Postgres in tests:** the suite uses `testcontainers[postgres]` but can also
  hit a local Docker Postgres directly. Credentials live in `.env` at the project
  root — **load it before running tests**:
  ```bash
  source .env && make test
  # or, if dotenv-cli is installed:
  dotenv make test
  ```
  `.env` sets `TEST_DATABASE_URL` (and `DATABASE_URL`) to the local Docker
  Postgres (`postgresql://news_dashboard:…@localhost:55432/news_dashboard_test`).
  When `TEST_DATABASE_URL` is present, `conftest.py` uses it directly instead of
  spinning a container — so tests run faster and never skip on Docker availability.
  Don't mock the DB into a fake; use the `pg_clean` fixture from `conftest.py`
  (gives a fresh-truncated Postgres URL per test). Read a neighbour test before
  writing a new one.
- **All tests must use Postgres.** The codebase is Postgres-only; SQLite
  `tmp_path` fixtures are no longer valid. Convert any `tmp_db` / `db_path`
  fixture to `pg_clean` and pass `database_url=pg_clean` to functions.
  Monkeypatching `DB_PATH` is also obsolete — patch `DATABASE_URL` env var or
  pass `database_url=` explicitly.
- **No live network.** Stub `httpx`/feed fetches; tests must pass offline.
  `filterwarnings = error` for the package's own DeprecationWarnings — don't
  introduce deprecated calls.
- Put a test next to the behavior you changed. A bug fix without a regression
  test is incomplete.

## 4. Dependencies — keep them clean

- Add deps by editing `pyproject.toml` (`dependencies` or the `dev` extra) and
  keeping `uv.lock` in sync (`uv lock`), or `uv add <pkg>` if uv is your driver.
  Don't `pip install` into the env and forget the manifest.
- Pin sanely (`>=` floors, as the repo does); avoid unpinned/`latest`.
- For third-party packages without type stubs, add a targeted
  `[[tool.mypy.overrides]]` with `ignore_missing_imports = true` (see existing
  feedparser/apscheduler entries) — scoped to that module only.
- Check new/updated deps for known CVEs (`pip-audit` / `uv pip audit`) and flag
  anything serious rather than pulling it in silently.

## 5. Before you say "done" — run the gate

Do not report success on unverified code. Run, in order, and fix until clean:

```bash
make lint                  # ruff check + ruff format --check
make typecheck             # mypy strict
source .env && make test   # pytest --cov (needs Postgres from .env)
```

`make format` auto-fixes lint/format issues. Quote the real output when
reporting results; if something fails, say so — don't claim green on red.

## 6. Before pushing

`make test` must pass before any push — tests are **not** in the pre-commit
hook (too slow), so they're the easy thing to skip. A `pre-push` git hook backs
this up (`pre-commit install --hook-type pre-push`); if the hook isn't installed
in this clone, run the tests manually. Never `--no-verify` past a failing gate.
