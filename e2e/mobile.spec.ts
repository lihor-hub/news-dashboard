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

  test('all 5 mobile nav items are visible', async ({ page }) => {
    await page.goto('/');
    const mobileNav = page.locator('nav.fixed').first();
    const links = mobileNav.locator('a');
    await expect(links).toHaveCount(5);
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

  test('tapping Today in mobile nav goes to /today', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/today"]').first().click();
    await expect(page).toHaveURL('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('tapping Later in mobile nav goes to /later', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/later"]').first().click();
    await expect(page).toHaveURL('/later');
  });

  test('tapping Starred in mobile nav goes to /starred', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/starred"]').first().click();
    await expect(page).toHaveURL('/starred');
  });
});

test.describe('Mobile — header', () => {
  test('header is visible on mobile', async ({ page }) => {
    await page.goto('/');
    const header = page.locator('header');
    await expect(header).toBeVisible();
  });

  test('RD brand mark is visible on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('RD')).toBeVisible();
  });

  test('More button is visible on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'More' })).toBeVisible();
  });

  test('More button opens sheet with secondary nav', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'More' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('Feeds')).toBeVisible();
    await expect(sheet.getByText('Stats')).toBeVisible();
    await expect(sheet.getByText('Archive')).toBeVisible();
    await expect(sheet.getByText('Settings')).toBeVisible();
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
