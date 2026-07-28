# Optional Dify Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure-by-default, optional Dify floating assistant to authenticated News Dashboard pages.

**Architecture:** The backend validates environment configuration and exposes only the public embed settings through `/api/config`. A focused React component owns an accessible launcher and disposable Dify WebApp iframe and is mounted by `AppShell`; deployment manifests and operator documentation carry the same configuration contract.

**Tech Stack:** FastAPI, Python 3.14, React 19, TypeScript, Vitest, Docker Compose, Helm

## Global Constraints

- Disabled by default and inert unless the explicit flag, base URL, and embed token are valid.
- Never expose a Dify service API key or send News Dashboard identity, account, or page context to the public WebApp. Dify WebApp identity remains separate.
- Allow HTTPS URLs in production and HTTP only for `localhost`, `127.0.0.1`, and `[::1]` development hosts.
- Require Dify to use an origin separate from News Dashboard so the iframe cannot read the authenticated parent DOM.
- Sandbox the iframe for scripts, Dify-origin storage, forms, downloads, and constrained popups without any top-navigation or popup-escape permission.
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

### Task 2: Dify iframe assistant lifecycle

**Files:**

- Create: `frontend/src/lib/publicConfig.ts`
- Create: `frontend/src/lib/publicConfig.test.ts`
- Create: `frontend/src/components/DifyChatWidget.tsx`
- Create: `frontend/src/components/DifyChatWidget.test.tsx`
- Create: `frontend/src/components/AppShell.dify.test.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/globals.css`

**Interfaces:**

- Produces: `fetchPublicConfig(): Promise<PublicConfig>`
- Produces: `DifyChatWidget()`
- Consumes `/api/config.dify` from Task 1

- [ ] **Step 1: Write failing component tests**

Mock `/api/config`. Assert that disabled and malformed configurations show no
launcher; enabled configuration shows a native accessible button but creates
no iframe until opened. Assert the exact `{baseUrl}/chatbot/{appToken}` iframe
URL, accessible panel/close/iframe names, keyboard activation and focus
restoration, and Escape dismissal while focus is on the parent close control.
Assert the required sandbox capabilities and the absence of top-navigation and
popup-escape permissions, iframe removal on close/unmount, fresh iframe
creation on reopen, and the absence of News Dashboard identity or context in
the URL and AppShell props. Add browser-validation tests for non-BMP Unicode
length parity and same-origin rejection.

- [ ] **Step 2: Run the focused Vitest file and confirm red**

Run:

```bash
npm run test:frontend -- frontend/src/components/DifyChatWidget.test.tsx frontend/src/components/AppShell.dify.test.tsx frontend/src/lib/publicConfig.test.ts
```

Expected: failure because the host-owned launcher and iframe lifecycle do not
exist and JavaScript counts non-BMP strings differently from Python.

- [ ] **Step 3: Implement the focused component**

Fetch public config with same-origin credentials and validate the response
shape again at the browser boundary using Unicode code-point lengths. Render a
News Dashboard-owned launcher and create the official Dify WebApp iframe only
while its panel is open. Reject a Dify URL whose origin equals the News
Dashboard origin. Apply an iframe sandbox that allows scripts,
`allow-same-origin` for Dify's own storage, forms, downloads, and constrained
popups, but no top-navigation or popup sandbox escape. Do not load a Dify
parent-document script or install Dify window globals, listeners, styles, or
identity/context variables. Mount the component inside `AppShell` only when an
authenticated user exists, keyed so an account change destroys any open
iframe.

- [ ] **Step 4: Add mobile-safe styling**

Give the host launcher and close control at least 44-by-44-pixel targets and
visible focus styles. Size and position the mobile panel above fixed navigation
and `env(safe-area-inset-bottom)`; use a bounded desktop chat layout at the `md`
breakpoint. Escape closes the panel and restores launcher focus only while
focus remains in the parent-document portion of the dialog. Once focus enters
the cross-origin WebApp, its events cannot bubble; the persistent close button
is reached by Shift+Tab back from the iframe.

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
News Dashboard variables, Dify `ALLOW_EMBED`, HTTPS production URLs and the
three loopback HTTP exceptions, the separate-origin requirement, reverse-proxy
`frame-src`, public WebApp/token behavior, the explicit zero-context privacy
decision, Dify's separate WebApp identity, the existing read-only MCP boundary,
and troubleshooting.

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

Inspect `git diff --check`, the complete diff, secret exposure, iframe URL and
sandbox construction, absence of top-navigation permission,
close/unmount/account cleanup, accessibility, privacy leaks, third-party
failure isolation, Helm renders, and documentation accuracy. Fix confirmed
issues and re-run affected gates.

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
