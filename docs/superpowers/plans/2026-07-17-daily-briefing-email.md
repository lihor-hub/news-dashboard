# Daily Briefing Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver each opted-in user's canonical AI briefing to their account email at their configured local time with safe rendering, observable generation, and one-click unsubscribe.

**Architecture:** A focused `briefing_email` backend module owns delivery persistence, rendering, unsubscribe tokens, and HTTP endpoints. The existing per-user scheduler invokes that module after the existing LangGraph briefing workflow produces or reuses a canonical saved briefing; PostgreSQL uniquely claims each user/local-date delivery and plain SMTP remains conservatively at-most-once at its ambiguous final hop. The existing settings API and Daily Brief UI expose explicit opt-in and preview controls.

**Tech Stack:** Python 3.14, FastAPI, PostgreSQL/psycopg, APScheduler, LangGraph 1.2, Langfuse 4.14, Jinja2 3.1, SMTP, React 19, TypeScript, Vitest, pytest.

## Global Constraints

- Runtime persistence is PostgreSQL-only SQL with psycopg `%s` parameters; no SQLite fallback, database sniffing, or placeholder translation.
- Email delivery defaults to disabled and supports only the signed-in user's existing non-empty, non-guest account email.
- Reuse the canonical saved briefing for app, push, and email; do not create a second generation pipeline.
- Reuse `briefing_time` and the IANA `briefing_timezone`; Europe/Bucharest DST must work without fixed UTC offsets.
- Target 1,200–1,800 briefing words and no filler email when no important stories qualify.
- Jinja HTML autoescaping is mandatory; only normalized HTTP(S) URLs may become links.
- Unsubscribe tokens contain no email address, use a purpose-specific salt, expire, and support public idempotent GET plus RFC 8058 POST.
- Never trace or log email addresses, tokens, SMTP credentials, MIME payloads, or raw provider errors.
- Langfuse remains optional and non-fatal; scheduled runs use `daily-email:{user_id}:{local_date}` without changing default briefing trace sessions.
- Database claiming is unique by `(user_id, local_delivery_date)`; stale `sending` rows are not automatically resent after an ambiguous SMTP result.
- Preserve existing OTP SMTP variable precedence and the legacy digest behavior.
- No third-party email provider SDK or LangGraph checkpointer is added.

---

### Task 1: Subscription schema and settings contract

**Files:**
- Modify: `backend/news_dashboard/db.py`
- Modify: `backend/news_dashboard/email.py`
- Modify: `backend/news_dashboard/user_settings/models.py`
- Modify: `backend/news_dashboard/user_settings/service.py`
- Modify: `backend/news_dashboard/export.py`
- Modify: `backend/news_dashboard/import_export.py`
- Modify: `backend/tests/test_push_notifications.py`
- Create: `backend/tests/test_briefing_email_deliveries.py`
- Modify: `backend/tests/test_export.py`
- Modify: `backend/tests/test_import_export.py`

**Interfaces:**
- Produces: `users.briefing_email_enabled BOOLEAN NOT NULL DEFAULT FALSE`.
- Produces: `briefing_email_deliveries` with the statuses and unique `(user_id, local_delivery_date)` contract from the design.
- Produces: notification response fields `email_enabled: bool`, `email_address: str | None`, `email_available: bool`, and `email_delivery_configured: bool`.
- Produces: `NotificationSettingsUpdate.email_enabled: bool | None`.
- Produces: `news_dashboard.email.smtp_configured() -> bool`, implemented from the existing `_smtp_config` environment resolution without sending mail.

- [ ] **Step 1: Write failing PostgreSQL and settings tests**

Add tests asserting the new column defaults false, the delivery status check and uniqueness constraint exist, GET returns capability metadata, PUT persists opt-in, and PUT rejects `email_enabled=true` for a guest, user without email, or missing SMTP configuration. Add import/export tests proving the optional preference exports but an imported `true` value does not silently opt a user in.

