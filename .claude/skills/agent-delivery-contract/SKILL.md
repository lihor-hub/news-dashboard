---
name: agent-delivery-contract
description: >-
  Use when work may edit files, push branches, open or update pull requests,
  wait for CI, merge changes, or modify issue state, especially when the prompt
  is terse or says AFK, take to completion, fix and merge, or do not stop.
---

# Agent Delivery Contract

Convert a terse request into an explicit contract before mutation. Infer routine mechanics from repository instructions; never infer broader authority.

## Delivery brief

State these fields in the first milestone update. Keep them compact; do not ask for confirmation when repository policy or the request answers them.

| Field | Required content |
|---|---|
| Target | Repository plus issue, PR, branch, or artifact |
| Outcome | Concrete result, not activity |
| Scope | Allowed changes and behavior that must remain stable |
| Authority | Whether edit, commit, push, comment, open PR, queue, or merge is authorized |
| Terminal state | Exact state at which work is complete |
| Verification | Focused checks, repository gates, and required checks in CI |
| Failure policy | When to repair, retry, stop, or request new authority |

User instructions override repository defaults. A terminal phrase such as “finish” grants persistence, not new authority.

## Execution contract

1. Preserve user work and inspect current state before changing it.
2. Keep the change causally scoped to the requested outcome. Separate unrelated work.
3. Use proportional verification: reproduce or test the narrow behavior first, then affected-area checks, then mandatory repository gates. Run broader suites when policy or cross-cutting risk requires them.
4. Treat required checks as authoritative. Never bypass hooks, branch protection, security gates, or the merge queue.
5. Make completion claims only from fresh evidence: command exit status, CI result, PR state, or external-system response observed in the current run.

## Failure policy

- Fix failures caused by the requested change, its branch, or a required rebase.
- Investigate unrelated failures enough to prove they are unrelated; do not absorb them without authority.
- Retry transient infrastructure failures only when the retry is safe and bounded.
- When credentials, external coordination, policy, or expanded scope are required, stop at the safest recoverable state and name the smallest user action needed.
- Never report a pending check as passed or an opened PR as merged.

## Communication contract

Report state transitions and decisions only: diagnosis, scope change, implementation ready, verification result, push/PR, actionable CI failure, queue entry, merge, or blocker. Do not narrate unchanged polling, percentages, quiet intervals, or repeated “still running” status.

The final report contains: outcome and links; changed behavior; verification evidence; final branch/PR/issue state; and any residual risk or required follow-up.

## Red flags

- “The user said finish, so I may merge.”
- “Most checks passed, so this is done.”
- “This nearby cleanup is convenient.”
- “I should send another unchanged polling update.”

Each red flag means: return to the delivery brief and follow its explicit authority, Terminal state, Verification, and Failure policy.
