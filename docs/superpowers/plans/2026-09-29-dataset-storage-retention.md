# Dataset Storage Statistics and Article Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PostgreSQL dataset/storage observability and safe, opt-in daily article retention to the existing administrator Stats and Scheduler pages.

**Architecture:** Extend the existing `stats` and `scheduler` feature modules, with retention SQL isolated in `scheduler/retention.py`. Expose typed admin APIs, render focused React child components on the existing pages, and reuse APScheduler plus scheduled-job history for daily/manual cleanup.

**Tech Stack:** Python 3.14, FastAPI, psycopg/PostgreSQL 16, APScheduler, React, TypeScript, Recharts, Vitest/Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-dataset-storage-retention-design.md`

## Global Constraints

- Runtime database support is PostgreSQL only, using psycopg `%s` parameters.
- Retention is instance-wide, stored in `settings`, disabled by default, and accepts only null or an integer of at least one day.
- Article age always uses `articles.discovered_at`.
- Cleanup runs at 03:30 UTC in batches of at most 500 and is serialized by a PostgreSQL advisory lock.
- Saving a policy never deletes; manual cleanup requires explicit UI confirmation.
- Protected articles include starred state, highlights, tags, briefing citations, shares, and canonical targets.
- Deletion makes PostgreSQL space reusable; the UI must not promise immediate database-file shrinkage.

## Review Focus

- Empty databases return zero/null metrics without division, percentile, or date-range errors; Task 1 tests this.
- Invalid, zero, negative, empty, or malformed retention values cannot accidentally enable deletion; Task 2 tests this.
- Preview and deletion share the same protection predicate, including canonical references and every durable user reference; Task 2 tests each rule.
- Two cleanup invocations cannot race; Task 2 tests advisory-lock contention as a skipped result.
- UI state remains truthful when fetching, saving, cleanup, or range reload fails; Tasks 4 and 5 test these states.

---

### Task 1: Dataset and storage metrics API

**Files:**
- Modify: `backend/news_dashboard/stats/models.py`
- Modify: `backend/news_dashboard/stats/service.py`
- Modify: `backend/news_dashboard/stats/router.py`
- Modify: `backend/tests/test_stats.py`
- Modify: `backend/tests/test_stats_api.py`

**Interfaces:**
- Produces: `dataset_stats(range_key: DatasetRange, database_url: str | None = None) -> dict[str, Any]`.
- Produces: admin `GET /api/stats/dataset?range=30d|90d|1y|all` with `summary`, `storage`, `trend`, and `retention_preview` fields.
- Consumes later: Task 4 uses the response shape through the frontend API type.

- [ ] **Step 1: Write failing service tests** for empty/populated summary values, PostgreSQL byte metrics, median row size, amortized size, and daily/weekly/monthly trend buckets.
- [ ] **Step 2: Run `source .env && pytest backend/tests/test_stats.py -q`** and confirm failures are caused by missing dataset metrics.
- [ ] **Step 3: Implement the range enum/model and `dataset_stats`** with PostgreSQL catalog functions and `generate_series`-based zero-filled bounded trends.
- [ ] **Step 4: Run the focused service tests** and confirm they pass.
- [ ] **Step 5: Write failing API tests** for admin success, invalid range validation, and non-admin rejection.
- [ ] **Step 6: Add the typed admin route and run `source .env && pytest backend/tests/test_stats_api.py -q`** until green.
- [ ] **Step 7: Commit** with `feat: add dataset storage metrics api`.

### Task 2: Retention policy, preview, and cleanup service

**Files:**
- Create: `backend/news_dashboard/scheduler/retention.py`
- Modify: `backend/news_dashboard/scheduler/models.py`
- Modify: `backend/news_dashboard/scheduler/router.py`
- Create: `backend/tests/test_article_retention.py`
- Modify: `backend/tests/test_scheduler.py`

**Interfaces:**
- Produces: `get_retention_days(database_url: str | None = None) -> int | None`.
- Produces: `set_retention_days(days: int | None, database_url: str | None = None) -> int | None`.
- Produces: `retention_preview(days: int | None = None, database_url: str | None = None) -> RetentionPreview`.
- Produces: `cleanup_old_articles(database_url: str | None = None, batch_size: int = 500) -> CleanupResult`.
- Produces: admin GET/PUT `/api/scheduler/article-retention` and POST `/api/scheduler/article-retention/run`.
- Consumes: Task 1 includes `retention_preview()` in dataset metrics; Task 3 schedules `cleanup_old_articles()`; Task 5 consumes the API.

- [ ] **Step 1: Write failing policy tests** for absent/default, null, positive, malformed, zero, and negative values using PostgreSQL `settings`.
- [ ] **Step 2: Run the focused tests** and confirm missing interfaces fail.
- [ ] **Step 3: Implement policy parsing/persistence** without changing the generic settings helpers.
- [ ] **Step 4: Write failing preview/cleanup tests** for `discovered_at`, eligible payload bytes, idempotency, 500-row batching, advisory-lock contention, and each protection relation.
- [ ] **Step 5: Implement a shared candidate CTE/predicate**, preview aggregation, advisory locking, and bounded batch deletion.
- [ ] **Step 6: Run `source .env && pytest backend/tests/test_article_retention.py -q`** until green.
- [ ] **Step 7: Write failing scheduler API tests** for authorization, validation, save-without-delete, disabled manual run, and successful manual run.
- [ ] **Step 8: Add Pydantic models and routes**, recording manual execution in scheduled-job history.
- [ ] **Step 9: Run focused scheduler/API tests** and commit with `feat: add article retention policy and cleanup`.

### Task 3: Daily scheduled cleanup

**Files:**
- Modify: `backend/news_dashboard/scheduler/service.py`
- Modify: `backend/tests/test_scheduler.py`
- Modify: `frontend/src/pages/SchedulerPage.tsx`
- Modify: `frontend/src/__tests__/schedulerPage.test.tsx`

**Interfaces:**
- Consumes: Task 2 `cleanup_old_articles()` and result fields.
- Produces: APScheduler job id/history name `article_retention` at hour `3`, minute `30` UTC.

- [ ] **Step 1: Add failing scheduler tests** for 03:30 registration, disabled-policy skipped result, successful summary, and failure recording.
- [ ] **Step 2: Run focused scheduler tests** and confirm the missing job fails.
- [ ] **Step 3: Implement `_run_article_retention`, `_job_article_retention`, and registration** through the existing `_run_and_record` wrapper.
- [ ] **Step 4: Add `article_retention` to the Scheduler job label map** and its rendering test.
- [ ] **Step 5: Run backend scheduler and frontend scheduler tests** and commit with `feat: schedule daily article retention`.

### Task 4: Dataset section on Stats

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/stats.ts`
- Create: `frontend/src/components/stats/DatasetOverview.tsx`
- Modify: `frontend/src/pages/StatsPage.tsx`
- Modify: `frontend/src/__tests__/api.test.ts`
- Modify: `frontend/src/__tests__/statsSettingsRunsPages.test.tsx`

