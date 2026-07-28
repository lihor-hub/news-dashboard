# Product Documentation Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document the current hosted and self-hosted product workflows that are missing from the published guide, illustrated with privacy-safe screenshots from the official hosted release.

**Architecture:** Add a small set of task-oriented guides to the Docusaurus site and mirror every end-user guide under `docs/user-guide/`. Reuse focused existing guides through links, surface already-written integration pages from their indexes, and store curated WebP screenshots under the published static image tree.

**Tech Stack:** Docusaurus 3, Markdown/MDX, WebP images, shell-based documentation validation.

## Global Constraints

- Documentation and documentation image assets only; do not change application behavior, deployment defaults, or feature availability.
- Treat `https://news.lihor.ro` as the visual source of truth and current source/configuration paths as authoritative for feature gates, roles, and self-hosted configuration.
- Every changed or added page under `website/docs/user-guide/` must have a content-equivalent mirror under `docs/user-guide/`.
- Screenshots must use a consistent desktop viewport, WebP output, descriptive filenames, concise alt text, and contain no email address, username, token, secret, source credential, internal identifier, or private account data.
- Explain hosted-service, self-hosted, administrator, and deployment-operator responsibilities at the step where the distinction matters.
- Do not duplicate focused existing guides; link to them.
- Verify the documentation website with `npm run build` from `website/`.

---

## File Structure

- `website/static/img/user-guide/*.webp` — privacy-safe hosted-release screenshots used by the new guides.
- `website/docs/getting-started/hosted-or-self-hosted.md` — deployment-choice and responsibility guide.
- `website/docs/user-guide/application-tour.md` — core navigation and first-reading workflow.
- `website/docs/user-guide/personalization-and-ai.md` — recommendations and optional AI workflows.
- `website/docs/user-guide/organize-and-learn.md` — saving, collections, learning, recaps, and offline workflows.
- `website/docs/user-guide/settings-and-account.md` — user-controlled settings, deliveries, privacy, and data lifecycle.
- `website/docs/user-guide/administration-and-operations.md` — application-admin and operational surfaces.
- `docs/user-guide/*.md` — repository mirrors of every new end-user guide.
- `website/docs/user-guide/index.md` and `docs/user-guide/README.md` — discoverability for the expanded guide.
- `website/docs/configuration/index.md` — links to existing MCP and Google Reader-compatible sync documentation.
- `website/docs/self-hosting/index.md` and `docs/SELF_HOSTING.md` — concise links from deployment setup to product configuration and role guidance.

### Task 1: Capture and curate hosted-release screenshots

**Files:**
- Create: `website/static/img/user-guide/generated-brief.webp`
- Create: `website/static/img/user-guide/today-feed.webp`
- Create: `website/static/img/user-guide/application-navigation.webp`
- Create: `website/static/img/user-guide/organize-and-learn.webp`
- Create: `website/static/img/user-guide/settings-personalization.webp`
- Create if privacy-safe: `website/static/img/user-guide/operations.webp`

**Interfaces:**
- Consumes: authenticated official hosted instance at `https://news.lihor.ro`.
- Produces: stable `/img/user-guide/<name>.webp` paths for Tasks 2 and 3.

- [ ] **Step 1: Read the browser screenshot documentation and set one desktop viewport**

Use the in-app browser’s screenshot documentation. Select one viewport of at least 1280 CSS pixels wide and keep it unchanged for all captures.

- [ ] **Step 2: Capture the Brief, Today, navigation, organization/learning, and settings views**

Use real hosted content. Frame the product controls needed by the guide, avoid unrelated browser chrome, and crop away personal or private values. Capture an operations view only if it contains no user identity, private feed details, or internal identifiers.

- [ ] **Step 3: Save optimized WebP assets**

Save each accepted image to the exact paths listed above. Keep images legible at documentation-column width and avoid unnecessary full-page height.

- [ ] **Step 4: Perform a privacy and legibility inspection**

Open every saved asset at original resolution. Reject or recapture any image containing an email address, username, token, secret, source credential, internal identifier, private account data, clipped labels, or unreadable controls.

- [ ] **Step 5: Verify image format and dimensions**

Run:

```bash
file website/static/img/user-guide/*.webp
identify website/static/img/user-guide/*.webp
```

Expected: every asset is reported as WebP, all use the same viewport-derived width or a deliberate privacy crop, and every label used by the guide is readable.

- [ ] **Step 6: Commit**

```bash
git add website/static/img/user-guide
git commit -m "docs: add hosted product screenshots (#1285)"
```

### Task 2: Add hosted and end-user workflow guides

**Files:**
- Create: `website/docs/getting-started/hosted-or-self-hosted.md`
- Create: `website/docs/user-guide/application-tour.md`
- Create: `website/docs/user-guide/personalization-and-ai.md`
- Create: `website/docs/user-guide/organize-and-learn.md`
- Create: `website/docs/user-guide/settings-and-account.md`
- Create: `docs/user-guide/application-tour.md`
- Create: `docs/user-guide/personalization-and-ai.md`
- Create: `docs/user-guide/organize-and-learn.md`
- Create: `docs/user-guide/settings-and-account.md`
- Modify: `website/docs/user-guide/index.md`
- Modify: `docs/user-guide/README.md`

