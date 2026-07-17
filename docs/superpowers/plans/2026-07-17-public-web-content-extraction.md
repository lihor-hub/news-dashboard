# Public Web Content Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one quality-gated extraction pipeline for static and JavaScript-rendered public pages and use it for lessons, article bodies, and URL ingestion.

**Architecture:** Add typed extraction results and deterministic candidate assessment in a focused module. Refactor `body_fetch.py` so static, Selenium, Crawl4AI, and optional AI stages report through one ordered orchestrator while `extract_body()` remains a compatibility wrapper. Migrate internal callers without changing public API response shapes.

**Tech Stack:** Python 3.14, stdlib `HTMLParser`/`urllib`, Selenium, Crawl4AI, pytest, PostgreSQL.

## Global Constraints

- PostgreSQL-only runtime behavior and psycopg parameter style remain unchanged.
- Publicly accessible web content only; do not add CAPTCHA, authentication, robots, or hard-paywall bypasses.
- Preserve current API response shapes and the user-facing `Could not extract readable article content.` message.
- Keep explicit byte caps and timeouts; no indefinite retries or parallel browser fallbacks.
- Never place URLs, domains, titles, or extracted content in metric labels.
- Live public-page probes are opt-in and never run in CI.
- Every production change follows red-green-refactor and is committed separately.

---

### Task 1: Typed Results and Candidate Quality

**Files:**
- Create: `backend/news_dashboard/content_extraction.py`
- Create: `backend/tests/test_content_extraction.py`

**Interfaces:**
- Produces: `ExtractionMethod`, `FailureReason`, `QualityEvidence`, `ExtractionAttempt`, `ExtractionResult`, and `assess_extracted_text(text: str) -> QualityEvidence`.
- Quality constants: 200 characters, 40 word-like tokens, and either two meaningful blocks or one block with at least 600 characters.

- [ ] **Step 1: Write failing tests for quality boundaries and typed results**

Cover empty text, a 49-character title, two meaningful paragraphs, one 600-character paragraph, known access-denied text, immutable attempt tuples, success construction, and failure construction. Assert exact rejection reason codes: `too_short`, `too_few_words`, `too_few_blocks`, and `failure_page`.

- [ ] **Step 2: Verify the tests fail because the module is absent**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_content_extraction.py`

Expected: collection fails with `ModuleNotFoundError: news_dashboard.content_extraction`.

- [ ] **Step 3: Implement the result model and assessor**

Use frozen dataclasses and literals:

```python
ExtractionMethod = Literal["static", "selenium", "crawl4ai", "ai"]
FailureReason = Literal[
    "unsafe_url", "not_found", "blocked", "fetch_failed",
    "non_html", "render_failed", "no_readable_content",
]

@dataclass(frozen=True)
class QualityEvidence:
    character_count: int
    word_count: int
    meaningful_block_count: int
    accepted: bool
    rejection_reasons: tuple[str, ...]

@dataclass(frozen=True)
class ExtractionAttempt:
    method: ExtractionMethod
    status: Literal["accepted", "rejected", "failed"]
    latency_ms: int
    quality: QualityEvidence | None = None
    failure_reason: FailureReason | None = None
    detail: str | None = None

@dataclass(frozen=True)
class ExtractionResult:
    status: Literal["ok", "error"]
    text: str
    method: ExtractionMethod | None
    quality: QualityEvidence | None
    attempts: tuple[ExtractionAttempt, ...]
    failure_reason: FailureReason | None
