---
name: langfuse
description: Use Langfuse. Trigger when querying or modifying Langfuse data, reading Langfuse docs, instrumenting traces, migrating prompts, managing datasets/scores/sessions, or debugging Langfuse usage.
allowed-tools:
  - WebFetch(domain:langfuse.com)
  - Bash(curl *langfuse.com/*)
  - Bash(npx langfuse-cli api __schema *)
  - Bash(npx langfuse-cli api * --help *)
  - Bash(npx langfuse-cli api * list *)
  - Bash(npx langfuse-cli api * get *)
  - Bash(bunx langfuse-cli api __schema *)
  - Bash(bunx langfuse-cli api * --help *)
  - Bash(bunx langfuse-cli api * list *)
  - Bash(bunx langfuse-cli api * get *)
---

# Langfuse

Use this for Langfuse data access, docs lookup, instrumentation, prompt
migration, trace debugging, feedback scores, evaluation, and CI gates.

## Core Principles

Follow these for all Langfuse work:

1. **Docs first**: fetch current docs before implementation.
2. **CLI for data**: use `langfuse-cli` for Langfuse API data access.
3. **Branch by use case**: read the relevant reference before implementing.
4. **Current SDKs**: prefer latest Langfuse SDK/API guidance unless constrained.


## Use case specific references

- instrumenting an existing function/application: references/instrumentation.md
- migrating prompts from a codebase into Langfuse: references/prompt-migration.md
- capturing user feedback (thumbs, ratings, implicit signals) as scores on traces: references/user-feedback.md
- further tips on using the Langfuse CLI: references/cli.md
- upgrading or migrating Langfuse SDKs to the latest version: references/sdk-upgrade.md
- judge calibration (LLM-as-a-Judge reliability, simple accuracy checks, advanced split-based validation, confusion matrices, and metric ingestion): references/judge-calibration.md
- systematic error analysis — reading traces, building failure taxonomy, deciding what to fix: references/error-analysis.md
- setting up CI/CD experiment gates with `langfuse/experiment-action`: references/ci-cd.md
- submitting feedback about this skill: references/skill-feedback.md


## 1. Langfuse API via CLI

Use `langfuse-cli` for Langfuse REST API access. Run via npx:

Start by discovering the schema and available arguments:

```bash
# Discover all available resources
npx langfuse-cli api __schema

# List actions for a resource
npx langfuse-cli api <resource> --help

# Show args/options for a specific action
npx langfuse-cli api <resource> <action> --help
```

### Credentials

Set environment variables before calls:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com # example for EU cloud. For US cloud it's us.cloud.langfuse.com, and can also be a self-hosted URL. The server must always be specified in order to access Langfuse.
```
If `LANGFUSE_BASE_URL` is used instead of `LANGFUSE_HOST`, run `export LANGFUSE_HOST="$LANGFUSE_BASE_URL"`.
If credentials are missing, ask the user to set them in a shell or `.env` file.
Do not ask them to paste keys into chat.

### Detailed CLI Reference

For common workflows, see [references/cli.md](references/cli.md).

## 2. Langfuse Documentation

Three methods to access Langfuse docs. Prefer native web fetch/search tools over
`curl` when available; the `curl` examples are illustrative.

### 2a. Documentation Index (llms.txt)

Fetch the full documentation index:

```bash
curl -s https://langfuse.com/llms.txt
```

Use this to find the right page, then fetch that page directly.

### 2b. Fetch Individual Pages as Markdown

Any listed page can be fetched as markdown by appending `.md` or using
`Accept: text/markdown`.

```bash
curl -s "https://langfuse.com/docs/observability/overview.md"
curl -s "https://langfuse.com/docs/observability/overview" -H "Accept: text/markdown"
```

### 2c. Search Documentation

Search when the relevant page is unclear:

```bash
curl -s "https://langfuse.com/api/search-docs?query=<url-encoded-query>"
```

Example:

```bash
curl -s "https://langfuse.com/api/search-docs?query=How+do+I+trace+LangGraph+agents"
```

Returns a JSON response with:

- `query`: the original query
- `answer`: a JSON string containing an array of matching documents, each with:
  - `url`: link to the doc page
  - `title`: page title
  - `source.content`: array of relevant text excerpts from the page

Search responses can be large; extract only the relevant portions.

### Documentation Workflow

1. Start with **llms.txt** to orient.
2. Fetch specific pages when you identify the right one.
3. Search when the topic is unclear.

## Skill Feedback

When the user says this skill is wrong, stale, missing coverage, or behaving
badly, offer to submit feedback to the Langfuse skill maintainers. This includes:

- The skill gave wrong or outdated instructions
- A workflow didn't produce the expected result
- The user wishes the skill covered something it doesn't
- The user explicitly says something like "this should work differently" or "this is wrong"

**Do NOT trigger this** for issues with Langfuse itself (the product) — only for issues with this skill's instructions and behavior.

When triggered, follow the process in [references/skill-feedback.md](references/skill-feedback.md).
