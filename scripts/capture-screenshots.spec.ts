/**
 * Captures the README/docs-site product screenshots from a live demo-mode
 * instance. Not part of the regular e2e suite — run via:
 *
 *   npm run capture:screenshots
 *
 * Requires a reachable Postgres server (DATABASE_URL / DEMO_DATABASE_URL);
 * see scripts/screenshots.playwright.config.ts for how the demo backend and
 * frontend dev server are started.
 */
import path from 'node:path';
import { mkdir } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'screenshots');

test.beforeAll(async () => {
  await mkdir(OUT_DIR, { recursive: true });
});

test.beforeEach(async ({ page }) => {
  // Force light theme regardless of OS/browser preference.
  await page.addInitScript(() => {
    window.localStorage.setItem('theme', 'light');
  });
});

test('capture product screenshots', async ({ page }) => {
  await page.goto('/login');
  await page.locator('#username').fill('guest');
  await page.locator('#password').fill('demo');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL('**/');
  await page.waitForLoadState('networkidle');

  // Fresh sessions can show a first-run onboarding dialog and/or a "What's
  // new" changelog dialog; both open asynchronously after the initial
  // render, so poll for each rather than checking visibility once.
  async function dismissIfShown(name: RegExp) {
    const button = page.getByRole('button', { name });
    const shown = await button
      .waitFor({ state: 'visible', timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    if (shown) {
      await button.click();
      await button.waitFor({ state: 'hidden' });
    }
  }
  await dismissIfShown(/skip for now/i);
  await dismissIfShown(/got it/i);

  // 1. Today feed — the primary triage view, used as the README hero shot.
  await page.goto('/today');
  await page.waitForLoadState('networkidle');
  const firstArticleLink = page.locator('a[href^="/a/"]').first();
  await expect(firstArticleLink).toBeVisible();
  await page.screenshot({ path: path.join(OUT_DIR, 'today-feed.png') });

  // 2. Article detail — navigate to the first article from the feed. A
  // direct goto is used instead of clicking the row: clicking intermittently
  // updates the URL via history.pushState without React Router committing
  // the corresponding route render.
  const articleHref = await firstArticleLink.getAttribute('href');
  await page.goto(articleHref!);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(OUT_DIR, 'article-detail.png') });

  // 3. Briefing page — the AI daily-briefing landing view.
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(OUT_DIR, 'briefing.png') });

  // 4. Sources page — feed management.
  await page.goto('/feeds');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(OUT_DIR, 'sources.png') });
});
