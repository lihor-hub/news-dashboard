# Public Web Content Extraction Design

**Issue:** [#1259](https://github.com/lihor-hub/news-dashboard/issues/1259)
**Status:** Implemented
**Date:** 2026-07-17

## Problem

Link-to-lesson generation accepts a URL only when the basic body extractor returns
non-empty text. That extractor parses static HTML and invokes Selenium only when
the static result is completely empty. A low-quality result, such as a page title
without its article, is therefore accepted and sent to lesson synthesis. The
article reader has additional Crawl4AI and optional AI fallbacks, but the lesson
pipeline does not use them.

The behavior is inconsistent across features and does not expose which extraction
method succeeded or why all methods failed.

## Goals

- Reliably extract meaningful text from ordinary public static pages and
  JavaScript-rendered public pages.
- Reject technically non-empty but unusable results before lesson synthesis.
- Give lessons, article reading, ingestion, and sharing the same extraction
  behavior.
- Keep fast static extraction as the normal path and pay browser or AI costs only
  when needed.
- Preserve URL-safety checks, download limits, timeouts, and bounded resource use
  at every stage.
- Record the successful method, quality evidence, latency, and structured failure
  reason for diagnostics.
- Cover behavior deterministically without making CI depend on public websites.

## Non-goals

- Bypassing authentication, CAPTCHAs, robots restrictions, or hard paywalls.
- Guaranteeing extraction from every URL or every file format.
- Treating CSS layout as article content. Browser rendering is needed for DOM
  changes made by JavaScript; stylesheets are not required for plain-text
  extraction unless a site fails to render without them.
- Adding PDF, audio, video, image OCR, or document-file extraction in this change.
- Maintaining a large catalog of domain-specific scraper adapters.

## Evidence from the Public-Page Probe

The current lesson extraction path was exercised against a small public corpus:

| Page type | Example | Result |
| --- | --- | --- |
| Static technical site | `https://capnproto.org/` | 5,674 characters, static |
| Server-rendered application docs | React and MDN | 17,000+ characters, static |
| Documentation with nested navigation | Python tutorial | Only a 49-character title was accepted |
| Encyclopedia | Wikipedia | 8,211 characters, static |
| JavaScript-only demo | `https://quotes.toscrape.com/js/` | 1,229 characters via Selenium |
| Technical blogs | GitHub Blog and Cloudflare Blog | 8,000+ characters, static |
| Listing pages | Ars Technica Science and Hacker News | Text extracted, but not necessarily a single article |
| Missing page | Incorrect GitHub Blog URL | HTTP 404, extraction error |

This corpus is exploratory evidence, not a permanent compatibility contract.

## Considered Approaches

### Layered, quality-gated extraction — selected

Try bounded static extraction first, assess the candidate, and invoke rendered or
AI fallbacks only when quality is inadequate. This preserves the common fast path
while supporting JavaScript applications and producing actionable diagnostics.

### Always render with Selenium

This handles client-rendered pages but adds seconds of latency and substantial
CPU/memory cost to every request. It still cannot solve authentication, CAPTCHAs,
or inaccessible source content.

### Domain-specific adapters

Adapters can improve a few strategic sites but become a brittle maintenance
burden. A small adapter hook may remain available, but adapters are not the core
reliability strategy.

## Architecture

### Shared result model

Introduce an internal typed extraction result with these fields:

- `status`: success or failure.
- `text`: normalized extracted text on success.
- `method`: `static`, `selenium`, `crawl4ai`, or `ai`.
- `quality`: character count, word count, meaningful block count, and the reasons
  a candidate was accepted or rejected.
- `attempts`: ordered method, outcome, latency, and safe diagnostic detail for
  each attempted stage.
- `failure_reason`: one of `unsafe_url`, `not_found`, `blocked`, `fetch_failed`,
  `non_html`, `render_failed`, or `no_readable_content`.

URLs and extracted content must not be added to metric labels. Logs may retain the
repository's existing URL logging behavior, while persisted agent-run errors stay
bounded and contain no article body.

Existing tuple-returning helpers may remain as compatibility wrappers while
callers migrate to the shared result.

### Pipeline

1. Validate the URL before any network or browser operation.
2. Fetch static content with the existing byte cap, timeout, redirect safety, and
   user agent.
3. Reject unsupported content types and classify HTTP outcomes where available.
4. Parse static HTML into candidate text and quality evidence.
5. Return immediately when the candidate passes the quality gate.
6. Otherwise render the page with Selenium, wait for meaningful DOM content, and
   reassess the rendered candidate with the same quality gate.
7. If rendered extraction fails or remains inadequate, use Crawl4AI only when
   it can enforce the same per-request network boundary. Otherwise record that
   stage as unavailable and fail closed instead of launching its browser.
8. If configured and permitted by the caller, use the existing AI extractor as
   the final fallback. Its output must pass the same quality gate.
9. Return the best successful candidate or a structured failure containing all
   bounded attempt diagnostics.

Fallback stages are sequential to cap resource usage. Browser instances are
always closed by their context manager.

### Candidate quality gate

The gate must be deterministic and conservative. It will use normalized character
count, word count, meaningful block count, and known failure-page signals. The
initial acceptance policy is:

- at least 200 normalized characters;
- at least 40 word-like tokens;
- either two meaningful text blocks or at least 600 characters in one block; and
- no dominant known error, consent, access-denied, CAPTCHA, or authentication
  message.

The parser must preserve block information long enough to make this assessment.
The thresholds are module constants with focused boundary tests, not user-facing
configuration in this change. Successful AI output is assessed identically.

Listing pages may pass when they contain substantial readable text. Determining
whether a URL semantically represents one article is outside this change; the
lesson title and synthesis stages remain responsible for describing the supplied
source accurately.

### Selenium behavior

Selenium remains a fallback, not the default. It will:

- validate the URL before navigation and intercept every HTTP(S) request before
  dispatch, covering redirects, subresources, and JavaScript navigation;
- use the existing page-load and script timeouts;
- wait until a candidate selector contains enough text to have a chance of
  passing the quality gate, instead of waiting only for the first matching tag;
- stop loading and inspect the partial DOM after a bounded navigation timeout;
- run existing consent and overlay cleanup for public content;
- return rendered HTML for the shared parser and quality gate; and
- fail closed if Chrome is unavailable or rendering raises an error.

The implementation must not add new paywall bypasses. Existing domain handlers
are not expanded by this project.

### Caller integration

- Link-to-lesson extraction uses the shared pipeline and persists method, latency,
  quality summary, and structured failure reason in its extraction agent step.
- Article body fetching uses the same pipeline and keeps its existing body cache
  and translation behavior.
- URL ingestion uses the shared non-AI path unless its current call site already
  authorizes AI use.
- Sharing continues to inherit extraction through article body fetching.

User-facing failure text remains concise. Internally distinguish blocked,
unsupported, missing, unsafe, and unreadable sources so future UI work can offer
better guidance without reparsing log messages.

## Safety and Resource Limits

- Every network-capable stage performs the existing SSRF validation before work.
- Redirect targets remain subject to the safe server-fetch implementation.
- Browser navigation must not weaken the private-network boundary. If Selenium
  cannot enforce redirect safety equivalently, rendered fallback must be denied
  for URLs whose resolved navigation cannot be validated.
- Static and AI HTML downloads keep explicit byte caps.
- Browser and extraction stages keep explicit timeouts and never retry
  indefinitely.
- No extracted article text, URL, or user data is placed in Prometheus labels.

## Testing

### Deterministic offline tests

Add fixtures for:

- ordinary static articles;
- void elements and nested excluded containers;
- title-only and navigation-only false positives;
- a client-rendered shell whose DOM becomes meaningful after JavaScript;
- redirects to safe and unsafe targets;
- malformed HTML;
- consent overlays and partial DOM after timeout;
- HTTP 404, 403, and 429 classification;
- non-HTML content types;
- missing browser support and render failure;
- quality thresholds and known failure-page signals;
- ordered fallback, early success, attempt diagnostics, and AI opt-in behavior;
- consistent lesson, article-reader, ingestion, and sharing integration.

Tests must stub external network access. Browser integration tests use a local
HTTP server and a minimal JavaScript fixture.

### Opt-in live smoke corpus

Provide a non-CI script or explicitly marked test for a small documented corpus of
stable public pages representing static documentation, blogs, and a JavaScript-only
demo. It reports method, character count, quality decision, latency, and failure
reason. Live failures are diagnostic and do not gate CI because public pages change.

## Observability

Record per-attempt method, status, and latency through the existing lesson agent
run step. Add low-cardinality counters by method and failure reason only if the
current metrics conventions support them; never label metrics with a URL, domain,
title, or content. Logs should state why a candidate was rejected without logging
the candidate body.

## Rollout and Compatibility

- Keep current public API response shapes and user-facing error text compatible.
- Preserve `extract_body()` as a compatibility wrapper until all internal callers
  are migrated.
- Land the shared pipeline and tests in one PR tied to issue #1259.
- Validate locally with lint, all configured type checkers, the PostgreSQL-backed
  backend suite, frontend tests, and the opt-in live smoke corpus.
- Run the opt-in corpus with
  `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=backend python scripts/check_live_content_extraction.py`.
- Queue the PR for auto-merge only after required CI succeeds.

## Acceptance Criteria

- The Cap'n Proto page and the JavaScript-only local fixture produce meaningful
  content through the appropriate extraction method.
- A title-only static response is rejected and triggers rendered fallback.
- Lessons and article body fetching use the same ordered pipeline.
- Successful results identify their method and carry quality evidence.
- Failures carry a structured reason and bounded attempt diagnostics.
- SSRF validation, byte caps, timeouts, and no-content-in-metric-label rules remain
  intact across every stage.
- Deterministic tests cover the fallback order and representative failure modes.
- The live corpus runner is opt-in and excluded from CI.
- Repository lint, type checks, tests, required CI, and merge queue pass.
