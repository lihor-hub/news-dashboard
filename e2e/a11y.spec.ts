/**
 * Accessibility smoke tests — desktop and mobile.
 *
 * Uses axe-core (bundled at e2e/axe.min.js) to check for serious/critical
 * WCAG 2 A/AA violations across the core routes. Intentional exclusions are
 * named inline with a comment explaining why they are safe.
 *
 * CI: wired as a required gate in ci.yml (test-a11y job). Runs on every PR
 * and push; failures block merging.
 */
import { expect, test } from '@playwright/test';
import { mockApi, SAMPLE_ARTICLE } from './fixtures';
import { checkA11y } from './a11y-helper';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

// ── Desktop routes ────────────────────────────────────────────────────────────

test.describe('a11y — desktop routes', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Brief / — no serious/critical violations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Today /today — no serious/critical violations', async ({ page }) => {
    await page.goto('/today');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Search /search — no serious/critical violations', async ({ page }) => {
    await page.goto('/search');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Ask AI /ask — no serious/critical violations', async ({ page }) => {
    await page.goto('/ask');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Feeds /feeds — no serious/critical violations', async ({ page }) => {
    await page.goto('/feeds');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Settings /settings — no serious/critical violations', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Article reader /a/1 — no serious/critical violations', async ({ page }) => {
    await page.goto('/a/1');
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: SAMPLE_ARTICLE.title })).toBeVisible();
    await checkA11y(page);
  });
});

// ── Dialog / overlay state ────────────────────────────────────────────────────

test.describe('a11y — command palette dialog', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('command palette open — no serious/critical violations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.keyboard.press('Control+k');
    await page.getByPlaceholder(/jump to a view/i).waitFor({ state: 'visible' });
    await checkA11y(page);
  });
});

// ── Mobile viewport ───────────────────────────────────────────────────────────

test.describe('a11y — mobile viewport', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('Brief / on mobile — no serious/critical violations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });

  test('Today /today on mobile — no serious/critical violations', async ({ page }) => {
    await page.goto('/today');
    await page.waitForLoadState('networkidle');
    await checkA11y(page);
  });
});
