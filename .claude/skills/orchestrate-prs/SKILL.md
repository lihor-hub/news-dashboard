---
name: orchestrate-prs
description: >-
  Use when two or more pull requests must be rebased, repaired, validated,
  queued, merged, drained, or coordinated as a set, especially for prompts such
  as take all open PRs, merge every PR, drain the PR queue, or orchestrate PRs.
---

# Orchestrate Pull Requests

Treat a PR set as a moving dependency graph, not a flat batch. Optimize for correct merges, not maximum simultaneous activity.

**REQUIRED SUB-SKILL:** Use agent-delivery-contract for fleet authority and terminal state.
**REQUIRED SUB-SKILL:** Use repair-pr independently for each selected PR.

## Inventory before execution

Build a status table with PR, intent, head/base, draft state, mergeability, required checks, review state, dependencies, labels, and overlapping files. Exclude PRs outside the user’s scope and identify changes already superseded by another PR.

Classify relationships:

- **Independent:** no dependency, shared migration, generated artifact, or overlapping files.
- **Ordered:** one PR depends on or should precede another.
- **Conflicting:** both change the same behavior or files and cannot retain trustworthy CI simultaneously.

State the proposed order before mutation. Use bounded concurrency only for independent diagnosis or repair; always serialize rebases, queue entry, and merges whenever PRs overlap or each merge changes the base relevant to the next PR.

## Execution loop

1. Select the next safe wave from current `origin/main`.
2. Run `repair-pr` for each selected PR to the authorized intermediate state.
3. Queue or merge only PRs whose current head has passed all required checks against the current eligible base.
4. After every merge, fetch `origin/main`. Re-evaluate every remaining PR’s dependency, overlap, mergeability, and CI validity before continuing.
5. Remove merged, closed, superseded, or newly blocked PRs from the active wave. Never rely on the initial inventory after main moves.

CI from a pre-rebase commit or obsolete base is evidence for that commit only. Do not call the fleet green because each PR was green at a different stale point in time.

## Failure and concurrency policy

- One blocked PR does not block independent PRs.
- A blocked prerequisite blocks only its dependent chain.
- Do not resolve the same conflict independently in multiple PRs; establish the canonical order first.
- Keep concurrency below repository, runner, and human-review limits. “All PRs” grants scope, not unlimited parallelism or merge authority.
- Apply the shared failure policy separately to every PR and to the fleet terminal state.

## Reporting

Maintain one compact status table with states such as discovered, diagnosing, repairing, pushed, CI, queued, merged, blocked, or skipped. Update it only on state transitions. The final report lists merged PRs, remaining PRs with precise blockers, and whether the requested fleet terminal state was reached.
