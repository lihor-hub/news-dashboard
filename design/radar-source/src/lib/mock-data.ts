import type { Article, Source, FeedRun, Category, Signal, WorkflowState } from "./types";

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;
const now = Date.now();
const iso = (ms: number) => new Date(ms).toISOString();

export const SOURCES: Source[] = [
  { id: "src-realpython", name: "Real Python", kind: "rss", category: "Python", enabled: true, health: "ok", lastChecked: iso(now - 12 * 60 * 1000), lastSuccess: iso(now - 12 * 60 * 1000), itemsFetched: 8, itemsInserted: 3 },
  { id: "src-pyweekly", name: "PyCoder's Weekly", kind: "rss", category: "Python", enabled: true, health: "ok", lastChecked: iso(now - 30 * 60 * 1000), lastSuccess: iso(now - 30 * 60 * 1000), itemsFetched: 12, itemsInserted: 5 },
  { id: "src-simonw", name: "Simon Willison's Weblog", kind: "rss", category: "AI/LLM", enabled: true, health: "ok", lastChecked: iso(now - 8 * 60 * 1000), lastSuccess: iso(now - 8 * 60 * 1000), itemsFetched: 5, itemsInserted: 2 },
  { id: "src-anthropic", name: "Anthropic News", kind: "rss", category: "AI/LLM", enabled: true, health: "ok", lastChecked: iso(now - 1 * HOUR), lastSuccess: iso(now - 1 * HOUR), itemsFetched: 2, itemsInserted: 1 },
  { id: "src-oai", name: "OpenAI Blog", kind: "rss", category: "AI/LLM", enabled: true, health: "stale", lastChecked: iso(now - 5 * HOUR), lastSuccess: iso(now - 2 * DAY), itemsFetched: 0, itemsInserted: 0 },
  { id: "src-langchain", name: "LangChain Blog", kind: "rss", category: "Agents", enabled: true, health: "ok", lastChecked: iso(now - 45 * 60 * 1000), lastSuccess: iso(now - 45 * 60 * 1000), itemsFetched: 3, itemsInserted: 1 },
  { id: "src-llamaindex", name: "LlamaIndex Blog", kind: "rss", category: "Agents", enabled: true, health: "ok", lastChecked: iso(now - 2 * HOUR), lastSuccess: iso(now - 2 * HOUR), itemsFetched: 1, itemsInserted: 0 },
  { id: "src-aws", name: "AWS What's New", kind: "rss", category: "Cloud/Infra", enabled: true, health: "ok", lastChecked: iso(now - 20 * 60 * 1000), lastSuccess: iso(now - 20 * 60 * 1000), itemsFetched: 14, itemsInserted: 4 },
  { id: "src-cloudflare", name: "Cloudflare Blog", kind: "rss", category: "Cloud/Infra", enabled: true, health: "ok", lastChecked: iso(now - 1.5 * HOUR), lastSuccess: iso(now - 1.5 * HOUR), itemsFetched: 4, itemsInserted: 2 },
  { id: "src-fly", name: "Fly.io Blog", kind: "scraped", category: "Cloud/Infra", enabled: false, health: "ok", lastChecked: iso(now - 8 * HOUR), lastSuccess: iso(now - 8 * HOUR), itemsFetched: 0, itemsInserted: 0 },
  { id: "src-hn", name: "Hacker News Front Page", kind: "scraped", category: "Trending", enabled: true, health: "ok", lastChecked: iso(now - 5 * 60 * 1000), lastSuccess: iso(now - 5 * 60 * 1000), itemsFetched: 30, itemsInserted: 7 },
  { id: "src-lobsters", name: "Lobsters", kind: "rss", category: "Trending", enabled: true, health: "ok", lastChecked: iso(now - 22 * 60 * 1000), lastSuccess: iso(now - 22 * 60 * 1000), itemsFetched: 18, itemsInserted: 3 },
  { id: "src-gh-trending", name: "GitHub Trending (Python)", kind: "trending", category: "Repositories", enabled: true, health: "ok", lastChecked: iso(now - 40 * 60 * 1000), lastSuccess: iso(now - 40 * 60 * 1000), itemsFetched: 25, itemsInserted: 6 },
  { id: "src-gh-releases", name: "FastAPI Releases", kind: "github", category: "Repositories", enabled: true, health: "ok", lastChecked: iso(now - 3 * HOUR), lastSuccess: iso(now - 3 * HOUR), itemsFetched: 1, itemsInserted: 1 },
  { id: "src-gh-uv", name: "astral-sh/uv Releases", kind: "github", category: "Repositories", enabled: true, health: "ok", lastChecked: iso(now - 50 * 60 * 1000), lastSuccess: iso(now - 50 * 60 * 1000), itemsFetched: 2, itemsInserted: 2 },
  { id: "src-eng-stripe", name: "Stripe Engineering", kind: "rss", category: "Engineering", enabled: true, health: "ok", lastChecked: iso(now - 4 * HOUR), lastSuccess: iso(now - 4 * HOUR), itemsFetched: 1, itemsInserted: 1 },
  { id: "src-eng-figma", name: "Figma Engineering", kind: "rss", category: "Engineering", enabled: true, health: "ok", lastChecked: iso(now - 6 * HOUR), lastSuccess: iso(now - 6 * HOUR), itemsFetched: 0, itemsInserted: 0 },
  { id: "src-eng-cloudflare-edge", name: "Cloudflare Workers Updates", kind: "scraped", category: "Engineering", enabled: true, health: "error", lastChecked: iso(now - 18 * 60 * 1000), lastSuccess: iso(now - 3 * DAY), itemsFetched: 0, itemsInserted: 0, errorMessage: "HTTP 503 from upstream (3 consecutive failures)" },
];