**Interfaces:**
- Consumes: screenshot paths from Task 1 and existing focused guides under `website/docs/user-guide/`.
- Produces: task-oriented hosted/user documentation and mirror-equivalent repository copies.

- [ ] **Step 1: Draft the hosted-versus-self-hosted choice guide**

Explain the official hosted service, local demo, and self-hosted deployment; identify who creates accounts and who controls server configuration; provide role labels for reader, administrator, and deployment operator; link to the first useful reading workflow and the self-hosting guide.

- [ ] **Step 2: Draft the application tour**

Explain the Brief, Today, article reading, Search, and More navigation. Embed `generated-brief.webp`, `today-feed.webp`, and `application-navigation.webp` with concise alt text. Link to the existing briefings, feed triage, search, sources, sharing, and saved-history guides.

- [ ] **Step 3: Draft personalization and AI**

Explain recommendations, Ask, AI Watchlists, AI Memory, Topic Map, and AI Stats. Mark optional-provider or administrator-controlled capabilities where source confirms them. Link to the existing recommendations and knowledge-graph guides.

- [ ] **Step 4: Draft organization and learning**

Explain Later, Starred, Reading List, Collections, Learn, Lesson Library, Learning Recap, Weekly Recap, and Offline Saved. Embed `organize-and-learn.webp` and explain what remains available offline without promising unsupported synchronization behavior.

- [ ] **Step 5: Draft settings and account data**

Explain theme, language, recommendation refresh, briefing schedule and timezone, email and push delivery, weekly recap, privacy analytics, export/restore, version checks, and account deletion. Embed `settings-personalization.webp`; keep all real personal values outside the image and examples.

- [ ] **Step 6: Mirror and index the guides**

Copy the user-guide content into the matching `docs/user-guide/` paths, adjusting only site-specific front matter or link syntax. Update both indexes with the same reader-oriented grouping and add the hosted-versus-self-hosted guide to the published getting-started flow.

- [ ] **Step 7: Verify mirror parity and links**

Run a normalized comparison that strips Docusaurus front matter before comparing each new `website/docs/user-guide/*.md` page to its `docs/user-guide/*.md` mirror. Search every new relative link and `/img/user-guide/` reference and confirm the target exists.

- [ ] **Step 8: Commit**

```bash
git add website/docs/getting-started website/docs/user-guide docs/user-guide
git commit -m "docs: explain hosted product workflows (#1285)"
```

### Task 3: Add administration, configuration, and self-hosted guidance

**Files:**
- Create: `website/docs/user-guide/administration-and-operations.md`
- Create: `docs/user-guide/administration-and-operations.md`
- Modify: `website/docs/user-guide/index.md`
- Modify: `docs/user-guide/README.md`
- Modify: `website/docs/configuration/index.md`
- Modify: `website/docs/self-hosting/index.md`
- Modify: `docs/SELF_HOSTING.md`

**Interfaces:**
- Consumes: current routes, permissions, environment-variable references, deployment guides, and optional `operations.webp` from Task 1.
- Produces: role-correct operational guidance and discoverable links to existing integration configuration.

- [ ] **Step 1: Verify admin and operator claims against source**

Confirm the current routes and access controls for user administration, feeds, schedules, run history, logs, statistics, and analytics. Confirm exact existing documentation targets and environment-variable names before mentioning them.

- [ ] **Step 2: Draft administration and operations**

Separate application-administrator tasks from deployment-operator tasks. Cover user administration, feed management, scheduling, run history, logs, statistics, and analytics. Embed `operations.webp` only if Task 1 accepted it as privacy-safe.

- [ ] **Step 3: Mirror and index the administration guide**

Create the equivalent `docs/user-guide/administration-and-operations.md` page and add it to both user-guide indexes under a clearly role-labeled section.

- [ ] **Step 4: Surface existing integration guides**

Add links and short task descriptions for `mcp-server.md` and `greader-sync.md` to `website/docs/configuration/index.md`. Include any other stable configuration guide already present in the directory but missing from the index.

- [ ] **Step 5: Connect self-hosting to product configuration**

Add concise role and next-step links to `website/docs/self-hosting/index.md` and `docs/SELF_HOSTING.md`. Point to the canonical environment reference and deployment methods rather than duplicating the variable catalogue.

- [ ] **Step 6: Verify all documentation**

Run:

```bash
cd website
npm run build
```

Expected: exit 0 with no broken internal links or missing image assets.

Then verify every new guide path, image reference, configuration-index target, and user-guide mirror exists. Inspect `git diff --check` and the complete diff for accidental private data, stale terminology, and duplicated focused-guide content.

- [ ] **Step 7: Commit**

```bash
git add website/docs docs/user-guide docs/SELF_HOSTING.md
git commit -m "docs: add administration and configuration guides (#1285)"
```
