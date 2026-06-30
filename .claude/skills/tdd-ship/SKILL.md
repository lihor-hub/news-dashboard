---
name: tdd-ship
description: >-
  The default end-to-end delivery workflow for this repo. Use this skill
  WHENEVER a request will change a tracked file in the repository — fixing a
  bug, adding a feature, refactoring, editing config, docs, or tests — even for
  a one-line change. It drives the full pipeline: open a GitHub issue, branch,
  write the failing test first (TDD), implement until green, open a PR that
  closes the issue, wait for CI, and auto-merge once CI is green. Do NOT use it
  for pure questions, explanations, research, or read-only investigation that
  touch no files. Triggers on: "fix", "add", "implement", "change", "update",
  "refactor", "rename", "bump", "tweak", or any phrasing that ends in a code or
  file change.
---

# TDD → Issue → PR → CI → Merge

This is how work ships in this repo. Any request that ends in a changed file
goes through the same pipeline, so changes are traceable (an issue), reviewable
(a PR), test-backed (TDD), and verified (CI) before they reach `main`. The goal
isn't ceremony — it's that nothing lands on `main` without a test proving it
works and CI confirming it.

## When this applies

Apply the full pipeline when the request will modify a tracked file: code, a new
feature, a bug fix, a refactor, config, Helm/deploy, docs, or tests.

Skip it for pure questions, explanations, research, or read-only investigation
("how does X work?", "where is Y defined?", "explain this") — answer those
directly. If a question turns into "…so fix it," the pipeline kicks in at that
point.

If you're unsure whether a request is big enough to warrant the pipeline, it is.
A one-line fix still gets an issue, a test, and a PR — that's the point.

## The pipeline

Run these in order. Don't skip steps, and don't merge anything by hand outside
this flow.

### 1. Open a GitHub issue

Capture the intent before writing code, so the change has a tracked rationale.

```bash
gh issue create --title "<concise imperative title>" \
  --body "<what & why; acceptance criteria as a checklist>" \
  --label "ready-for-agent"
```

Keep the title in the repo's voice (e.g. `fix:`/`feat:` style matches commits).
Note the issue number — you'll reference it in the branch and the PR.

**Always apply the `ready-for-agent` label** to every issue you open. The body
must be fully specified — context, file references, and acceptance criteria as a
checklist — so an agent can pick it up with no further human context. If you add
the label to an existing issue, use `gh issue edit <issue#> --add-label
"ready-for-agent"`.

### 2. Branch off an up-to-date `main`

Never commit to `main` directly, and never start from a stale base. Sync with
`origin/main` first, then branch:

```bash
git fetch origin
git switch main && git pull --ff-only
git switch -c <type>/<short-slug>-<issue#>   # e.g. feat/share-internal-123
```

If you're already on a feature branch for this work (e.g. a worktree where you
can't `git switch main`), stay on it — but rebase it onto the freshly fetched
base before you write anything: `git fetch origin && git rebase origin/main`.
Starting from an up-to-date `main` keeps the diff clean and avoids merge
conflicts when you push.

### 3. TDD — write the failing test first

This is the heart of the workflow. Write the test that describes the desired
behavior **before** the implementation, watch it fail for the right reason, then
make it pass. A test written after the code tends to assert what the code does,
not what it should do — writing it first is what makes it a spec.

- **Red**: add/modify a test that encodes the new behavior. Run it; confirm it
  fails because the behavior is missing (not because of a typo or import error).
- **Green**: write the minimum implementation to make it pass.
- **Refactor**: clean up code and test while keeping the suite green.

Match the repo's test conventions and run the gates locally before pushing —
defer to the language skills for exact commands and patterns:

- Python / backend changes → follow `python-dev` (pytest needs
  `source .env && make test`; ruff + mypy + ty + pyrefly must pass).
- TypeScript / React / frontend changes → follow `typescript-dev`
  (vitest, eslint `--max-warnings 0`, prettier, `tsc`).

Codex worktrees may not include the ignored `.env` file. Before running
backend tests or pushing, check whether the current worktree has `.env`; if it
does not, copy it from the main checkout (usually `/Users/ioachimlihor/news-dashboard/.env`)
into the worktree. Do not print secret values. It is enough to verify that
`DATABASE_URL` and `TEST_DATABASE_URL` are present so the pre-push backend
pytest hook can connect to PostgreSQL.

Push only once the relevant tests and type/lint gates pass locally — CI runs the
same gates, so green-locally is the cheapest way to a green PR.

### 4. Rebase on `origin/main`, open the PR, and queue it for merge

`main` may have moved while you worked, so re-sync immediately before pushing.
Rebase (don't merge) so the branch stays linear, re-run the gates if the rebase
pulled anything in, push, open the PR, then immediately hand it to GitHub's merge
queue:

```bash
git fetch origin && git rebase origin/main
git push -u origin HEAD
gh pr create --fill --base main \
  --body "Closes #<issue#>\n\n<summary of the change and the test that backs it>"
gh pr merge --squash --auto
```

The `Closes #<issue#>` line is required — it links the PR to the issue and
auto-closes it on merge. End the PR body with the standard trailer:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Always open PRs with auto-merge enabled (`--auto`). Branch protection on `main`
requires a merge queue, so `gh pr merge` does not merge directly. If required
checks are still pending, it enables auto-merge; once the PR is eligible, GitHub
adds it to the queue and creates a `merge_group` ref. The queue then waits for
the required checks on that merge group before landing the PR. Do not pass
`--delete-branch` when merge queue is enabled; `gh` rejects that flag for queued
merges. A repo-level workflow (`.github/workflows/auto-merge.yml`) also enables
auto-merge on every non-draft PR as a backstop, but don't rely on it — set
`--auto` yourself.

Do not bypass the queue with `gh pr merge --admin` or a direct push to `main`.

### 5. Watch CI and the merge queue

CI (`.github/workflows/ci.yml`) runs on every PR to `main`. Watch it:

```bash
gh pr checks --watch
```

If a check fails, read the logs (`gh run view <run-id> --log-failed`), fix the
cause on the branch, push, and let CI re-run. When the PR reaches the merge
queue, CI runs again on the `merge_group` event for the temporary queue ref. The
required checks are `Lint & typecheck` and `Test & build`; both must pass on the
merge group before GitHub squash-merges the PR.

### 6. Confirm the merge completed

Once CI is green, confirm auto-merge actually landed the PR (`gh pr view
<pr#> --json state,mergedAt`). Then confirm the issue closed (the `Closes #`
link handles it), delete the remote branch if GitHub did not delete it
automatically, and report the merged PR and issue numbers back to the user.
Only step in with `gh pr merge --squash --auto` if auto-merge was disabled (e.g.
the PR was converted to a draft); do not use an admin merge to skip the queue.

## Reporting back

After merge, give the user a one-line summary with links: the issue, the PR, and
confirmation that CI passed and the branch was deleted. If anything blocked the
pipeline (flaky CI, a check that needs secrets, a merge conflict), surface it
instead of silently stopping.

## Guardrails

- **Authorization to merge is built in** — the user has opted into auto-merge on
  green CI for this repo, so you don't need to re-ask before each merge. But
  never force-merge past a failing or pending required check.
- **One issue/PR per logical change.** If a request bundles unrelated changes,
  split them so each PR stays reviewable.
- **If the user explicitly says "just edit, don't open a PR"** or is clearly
  working in a throwaway/experimental context, honor that and skip the pipeline
  for that request.