const TITLES: { title: string; src: string; cat: Category; reason: string; signal: Signal; tags: string[]; bodyOk?: boolean }[] = [
  { title: "uv 0.5 released: workspaces, lockfile v2, faster resolver", src: "src-gh-uv", cat: "Repositories", reason: "Lockfile format change — pin your CI before upgrading shared repos.", signal: "high", tags: ["python", "packaging", "uv"] },
  { title: "FastAPI 0.116 ships dependency injection improvements", src: "src-gh-releases", cat: "Repositories", reason: "Resolves long-standing async generator teardown bug in middleware.", signal: "high", tags: ["fastapi", "release"] },
  { title: "Anthropic introduces Claude 4 with structured tool calls", src: "src-anthropic", cat: "AI/LLM", reason: "Tool-call schema is OpenAI-compatible — drop-in for existing agents.", signal: "high", tags: ["claude", "llm", "tools"] },
  { title: "Simon Willison: Annotated notes on agent frameworks in 2026", src: "src-simonw", cat: "Agents", reason: "Sharp opinionated read on where most agent stacks still leak abstractions.", signal: "high", tags: ["agents", "opinion"] },
  { title: "Real Python: Pattern matching after three years in production", src: "src-realpython", cat: "Python", reason: "Concrete refactors — useful before your next protocol parser PR.", signal: "mid", tags: ["python", "match"] },
  { title: "PyCoder's Weekly #634", src: "src-pyweekly", cat: "Python", reason: "Curated digest — skim the dependency-resolver deep dive.", signal: "mid", tags: ["newsletter"] },
  { title: "Cloudflare Workers add Python runtime to GA", src: "src-cloudflare", cat: "Cloud/Infra", reason: "Python on the edge with real packages — viable for small APIs now.", signal: "high", tags: ["cloudflare", "python", "edge"] },
  { title: "AWS Lambda doubles SnapStart support to all Python runtimes", src: "src-aws", cat: "Cloud/Infra", reason: "Cold starts drop ~70% for ML-heavy handlers — worth re-benchmarking.", signal: "mid", tags: ["aws", "lambda"] },
  { title: "Hacker News: Show HN — a tiny task runner written in 200 lines", src: "src-hn", cat: "Trending", reason: "Worth a 2-minute skim; nice ergonomics around dependency graphs.", signal: "low", tags: ["showhn"] },
  { title: "LangChain LCEL deprecated in favor of LangGraph primitives", src: "src-langchain", cat: "Agents", reason: "Migration path is non-trivial — start planning before the 6-month window.", signal: "high", tags: ["langchain", "migration"] },
  { title: "LlamaIndex 0.13 brings native multi-modal retrievers", src: "src-llamaindex", cat: "Agents", reason: "Image + text retrieval without bolting on CLIP yourself.", signal: "mid", tags: ["rag", "multimodal"], bodyOk: false },
  { title: "Stripe Engineering: Migrating a 4-petabyte ledger online", src: "src-eng-stripe", cat: "Engineering", reason: "Reference-quality write-up on shadow reads and dual-write cutover.", signal: "high", tags: ["databases", "migrations"] },
  { title: "OpenAI: Realtime API now supports interruptions", src: "src-oai", cat: "AI/LLM", reason: "Closes a real gap for voice agents — re-evaluate your audio stack.", signal: "mid", tags: ["openai", "voice"] },
  { title: "GitHub Trending: simonw/llm hits 14k stars this week", src: "src-gh-trending", cat: "Repositories", reason: "CLI for piping LLMs through Unix tools — surprisingly useful daily.", signal: "mid", tags: ["cli", "llm"] },
  { title: "Lobsters: Why your async Python is slower than threads", src: "src-lobsters", cat: "Trending", reason: "Common GIL misconceptions debunked with reproducible benchmarks.", signal: "mid", tags: ["python", "async"] },
  { title: "Figma Engineering: Building a multiplayer cursor at scale", src: "src-eng-figma", cat: "Engineering", reason: "Practical CRDT tradeoffs from a team that's actually shipping it.", signal: "mid", tags: ["realtime", "crdt"] },
  { title: "PEP 750: Template strings advance to Final", src: "src-realpython", cat: "Python", reason: "First new string syntax in years — read before reviewing teammates' code.", signal: "high", tags: ["pep", "python"] },
  { title: "Pydantic 3 alpha: sub-millisecond validation in pure Rust", src: "src-pyweekly", cat: "Python", reason: "Breaking changes are small; perf is worth the early upgrade plan.", signal: "high", tags: ["pydantic"] },
  { title: "Anthropic: Computer use beta opens to all developers", src: "src-anthropic", cat: "AI/LLM", reason: "Sandbox guidance is now explicit — required reading before you ship.", signal: "high", tags: ["claude", "tools"] },
  { title: "Simon Willison: Datasette plugin for SQLite vector search", src: "src-simonw", cat: "AI/LLM", reason: "Tiny but composable — could replace a small pgvector deployment.", signal: "mid", tags: ["sqlite", "vector"] },
  { title: "Real Python: Profiling memory with memray in CI", src: "src-realpython", cat: "Python", reason: "Concrete CI snippet — adopt before the next leak hunt.", signal: "mid", tags: ["python", "profiling"] },
  { title: "AWS announces S3 conditional writes for compare-and-swap", src: "src-aws", cat: "Cloud/Infra", reason: "Removes a class of distributed locks built on DynamoDB.", signal: "high", tags: ["aws", "s3"] },
  { title: "Cloudflare R2 adds event notifications to Queues", src: "src-cloudflare", cat: "Cloud/Infra", reason: "Native object-storage events without polling — clean ETL trigger.", signal: "mid", tags: ["cloudflare", "r2"] },
  { title: "Hacker News: Ask HN — best resource for distributed systems in 2026?", src: "src-hn", cat: "Trending", reason: "Skim the top 5 answers; rest is mostly noise.", signal: "low", tags: ["askhn"] },
  { title: "LangChain: New retriever benchmark suite open-sourced", src: "src-langchain", cat: "Agents", reason: "Standardized harness — useful for your evals next sprint.", signal: "mid", tags: ["evals", "rag"] },
  { title: "Hacker News: Postgres 18 released", src: "src-hn", cat: "Trending", reason: "Async I/O lands in core — meaningful for write-heavy workloads.", signal: "high", tags: ["postgres"] },
  { title: "Lobsters: How we removed Redis from our stack", src: "src-lobsters", cat: "Trending", reason: "Postgres LISTEN/NOTIFY + advisory locks; honest about the tradeoffs.", signal: "mid", tags: ["postgres", "architecture"] },
  { title: "GitHub Trending: astral-sh/ruff overtakes black this month", src: "src-gh-trending", cat: "Repositories", reason: "Adoption signal — formatter wars are effectively over.", signal: "low", tags: ["python", "tooling"] },
  { title: "OpenAI: Embeddings v4 with native multilingual support", src: "src-oai", cat: "AI/LLM", reason: "Quality jump on non-English benchmarks — re-embed if you serve EU users.", signal: "mid", tags: ["embeddings"] },
  { title: "LlamaIndex: Recipe for a 10k-doc agent with sub-second retrieval", src: "src-llamaindex", cat: "Agents", reason: "Useful chunking heuristics — adopt the hierarchical splitter.", signal: "mid", tags: ["rag"] },
  { title: "Real Python: A complete guide to typing.Protocol", src: "src-realpython", cat: "Python", reason: "Best reference yet on structural typing in real codebases.", signal: "mid", tags: ["python", "typing"] },
  { title: "PyCoder's Weekly: deep dive on free-threaded CPython", src: "src-pyweekly", cat: "Python", reason: "What actually breaks today vs what's safe to try.", signal: "high", tags: ["python", "gil"] },
  { title: "Stripe Engineering: Idempotency keys at 100k RPS", src: "src-eng-stripe", cat: "Engineering", reason: "Practical pattern; the cache eviction story is the gold.", signal: "mid", tags: ["idempotency"] },
  { title: "Cloudflare adds Durable Objects SQLite storage GA", src: "src-cloudflare", cat: "Cloud/Infra", reason: "Per-tenant SQLite on the edge — viable for multi-tenant SaaS now.", signal: "high", tags: ["cloudflare", "sqlite"] },
  { title: "AWS Bedrock now supports custom model import", src: "src-aws", cat: "Cloud/Infra", reason: "Bring-your-own weights with managed inference — useful for fine-tunes.", signal: "mid", tags: ["aws", "bedrock"] },
  { title: "Simon Willison: Notes on building a tiny RAG over my blog", src: "src-simonw", cat: "AI/LLM", reason: "Pragmatic recipe; SQLite + embeddings is enough for personal data.", signal: "mid", tags: ["rag", "personal"] },
  { title: "Anthropic publishes prompt caching cost model", src: "src-anthropic", cat: "AI/LLM", reason: "Concrete numbers — restructure your system prompt before the next bill.", signal: "high", tags: ["claude", "cost"] },
  { title: "Hacker News: I rewrote my SaaS in Go and regret it", src: "src-hn", cat: "Trending", reason: "Honest postmortem; nuance about team velocity is worth it.", signal: "low", tags: ["postmortem"] },
  { title: "GitHub Trending: pydantic/logfire crosses 5k stars", src: "src-gh-trending", cat: "Repositories", reason: "OpenTelemetry-native observability with great Python ergonomics.", signal: "mid", tags: ["observability"] },
  { title: "Lobsters: A pragmatic guide to Postgres partitioning", src: "src-lobsters", cat: "Trending", reason: "The decision tree at the end is worth bookmarking.", signal: "mid", tags: ["postgres"] },
  { title: "Real Python: Async context managers, properly explained", src: "src-realpython", cat: "Python", reason: "Clears up the AsyncExitStack confusion in older docs.", signal: "low", tags: ["python", "async"] },
  { title: "FastAPI 0.117 patch — security fix for form parsing", src: "src-gh-releases", cat: "Repositories", reason: "Patch-level upgrade; do it today.", signal: "high", tags: ["fastapi", "security"], bodyOk: false },
  { title: "OpenAI: Structured outputs now support recursive schemas", src: "src-oai", cat: "AI/LLM", reason: "Removes a real workaround in agent toolchains.", signal: "mid", tags: ["openai", "schemas"] },
  { title: "LangChain: Tool-call routing benchmark across 12 models", src: "src-langchain", cat: "Agents", reason: "Numbers, not vibes — useful baseline for model selection.", signal: "mid", tags: ["agents", "evals"] },
  { title: "Stripe Engineering: How we shrunk our protobuf graph", src: "src-eng-stripe", cat: "Engineering", reason: "Schema hygiene story — applicable to any growing service.", signal: "low", tags: ["protobuf"] },
  { title: "Figma Engineering: Building an inspector that doesn't lag", src: "src-eng-figma", cat: "Engineering", reason: "Browser perf deep dive; the layout-thrash section is the takeaway.", signal: "mid", tags: ["frontend", "perf"] },
  { title: "AWS Step Functions: distributed map now supports 1M iterations", src: "src-aws", cat: "Cloud/Infra", reason: "Removes a real workaround for large-fanout ETL.", signal: "mid", tags: ["aws"] },
  { title: "PyCoder's Weekly: Type narrowing patterns that actually work", src: "src-pyweekly", cat: "Python", reason: "Solid examples — adopt the guard-clause pattern.", signal: "mid", tags: ["typing"] },
  { title: "Cloudflare adds Hyperdrive caching for Postgres", src: "src-cloudflare", cat: "Cloud/Infra", reason: "Edge-side query cache — re-evaluate your read replicas.", signal: "mid", tags: ["postgres", "edge"] },
  { title: "Hacker News: A founder's regret about microservices", src: "src-hn", cat: "Trending", reason: "Familiar lesson; useful link for a teammate who needs convincing.", signal: "low", tags: ["architecture"] },
  { title: "Simon Willison: SQLite as a deploy artifact", src: "src-simonw", cat: "Engineering", reason: "Distribution-as-database — applicable to small read-mostly apps.", signal: "mid", tags: ["sqlite"] },
  { title: "GitHub Trending: huggingface/smolagents quietly hits 10k", src: "src-gh-trending", cat: "Repositories", reason: "Minimal agent framework — useful baseline to compare against.", signal: "mid", tags: ["agents"] },
  { title: "Lobsters: A short rant about overusing Kafka", src: "src-lobsters", cat: "Trending", reason: "Skim the comments — the alternatives discussion is the real value.", signal: "low", tags: ["kafka"] },
  { title: "Real Python: Building a CLI with Typer and Rich", src: "src-realpython", cat: "Python", reason: "Tutorial-quality; good template for internal tooling.", signal: "low", tags: ["cli"] },
  { title: "Anthropic: Long-context retrieval benchmark", src: "src-anthropic", cat: "AI/LLM", reason: "Confirms intuition — RAG still beats long context for cost.", signal: "mid", tags: ["claude", "rag"] },
  { title: "LlamaIndex: Re-rankers compared head-to-head", src: "src-llamaindex", cat: "Agents", reason: "Useful for picking a re-ranker without burning a week on evals.", signal: "mid", tags: ["rag"] },
  { title: "OpenAI: Assistants API deprecation timeline confirmed", src: "src-oai", cat: "AI/LLM", reason: "Migration window is shorter than expected — start now.", signal: "high", tags: ["openai", "migration"] },
  { title: "AWS announces VPC Lattice global endpoints", src: "src-aws", cat: "Cloud/Infra", reason: "Cross-region service mesh; reduces a lot of glue code.", signal: "low", tags: ["aws", "networking"] },
  { title: "PyCoder's Weekly: The state of Python packaging in 2026", src: "src-pyweekly", cat: "Python", reason: "Annual landscape read; uv has effectively won.", signal: "mid", tags: ["packaging"] },
  { title: "Hacker News: Show HN — a markdown-first knowledge base in Rust", src: "src-hn", cat: "Trending", reason: "Pretty UI; worth borrowing the keyboard model.", signal: "low", tags: ["showhn"] },
];

