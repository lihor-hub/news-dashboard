---
name: drain-backlog
description: >-
  Drain the ready-for-agent GitHub issue backlog: claim the oldest unclaimed
  issue via the lock-branch protocol, ship it through tdd-ship, label the
  outcome, repeat.
disable-model-invocation: true
---

# Drain the AFK backlog

Work the `ready-for-agent` queue one issue at a time until it is empty or
every remaining issue is blocked. `report-issue` produces this queue; you are
the consumer. Multiple agents (claude, codex, antigravity) consume it
concurrently, so claims go through remote lock branches, not labels alone.
Your agent name in a Claude Code session is `claude`.

## The loop

### 0. Resume your own abandoned work first

Sessions die mid-run (limits, crashes) and leave valid work behind. Before
claiming anything new, check for a previous claim of yours:

```bash
gh issue list --label agent-taken-claude --state open --json number,title
```

If one exists, resume it: find its branch/PR (`gh pr list --author @me`,
`git ls-remote --heads origin 'agent-lock/*'`), finish the ship step, and
close it out. Only when nothing of yours is pending do you claim fresh work.

### 1. Pick a candidate

List the open backlog:

```bash
gh issue list --label ready-for-agent --state open \
  --json number,title,labels,createdAt --jq 'sort_by(.createdAt)'
```

Order candidates by `priority-critical` > `priority-high` > `priority-medium`
> `priority-low`, then oldest first. Skip issues labelled `agent-blocked`,
`ready-for-human`, or carrying any `agent-taken-*` label — unless the claim
is stale (see step 2).

### 2. Acquire the lock

Before any worktree, branch, or code change, take the exclusive remote lock
by creating this branch from the current `main` commit. Use the refs API —
it fails atomically with "Reference already exists" if another agent got
there first (a plain `git push` can report success when the ref already
exists at the same commit):

```bash
git fetch origin
gh api repos/{owner}/{repo}/git/refs \
  -f ref="refs/heads/agent-lock/issue-<n>" \
  -f sha="$(git rev-parse origin/main)"
```

**If creation fails because the reference exists**, the issue is normally
taken — but locks leak when a run dies. The lock is **stale** and may be
deleted and re-acquired when either:

- the issue is closed, or
- the issue has no `agent-taken-*` label **and** no open PR references it,
  and the lock branch's commit is more than 24 hours old
  (`gh api repos/{owner}/{repo}/branches/agent-lock/issue-<n> --jq
  '.commit.commit.committer.date'`).

Otherwise the claim is live: move to the next candidate.

After acquiring the lock, re-fetch the issue. If it closed or gained an
`agent-taken-*` label in the meantime, delete the lock and pick another.
Otherwise finalize the claim:

```bash
gh issue edit <n> --add-label agent-taken-claude
gh issue comment <n> --body "claude has claimed this issue and is starting implementation. Lock: agent-lock/issue-<n>"
```

Completion: exactly one issue is locked and labelled by you, or the list is
empty and you report the drain finished.

### 3. Ship

Run `tdd-ship` against the claimed issue. The issue body is the spec — a
`ready-for-agent` issue is contractually implementable cold, so do not
re-litigate its scope. The issue already exists, so don't file a new one; use
its number for the branch name and the `Closes #<n>` line.

If the spec turns out **not** to be implementable cold (missing context, a
product decision, broken file references), do not guess: comment on the issue
stating exactly what is missing, then release the claim fully —

```bash
gh issue edit <n> --add-label agent-blocked --remove-label agent-taken-claude
git push origin --delete "agent-lock/issue-<n>"
```

Deleting the lock matters: a kept lock on a blocked issue deadlocks it for
every agent forever.

Completion: the PR merged and the issue auto-closed, or the issue is labelled
`agent-blocked` with a comment and its lock released.

### 4. Close out

On a merged PR, mark the issue and release the lock:

```bash
gh issue edit <n> --add-label agent-done --remove-label agent-taken-claude
git push origin --delete "agent-lock/issue-<n>"
```

### 5. Repeat

Return to step 0. Stop only when no unclaimed, unblocked `ready-for-agent`
issues remain. Then report a summary: issues shipped (with PR links), issues
blocked (with reasons).

## Guardrails

- **One issue in flight at a time.** A merged PR or an `agent-blocked` comment
  is the only exit from step 3.
- **Never take** issues labelled `ready-for-human`, or live claims by another
  agent.
- **Every claimed issue ends with its lock deleted** and labelled
  `agent-done` or `agent-blocked` — never silently abandoned. The lock branch
  outliving the claim is the protocol's one unrecoverable failure mode; treat
  deleting it as part of done.
- For long drains, pace the loop with `/loop` rather than grinding a single
  context window to exhaustion.
