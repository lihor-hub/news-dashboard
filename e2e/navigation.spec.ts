/**
 * E2E tests for navigation: desktop rail, mobile bottom nav, routing, header.
 */
import { test, expect } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Header', () => {
  test('shows "Brief" title at /', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1').filter({ hasText: 'Brief' })).toBeVisible();
  });

  test('shows "Today" title at /today', async ({ page }) => {
    await page.goto('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('shows "Later" title at /later', async ({ page }) => {
    await page.goto('/later');
    await expect(page.locator('h1').filter({ hasText: 'Later' })).toBeVisible();
  });

  test('shows "Starred" title at /starred', async ({ page }) => {
    await page.goto('/starred');
    await expect(page.locator('h1').filter({ hasText: 'Starred' })).toBeVisible();
  });

  test('shows "Search" title at /search', async ({ page }) => {
    await page.goto('/search');
    await expect(page.locator('h1').filter({ hasText: 'Search' })).toBeVisible();
  });

  test('shows "Ask AI" title at /ask', async ({ page }) => {
    await page.goto('/ask');
    await expect(page.locator('h1').filter({ hasText: 'Ask AI' })).toBeVisible();
  });

  test('logo/brand mark is visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('RD')).toBeVisible();
  });
});

test.describe('Desktop navigation rail', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('shows Brief link pointing to /', async ({ page }) => {
    await page.goto('/');
    const briefLink = page.locator('aside a[href="/"]').first();
    await expect(briefLink).toBeVisible();
  });

  test('shows Today link pointing to /today', async ({ page }) => {
    await page.goto('/');
    const todayLink = page.locator('aside a[href="/today"]').first();
    await expect(todayLink).toBeVisible();
  });

  test('shows Later link', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside a[href="/later"]').first()).toBeVisible();
  });

  test('shows Starred link', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside a[href="/starred"]').first()).toBeVisible();
  });

  test('Brief is active at /', async ({ page }) => {
    await page.goto('/');
    const briefLink = page.locator('aside a[href="/"]').first();
    // Active link has bg-surface-2 class
    await expect(briefLink).toHaveClass(/bg-surface-2/);
  });

  test('Today is active at /today', async ({ page }) => {
    await page.goto('/today');
    const todayLink = page.locator('aside a[href="/today"]').first();
    await expect(todayLink).toHaveClass(/bg-surface-2/);
  });

  test('Brief is NOT active at /today', async ({ page }) => {
    await page.goto('/today');
    const briefLink = page.locator('aside a[href="/"]').first();
    await expect(briefLink).not.toHaveClass(/bg-surface-2/);
  });

  test('clicking Today link navigates to /today', async ({ page }) => {
    await page.goto('/');
    await page.locator('aside a[href="/today"]').first().click();
    await expect(page).toHaveURL('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('clicking Brief link navigates to /', async ({ page }) => {
    await page.goto('/today');
    await page.locator('aside a[href="/"]').first().click();
    await expect(page).toHaveURL('/');
  });

  test('secondary nav shows Feeds, Stats, Archive, Settings', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside a[href="/feeds"]').first()).toBeVisible();
    await expect(page.locator('aside a[href="/stats"]').first()).toBeVisible();
    await expect(page.locator('aside a[href="/archive"]').first()).toBeVisible();
    await expect(page.locator('aside a[href="/settings"]').first()).toBeVisible();
  });
});

test.describe('Mobile bottom navigation', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('shows Brief in mobile nav', async ({ page }) => {
    await page.goto('/');
    const briefLink = page.locator('nav.fixed a[href="/"]').first();
    await expect(briefLink).toBeVisible();
  });

  test('shows Today in mobile nav', async ({ page }) => {
    await page.goto('/');
    const todayLink = page.locator('nav.fixed a[href="/today"]').first();
    await expect(todayLink).toBeVisible();
  });

  test('shows Later in mobile nav', async ({ page }) => {
    await page.goto('/');
    const laterLink = page.locator('nav.fixed a[href="/later"]').first();
    await expect(laterLink).toBeVisible();
  });

  test('shows Starred in mobile nav', async ({ page }) => {
    await page.goto('/');
    const starredLink = page.locator('nav.fixed a[href="/starred"]').first();
    await expect(starredLink).toBeVisible();
  });

  test('mobile nav has 5 items', async ({ page }) => {
    await page.goto('/');
    const mobileNav = page.locator('nav.fixed').first();
    const links = mobileNav.locator('a');
    await expect(links).toHaveCount(5);
  });

  test('clicking Today in mobile nav navigates', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/today"]').first().click();
    await expect(page).toHaveURL('/today');
  });
});

test.describe('Route coverage — all major routes render', () => {
  for (const [path, heading] of [
    ['/', 'Brief'],
    ['/today', 'Today'],
    ['/later', 'Later'],
    ['/starred', 'Starred'],
    ['/search', 'Search'],
    ['/ask', 'Ask AI'],
  ]) {
    test(`${path} renders ${heading}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('h1').filter({ hasText: heading })).toBeVisible();
    });
  }

  test('/feeds renders Feeds', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });
});

test.describe('Legacy redirects', () => {
  test('/inbox redirects to /today', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page).toHaveURL('/today');
  });

  test('/saved redirects to /starred', async ({ page }) => {
    await page.goto('/saved');
    await expect(page).toHaveURL('/starred');
  });

  test('/sources redirects to /feeds', async ({ page }) => {
    await page.goto('/sources');
    await expect(page).toHaveURL('/feeds');
  });
});