function genBody(title: string, reason: string): string {
  return `## Overview

${reason} This article walks through the change in concrete terms, contrasts it with the previous behavior, and discusses migration paths for teams already running this in production.

## What changed

The maintainers introduced a focused set of changes that aim to reduce common friction without breaking existing call sites. The diff is small but the implications ripple through dependent libraries.

- Behavior is now consistent across sync and async code paths.
- The deprecated path emits a \`DeprecationWarning\` instead of failing silently.
- A new opt-in flag controls the strict variant for libraries that need it.

## Example

\`\`\`python
from project import Client

client = Client(strict=True)
result = client.run("payload")
assert result.ok
\`\`\`

The new \`strict=True\` flag is the recommended default for new code. Existing callers continue to work without changes, but will see warnings in the test suite.

## Why it matters

For most teams the practical impact is small but positive: less surprising behavior, fewer one-off workarounds, and a clearer mental model. If you maintain a library that wraps this API, plan to remove your compatibility shims within the next minor release.

## Notes from the field

A few engineers have reported edge cases around process forking and module reloading. The maintainers have acknowledged these and a follow-up patch is expected within two weeks. None of the reports indicate data loss.`;
}

const reasonsForLater = [3, 14, 27, 33];
const archivedIdx = [40, 48, 53];
const skippedIdx = [22, 38, 49];
const doneIdx = [1, 6, 11, 16, 19, 26, 31, 37, 42, 47, 50, 56];
const starredIdx = [0, 2, 4, 11, 19, 36, 41, 55];

