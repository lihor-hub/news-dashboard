---
name: write-documentation
description: >-
  Documentation writing for repo docs, READMEs, guides, runbooks, ADRs, API
  docs, and inline explanatory docs. Use when the user asks to write, update,
  edit, tighten, or review documentation.
---

# Write Documentation

Write docs that help the reader act.

## Workflow

1. Identify the reader, task, and source of truth.
   Completion: you can name who reads the doc, what they need to do, and which
   files, code paths, specs, or user notes prove each claim.

2. Gather facts before drafting.
   Completion: every non-obvious claim is backed by current source material or
   marked as an assumption.

3. Draft around the task.
   Completion: the doc starts with the needed answer, then gives only the
   context, steps, decisions, or constraints the reader needs.

4. Prune hard.
   Completion: each sentence changes what the reader knows or does.

5. Verify the result.
   Completion: commands, paths, option names, links, and examples are accurate;
   formatting matches nearby docs.

## Style Gate

- Do not add filler words.
- Make every sentence information dense.
- Get to the point.
- Use short words and fewer words.
- Avoid multiple examples.
- Do not use phrases like "it's important to note".
- Avoid needless transitions.

## Output Rules

- Prefer concrete nouns and verbs over broad claims.
- Put warnings and limits next to the step or fact they affect.
- Keep examples singular unless the reader needs a contrast.
- Delete throat-clearing introductions.
- Delete summaries that restate the heading.
- Keep terminology consistent with the repo.
