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
    await expect(page.getByRole('img', { name: 'ReadingDNA' })).toBeVisible();
  });
});

test.describe('Desktop hub rail', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('shows the five hubs in the rail', async ({ page }) => {
    await page.goto('/');
    for (const href of ['/', '/later', '/ask', '/learn', '/recap']) {
      await expect(page.locator(`aside a[href="${href}"]`).first()).toBeVisible();
    }
  });

  test('Read hub is active at / and /today', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside a[href="/"]').first()).toHaveClass(/bg-surface-2/);
    await page.goto('/today');
    await expect(page.locator('aside a[href="/"]').first()).toHaveClass(/bg-surface-2/);
  });

  test('Read hub is NOT active in the Library hub', async ({ page }) => {
    await page.goto('/later');
    await expect(page.locator('aside a[href="/"]').first()).not.toHaveClass(/bg-surface-2/);
    await expect(page.locator('aside a[href="/later"]').first()).toHaveClass(/bg-surface-2/);
  });

  test('hub tabs switch between Brief and Today', async ({ page }) => {
    await page.goto('/');
    const tabs = page.getByRole('navigation', { name: 'Read' });
    await tabs.getByRole('link', { name: 'Today' }).click();
    await expect(page).toHaveURL('/today');
    await expect(tabs.getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page');
    await tabs.getByRole('link', { name: 'Brief', exact: true }).click();
    await expect(page).toHaveURL('/');
  });

  test('Library hub tabs show Later, Starred, Archive', async ({ page }) => {
    await page.goto('/later');
    const tabs = page.getByRole('navigation', { name: 'Library' });
    for (const href of ['/later', '/starred', '/archive']) {
      await expect(tabs.locator(`a[href="${href}"]`)).toBeVisible();
    }
  });

  test('account menu shows Feeds, Settings and admin pages', async ({ page }) => {
    await page.goto('/');
    await page.locator('aside').getByRole('button').last().click();
    const menu = page.getByRole('dialog');
    await expect(menu.getByRole('link', { name: 'Feeds', exact: true })).toBeVisible();
    await expect(menu.getByRole('link', { name: 'Settings', exact: true })).toBeVisible();
    await expect(menu.getByRole('group', { name: 'Theme' })).toBeVisible();
  });
});

test.describe('Mobile bottom navigation', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('shows Read, Library, Ask, Learn and You', async ({ page }) => {
    await page.goto('/');
    const bar = page.locator('nav.fixed').first();
    for (const href of ['/', '/later', '/ask', '/learn']) {
      await expect(bar.locator(`a[href="${href}"]`)).toBeVisible();
    }
    await expect(bar.getByRole('button', { name: 'You' })).toBeVisible();
  });

  test('Later is reachable from the Library hub', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav.fixed a[href="/later"]').first().click();
    await expect(page).toHaveURL('/later');
  });

  test('mobile nav has 5 slots', async ({ page }) => {
    await page.goto('/');
    const mobileNav = page.locator('nav.fixed').first();
    await expect(mobileNav.locator('a')).toHaveCount(4);
    await expect(mobileNav.locator('button')).toHaveCount(1);
  });

  test('You sheet exposes Insights and account pages', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'You' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByRole('link', { name: 'Weekly Recap' })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Feeds', exact: true })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Settings', exact: true })).toBeVisible();
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
