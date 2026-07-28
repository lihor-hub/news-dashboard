# Optional Dify Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure-by-default, optional Dify floating assistant to authenticated News Dashboard pages.

**Architecture:** The backend validates environment configuration and exposes only the public embed settings through `/api/config`. A focused React component owns the third-party script lifecycle and is mounted by `AppShell`; deployment manifests and operator documentation carry the same configuration contract.

**Tech Stack:** FastAPI, Python 3.14, React 19, TypeScript, Vitest, Docker Compose, Helm

## Global Constraints

- Disabled by default and inert unless the explicit flag, base URL, and embed token are valid.
- Never expose a Dify service API key or treat browser-provided user context as authorization.
- Allow HTTPS URLs in production and HTTP only for loopback development hosts.
- Preserve all existing News Dashboard behavior when Dify is unavailable.
- Use PostgreSQL-specific runtime behavior; this feature adds no database changes.

---

### Task 1: Public runtime configuration

**Files:**
- Create: `backend/news_dashboard/dify.py`
- Modify: `backend/news_dashboard/system/service.py`
- Test: `backend/tests/test_dify_config.py`
- Modify: `backend/tests/test_error_tracking.py`

**Interfaces:**
- Produces: `public_dify_config() -> dict[str, object]`
- Produces `/api/config.dify` with `enabled`, `base_url`, `app_token`, and `title`

- [ ] **Step 1: Write failing backend tests**

Cover an empty environment, a partial configuration, an enabled HTTPS
configuration, trailing-slash normalization, loopback HTTP, non-loopback HTTP,
and control/length validation. Update the exact `/api/config` assertions to
include the disabled Dify object.

- [ ] **Step 2: Run the focused tests and confirm red**

Run:

```bash
PATH="$PWD/.venv/bin:$PATH" source .env
pytest backend/tests/test_dify_config.py backend/tests/test_error_tracking.py -q
```

Expected: failure because the Dify configuration module and response field do
not exist.

- [ ] **Step 3: Implement minimal validated configuration**

Parse the four documented environment variables, normalize the URL, validate
scheme/host and bounded strings, and merge the result into `public_config()`.
Invalid input must return the same disabled object as an unset environment.

- [ ] **Step 4: Re-run the focused tests**

Run the Step 2 command. Expected: all selected tests pass.

### Task 2: Dify widget lifecycle

**Files:**
- Create: `frontend/src/lib/publicConfig.ts`
- Create: `frontend/src/components/DifyChatWidget.tsx`
- Create: `frontend/src/components/DifyChatWidget.test.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/globals.css`

**Interfaces:**
- Produces: `fetchPublicConfig(): Promise<PublicConfig>`
- Produces: `DifyChatWidget({ user }: { user: User })`
- Consumes `/api/config.dify` from Task 1

- [ ] **Step 1: Write failing component tests**

Mock `/api/config` and script loading. Assert that disabled and invalid
configurations add no script; enabled configuration sets
`window.difyChatbotConfig`, uses `{baseUrl}/embed.min.js`, supplies stable user
display context, avoids duplicate scripts, and cleans up after unmount.

- [ ] **Step 2: Run the focused Vitest file and confirm red**

Run:

```bash
npm run test:frontend -- frontend/src/components/DifyChatWidget.test.tsx
```

Expected: failure because the widget does not exist.

- [ ] **Step 3: Implement the focused component**

Fetch public config with same-origin credentials, validate the response shape
again at the browser boundary, set the documented Dify global, load the script
once, and remove owned global/script/DOM state during cleanup. Mount the
component inside `AppShell` only when an authenticated user exists.

- [ ] **Step 4: Add mobile-safe styling**

Set Dify's documented bubble offset variables so the button clears the fixed
mobile navigation and `env(safe-area-inset-bottom)`, with the desktop offset
restored at the `md` breakpoint.

- [ ] **Step 5: Re-run the focused frontend tests**

Run the Step 2 command. Expected: all selected tests pass.

### Task 3: Deployment configuration

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `helm/news-dashboard/values.yaml`
- Modify: `helm/news-dashboard/templates/_helpers.tpl`
- Modify: `helm/news-dashboard/templates/deployment.yaml`
- Test: `backend/tests/test_chart_render.py`
- Test: `backend/tests/test_dify_deployment_config.py`

**Interfaces:**
- Consumes the four environment variables from Task 1
- Produces matching Compose and Helm operator settings

- [ ] **Step 1: Write failing deployment tests**

Assert that both Compose files forward all four variables, Helm is disabled by
default, and an enabled Helm render contains the configured base URL, app
token secret reference, and title.

- [ ] **Step 2: Run the deployment tests and confirm red**

Run:

```bash
PATH="$PWD/.venv/bin:$PATH" pytest backend/tests/test_dify_deployment_config.py backend/tests/test_chart_render.py -q
```

Expected: new Dify assertions fail.

- [ ] **Step 3: Add Compose and Helm wiring**

Use a plain ConfigMap-style value for enabled/base URL/title and support a
Kubernetes Secret reference for the embed token. Do not create or accept a
Dify service API key.

- [ ] **Step 4: Re-run deployment tests**

Run the Step 2 command. Expected: all selected tests pass.

### Task 4: Operator documentation

**Files:**
- Create: `website/docs/configuration/dify-assistant.md`
- Modify: `website/docs/configuration/index.md`
- Modify: `docs/SELF_HOSTING.md`
- Modify: `README.md`

**Interfaces:**
- Documents the exact variables and behavior produced by Tasks 1–3

- [ ] **Step 1: Write the operator guide**

Document Dify Chatbot/Agent/Chatflow suitability, Publish → Embed, the four
News Dashboard variables, Dify `ALLOW_EMBED`, browser-reachable HTTPS URLs,
CORS and reverse-proxy CSP requirements, public WebApp/token behavior,
identity limitations, the existing read-only MCP boundary, and troubleshooting.

- [ ] **Step 2: Link the guide**

Add it to the published configuration index, self-hosting guide, and README
configuration table.

- [ ] **Step 3: Verify documentation**

Run:

```bash
npm run format:check
rg -n "DIFY_CHAT_(ENABLED|BASE_URL|APP_TOKEN|TITLE)" README.md docs .env.example docker-compose*.yml helm/news-dashboard
```

Expected: formatting passes and every variable is consistently documented.

### Task 5: Verification and delivery

**Files:**
- Review all files changed by Tasks 1–4

**Interfaces:**
- Produces a merge-ready branch for issue #1292

- [ ] **Step 1: Run Python gates**

```bash
export PATH="$PWD/.venv/bin:$PATH"
make lint
make typecheck
source .env
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
make test
```

- [ ] **Step 2: Run frontend gates using the repository Node runtime**

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test:frontend
npm run build
```

- [ ] **Step 3: Review and fix confirmed findings**

Inspect `git diff --check`, the complete diff, secret exposure, script cleanup,
URL validation, third-party failure isolation, Helm renders, and documentation
accuracy. Fix confirmed issues and re-run affected gates.

- [ ] **Step 4: Rebase, commit, push, and open the PR**

```bash
git fetch origin
git rebase origin/main
git push -u origin HEAD
gh pr create --base main --body-file /tmp/dify-pr-body.md
gh pr merge --squash --auto
```

The PR body must include `Closes #1292`, the delivered behavior, verification,
and the repository's generated-with trailer.

- [ ] **Step 5: Monitor required checks and confirm merge**

Repair branch-caused failures, retry bounded transient failures, and stop only
for credentials or unrelated infrastructure. Confirm the PR merged and issue
closed before reporting completion.
