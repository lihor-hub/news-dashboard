# Manual Duplicate Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only manual "Remove duplicates" action that runs the existing embedding deduplication job immediately while preserving the scheduled hourly job.

**Architecture:** Keep deduplication behavior centralized in `news_dashboard.embedding_dedup.run_embedding_dedup`. Add a scheduler service wrapper that records a normal `embedding_dedup` job-history row, expose it through the existing scheduler router, and connect the Schedule page button to the new endpoint.

**Tech Stack:** FastAPI, PostgreSQL/psycopg, pytest, React, TypeScript, Vitest, Testing Library.

## Global Constraints

- Runtime code must use PostgreSQL-specific SQL and psycopg parameter style.
- Do not add SQLite runtime fallbacks, database-type sniffing, placeholder translation layers, or generic multi-database SQL.
- Duplicate articles are archived and linked to their canonical article; they are never hard-deleted.
- Preserve the existing embedding dedup candidate window, similarity threshold, source-visibility boundaries, and triaged-article protections.
- Require administrator authentication through `require_admin`.
- Do not introduce additional dependencies or configuration.
- Hourly APScheduler registration and `EMBEDDING_DEDUP_INTERVAL_MINUTES` remain unchanged.

---

## File Structure

- `backend/news_dashboard/scheduler/service.py`: add `run_embedding_dedup_now()` and make `_run_and_record()` return the recorded outcome so manual runs can reuse the same history path.
- `backend/news_dashboard/scheduler/router.py`: add `POST /api/scheduler/jobs/embedding-dedup/run`.
- `backend/tests/test_scheduler.py`: cover manual service success and failure.
- `backend/tests/test_scheduled_job_history.py`: cover the admin route payload and OpenAPI presence.
- `frontend/src/api/scheduler.ts`: add `EmbeddingDedupResult` and `runEmbeddingDedup()`.
- `frontend/src/__tests__/api.test.ts`: cover the exact POST endpoint.
- `frontend/src/pages/SchedulerPage.tsx`: add state, button, toast, and history refresh.
- `frontend/src/__tests__/schedulerPage.test.tsx`: cover clicking the manual cleanup action and pending state.

### Task 1: Backend Manual Service

**Files:**
- Modify: `backend/news_dashboard/scheduler/service.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Produces: `run_embedding_dedup_now() -> dict[str, int | str]`
- Reuses: `_run_embedding_dedup() -> tuple[str, str | None]`
- Reuses: `_run_and_record(job_name: str, fn: Callable[[], tuple[str, str | None] | None]) -> tuple[str, str | None] | None`

- [ ] **Step 1: Write failing service tests**

Add imports in `backend/tests/test_scheduler.py`:

```python
from news_dashboard.scheduler.service import (
    _run_briefing,
    _run_per_user_briefings,
    _run_weekly_lesson_recaps,
    _run_weekly_recaps,
    run_embedding_dedup_now,
)
```

Add tests near other scheduler service tests:

```python
def test_run_embedding_dedup_now_records_history_and_returns_counts() -> None:
    summary = {"embedded": 4, "merged": 2}

    with (
        patch("news_dashboard.embedding_dedup.run_embedding_dedup", return_value=summary),
        patch("news_dashboard.scheduled_job_history.save_job_run") as save_job_run,
    ):
        result = run_embedding_dedup_now()

    assert result == {"status": "success", "embedded": 4, "merged": 2}
    save_job_run.assert_called_once()
    assert save_job_run.call_args.kwargs["job_name"] == "embedding_dedup"
    assert save_job_run.call_args.kwargs["status"] == "success"
    assert save_job_run.call_args.kwargs["message"] == "embedded=4 merged=2"
```

```python
def test_run_embedding_dedup_now_records_failure_and_raises() -> None:
    with (
        patch(
            "news_dashboard.embedding_dedup.run_embedding_dedup",
            side_effect=RuntimeError("embedding service unavailable"),
        ),
        patch("news_dashboard.scheduled_job_history.save_job_run") as save_job_run,
    ):
        with pytest.raises(RuntimeError, match="embedding service unavailable"):
            run_embedding_dedup_now()

    save_job_run.assert_called_once()
    assert save_job_run.call_args.kwargs["job_name"] == "embedding_dedup"
    assert save_job_run.call_args.kwargs["status"] == "failure"
    assert save_job_run.call_args.kwargs["message"] == "embedding service unavailable"
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
source .env && pytest backend/tests/test_scheduler.py \
  -k 'run_embedding_dedup_now' -q
```

Expected: FAIL because `run_embedding_dedup_now` does not exist.

- [ ] **Step 3: Implement the service wrapper**

In `backend/news_dashboard/scheduler/service.py`, change `_run_and_record()` to return `result`, re-raise only when instructed, and add `run_embedding_dedup_now()`:

```python
def _run_and_record(
    job_name: str,
    fn: Callable[[], tuple[str, str | None] | None],
    *,
    raise_on_failure: bool = False,
) -> tuple[str, str | None] | None:
    ...
    try:
        result = fn()
    except Exception as exc:
        result = ("failure", str(exc)[:500])
        captured_exc = exc
    else:
        captured_exc = None
    if result is None:
        return None
    ...
    if captured_exc is not None and raise_on_failure:
        raise captured_exc
    return result
