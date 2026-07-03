/**
 * E2E tests for the PWA share-target flow and offline article reading.
 *
 * The dev server (used by playwright.config.ts) runs VitePWA with
 * `devOptions.enabled: false`, so no real service worker/workbox cache is
 * active here — that only exists in a production build. These tests instead
 * verify the app-level behavior: the share-target route saves a shared link
 * and redirects to it, and the app keeps rendering already-fetched data
 * (via mocked routes, which Playwright still fulfills even once the browser
 * context is offline) while surfacing an offline indicator.
 */
import { test, expect } from '@playwright/test';
import { mockApi, SAMPLE_ARTICLE } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Share target', () => {
  test('saves a shared URL and redirects to the article', async ({ page }) => {
    let requestBody: unknown;
    await page.route('/api/articles/from-url', async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...SAMPLE_ARTICLE, id: 1, state: 'later' }),
      });
    });

    await page.goto(
      '/share-target?url=' +
        encodeURIComponent('https://example.com/shared-article') +
        '&title=' +
        encodeURIComponent('Shared Article')
    );

    await expect(page).toHaveURL('/a/1');
    expect(requestBody).toMatchObject({
      url: 'https://example.com/shared-article',
      title: 'Shared Article',
    });
  });

  test('shows an error when no link is present in the shared content', async ({ page }) => {
    await page.goto('/share-target?title=' + encodeURIComponent('just a title, no link'));
    await expect(page.getByText("Couldn't save link")).toBeVisible();
  });
});

test.describe('Offline reading', () => {
  test('shows the offline indicator when the network drops', async ({ page, context }) => {
    await page.goto('/a/1');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();

    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));

    await expect(page.getByText(/you're offline/i)).toBeVisible();

    await context.setOffline(false);
  });

  test('a previously loaded article still renders after a client-side revisit while offline', async ({
    page,
    context,
  }) => {
    await page.goto('/today');
    await page.getByText(SAMPLE_ARTICLE.title).click();
    await expect(page).toHaveURL('/a/1');
    await expect(page.getByText('Full article body text here.')).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL('/today');

    // A full page navigation would fail offline (no service worker in dev
    // mode), but revisiting the article is a client-side route change —
    // only the mocked /api/* calls run, and Playwright still fulfills those
    // while the browser context is offline.
    await context.setOffline(true);
    await page.getByText(SAMPLE_ARTICLE.title).click();
    await expect(page).toHaveURL('/a/1');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();

    await context.setOffline(false);
  });
});