```python
def test_notification_email_requires_account_email(client: TestClient) -> None:
    response = client.put("/api/settings/notifications", json={"email_enabled": True})
    assert response.status_code == 422
    assert response.json()["detail"] == "account email is required"


@pytest.mark.postgres
def test_delivery_local_date_is_unique(pg_clean: str, user_id: int) -> None:
    first = claim_delivery(user_id, date(2026, 7, 17), database_url=pg_clean)
    second = claim_delivery(user_id, date(2026, 7, 17), database_url=pg_clean)
    assert first is not None
    assert second is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `source .env && pytest backend/tests/test_push_notifications.py backend/tests/test_briefing_email_deliveries.py backend/tests/test_export.py backend/tests/test_import_export.py -x -v`

Expected: failures for the missing column/table, request field, settings payload, and claim function—not connection or fixture errors.

- [ ] **Step 3: Implement the schema and settings behavior**

Append idempotent PostgreSQL DDL to `POSTGRES_SCHEMA`. Add `smtp_configured()` beside the existing SMTP configuration resolver. Add `email_enabled` validation and response metadata without copying the account email into a subscription table. Export the preference but ignore `true` during archive restore so restore cannot create consent.

```python
class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool | None = None


if payload.email_enabled:
    if not row["email"] or row["is_guest"]:
        raise ValueError("account email is required")
    if not smtp_configured():
        raise ValueError("email delivery is not configured")
```

- [ ] **Step 4: Run focused tests and refactor green**

Run the Step 2 command until all selected tests pass. Run `make lint` and `make typecheck` for the touched backend interfaces.

- [ ] **Step 5: Commit**

```bash
git add backend/news_dashboard/db.py backend/news_dashboard/email.py backend/news_dashboard/user_settings backend/news_dashboard/export.py backend/news_dashboard/import_export.py backend/tests/test_push_notifications.py backend/tests/test_briefing_email_deliveries.py backend/tests/test_export.py backend/tests/test_import_export.py
git commit -m "feat: add briefing email subscriptions"
```

### Task 2: Shared SMTP transport and Jinja rendering

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `backend/news_dashboard/email.py`
- Create: `backend/news_dashboard/briefing_email/__init__.py`
- Create: `backend/news_dashboard/briefing_email/rendering.py`
- Create: `backend/news_dashboard/briefing_email/templates/briefing.html.j2`
- Create: `backend/news_dashboard/briefing_email/templates/briefing.txt.j2`
- Modify: `backend/tests/test_email.py`
- Create: `backend/tests/test_briefing_email_rendering.py`
- Modify: `backend/tests/test_digest.py`

**Interfaces:**
- Produces: `smtp_configured() -> bool`.
- Produces: `send_email(*, recipient: str, subject: str, text_body: str, html_body: str, headers: Mapping[str, str] | None = None) -> str | None`.
- Produces: `render_briefing_email(briefing: Mapping[str, Any], *, local_date: date, timezone_name: str, briefing_url: str, preferences_url: str, unsubscribe_url: str) -> RenderedEmail`, where `RenderedEmail` has `subject`, `html_body`, `text_body`, and `estimated_minutes`.
- Consumes: complete briefing mappings returned by `briefings.service.get_briefing` or `generate_briefing`.

- [ ] **Step 1: Write failing transport and rendering tests**

Test multipart HTML/plain output, custom unsubscribe headers, STARTTLS and implicit TLS, optional authentication, explicit sender, safe exception text, Jinja escaping, `javascript:` link suppression, story order, executive summary, reading-time estimate, and footer links. Keep every existing OTP and digest SMTP test green.

```python
def test_rendering_escapes_generated_html() -> None:
    rendered = render_briefing_email(_briefing(body="<script>alert(1)</script>"), **_urls())
    assert "<script>" not in rendered.html_body
    assert "&lt;script&gt;" in rendered.html_body