```

```python
def run_embedding_dedup_now() -> dict[str, int | str]:
    status, message = _run_and_record(
        "embedding_dedup",
        _run_embedding_dedup,
        raise_on_failure=True,
    ) or ("success", "embedded=0 merged=0")
    embedded = 0
    merged = 0
    if message:
        parts = dict(part.split("=", 1) for part in message.split() if "=" in part)
        embedded = int(parts.get("embedded", "0"))
        merged = int(parts.get("merged", "0"))
    return {"status": status, "embedded": embedded, "merged": merged}
```

- [ ] **Step 4: Run tests and confirm green**

Run:

```bash
source .env && pytest backend/tests/test_scheduler.py \
  -k 'run_embedding_dedup_now' -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/news_dashboard/scheduler/service.py backend/tests/test_scheduler.py
git commit -m "feat: add manual embedding dedup service"
```

### Task 2: Backend Admin Route

**Files:**
- Modify: `backend/news_dashboard/scheduler/router.py`
- Test: `backend/tests/test_scheduled_job_history.py`

**Interfaces:**
- Consumes: `run_embedding_dedup_now() -> dict[str, int | str]`
- Produces: `POST /api/scheduler/jobs/embedding-dedup/run`

- [ ] **Step 1: Write failing route tests**

Add:

```python
def test_manual_embedding_dedup_route_runs_for_admin(client: TestClient) -> None:
    with patch(
        "news_dashboard.scheduler.router.run_embedding_dedup_now",
        return_value={"status": "success", "embedded": 4, "merged": 2},
    ) as run:
        resp = client.post("/api/scheduler/jobs/embedding-dedup/run")

    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "embedded": 4, "merged": 2}
    run.assert_called_once_with()
```

```python
def test_manual_embedding_dedup_route_surfaces_failure(client: TestClient) -> None:
    with patch(
        "news_dashboard.scheduler.router.run_embedding_dedup_now",
        side_effect=RuntimeError("embedding service unavailable"),
    ):
        resp = client.post("/api/scheduler/jobs/embedding-dedup/run")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "duplicate cleanup failed"
```

```python
def test_manual_embedding_dedup_route_is_in_openapi(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/scheduler/jobs/embedding-dedup/run" in resp.json()["paths"]
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
source .env && pytest backend/tests/test_scheduled_job_history.py \
  -k 'manual_embedding_dedup_route' -q
```

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement the route**

In `backend/news_dashboard/scheduler/router.py`, import `run_embedding_dedup_now` and add:

```python
@router.post("/api/scheduler/jobs/embedding-dedup/run", dependencies=_admin_dep)
def scheduler_run_embedding_dedup() -> dict[str, int | str]:
    try:
        return run_embedding_dedup_now()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="duplicate cleanup failed") from exc
```

- [ ] **Step 4: Run tests and confirm green**

Run:

```bash
source .env && pytest backend/tests/test_scheduled_job_history.py \
  -k 'manual_embedding_dedup_route' -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/news_dashboard/scheduler/router.py backend/tests/test_scheduled_job_history.py
