---
name: write-documentation
description: >-
  Documentation writing for repo docs, READMEs, guides, runbooks, ADRs, API
  docs, and inline explanatory docs. Use when the user asks to write, update,
  edit, tighten, or review documentation.
---

# Write documentation in this repo

Write docs that help the reader act, then ship them through `tdd-ship` like
any other tracked change.

## Where docs live

- `docs/README.md` — index of technical docs. New technical docs go in
  `docs/` and get a row in its table.
- `docs/adr/` — Architecture Decision Records. Copy `0000-template.md` to the
  next sequential 4-digit number, fill the template fields (Status, Deciders,
  Context, Drivers, Options, Consequences), and add the ADR to the index in
  `docs/adr/README.md`.
- `docs/user-guide/` — markdown mirror of the end-user guide. The published
  copy lives in `website/docs/`; when you edit one, update the other.
- `website/docs/` — source of the published site (docs.lihor.ro). Pushes to
  `main` touching `website/**` deploy it via `.github/workflows/docs.yml`
  (GitHub Pages).
- `docs/SELF_HOSTING.md` — running your own instance.
- The in-app "What's New" changelog (`/api/changelog`) is AI-generated at
  release time — never hand-edit `CHANGELOG.md` as documentation; see the
  `release` skill.

## Workflow

1. Identify the reader, task, and source of truth.
   Completion: you can name who reads the doc, what they need to do, and which
   files, code paths, specs, or user notes prove each claim.

2. Gather facts before drafting.
   Completion: every non-obvious claim is backed by current source material or
   marked as an assumption.

3. Draft around the task.
   Completion: the doc starts with the needed answer, then gives only the
   context, steps, decisions, or constraints the reader needs. Warnings and
   limits sit next to the step or fact they affect, not in a separate section.

4. Prune hard.
   Completion: each sentence changes what the reader knows or does; headings
   are not restated as prose.

5. Verify the result.
   Completion: commands, paths, option names, links, and examples are accurate;
   formatting and terminology match nearby docs; any mirrored copy
   (`docs/user-guide/` ↔ `website/docs/`) is updated in the same PR.