export const ARTICLES: Article[] = TITLES.map((t, i) => {
  const src = SOURCES.find((s) => s.id === t.src)!;
  const ageHours = 0.5 + i * 1.7 + (i % 5) * 3;
  const published = now - ageHours * HOUR;
  const ingested = published + 8 * 60 * 1000;
  const bodyOk = t.bodyOk !== false;
  let state: WorkflowState = "today";
  let later_until: string | undefined;
  let done_at: string | undefined;
  let skipped_at: string | undefined;
  let archived_at: string | undefined;
  if (reasonsForLater.includes(i)) {
    state = "later";
    later_until = iso(now + (1 + (i % 3)) * DAY);
  } else if (doneIdx.includes(i)) {
    state = "done";
    done_at = iso(now - (i % 6) * HOUR - HOUR);
  } else if (skippedIdx.includes(i)) {
    state = "skipped";
    skipped_at = iso(now - (i % 4) * HOUR - HOUR);
  } else if (archivedIdx.includes(i)) {
    state = "archived";
    archived_at = iso(now - i * HOUR);
  }
  const starred = starredIdx.includes(i);
  return {
    id: `a-${String(i + 1).padStart(3, "0")}`,
    title: t.title,
    sourceId: src.id,
    sourceName: src.name,
    category: t.cat,
    url: `https://example.com/articles/${i + 1}`,
    publishedAt: iso(published),
    ingestedAt: iso(ingested),
    reason: t.reason,
    summary: `${t.reason} The piece dives into the practical implications, references prior art, and ends with concrete next steps the author recommends for teams currently running this in production.`,
    signal: t.signal,
    tags: t.tags,
    body: bodyOk ? genBody(t.title, t.reason) : undefined,
    bodyStatus: bodyOk ? "ok" : "error",
    state,
    starred,
    later_until,
    done_at,
    skipped_at,
    archived_at,
    starred_at: starred ? iso(now - (i + 1) * HOUR) : undefined,
  };
});

