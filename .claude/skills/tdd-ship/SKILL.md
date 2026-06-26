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
  --body "<what & why; acceptance criteria as a checklist>"
```

Keep the title in the repo's voice (e.g. `fix:`/`feat:` style matches commits).
Note the issue number — you'll reference it in the branch and the PR.

### 2. Branch off `main`

Never commit to `main` directly. Branch first:

```bash
git switch main && git pull --ff-only
git switch -c <type>/<short-slug>-<issue#>   # e.g. feat/share-internal-123
```

If you're already on a feature branch for this work, stay on it.

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

Push only once the relevant tests and type/lint gates pass locally — CI runs the
same gates, so green-locally is the cheapest way to a green PR.

### 4. Open the PR (it must close the issue)

```bash
git push -u origin HEAD
gh pr create --fill --base main \
  --body "Closes #<issue#>\n\n<summary of the change and the test that backs it>"
```

The `Closes #<issue#>` line is required — it links the PR to the issue and
auto-closes it on merge. End the PR body with the standard trailer:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

### 5. Wait for CI to pass

CI (`.github/workflows/ci.yml`) runs on every PR to `main`. Watch it:

```bash
gh pr checks --watch
```

If a check fails, read the logs (`gh run view <run-id> --log-failed`), fix the
cause on the branch, push, and let CI re-run. Do not proceed until every
required check is green.

### 6. Auto-merge once CI is green

When all checks pass, merge without pausing — squash to keep `main` linear, and
delete the branch:

```bash
gh pr merge --squash --delete-branch
```

Then confirm the issue closed (the `Closes #` link handles it) and report the
merged PR and issue numbers back to the user.

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
