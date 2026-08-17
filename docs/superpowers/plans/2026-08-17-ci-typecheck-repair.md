# CI Typecheck Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current dependency graph pass backend type checking without removing behavioral coverage.

**Architecture:** CI will use `uv sync --frozen --all-extras`, the same locked dependency graph used by local worktree bootstrap. This prevents a runner from resolving newer Python packages than the repository has tested. CI lanes remain unless their commands and PR inputs are identical to an existing required lane.

**Tech Stack:** Python 3.14, pytest, mypy, OpenAI SDK, A2A SDK, GitHub Actions.

## Global Constraints

- Keep PostgreSQL-only runtime behavior unchanged.
- Do not loosen type-checker configuration or delete behavioral tests to make the check pass.
- Remove a CI lane only with evidence that an existing required lane runs the same command on the same inputs.

---

### Task 1: Make CI honor `uv.lock`

**Files:**
- Modify: `.github/workflows/ci.yml:91-210`
- Create: `scripts/test_ci_python_lock.py`

**Interfaces:**
- Consumes: the committed `uv.lock` dependency graph.
- Produces: deterministic Python environments for all CI jobs in `ci.yml`.

- [ ] **Step 1: Write the failing CI workflow regression test**

Run: `pytest scripts/test_ci_python_lock.py -q`

Expected: FAIL because CI invokes `pip install -e '.[dev]'` instead of `uv sync --frozen --all-extras`.

- [ ] **Step 2: Replace unpinned CI installs with locked `uv` installs**

Add the pinned `astral-sh/setup-uv` action after Python setup in each CI Python job, remove the unused pip cache configuration, and run `uv sync --frozen --all-extras`.

- [ ] **Step 3: Verify the repaired type check and regression test**

Run: `pytest scripts/test_ci_python_lock.py -q` and `make typecheck`.

Expected: no type errors and a passing CI workflow regression test.

- [ ] **Step 4: Commit the focused repair**

```bash
git add .github/workflows/ci.yml scripts/test_ci_python_lock.py
git commit -m "fix: use locked Python dependencies in CI"
```

### Task 2: Prove or retain CI lanes

**Files:**
- Inspect: `.github/workflows/ci.yml`
- Inspect: `scripts/smoke-mcp-container.sh`

**Interfaces:**
- Consumes: the workflow event and path filters.
- Produces: a minimal CI graph that preserves unique required coverage.

- [ ] **Step 1: Collect MCP smoke failure logs and reproduce its command**

Run: `gh run view 31990493265 --job 95273024712 --log-failed` and `scripts/smoke-mcp-container.sh`.

Expected: identify whether the failure is a current deterministic defect or external/transient.

- [ ] **Step 2: Compare every candidate lane's command and trigger inputs**

Verify that a proposed removal has an identical command and event/path coverage in a required lane. Retain lanes that cover a different tool, environment, input filter, or merge-queue event.

- [ ] **Step 3: Verify required local and GitHub gates**

Run `make lint`, `make typecheck`, selected tests, and relevant frontend gates when workflow files change. Push the branch and confirm the PR's required checks pass.
