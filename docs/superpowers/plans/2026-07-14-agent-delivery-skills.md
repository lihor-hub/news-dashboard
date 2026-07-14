# Agent Delivery Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make terse delivery prompts reliably inherit explicit authority, completion, failure, verification, communication, and concurrency rules.

**Architecture:** A concise `agent-delivery-contract` skill owns rules shared by delivery workflows. `repair-pr` and `orchestrate-prs` apply that contract to single-PR and fleet operations, while `tdd-ship` references it instead of duplicating policy. Repository tests treat representative pressure scenarios as executable content contracts.

**Tech Stack:** Markdown agent skills, Python 3.14, pytest, pathlib.

## Global Constraints

- Keep `.agents/skills` as a symlink to `.claude/skills`; never duplicate skills.
- Keep each skill focused and discoverable through a trigger-only description.
- Report only state transitions and decisions, not unchanged polling.
- Never bypass required checks or the merge queue.
- Use proportional local verification and preserve fresh evidence before completion claims.

---

### Task 1: Shared delivery contract

**Files:**
- Create: `.claude/skills/agent-delivery-contract/SKILL.md`
- Modify: `scripts/test_agent_skill_sync.py`

**Interfaces:**
- Consumes: user scope, repository instructions, and workflow-specific authority.
- Produces: a normalized delivery brief and shared execution/reporting policy.

- [ ] Add failing contract tests for authority, terminal state, failure policy, proportional verification, and milestone reporting.
- [ ] Run `pytest scripts/test_agent_skill_sync.py -q` and confirm failure because the skill is absent.
- [ ] Add the minimal skill content satisfying the pressure contracts.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Single-PR repair workflow

**Files:**
- Create: `.claude/skills/repair-pr/SKILL.md`
- Modify: `.claude/skills/tdd-ship/SKILL.md`
- Modify: `scripts/test_agent_skill_sync.py`

**Interfaces:**
- Consumes: one existing PR and `agent-delivery-contract`.
- Produces: a rebased, diagnosed, verified PR in the user-authorized terminal state.

- [ ] Add failing tests for lease-protected rebases, causality-scoped fixes, required CI, merge queue behavior, and post-merge confirmation.
- [ ] Run the focused test and confirm failure because the workflow is absent.
- [ ] Create `repair-pr` and make `tdd-ship` require the shared contract.
- [ ] Re-run the focused test and confirm it passes.

### Task 3: Multi-PR orchestration and shipment

**Files:**
- Create: `.claude/skills/orchestrate-prs/SKILL.md`
- Modify: `scripts/test_agent_skill_sync.py`

**Interfaces:**
- Consumes: a PR set and `repair-pr`.
- Produces: a dependency-aware execution order with conflicting PRs serialized and state re-evaluated after each merge.

- [ ] Add failing tests for inventory, overlap detection, serialization, bounded concurrency, re-evaluation, and compact status reporting.
- [ ] Run the focused test and confirm failure because the workflow is absent.
- [ ] Add the orchestration skill and close wording loopholes found by the tests.
- [ ] Run focused tests, lint, typecheck, and the repository-required test gate.
- [ ] Review, rebase, push, open a PR closing #1221, enable auto-merge only if authorized by the requested terminal state, and report evidence.
