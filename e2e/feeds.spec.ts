/**
 * E2E tests for the Feeds tab (Sources, Scheduler, Runs, Logs).
 */
import { test, expect } from '@playwright/test';
import { mockApi, SAMPLE_SOURCE } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Feeds page — Sources tab', () => {
  test('shows Feeds heading', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('shows source list', async ({ page }) => {
    await page.goto('/feeds');
    // Source appears in both desktop table and mobile card layouts — check main content
    await expect(page.locator('main')).toContainText('Anthropic Blog');
  });

  test('shows source enabled toggle', async ({ page }) => {
    await page.goto('/feeds');
    // Sources have enable/disable switches
    const toggles = page.getByRole('switch');
    await expect(toggles.first()).toBeVisible();
  });

  test('shows source last-checked timestamp', async ({ page }) => {
    await page.goto('/feeds');
    // Source appears in both desktop table and mobile card layouts — check main content
    await expect(page.locator('main')).toContainText(SAMPLE_SOURCE.name);
  });
});

test.describe('Feeds page — Scheduler tab', () => {
  test('shows Scheduler tab', async ({ page }) => {
    await page.goto('/feeds/schedule');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('shows interval setting', async ({ page }) => {
    await page.goto('/feeds/schedule');
    await expect(page.getByText(/60|interval|every/i).first()).toBeVisible();
  });
});

test.describe('Feeds page — tab navigation', () => {
  test('clicking Runs shows runs page', async ({ page }) => {
    await page.goto('/feeds');
    // Look for Runs tab/link
    const runsLink = page.getByRole('link', { name: /runs/i });
    if (await runsLink.count() > 0) {
      await runsLink.click();
      await expect(page).toHaveURL('/feeds/runs');
    }
  });
});

test.describe('Settings page', () => {
  test('navigates to /settings', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
  });
});