git commit -m "feat: expose manual duplicate cleanup endpoint"
```

### Task 3: Frontend API Helper

**Files:**
- Modify: `frontend/src/api/scheduler.ts`
- Test: `frontend/src/__tests__/api.test.ts`

**Interfaces:**
- Produces: `runEmbeddingDedup(): Promise<EmbeddingDedupResult>`
- Produces type: `EmbeddingDedupResult = { status: 'success'; embedded: number; merged: number }`

- [ ] **Step 1: Write failing API test**

Add to `frontend/src/__tests__/api.test.ts`:

```typescript
it('runEmbeddingDedup POSTs to the manual duplicate cleanup endpoint', async () => {
  fetchMock.mockResponseOnce(JSON.stringify({ status: 'success', embedded: 4, merged: 2 }));
  const result = await api.runEmbeddingDedup();
  expect(fetchMock).toHaveBeenCalledWith('/api/scheduler/jobs/embedding-dedup/run', {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  expect(result).toEqual({ status: 'success', embedded: 4, merged: 2 });
});
```

- [ ] **Step 2: Run test and confirm red**

Run:

```bash
npm test -- --run frontend/src/__tests__/api.test.ts -t runEmbeddingDedup
```

Expected: FAIL because `runEmbeddingDedup` does not exist.

- [ ] **Step 3: Implement helper**

In `frontend/src/api/scheduler.ts`, add:

```typescript
export interface EmbeddingDedupResult {
  status: 'success';
  embedded: number;
  merged: number;
}

export async function runEmbeddingDedup(): Promise<EmbeddingDedupResult> {
  return requestJson<EmbeddingDedupResult>('/api/scheduler/jobs/embedding-dedup/run', {
    method: 'POST',
  });
}
```

- [ ] **Step 4: Run test and confirm green**

Run:

```bash
npm test -- --run frontend/src/__tests__/api.test.ts -t runEmbeddingDedup
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/scheduler.ts frontend/src/__tests__/api.test.ts
git commit -m "feat: add duplicate cleanup api client"
```

### Task 4: Scheduler Page Manual Action

**Files:**
- Modify: `frontend/src/pages/SchedulerPage.tsx`
- Test: `frontend/src/__tests__/schedulerPage.test.tsx`

**Interfaces:**
- Consumes: `runEmbeddingDedup(): Promise<EmbeddingDedupResult>`
- Behavior: Button text `Remove duplicates`; pending text `Removing duplicates...`; success toast reports `merged` and `embedded`; calls `fetchLatestJobRuns()` again after success.

- [ ] **Step 1: Write failing page tests**

Add `runEmbeddingDedup: vi.fn()` to the API mock.

Add:

```typescript
it('runs duplicate cleanup and refreshes job history', async () => {
  apiMock.runEmbeddingDedup.mockResolvedValue({ status: 'success', embedded: 4, merged: 2 });
  render(<SchedulerPage />);

  await userEvent.click(await screen.findByRole('button', { name: 'Remove duplicates' }));

  await waitFor(() => expect(apiMock.runEmbeddingDedup).toHaveBeenCalledOnce());
  expect(apiMock.fetchLatestJobRuns).toHaveBeenCalledTimes(2);
  expect(await screen.findByText('Remove duplicates')).toBeTruthy();
});
```

Add:

```typescript
it('shows a pending label while duplicate cleanup is running', async () => {
  let resolveRun: (value: { status: 'success'; embedded: number; merged: number }) => void;
  apiMock.runEmbeddingDedup.mockReturnValue(
    new Promise((resolve) => {
      resolveRun = resolve;
    })
  );
  render(<SchedulerPage />);

  await userEvent.click(await screen.findByRole('button', { name: 'Remove duplicates' }));

  expect(screen.getByRole('button', { name: 'Removing duplicates...' })).toBeDisabled();
  resolveRun!({ status: 'success', embedded: 0, merged: 0 });
});
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
npm test -- --run frontend/src/__tests__/schedulerPage.test.tsx -t 'duplicate cleanup'
```

Expected: FAIL because the mock helper/button do not exist.

- [ ] **Step 3: Implement the page behavior**

In `frontend/src/pages/SchedulerPage.tsx`:

```typescript
import {
  ...
  runEmbeddingDedup,
  ...
} from '../api';
```

Add state:

```typescript
const [deduplicating, setDeduplicating] = useState(false);
```

Add handler:

```typescript
async function handleRemoveDuplicates() {
  setDeduplicating(true);
  const id = toast.loading('Removing duplicate articles...');
  try {
    const result = await runEmbeddingDedup();
    toast.success(
      `Done - ${result.merged} duplicate article${result.merged !== 1 ? 's' : ''} removed, ${result.embedded} article${result.embedded !== 1 ? 's' : ''} embedded`,
      { id }
    );
    await loadJobRuns();
  } catch {
    toast.error('Duplicate cleanup failed', { id });
  } finally {
    setDeduplicating(false);
  }
}
```

Add a button beside `Fetch now`:

```tsx
<Button
  variant="outline"
  onClick={() => void handleRemoveDuplicates()}
  disabled={deduplicating || ingesting || actionPending}
>
  {deduplicating ? 'Removing duplicates...' : 'Remove duplicates'}
</Button>
```

Add to `JOB_LABELS`:

```typescript
embedding_dedup: 'Duplicate cleanup',
```

- [ ] **Step 4: Run tests and confirm green**

Run:

```bash
npm test -- --run frontend/src/__tests__/schedulerPage.test.tsx -t 'duplicate cleanup'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SchedulerPage.tsx frontend/src/__tests__/schedulerPage.test.tsx
git commit -m "feat: add manual duplicate cleanup control"
```

### Task 5: Final Verification and Delivery

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused backend tests**

```bash
source .env && pytest backend/tests/test_scheduler.py backend/tests/test_scheduled_job_history.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

```bash
npm test -- --run frontend/src/__tests__/api.test.ts frontend/src/__tests__/schedulerPage.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run repo quality gates**

```bash
make lint
make typecheck
source .env && export PGOPTIONS='-c max_parallel_workers_per_gather=0' && make test
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 4: Review diff**

```bash
git diff --check
git diff origin/main...HEAD
```

Expected: no whitespace errors and diff matches the spec.

- [ ] **Step 5: Push and open PR**

```bash
git fetch origin main
git rebase origin/main
git push -u origin codex/manual-duplicate-cleanup-1230
gh pr create --title "feat: add manual duplicate cleanup" --body "Closes #1230"
```

Expected: PR created.

- [ ] **Step 6: Wait for CI and merge**

```bash
gh pr checks --watch
gh pr merge --squash --auto --delete-branch
```

Expected: required checks pass and PR merges.
