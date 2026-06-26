---
name: report-issue
description: >-
  Turn a reported problem or feature request into a fully-specified GitHub issue
  that an autonomous agent can pick up and ship AFK — no further human context
  needed. Use this WHENEVER the user wants to "report a problem", "file/open/create
  an issue", "log a bug", "track this for later", or describes something to fix or
  build but explicitly does NOT want it implemented right now. The skill
  investigates the codebase to scope the request, writes a self-contained issue
  (problem, current state, file references, scope, acceptance criteria, test
  expectations), and labels it `ready-for-agent` so it can be picked up from the
  backlog and solved autonomously. Do NOT use this when the user wants the change
  implemented now — that is `tdd-ship`.
---

# Report a problem → AFK-ready GitHub issue

The purpose of this skill is to capture work as a **GitHub issue specified well
enough that an agent can implement it cold**, from the issue text alone, with no
memory of the conversation that produced it. The issue is the handoff. If it is
vague, the AFK agent guesses; if it is precise, the AFK agent ships.

Use this when the user wants to *record* work, not do it now. If they want it
done immediately, use `tdd-ship` instead.

## The contract: what "AFK-ready" means

The downstream agent starts from a cold checkout with only the issue body. So
the body must stand alone. Before writing it, do the investigation the AFK agent
would otherwise have to redo — then bake the answers into the issue.

A `ready-for-agent` issue MUST contain:

1. **Problem / goal** — what is wrong or wanted, and *why*. One or two sentences.
2. **Current state** — what exists today, with concrete `path/to/file.py:line`
   references for every relevant call site. This is what saves the AFK agent its
   own discovery pass. Name the functions, endpoints, and modules involved.
3. **Scope** — a numbered list of the concrete changes to make. Be specific
   about which files/functions change and how. Call out anything explicitly
   *out* of scope or "leave as-is" so the agent doesn't over-build.
4. **Acceptance criteria** — a `- [ ]` checklist of verifiable outcomes. Each
   item should be objectively checkable (a test passes, a label shows up, an
   endpoint returns X), not a vibe.
5. **Test expectations** — what tests should back the change and roughly where
   they live (match the repo's existing test conventions). The downstream flow
   is TDD, so this seeds the failing test.

If you cannot fill in section 2 or 3 from the codebase, the issue is not ready —
investigate first (read the relevant files, grep the call sites) or ask the user
the one or two questions that unblock it. Do not file a hand-wavy issue.

## Workflow

### 1. Understand the report

Read what the user described. If it is a bug, reproduce the reasoning: where in
the code does it go wrong? If it is a feature, where does it slot in? Use the
file/search tools to ground every claim. Spend the investigation budget here so
the issue is self-contained — this is the whole value of the skill.

Only ask the user a question when the answer genuinely changes the spec and you
cannot derive it from the code (e.g. a product decision like "leave TTS untraced
vs. tag it `system`"). Otherwise pick the sensible default and note it in the
issue.

### 2. Choose labels

Always apply `ready-for-agent` (the AFK-pickup marker: "Fully specified,
AFK-ready: an agent can pick it up with no human context"). Add the matching
domain label(s) so the backlog stays filterable — check `gh label list` and use
what fits, e.g.:

- `bug` / `enhancement` — kind of work
- `epic: ai`, `epic: automation`, `epic: content`, `epic: reader-ux` — area
- `ci-cd`, `ux`, `documentation` — cross-cutting

If a needed label doesn't exist, create it (`gh label create`) rather than
forcing a poor fit. Never apply `ready-for-human` to an AFK issue — that label
is for work that needs a person; the two are mutually exclusive.

### 3. Create the issue

Write the body to a temp file (heredoc) to keep markdown intact, then:

```bash
gh issue create \
  --title "<type>: <concise imperative title>" \
  --body-file /tmp/issue.md \
  --label ready-for-agent \
  --label <domain-label>
```

Match the repo's commit voice in the title (`fix:` / `feat:` / `chore:`).

### 4. Report back

Give the user the issue URL and a one-line summary of what it asks for, plus the
labels applied. Make clear it is queued for AFK pickup — you are NOT implementing
it now. If, while scoping, you found the change is trivial or the user seems to
want it done, offer `tdd-ship` as the next step rather than assuming.

## How AFK pickup works

Issues labelled `ready-for-agent` form the autonomous backlog. An agent drains
that pool and ships each one through the standard `tdd-ship` pipeline (branch →
failing test → implement → PR that closes the issue → CI → auto-merge). Because
this skill front-loads the specification, the AFK agent needs no conversation
context — it reads the issue, implements exactly the scope, and the acceptance
criteria tell it when it's done.

To dispatch the backlog, point an agent at the open `ready-for-agent` issues:

```bash
gh issue list --label ready-for-agent --state open
```

Then, for a chosen issue, run `tdd-ship` against it (e.g. "implement issue #NNN").
This can be wired to a scheduled cloud agent / routine (see the `schedule` skill)
so the queue is drained automatically on a cadence — each run picks the next open
`ready-for-agent` issue and ships it.

## Guardrails

- **Specify, don't implement.** This skill ends at a created issue. Touch no
  tracked source files. If implementation is wanted, hand off to `tdd-ship`.
- **One issue per logical change.** If the report bundles unrelated problems,
  file separate issues so each is independently shippable and reviewable.
- **Ground every reference.** Every `file:line` in the issue must be real and
  current — verify with the search tools before writing it, since the AFK agent
  will trust it blindly.
- **No secrets in issue bodies.** Issues are world-readable on public repos;
  reference env var *names*, never values.
