/**
 * E2E tests for the command palette (⌘K / Ctrl+K).
 */
import { test, expect } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
});

test.describe('Command palette — open/close', () => {
  test('opens with Ctrl+K', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
  });

  test('opens with Meta+K', async ({ page }) => {
    await page.keyboard.press('Meta+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
  });

  test('closes with Escape', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByPlaceholder(/jump to a view/i)).not.toBeVisible();
  });

  test('desktop Command button opens palette', async ({ page, viewport }) => {
    if (!viewport || viewport.width < 768) test.skip();
    await page.click('button:has-text("Command")');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
  });
});

test.describe('Command palette — navigation items', () => {
  test.beforeEach(async ({ page }) => {
    await page.keyboard.press('Control+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
  });

  test('shows Brief nav item', async ({ page }) => {
    await expect(page.getByRole('option', { name: /brief/i })).toBeVisible();
  });

  test('shows Today nav item', async ({ page }) => {
    await expect(page.getByRole('option', { name: /today/i })).toBeVisible();
  });

  test('shows Later nav item', async ({ page }) => {
    await expect(page.getByRole('option', { name: /later/i })).toBeVisible();
  });

  test('shows Starred nav item', async ({ page }) => {
    await expect(page.getByRole('option', { name: /starred/i })).toBeVisible();
  });

  test('shows Ask AI nav item', async ({ page }) => {
    await expect(page.getByRole('option', { name: /ask ai/i })).toBeVisible();
  });

  test('shows Feeds nav item', async ({ page }) => {
    // Use exact name to avoid matching "Refresh Feeds Now" action item
    await expect(page.getByRole('option', { name: 'Feeds', exact: true })).toBeVisible();
  });

  test('shows Refresh feeds action', async ({ page }) => {
    await expect(page.getByText(/refresh feeds now/i)).toBeVisible();
  });

  test('shows Keyboard shortcuts action', async ({ page }) => {
    await expect(page.getByText(/keyboard shortcuts/i)).toBeVisible();
  });
});

test.describe('Command palette — article search', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/search**', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 10,
              url: 'https://example.com/search-result',
              canonical_url: 'https://example.com/search-result',
              title: 'Search Result Article',
              source_slug: 'test-source',
              source_name: 'Test Source',
              category: 'ai',
              kind: 'rss_feed',
              published_at: '2026-06-13T10:00:00+00:00',
              discovered_at: '2026-06-13T11:00:00+00:00',
              status: 'new',
              state: 'today',
              importance_score: 70,
              summary: 'A search result.',
              reason: 'Relevant.',
              tags: '[]',
              starred: false,
              read_at: null,
              saved_at: null,
              skipped_at: null,
              archived_at: null,
              done_at: null,
              starred_at: null,
              later_until: null,
              restored_at: null,
              body: null,
              body_status: 'missing',
            },
          ],
        }),
      })
    );
    await page.keyboard.press('Control+k');
  });

  test('searching shows article results', async ({ page }) => {
    await page.getByPlaceholder(/jump to a view/i).fill('search result');
    await expect(page.getByText('Search Result Article')).toBeVisible({ timeout: 2000 });
  });
});

test.describe('Command palette — navigation action', () => {
  test('clicking Today navigates to /today', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await page.getByRole('option', { name: /^today$/i }).click();
    await expect(page).toHaveURL('/today');
  });

  test('clicking Brief navigates to /', async ({ page }) => {
    await page.goto('/today');
    await page.keyboard.press('Control+k');
    await page.getByRole('option', { name: /^brief$/i }).click();
    await expect(page).toHaveURL('/');
  });
});
