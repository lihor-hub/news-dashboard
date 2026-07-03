---
name: drain-backlog
description: >-
  Drain the ready-for-agent GitHub issue backlog: claim the oldest unclaimed
  issue, ship it through tdd-ship, label the outcome, repeat.
disable-model-invocation: true
---

# Drain the AFK backlog

Work the `ready-for-agent` queue one issue at a time until it is empty or
every remaining issue is blocked. `report-issue` produces this queue; you are
the consumer.

## The loop

### 1. Claim

List the open backlog, oldest first:

```bash
gh issue list --label ready-for-agent --state open \
  --json number,title,labels,createdAt --jq 'sort_by(.createdAt)'
```

Skip issues carrying any `agent-taken-*` label (another agent owns them) or
`agent-blocked`. Claim the oldest remaining one:

```bash
gh issue edit <n> --add-label agent-taken-claude
```

Completion: exactly one issue is claimed by you, or the list is empty and you
report the drain finished.

### 2. Ship

Run `tdd-ship` against the claimed issue. The issue body is the spec — a
`ready-for-agent` issue is contractually implementable cold, so do not
re-litigate its scope. The issue already exists, so don't file a new one; use
its number for the branch name and the `Closes #<n>` line.

If the spec turns out **not** to be implementable cold (missing context, a
product decision, broken file references), do not guess: comment on the issue
stating exactly what is missing, label it `agent-blocked`, remove
`agent-taken-claude`, and move on.

Completion: the PR merged and the issue auto-closed, or the issue is labelled
`agent-blocked` with a comment explaining why.

### 3. Close out

On a merged PR, mark the issue `agent-done`:

```bash
gh issue edit <n> --add-label agent-done --remove-label agent-taken-claude
```

### 4. Repeat

Return to step 1. Stop only when no unclaimed, unblocked `ready-for-agent`
issues remain. Then report a summary: issues shipped (with PR links), issues
blocked (with reasons).

## Guardrails

- **One issue in flight at a time.** A merged PR or an `agent-blocked` comment
  is the only exit from step 2.
- **Never take** issues labelled `ready-for-human` or claimed via
  `agent-taken-*`.
- **Every claimed issue ends labelled** — `agent-done` or `agent-blocked`,
  never silently abandoned with a stale claim.
- For long drains, pace the loop with `/loop` rather than grinding a single
  context window to exhaustion.
