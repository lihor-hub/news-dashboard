---
name: tdd-ship
description: >-
  Default delivery workflow for tracked repo changes. Use when the user asks to
  fix, add, implement, update, refactor, rename, bump, tweak, or otherwise end
  in a file change. Do not use for read-only questions or investigation.
---

# TDD → Issue → PR → CI → Merge

This is how tracked changes ship in this repo: issue -> branch -> red/green
TDD -> PR -> CI -> auto-merge.

## When this applies

Apply the full pipeline when the request modifies a tracked file: code, config,
docs, tests, or deploy files.

Skip it for pure questions, explanations, research, or read-only investigation
("how does X work?", "where is Y defined?", "explain this") — answer those
directly. If a question turns into "…so fix it," the pipeline kicks in at that
point.

If the user explicitly asks to edit locally without a PR, honor that scope but
keep the branch, tests, and reporting discipline.

## The pipeline

Run these in order.

### 1. Open a GitHub issue

Capture the intent before writing code.

```bash
gh issue create --title "<concise imperative title>" \
  --body "<what & why; acceptance criteria as a checklist>" \
  --label "ready-for-agent"
```

Keep the title in the repo's voice (`fix:`/`feat:` style matches commits).
Always apply `ready-for-agent`; the issue body needs context, file references,
scope, acceptance criteria, and test expectations.

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

Push only after the relevant tests and type/lint gates pass locally.

### 4. Rebase on `origin/main`, open the PR, and queue it for merge

Rebase immediately before pushing, re-run gates if the rebase changes the base,
push, open the PR, then queue auto-merge:

```bash
git fetch origin && git rebase origin/main
git push -u origin HEAD
gh pr create --fill --base main \
  --body "Closes #<issue#>\n\n<summary of the change and the test that backs it>"
gh pr merge --squash --auto
```

The `Closes #<issue#>` line is required. End the PR body with the standard trailer:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Always open PRs with auto-merge enabled (`--auto`). Branch protection uses a
merge queue; do not pass `--delete-branch` with queued merges.

Do not bypass the queue with `gh pr merge --admin` or a direct push to `main`.

### 5. Watch CI and the merge queue

CI (`.github/workflows/ci.yml`) runs on every PR to `main`. Watch it:

```bash
gh pr checks --watch
```

If a check fails, read the logs (`gh run view <run-id> --log-failed`), fix the
cause on the branch, push, and let CI re-run. Required checks are `Lint &
typecheck` and `Test & build`; both must pass on the PR and merge queue.

### 6. Confirm the merge completed

Once CI is green, confirm auto-merge landed (`gh pr view <pr#> --json
state,mergedAt`), confirm the issue closed, delete the remote branch if GitHub
did not, and report the PR/issue numbers.

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
