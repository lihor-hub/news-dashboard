---
name: repair-pr
description: >-
  Use when an existing pull request must be diagnosed, rebased, repaired,
  pushed, brought through CI, queued, or merged, including prompts such as fix
  this PR, rebase on main, fix CI, push back, CI pass, or merge.
---

# Repair a Pull Request

Take one existing PR from its current state to the user-authorized terminal state without widening its intent.

**REQUIRED SUB-SKILL:** Use agent-delivery-contract.
**REQUIRED SUB-SKILL:** Use the relevant language development skill when files change.

## Workflow

1. Read the PR description, issue, diff, review threads, checks, base/head refs, and repository instructions. Record the authorized terminal state: pushed, CI-green, queued, or merged.
2. Fetch current refs and attach the worktree to the PR branch. Confirm the remote tip before editing.
3. Diagnose before changing code. Reproduce the smallest failing check and distinguish failures caused by the PR or required rebase from unrelated or infrastructure failures.
4. Rebase onto current `origin/main` when required. Resolve conflicts by preserving the PR’s intent and current base behavior. Never merge `main` into the branch when repository policy requires rebase.
5. Write a regression test first for a code defect. Make the smallest causally scoped repair, then run proportional verification and mandatory gates.
6. Fetch and rebase again immediately before pushing. If history changed, push only with `--force-with-lease` against the observed remote tip; never use an unguarded force push.
7. Watch all required checks. Fix failures caused by the PR. For an unrelated failure, collect the check, run, logs, and evidence of non-causality; do not modify unrelated code.
8. If authorized, enable the repository’s normal merge method or merge queue only after required checks satisfy policy. Never use an admin bypass.
9. Confirm the requested terminal state from GitHub. For a merge, query PR state and `mergedAt`, confirm the linked issue state when applicable, and verify branch cleanup policy.

## Infrastructure failures

Retry safe transient infrastructure failures with bounded attempts. If runners, credentials, external services, or policy remain blocked, leave the PR recoverable and report the exact failing check, evidence, attempts, and smallest next action. Pending is not passing.

## Quick reference

| Situation | Action |
|---|---|
| Remote branch changed | Stop; fetch and reassess before any lease push |
| Rebase rewrote history | Use `--force-with-lease` |
| Failure is caused by the PR | Test-first repair and re-run affected gates |
| Failure is unrelated | Prove and report; do not absorb |
| Merge was not authorized | Stop after the requested pushed/green state |
| Merge queue is authorized | Queue normally, then confirm the actual merge |

## Milestone reporting

Report only diagnosis, repair ready, local gates, push, actionable CI result, queue entry, merge, or blocker. Do not emit unchanged polling updates.