```

Normalize CRLF and blank-line runs before counting. Count meaningful blocks as non-empty blocks of at least 40 characters. Treat access-denied, CAPTCHA, sign-in-required, and bot-verification messages as failure pages only when they dominate a short candidate.

- [ ] **Step 4: Run the focused tests and refactor names without changing behavior**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_content_extraction.py`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/news_dashboard/content_extraction.py backend/tests/test_content_extraction.py
git commit -m "feat: score extracted web content quality (#1259)"
```

### Task 2: Separate Static and Rendered Extraction

**Files:**
- Modify: `backend/news_dashboard/body_fetch.py:281-399`
- Modify: `backend/news_dashboard/selenium_client.py:21-286`
- Test: `backend/tests/test_body_fetch.py`
- Test: `backend/tests/test_selenium_client.py`

**Interfaces:**
- Consumes: `assess_extracted_text()` and result types from Task 1.
- Produces: `_static_extract_body(url: str) -> tuple[str, str, FailureReason | None]` and `_selenium_extract_body(url: str) -> tuple[str, str]` with meaningful-content waiting.

- [ ] **Step 1: Add failing static extraction tests**

Add offline HTTP fixtures asserting that valid HTML succeeds, title-only HTML returns text but fails the shared quality gate, `text/plain` returns `non_html`, 404 returns `not_found`, and 403/429 return `blocked`. Keep the existing unsafe-URL test.

- [ ] **Step 2: Run the static tests and confirm expected failures**

Run the new node IDs from `backend/tests/test_body_fetch.py` with `pytest -q`.

Expected: failures because `extract_body()` does not expose classification and accepts title-only text.

- [ ] **Step 3: Extract the static stage**

Move the urllib fetch/parser portion into `_static_extract_body()`. Validate content type before decoding, classify `urllib.error.HTTPError` codes 404, 403, and 429, and preserve the 500 KB cap. Do not invoke Selenium from this helper.

- [ ] **Step 4: Add failing Selenium readiness tests**

In `test_selenium_client.py`, fake `WebDriverWait` and the driver so the wait condition observes short text first and meaningful text later. Assert that the condition does not succeed merely because a selector exists. Add final-URL validation coverage and retain cleanup/quit coverage.

- [ ] **Step 5: Implement meaningful DOM readiness**

Add a private wait predicate that inspects `article, main, .post-content, .entry-content, p`, joins visible text, and returns true only once `assess_extracted_text()` accepts it or the timeout expires. Validate `driver.current_url` after navigation and fail closed when it is unsafe. Do not add domain handlers or paywall logic.

- [ ] **Step 6: Run body-fetch and Selenium tests**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_body_fetch.py backend/tests/test_selenium_client.py`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/news_dashboard/body_fetch.py backend/news_dashboard/selenium_client.py backend/tests/test_body_fetch.py backend/tests/test_selenium_client.py
git commit -m "refactor: separate static and rendered extraction (#1259)"
```

### Task 3: Ordered Shared Extraction Pipeline

**Files:**
- Modify: `backend/news_dashboard/body_fetch.py:334-570`
- Test: `backend/tests/test_body_fetch.py`

**Interfaces:**
- Produces: `extract_public_content(url: str, *, user_id: int | None = None, allow_ai: bool = True) -> ExtractionResult`.
- Preserves: `extract_body(url: str) -> tuple[str, str]` as a static-plus-Selenium compatibility wrapper.

- [ ] **Step 1: Add failing orchestrator tests**

Test these exact sequences with patched stage helpers:

- accepted static candidate stops immediately;
- rejected title-only static candidate falls back to Selenium;
- failed Selenium falls back to Crawl4AI;
- failed Crawl4AI invokes AI only when `allow_ai=True`;
- AI is skipped when disabled;
- every attempt records method, outcome, latency, quality, and bounded detail;
- final failure prefers `unsafe_url`, `not_found`, or `blocked` over generic unreadable failure;
- AI output must pass the same quality gate.

- [ ] **Step 2: Run orchestrator tests and verify red**

Run the new `extract_public_content` node IDs with `pytest -q`.

Expected: import or assertion failures because the orchestrator does not exist.

- [ ] **Step 3: Implement sequential orchestration**

Call `_static_extract_body`, `_selenium_extract_body`, `_crawl4ai_extract_body`, and `_ai_extract_body` in order. Measure each attempt with `time.monotonic()`, assess every non-empty candidate, return the first accepted result, and retain only bounded status detail—not extracted text—in attempts.

Make `extract_body()` call the shared internal runner with Crawl4AI and AI disabled, returning only `(text, "ok")` or `("", "error")` for compatibility.

- [ ] **Step 4: Run all body-fetch tests**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_body_fetch.py backend/tests/test_content_extraction.py`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/news_dashboard/body_fetch.py backend/tests/test_body_fetch.py
git commit -m "feat: add layered public content extraction (#1259)"
```

### Task 4: Migrate Lessons, Articles, and Ingestion

**Files:**
- Modify: `backend/news_dashboard/learn_from_link/service.py:18,1555-1594`
- Modify: `backend/news_dashboard/body_fetch.py:534-570`
- Modify: `backend/news_dashboard/ingest/service.py:320-355`
- Test: `backend/tests/test_learn_from_link.py`
- Test: `backend/tests/test_learn_from_link_agent_runs.py`
- Test: `backend/tests/test_body_fetch.py`
- Test: `backend/tests/test_hf_blog_ingest.py`

**Interfaces:**
- Consumes: `extract_public_content()` from Task 3.
- Lesson extraction persists a JSON-safe summary of method, quality, attempts, and failure reason in the existing extraction agent-run step without changing public lesson responses.

- [ ] **Step 1: Add failing lesson integration tests**

Patch `extract_public_content()` to return a successful Selenium result and assert the lesson stores the text and completes. Return a blocked failure and assert the existing user-facing message remains unchanged while the agent-run extraction error includes `failure_reason=blocked` and no source body.

- [ ] **Step 2: Add failing article and ingestion tests**

Assert article fetching calls the shared pipeline once, retains caching and translation, and passes `user_id`. Assert ingestion uses `allow_ai=False` and accepts a rendered result.

- [ ] **Step 3: Run the focused integration tests and verify red**

Run the named lesson, body-fetch, and ingestion tests with `pytest -q`.

Expected: failures because callers still invoke `extract_body()` and manually chain fallbacks.

- [ ] **Step 4: Migrate callers**

Replace lesson and article manual extraction with `extract_public_content()`. Add a small serializer for attempt diagnostics containing only method, status, latency, counts, reason codes, and bounded detail. Use `allow_ai=False` from ingestion. Keep public response fields, cache columns, translation, and failure copy unchanged.

- [ ] **Step 5: Run affected suites**

Run:

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -q \
  backend/tests/test_learn_from_link.py \
  backend/tests/test_learn_from_link_agent_runs.py \
  backend/tests/test_body_fetch.py \
  backend/tests/test_hf_blog_ingest.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/news_dashboard/learn_from_link/service.py backend/news_dashboard/body_fetch.py backend/news_dashboard/ingest/service.py backend/tests
git commit -m "feat: share extraction across lessons and articles (#1259)"
```