def test_send_email_adds_one_click_headers() -> None:
    send_email(
        recipient="reader@example.com",
        subject="Daily brief",
        text_body="text",
        html_body="<p>html</p>",
        headers={
            "List-Unsubscribe": "<https://news.example/unsubscribe/token>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `source .env && pytest backend/tests/test_email.py backend/tests/test_briefing_email_rendering.py backend/tests/test_digest.py -x -v`

Expected: import failures for the new renderer/transport or missing multipart/header behavior.

- [ ] **Step 3: Declare Jinja2 and implement focused templates**

Add `jinja2>=3.1.6` as a direct dependency and regenerate `uv.lock`. Use a Jinja `Environment` with `PackageLoader("news_dashboard.briefing_email", "templates")`, `select_autoescape`, and `StrictUndefined`. Configure hatch so `.j2` package assets are present in built wheels. Normalize every link through one helper that accepts only `http` and `https`.

- [ ] **Step 4: Extract a compatible shared SMTP send path**

Preserve `_smtp_config()` precedence exactly. Build `EmailMessage` multipart alternatives and apply caller-supplied headers from a fixed safe mapping. Do not log the recipient. Adapt OTP to call the shared transport; retain legacy digest behavior or adapt its private send wrapper without changing public configuration.

- [ ] **Step 5: Run focused tests and build the wheel**

Run the Step 2 command, then `uv build` and inspect the wheel with `unzip -l dist/*.whl | rg 'briefing\.(html|txt)\.j2'`. Expected: tests pass and both templates are packaged.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock backend/news_dashboard/email.py backend/news_dashboard/briefing_email backend/tests/test_email.py backend/tests/test_briefing_email_rendering.py backend/tests/test_digest.py
git commit -m "feat: render and send briefing emails"
```

### Task 3: Signed unsubscribe and authenticated preview API

**Files:**
- Create: `backend/news_dashboard/briefing_email/tokens.py`
- Create: `backend/news_dashboard/briefing_email/models.py`
- Create: `backend/news_dashboard/briefing_email/router.py`
- Create: `backend/news_dashboard/briefing_email/service.py`
- Modify: `backend/news_dashboard/main.py`
- Create: `backend/tests/test_briefing_email_tokens.py`
- Create: `backend/tests/test_briefing_email_api.py`
- Modify: `backend/tests/test_main_feature_modules.py`

**Interfaces:**
- Produces: `make_unsubscribe_token(user_id: int) -> str` and `verify_unsubscribe_token(token: str, *, max_age_seconds: int = 2_592_000) -> int`.
- Produces: public `GET /email/briefing/unsubscribe?token=...` and `POST /email/briefing/unsubscribe` accepting form field `List-Unsubscribe=One-Click` plus the token query.
- Produces: authenticated `POST /api/settings/notifications/email/preview` returning `{"sent": true}`.
- Produces: `unsubscribe_user(user_id: int, *, database_url: str | None = None) -> bool` and `send_preview(user_id: int, *, database_url: str | None = None) -> bool`.

- [ ] **Step 1: Write failing token and endpoint tests**

Cover round-trip, expiry, tampering, purpose binding, version rejection, no PII in decoded payload, idempotent GET/POST unsubscribe, invalid-token 400, authenticated preview, preview without account email, no complete briefing, and a per-user preview cooldown.

```python
def test_unsubscribe_is_idempotent(client: TestClient, token: str) -> None:
    first = client.get("/email/briefing/unsubscribe", params={"token": token})
    second = client.get("/email/briefing/unsubscribe", params={"token": token})
    assert first.status_code == second.status_code == 200


def test_token_payload_contains_no_email(monkeypatch: pytest.MonkeyPatch) -> None:
    token = make_unsubscribe_token(42)
    assert "reader@example.com" not in token
    assert verify_unsubscribe_token(token) == 42
```

- [ ] **Step 2: Run tests and verify RED**

Run: `source .env && pytest backend/tests/test_briefing_email_tokens.py backend/tests/test_briefing_email_api.py backend/tests/test_main_feature_modules.py -x -v`

Expected: missing module/routes/function failures.

- [ ] **Step 3: Implement tokens and routes**

Use `URLSafeTimedSerializer` with salt `news-dashboard-briefing-email-unsubscribe-v1` and payload `{"user_id": user_id, "action": "unsubscribe", "version": 1}`. Export authenticated and public routers separately and mount them on `api` and `public_router` in `main.py`. Return a small escaped confirmation page for GET and an empty 200 response for valid RFC 8058 POST.

- [ ] **Step 4: Implement preview without altering delivery claims**

Load the latest complete user briefing, render it with a signed unsubscribe link, and call `send_email`. Enforce a purpose-keyed in-process 60-second cooldown keyed by user ID, bounded to 10,000 entries and cleared on process restart; do not insert a scheduled delivery row or change `briefing_email_enabled`.

- [ ] **Step 5: Run focused tests and commit**

Run the Step 2 command until green, then:

```bash
git add backend/news_dashboard/briefing_email backend/news_dashboard/main.py backend/tests/test_briefing_email_tokens.py backend/tests/test_briefing_email_api.py backend/tests/test_main_feature_modules.py
git commit -m "feat: add briefing email unsubscribe and preview"
```

### Task 4: Claim-safe delivery orchestration and scheduler integration

**Files:**
- Modify: `backend/news_dashboard/briefing_email/service.py`
- Modify: `backend/news_dashboard/scheduler/service.py`
- Modify: `backend/news_dashboard/briefings/service.py`
- Modify: `backend/news_dashboard/briefing_agent.py`
- Modify: `backend/tests/test_briefing_email_deliveries.py`
- Modify: `backend/tests/test_scheduler.py`
- Modify: `backend/tests/test_briefings_db.py`
- Modify: `backend/tests/test_briefing_agent.py`

**Interfaces:**
- Produces: `claim_delivery(user_id: int, local_date: date, *, database_url: str | None = None) -> Delivery | None` using `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
- Produces: `deliver_daily_briefing(user_id: int, *, now: datetime | None = None, database_url: str | None = None) -> DeliveryOutcome`.
- Produces: optional `generate_briefing(..., langfuse_session_id: str | None = None, langfuse_tags: list[str] | None = None)` parameters; existing callers retain `briefing-run:{run_id}` and `["briefing"]` defaults.
- Consumes: Task 2 renderer/transport and Task 3 unsubscribe token.

- [ ] **Step 1: Write failing state-machine and scheduler tests**

Cover concurrent/repeated claims, successful status transitions, retryable vs permanent failures, stale claim recovery, conservative stale `sending`, opt-out before retry, no-candidate `skipped`, reuse of a current-local-day complete briefing, email-only subscribers, per-user failure isolation, invalid timezone fallback, and Bucharest summer/winter plus DST repeated-time protection.

```python
def test_scheduler_email_only_user_generates_and_delivers() -> None:
    rows = [{
        "id": 42,
        "briefing_time": "21:00",
        "briefing_timezone": "Europe/Bucharest",
        "briefing_push_enabled": False,
        "briefing_email_enabled": True,
    }]
    # At 18:00 UTC in summer, assert canonical generation and one email delivery.
```

- [ ] **Step 2: Run tests and verify RED**

Run: `source .env && pytest backend/tests/test_briefing_email_deliveries.py backend/tests/test_scheduler.py backend/tests/test_briefings_db.py backend/tests/test_briefing_agent.py -x -v`

Expected: failures for missing claims, delivery orchestration, email scheduler fields, or tracing overrides.

- [ ] **Step 3: Implement delivery state transitions**

Claim before generation. Query a complete user briefing whose local-day window matches before invoking the graph. Store sanitized failure categories only. Recheck `briefing_email_enabled`, account email, and configuration immediately before transitioning `rendered → sending`. Retry only `retryable_failed` rows with `next_attempt_at <= now`; never automatically retry stale `sending`.

- [ ] **Step 4: Integrate the existing per-user minute scheduler**

Extend `_run_per_user_briefings` to select both channel flags and invoke one canonical generation path. Push and email failures are reported independently. The unique local-date claim prevents a second send when the scheduler repeats or multiple replicas match the same minute.

- [ ] **Step 5: Add scheduled Langfuse attributes and deterministic quality checks**

Pass session `daily-email:{user_id}:{local_date.isoformat()}` and tags `["daily-email", "briefing"]` only from scheduled email delivery. Preserve default trace tests. Enforce non-empty summary, safe citations, duplicate citation removal, and the 1,800-word ceiling before persistence; quiet days do not generate filler.

- [ ] **Step 6: Run focused tests and commit**

Run the Step 2 command until green, then:

```bash
git add backend/news_dashboard/briefing_email/service.py backend/news_dashboard/scheduler/service.py backend/news_dashboard/briefings/service.py backend/news_dashboard/briefing_agent.py backend/tests/test_briefing_email_deliveries.py backend/tests/test_scheduler.py backend/tests/test_briefings_db.py backend/tests/test_briefing_agent.py
git commit -m "feat: schedule daily briefing email delivery"
```

### Task 5: Email subscription and preview UI

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/notifications.ts`
- Modify: `frontend/src/components/settings/DailyBriefSection.tsx`
- Modify: `frontend/src/__tests__/dailyBriefSettings.test.tsx`
- Modify: `frontend/src/__tests__/api.test.ts`
- Modify: `e2e/fixtures.ts`
- Create: `e2e/settings-email.spec.ts`

**Interfaces:**
- Consumes: notification fields and endpoints from Tasks 1 and 3.
- Produces: `sendEmailBriefingPreview(): Promise<{sent: boolean}>`.
- Produces: accessible Email briefing settings region with channel-specific enable, disable, and preview actions.

- [ ] **Step 1: Write failing component and API tests**

Add typed default settings and mock preview API. Test available-disabled enable, enabled disable, unavailable account email, server delivery unavailable, mutation rollback/error alert, preview pending/success/error, and exact preview URL/method. Scope queries with `within` so existing push “Enabled” tests remain unambiguous.

```tsx
it('enables email briefing for the account address', async () => {
  renderSettings({ email_enabled: false, email_address: 'reader@example.com' });
  const region = await screen.findByRole('region', { name: 'Email briefing' });
  await userEvent.click(within(region).getByRole('button', { name: 'Enable email briefing' }));
  expect(mockUpdateSettings).toHaveBeenCalledWith({ email_enabled: true });
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `npm run test:frontend -- frontend/src/__tests__/dailyBriefSettings.test.tsx frontend/src/__tests__/api.test.ts`

Expected: missing fields/action/UI failures.

- [ ] **Step 3: Implement the typed API and UI states**

Place Email briefing after timezone and before push. Display the account email, explicit channel-specific buttons, pending states, `role="alert"` errors, preview confirmation, and explanatory unavailable states. Do not duplicate the time/timezone controls or derive consent from account email presence.

- [ ] **Step 4: Add mocked browser flow**

Extend `mockApi` with GET/PUT notification state and preview POST. In `e2e/settings-email.spec.ts`, verify the account email, enable payload, enabled state, and preview success at desktop and mobile widths without live SMTP.

- [ ] **Step 5: Run frontend gates and commit**

Run:

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test:frontend
npm run build
npx playwright test e2e/settings-email.spec.ts
```

Then commit:

```bash
git add frontend/src/types.ts frontend/src/api/notifications.ts frontend/src/components/settings/DailyBriefSection.tsx frontend/src/__tests__/dailyBriefSettings.test.tsx frontend/src/__tests__/api.test.ts e2e/fixtures.ts e2e/settings-email.spec.ts
git commit -m "feat: add daily email briefing settings"
```

### Task 6: Deployment configuration and operator documentation

**Files:**
- Modify: `helm/news-dashboard/values.yaml`
- Modify: `helm/news-dashboard/templates/deployment.yaml`
- Modify: `scripts/test_helm_email_secret.py`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `docs/SELF_HOSTING.md`
- Modify: `website/docs/configuration/index.md`

**Interfaces:**
- Produces: deployment-owned generic SMTP host, port, user, password, sender, TLS mode, and public base URL environment variables.
- Preserves: legacy `SMTP_USERNAME`/`SMTP_PASSWORD` and OTP-specific precedence.

- [ ] **Step 1: Write failing Helm render tests**

Assert defaults expose no secret values, existing secrets retain legacy credential keys, generic host/port/from/TLS render when configured, and a public base URL is available independently of Keycloak.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest scripts/test_helm_email_secret.py -x -v`

Expected: missing generic environment names or public base URL.

- [ ] **Step 3: Wire configuration and document it**

Add inert Docker Compose passthroughs and Helm values for `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TLS`, and `APP_BASE_URL` while retaining aliases. Document that email controls cannot enable delivery until SMTP and an absolute public base URL are configured; never include example secrets.

- [ ] **Step 4: Run deployment gates and commit**

Run `pytest scripts/test_helm_email_secret.py -v && make helm-validate`, then:

```bash
git add helm/news-dashboard/values.yaml helm/news-dashboard/templates/deployment.yaml scripts/test_helm_email_secret.py docker-compose.yml docker-compose.prod.yml docs/SELF_HOSTING.md website/docs/configuration/index.md
git commit -m "docs: configure daily briefing email delivery"
```

### Task 7: Whole-feature verification, review, and release handoff

**Files:**
- Modify only files required to fix confirmed verification or review findings.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a clean branch ready for the issue #1256 PR and merge queue.

- [ ] **Step 1: Run focused backend and deployment tests**

```bash
source .env
pytest backend/tests/test_email.py backend/tests/test_digest.py backend/tests/test_briefing_email_rendering.py backend/tests/test_briefing_email_tokens.py backend/tests/test_briefing_email_api.py backend/tests/test_briefing_email_deliveries.py backend/tests/test_scheduler.py backend/tests/test_push_notifications.py scripts/test_helm_email_secret.py -v
```

- [ ] **Step 2: Run repository gates**

```bash
make lint
make typecheck
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
make test
npm run build
make helm-validate
```

Expected: every command exits 0. Confirm `podman ps --filter name=nd-test-pg` points `.env` tests to port 55432 before the full backend suite.

- [ ] **Step 3: Verify the running user flow**

Run the app with a non-production SMTP capture server or mocked transport. Confirm settings display, Bucharest 21:00 scheduling data, preview rendering at desktop/mobile widths, safe external links, plain-text alternative, and one-click unsubscribe. Do not send to a real recipient during verification.

- [ ] **Step 4: Perform independent whole-branch review**

Review the merge-base diff for design compliance, concurrency and SMTP ambiguity, token safety, sensitive-data leakage, frontend accessibility, and PostgreSQL-only SQL. Fix every confirmed Critical or Important finding and rerun the tests covering each fix.

- [ ] **Step 5: Rebase, push, open PR, and queue auto-merge**

```bash
git fetch origin
git rebase origin/main
git push -u origin HEAD
gh pr create --base main --title "feat: deliver timezone-aware daily briefing emails" --body $'Closes #1256\n\nAdds opt-in, timezone-aware delivery of canonical AI briefings with Jinja HTML/plain-text templates, claim-safe PostgreSQL delivery state, Langfuse sessions, preview controls, and one-click unsubscribe.\n\nTested with focused backend/frontend/Helm suites and repository lint, typecheck, test, and build gates.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)'
gh pr merge --squash --auto
gh pr checks --watch
```

- [ ] **Step 6: Confirm terminal state**

Use `gh pr view --json state,mergedAt,url` and `gh issue view 1256 --json state,url` to confirm the PR is merged and issue closed. Delete the remote branch if GitHub did not. Report CI evidence and any residual SMTP-provider risk.