export const FEED_RUNS: FeedRun[] = [
  {
    id: "run-1",
    startedAt: iso(now - 12 * 60 * 1000),
    durationMs: 18_400,
    status: "ok",
    itemsFound: 126,
    itemsInserted: 38,
    perSource: SOURCES.slice(0, 10).map((s) => ({ sourceId: s.id, sourceName: s.name, found: s.itemsFetched, inserted: s.itemsInserted, status: "ok" })),
  },
  {
    id: "run-2",
    startedAt: iso(now - 1.2 * HOUR),
    durationMs: 22_100,
    status: "partial",
    itemsFound: 118,
    itemsInserted: 31,
    perSource: SOURCES.slice(0, 12).map((s, i) => ({ sourceId: s.id, sourceName: s.name, found: s.itemsFetched, inserted: s.itemsInserted, status: i === 11 ? "error" : "ok", error: i === 11 ? "Read timeout after 15s" : undefined })),
  },
  {
    id: "run-3",
    startedAt: iso(now - 2.3 * HOUR),
    durationMs: 19_900,
    status: "ok",
    itemsFound: 142,
    itemsInserted: 44,
    perSource: SOURCES.slice(0, 9).map((s) => ({ sourceId: s.id, sourceName: s.name, found: s.itemsFetched, inserted: s.itemsInserted, status: "ok" })),
  },
  {
    id: "run-4",
    startedAt: iso(now - 4.5 * HOUR),
    durationMs: 28_500,
    status: "error",
    itemsFound: 12,
    itemsInserted: 2,
    perSource: [
      { sourceId: "src-eng-cloudflare-edge", sourceName: "Cloudflare Workers Updates", found: 0, inserted: 0, status: "error", error: "HTTP 503 from upstream (3 consecutive failures)" },
    ],
  },
  {
    id: "run-5",
    startedAt: iso(now - 6 * HOUR),
    durationMs: 17_300,
    status: "ok",
    itemsFound: 108,
    itemsInserted: 29,
    perSource: SOURCES.slice(0, 8).map((s) => ({ sourceId: s.id, sourceName: s.name, found: s.itemsFetched, inserted: s.itemsInserted, status: "ok" })),
  },
];