### Task 5: Opt-in Live Corpus and Complete Verification

**Files:**
- Create: `scripts/check_live_content_extraction.py`
- Modify: `docs/superpowers/specs/2026-07-17-public-web-content-extraction-design.md`
- Test: `backend/tests/test_live_content_extraction_script.py`

**Interfaces:**
- Script accepts zero or more URLs and prints one line per URL with status, method, character count, quality decision, elapsed milliseconds, and failure reason.
- Default corpus contains Cap'n Proto, React Thinking in React, MDN DOM, GitHub Blog RAG, Cloudflare AI Platform, and Quotes to Scrape JS.

- [ ] **Step 1: Write a failing script-unit test**

Import the script module, patch `extract_public_content`, and assert deterministic tabular output without performing network access. Assert the module performs no work at import time.

- [ ] **Step 2: Run the script test and verify red**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_live_content_extraction_script.py`

Expected: module-not-found failure.

- [ ] **Step 3: Implement the opt-in runner**

Use `argparse`; run only under `if __name__ == "__main__"`; return a nonzero exit code only for script/runtime errors, not individual public-page extraction failures. Include no credentials and write no files.

- [ ] **Step 4: Run deterministic tests and the live corpus**

Run:

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -q backend/tests/test_live_content_extraction_script.py
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=backend python scripts/check_live_content_extraction.py
```

Expected: deterministic test passes; live output reports each URL without an unhandled exception. Record public-page failures as residual evidence rather than weakening tests.

- [ ] **Step 5: Update the design status**

Change the spec status from `Draft for implementation review` to `Implemented` and add the live-corpus command under rollout verification.

- [ ] **Step 6: Run repository gates**

Run:

```bash
PATH="$PWD/.venv/bin:$PATH" make lint
PATH="$PWD/.venv/bin:$PATH" make typecheck
PATH="$PWD/.venv/bin:$PATH" PGOPTIONS='-c max_parallel_workers_per_gather=0' dotenv run -- make test
```

Expected: lint, mypy, ty, pyrefly, backend pytest, frontend tests, and build all pass.

- [ ] **Step 7: Review, rebase, and ship**

Review the diff against issue #1259 and the approved spec. Fix confirmed findings, fetch and rebase on `origin/main`, rerun gates if the base changed, push without bypassing hooks, open a PR containing `Closes #1259`, enable squash auto-merge, watch required CI, and confirm the issue closes and remote branch is deleted.