**Interfaces:**
- Consumes: Task 1 dataset endpoint.
- Produces: `fetchDatasetStats(range: DatasetRange): Promise<DatasetStats>` and the range-aware dataset panel.

- [ ] **Step 1: Add failing API tests** for range query serialization and typed response use.
- [ ] **Step 2: Implement frontend dataset types and API client** and run the API test.
- [ ] **Step 3: Add failing component/page tests** for all metrics, byte formatting, empty dates, range selection, loading, and error preservation.
- [ ] **Step 4: Implement `DatasetOverview` and integrate it into `StatsPage`**, keeping existing charts intact.
- [ ] **Step 5: Run focused Vitest tests** and commit with `feat: show dataset storage statistics`.

### Task 5: Retention controls on Scheduler

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/scheduler.ts`
- Create: `frontend/src/components/scheduler/ArticleRetentionCard.tsx`
- Modify: `frontend/src/pages/SchedulerPage.tsx`
- Modify: `frontend/src/__tests__/api.test.ts`
- Modify: `frontend/src/__tests__/schedulerPage.test.tsx`

**Interfaces:**
- Consumes: Task 2 retention endpoints.
- Produces: fetch/update/run API functions and the retention configuration card.

- [ ] **Step 1: Add failing frontend API tests** for GET, nullable PUT, numeric PUT, and POST cleanup requests.
- [ ] **Step 2: Implement retention types and API functions** and run focused API tests.
- [ ] **Step 3: Add failing UI tests** for keep forever, numeric save without cleanup, preview values, disabled manual action, confirmation/cancel, success refresh, and request failures.
- [ ] **Step 4: Implement `ArticleRetentionCard` and integrate it into Scheduler**, using the existing button/input/dialog/toast primitives.
- [ ] **Step 5: Run focused scheduler page tests** and commit with `feat: manage article retention in scheduler`.

### Task 6: Full verification and delivery

**Files:**
- Modify only files required by confirmed review or verification findings.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a verified, review-ready branch and merged pull request closing issue #1500.

- [ ] **Step 1: Bootstrap/check the PostgreSQL test environment** with `scripts/bootstrap-worktree.sh` if dependencies are missing, verify `nd-test-pg`, source `.env`, and set `PGOPTIONS='-c max_parallel_workers_per_gather=0'`.
- [ ] **Step 2: Run backend gates**: `make lint`, `make typecheck`, and `source .env && make test`.
- [ ] **Step 3: Run frontend gates**: `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run test:frontend`, and `npm run build`.
- [ ] **Step 4: Verify the administrator flows in the running app**: Stats range changes, retention save, confirmation cancellation, and a no-op/manual cleanup result.
- [ ] **Step 5: Review the working diff once**, fix confirmed findings, and rerun affected gates.
- [ ] **Step 6: Rebase on `origin/main`, rerun gates if the base changed, push, and open a PR with `Closes #1500` and the required generated-code trailer.
- [ ] **Step 7: Attach the PR artifact, enable squash auto-merge, watch required checks, repair owned failures, and confirm merge plus issue closure.
