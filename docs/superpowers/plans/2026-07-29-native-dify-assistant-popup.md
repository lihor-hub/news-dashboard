# Native Dify Assistant Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicate News Dashboard heading from the Dify popup while preserving its dimensions, security boundary, behavior, and professional **News Assistant** identity.

**Architecture:** Keep Dify isolated in the existing sandboxed cross-origin iframe and make the News Dashboard dialog a titleless semantic frame. Move the close action into a compact control on the frame edge, and document that Dify's own application name controls the single visible heading inside the iframe.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, shadcn-style `Button`, Lucide icons, Vitest, Testing Library.

## Global Constraints

- Keep the existing popup width, height, responsive placement, and mobile behavior unchanged.
- Keep the existing iframe URL, referrer policy, sandbox permissions, disposable lifecycle, and privacy boundary unchanged.
- The one visible product name is exactly **News Assistant**.
- Do not inject styles or scripts into Dify, proxy its document, or relax same-origin isolation.
- Keep the existing launcher, Escape-to-close, and focus-restoration behavior.

---

### Task 1: Render a titleless native popup frame

**Files:**
- Modify: `frontend/src/components/DifyChatWidget.test.tsx`
- Modify: `frontend/src/components/DifyChatWidget.tsx`
- Modify: `website/docs/configuration/dify-assistant.md`

**Interfaces:**
- Consumes: `PublicDifyConfig.title: string`, the existing `Button` component, and the Dify iframe URL assembled by `DifyChatWidget`.
- Produces: the unchanged `DifyChatWidget(): JSX.Element | null` component contract, with a titleless host frame and `Close ${dify.title}` close action.

- [ ] **Step 1: Write the failing popup-structure test**

Add this test after the existing keyboard-opening test:

```tsx
it('uses Dify as the single visible heading without shrinking the popup', async () => {
  const pointer = userEvent.setup();
  const { launcher } = await renderEnabledWidget();
  await pointer.click(launcher);

  const dialog = screen.getByRole('dialog', { name: 'News Assistant' });
  expect(within(dialog).queryByRole('heading')).not.toBeInTheDocument();
  expect(dialog.querySelector('header')).toBeNull();
  expect(dialog).toHaveClass(
    'h-[calc(100dvh-76px-env(safe-area-inset-bottom))]',
    'max-h-[44rem]',
    'md:h-[min(44rem,calc(100dvh-2rem))]',
    'md:w-96'
  );
  expect(screen.getByTitle('News Assistant conversation')).toHaveClass('flex-1');
});
```

Add `within` to the existing Testing Library import:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
npx vitest run frontend/src/components/DifyChatWidget.test.tsx
```

Expected: FAIL because the open dialog still contains the host-owned
`<header>` and `<h2>News Assistant</h2>`.

- [ ] **Step 3: Implement the titleless frame**

Replace the host `<header>` block with the existing close `Button` directly
inside the dialog:

```tsx
<Button
  ref={closeRef}
  type="button"
  size="icon"
  variant="outline"
  className="absolute -right-2 -top-2 z-10 size-8 rounded-full bg-background shadow-md focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
  aria-label={closeLabel}
  title={closeLabel}
  onClick={() => setOpen(false)}
>
  <X className="size-4" aria-hidden="true" />
</Button>
```

Keep the dialog's sizing and positioning classes exactly as they are. Change
only `overflow-hidden` to `overflow-visible` on the dialog so the edge-mounted
control is not clipped. Add `rounded-[inherit]` to the iframe class so the
cross-origin surface remains clipped to the host frame:

```tsx
className="min-h-0 w-full flex-1 rounded-[inherit] border-0 bg-background"
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
npx vitest run frontend/src/components/DifyChatWidget.test.tsx
```

Expected: all `DifyChatWidget` tests PASS, including sandbox, lifecycle,
privacy, Escape, close, and focus restoration.

- [ ] **Step 5: Document the single-heading Dify setting**

After the basic environment configuration in
`website/docs/configuration/dify-assistant.md`, add:

```markdown
### Use one professional assistant name

Set both `DIFY_CHAT_TITLE` and the Dify application's display name to
`News Assistant`. The News Dashboard popup intentionally has no second visible
title; Dify renders the single heading inside its cross-origin iframe.

In Dify, open the application's settings, change its display name to
`News Assistant`, and publish the application again. News Dashboard cannot
override that internal heading because the embedded application remains
cross-origin and sandboxed.
```

- [ ] **Step 6: Format and rerun the focused test**

Run:

```bash
npm run format
npx vitest run frontend/src/components/DifyChatWidget.test.tsx
```

Expected: formatting completes and all focused tests PASS.

- [ ] **Step 7: Commit the independently verified behavior**

```bash
git add frontend/src/components/DifyChatWidget.tsx \
  frontend/src/components/DifyChatWidget.test.tsx \
  website/docs/configuration/dify-assistant.md
git commit -m "fix: make Dify assistant popup feel native"
```

### Task 2: Verify and visually review the integration

**Files:**
- Verify: `frontend/src/components/DifyChatWidget.tsx`
- Verify: `frontend/src/components/DifyChatWidget.test.tsx`
- Verify: `website/docs/configuration/dify-assistant.md`

**Interfaces:**
- Consumes: the titleless `DifyChatWidget` from Task 1.
- Produces: fresh repository-gate evidence and desktop/mobile visual evidence for PR review.

- [ ] **Step 1: Run all required frontend gates**

Run:

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test:frontend
npm run build
```

Expected: every command exits `0` with no warnings or test failures.

- [ ] **Step 2: Review the diff against the approved design**

Run:

```bash
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- \
  frontend/src/components/DifyChatWidget.tsx \
  frontend/src/components/DifyChatWidget.test.tsx \
  website/docs/configuration/dify-assistant.md
```

Confirm the dialog size and security attributes are unchanged, only one
host-side close control remains, and the documentation names **News Assistant**.

- [ ] **Step 3: Visually verify desktop and mobile popup states**

Run the application with its normal local environment, open the Dify launcher,
and inspect desktop and mobile viewport screenshots. Confirm:

- the frame dimensions match the previous popup;
- no host-owned title or separator appears;
- the close control is reachable and does not cover Dify's refresh action;
- Dify is the sole visible heading surface;
- the frame radius, border, background, and shadow match News Dashboard.

- [ ] **Step 4: Rebase and rerun affected gates if the base changed**

```bash
git fetch origin
git rebase origin/main
```

If the rebase changes commits under the branch, rerun Step 1 before pushing.

- [ ] **Step 5: Push, open the PR, and queue auto-merge**

```bash
git push -u origin HEAD
gh pr create --base main --title "fix: make Dify assistant popup feel native" --body "<body closing #1296>"
gh pr merge --squash --auto
gh pr checks --watch
```

The PR body must include `Closes #1296`, the behavior and verification summary,
and the standard generated-with-Claude trailer required by the repository.

- [ ] **Step 6: Confirm terminal state**

Verify the PR is merged, issue #1296 is closed, required checks passed, and the
remote feature branch is deleted.
