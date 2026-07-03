---
name: pr-review
description: >-
  Review a GitHub PR of this repo: description accuracy, code quality against
  the project dev-skill standards, and a bug hunt with concrete failure
  scenarios.
disable-model-invocation: true
---

# PR review

Invoked as `/pr-review <PR#>`; without a number, review the PR of the current
branch. Work the steps in order — the verdict is earned by the evidence, not
sketched first.

## 1. Load the PR

```bash
gh pr view <PR#> --json title,body,url,baseRefName,statusCheckRollup
gh pr diff <PR#>
```

Read the linked issue if the body names one. For every changed file, read
enough surrounding source to judge the hunk — a hunk alone is not context;
follow the change into its callers and callees. Completion: every file in the
diff read, in place, with its neighbours.

## 2. Audit the description

Treat the description as a set of **claims** and audit in both directions:

- Every claim checked against the diff — does the code do what the
  description says it does, the way it says it does it?
- Every change in the diff traced back to a claim — an undisclosed change is
  a finding, whether it is scope creep or a forgotten mention.

Completion: each claim marked verified or flagged, and each changed file
mapped to a claim.

## 3. Check quality against the project standards

The quality rules live in the dev skills — apply them, do not restate them:

- Diff touches `.py`, `pyproject.toml`, or backend tests → read
  [`python-dev/SKILL.md`](../python-dev/SKILL.md).
- Diff touches `.ts`/`.tsx`, npm or Vite config, or frontend tests → read
  [`typescript-dev/SKILL.md`](../typescript-dev/SKILL.md).

Hold the changed lines against every rule in the matching skill, including
its test-authoring rules — a behavior change with no regression test is a
finding. Completion: every changed file checked against its standard, or
explicitly outside both.

## 4. Hunt bugs

Read the diff as an **adversary**: for each changed function, look for the
inputs or state that make it misbehave. A finding is **confirmed** only when
you can state that concrete failure scenario, traced through the actual code —
not pattern-matched from its shape. What you suspect but cannot trace is
**potential**, reported separately, never silently dropped. Completion: every
changed function either cleared or attached to a finding.

## 5. Report

Deliver the review in the session; comment on the PR only when asked.

- Verdict first: approve or request changes.
- Findings ranked by severity, each with `file:line`, its axis
  (description / quality / confirmed bug / potential issue), and — for bugs —
  the failure scenario.
- One line on what was checked and found clean, so a short findings list
  reads as a clean bill rather than a shallow pass.
