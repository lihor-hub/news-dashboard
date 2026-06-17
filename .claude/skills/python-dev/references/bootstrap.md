# Bootstrapping Python tooling in a project that has none

Read this only when a project has **no** Python lint/type/test setup and you've
been asked to establish one. If config already exists, follow it instead — do
not overwrite a working setup.

The target is the same stack this repo proved out: **ruff** (lint + format),
**mypy strict**, **pytest** (+ coverage), wired through **pre-commit** and a
`Makefile`, with **uv** for locking.

## Minimum `pyproject.toml`

```toml
[tool.ruff]
line-length = 100
src = ["src"]            # adjust to the package root

[tool.ruff.lint]
select = ["E","W","F","I","N","UP","B","A","C4","DTZ","EM","G","ISC","PIE",
          "PT","RET","RSE","S","SIM","T20","ARG","PERF","PL","RUF","TRY"]
ignore = ["ISC001"]      # conflicts with the formatter

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "PLR0915"]   # asserts + long tests are fine in tests

[tool.mypy]
strict = true
warn_unreachable = true
pretty = true

[tool.pytest.ini_options]
addopts = "-ra --strict-markers --strict-config"
testpaths = ["tests"]

[tool.coverage.run]
branch = true
```

## pre-commit + pre-push

Put ruff (with `--fix`) and ruff-format as managed hooks, and mypy as a local
`system` hook. Add a **pre-push** stage that runs the test suite so tests gate
the push without slowing every commit:

```yaml
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        stages: [pre-push]
```

Install both hook types:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Makefile entry points

Mirror this repo's `make lint` / `typecheck` / `test` / `check` so humans and
CI share one path. `check` should chain `lint typecheck test`.

Tune ruff/mypy strictness to the team's appetite, but start strict — relaxing
later is easy; retrofitting types onto a loose codebase is not.
