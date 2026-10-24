/**
 * E2E tests for mobile viewport behavior.
 * Tests run at iPhone 14 dimensions (390×844).
 */
import { test, expect } from '@playwright/test';
import { mockApi } from './fixtures';

// All tests in this file use mobile viewport
test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Mobile — Brief page', () => {
  test('renders correctly on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('AI Safety Takes Center Stage')).toBeVisible();
  });

  test('desktop rail is hidden on mobile', async ({ page }) => {
    await page.goto('/');
    const rail = page.locator('aside.hidden');
    await expect(rail).toBeAttached();
  });

  test('mobile bottom nav is visible', async ({ page }) => {
    await page.goto('/');
    const mobileNav = page.locator('nav.fixed').first();
    await expect(mobileNav).toBeVisible();
  });

  test('all 5 mobile nav slots are visible', async ({ page }) => {
    await page.goto('/');
    const mobileNav = page.locator('nav.fixed').first();
    await expect(mobileNav.locator('a')).toHaveCount(4);
    await expect(mobileNav.getByRole('button', { name: 'You' })).toBeVisible();
  });
});

test.describe('Mobile — Today feed', () => {
  test('Today feed renders on mobile', async ({ page }) => {
    await page.goto('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });
});

test.describe('Mobile — navigation', () => {
  test('tapping Brief in mobile nav stays at /', async ({ page }) => {
    await page.goto('/today');
    await page.locator('nav.fixed a[href="/"]').first().click();
    await expect(page).toHaveURL('/');
    await expect(page.locator('h1').filter({ hasText: 'Brief' })).toBeVisible();
  });

  test('tapping the Today tab of the Read hub goes to /today', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('navigation', { name: 'Read' }).locator('a[href="/today"]').click();
    await expect(page).toHaveURL('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('Later is reachable from the Library hub', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/later"]').first().click();
    await expect(page).toHaveURL('/later');
  });

  test('tapping the Starred tab of the Library hub goes to /starred', async ({ page }) => {
    await page.goto('/later');
    await page.getByRole('navigation', { name: 'Library' }).locator('a[href="/starred"]').click();
    await expect(page).toHaveURL('/starred');
  });
});

test.describe('Mobile — header', () => {
  test('header is visible on mobile', async ({ page }) => {
    await page.goto('/');
    const header = page.getByRole('banner');
    await expect(header).toBeVisible();
  });

  test('ReadingDNA brand mark is visible on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('img', { name: 'ReadingDNA' })).toBeVisible();
  });

  test('You button is visible on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'You' })).toBeVisible();
  });

  test('You sheet lists Insights and account pages', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'You' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByRole('link', { name: 'Feeds', exact: true })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Stats', exact: true })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Weekly Recap', exact: true })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Settings', exact: true })).toBeVisible();
  });

  test('Library hub tabs scroll to Archive', async ({ page }) => {
    await page.goto('/later');
    const tabs = page.getByRole('navigation', { name: 'Library' });
    await tabs.getByRole('link', { name: 'Archive' }).click();
    await expect(page).toHaveURL('/archive');
  });
});

test.describe('Mobile — no layout overflow', () => {
  test('Brief page does not overflow horizontally', async ({ page }) => {
    await page.goto('/');
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = 390;
    // Allow small margin (scrollbar etc)
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 20);
  });

  test('Today feed does not overflow horizontally', async ({ page }) => {
    await page.goto('/today');
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(bodyWidth).toBeLessThanOrEqual(410);
  });
});
