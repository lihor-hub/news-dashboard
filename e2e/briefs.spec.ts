/**
 * E2E tests for the Briefing History pages (/briefs and /briefs/:id).
 */
import { test, expect } from '@playwright/test';
import { mockApi, SAMPLE_BRIEFING } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Briefing History list — /briefs', () => {
  test('shows Briefs heading', async ({ page }) => {
    await page.goto('/briefs');
    await expect(page.locator('h1').filter({ hasText: 'Briefs' })).toBeVisible();
  });

  test('shows page sub-heading', async ({ page }) => {
    await page.goto('/briefs');
    await expect(page.getByText('Briefing History')).toBeVisible();
  });

  test('renders briefing title in the list', async ({ page }) => {
    await page.goto('/briefs');
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
  });

  test('briefing row links to detail page', async ({ page }) => {
    await page.goto('/briefs');
    const row = page.getByRole('link', { name: new RegExp(SAMPLE_BRIEFING.title) });
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('href', `/briefs/${SAMPLE_BRIEFING.id}`);
  });

  test('briefing summary snippet is shown', async ({ page }) => {
    await page.goto('/briefs');
    await expect(page.locator('main')).toContainText(
      SAMPLE_BRIEFING.summary.slice(0, 30)
    );
  });

  test('clicking a row navigates to the detail page', async ({ page }) => {
    await page.goto('/briefs');
    const row = page.getByRole('link', { name: new RegExp(SAMPLE_BRIEFING.title) });
    await row.click();
    await expect(page).toHaveURL(`/briefs/${SAMPLE_BRIEFING.id}`);
  });
});

test.describe('Briefing History detail — /briefs/:id', () => {
  test('shows Briefs heading', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    await expect(page.locator('h1').filter({ hasText: 'Briefs' })).toBeVisible();
  });

  test('shows back link to history', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    const back = page.getByRole('link', { name: /briefing history/i });
    await expect(back).toBeVisible();
    await expect(back).toHaveAttribute('href', '/briefs');
  });

  test('renders briefing title', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
  });

  test('renders briefing summary', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    await expect(page.getByText(SAMPLE_BRIEFING.summary)).toBeVisible();
  });

  test('renders section heading', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    const sectionTitle = SAMPLE_BRIEFING.content.sections[0].title;
    await expect(page.getByText(sectionTitle, { exact: true })).toBeVisible();
  });

  test('back link navigates to /briefs', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    const back = page.getByRole('link', { name: /briefing history/i });
    await back.click();
    await expect(page).toHaveURL('/briefs');
  });

  test('no Refresh button on detail page', async ({ page }) => {
    await page.goto(`/briefs/${SAMPLE_BRIEFING.id}`);
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
    await expect(page.getByRole('button', { name: /refresh/i })).toHaveCount(0);
  });
});

test.describe('Brief page — View history link', () => {
  test('BriefPage shows "View history" link to /briefs', async ({ page }) => {
    await page.goto('/');
    const link = page.getByRole('link', { name: /view history/i });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', '/briefs');
  });

  test('"View history" link navigates to /briefs', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /view history/i }).click();
    await expect(page).toHaveURL('/briefs');
  });
});

test.describe('Navigation — Brief History entries', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('desktop rail secondary nav shows Brief History', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside a[href="/briefs"]').first()).toBeVisible();
  });

  test('Brief History is active at /briefs', async ({ page }) => {
    await page.goto('/briefs');
    await expect(page.locator('aside a[href="/briefs"]').first()).toHaveClass(/bg-surface-2/);
  });

  test('clicking Brief History in nav navigates to /briefs', async ({ page }) => {
    await page.goto('/');
    await page.locator('aside a[href="/briefs"]').first().click();
    await expect(page).toHaveURL('/briefs');
  });
});

test.describe('Command palette — Briefing History', () => {
  test('command palette includes Briefing History item', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Meta+k');
    const option = page.getByRole('option', { name: 'Briefing History', exact: true });
    await expect(option).toBeVisible();
    await page.keyboard.press('Escape');
  });
});
