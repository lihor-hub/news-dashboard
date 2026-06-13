/**
 * E2E tests for Later, Starred, Search, Archive, and article reader pages.
 */
import { test, expect } from '@playwright/test';
import { mockApi, SAMPLE_ARTICLE, SAMPLE_ARTICLE_3, SAMPLE_STARRED_ARTICLE } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Later page', () => {
  test('shows Later heading', async ({ page }) => {
    await page.goto('/later');
    await expect(page.locator('h1').filter({ hasText: 'Later' })).toBeVisible();
  });

  test('shows later articles', async ({ page }) => {
    await page.route('/api/articles**', (r) => {
      const url = new URL(r.request().url());
      if (url.searchParams.get('state') === 'later') {
        return r.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [SAMPLE_ARTICLE_3] }),
        });
      }
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    });
    await page.goto('/later');
    await expect(page.getByText(SAMPLE_ARTICLE_3.title)).toBeVisible();
  });

  test('shows empty state when no later articles', async ({ page }) => {
    await page.route('/api/articles**', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    );
    await page.goto('/later');
    await expect(page.getByText('Nothing snoozed')).toBeVisible();
  });
});

test.describe('Starred page', () => {
  test('shows Starred heading', async ({ page }) => {
    await page.goto('/starred');
    await expect(page.locator('h1').filter({ hasText: 'Starred' })).toBeVisible();
  });

  test('shows starred articles', async ({ page }) => {
    await page.route('/api/articles**', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [SAMPLE_STARRED_ARTICLE] }),
      })
    );
    await page.goto('/starred');
    await expect(page.getByText(SAMPLE_STARRED_ARTICLE.title)).toBeVisible();
  });
});

test.describe('Search page', () => {
  test('shows Search heading', async ({ page }) => {
    await page.goto('/search');
    await expect(page.locator('h1').filter({ hasText: 'Search' })).toBeVisible();
  });

  test('shows search input', async ({ page }) => {
    await page.goto('/search');
    await expect(page.getByRole('textbox')).toBeVisible();
  });

  test('search results appear after typing', async ({ page }) => {
    await page.route('/api/search**', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [SAMPLE_ARTICLE] }),
      })
    );
    await page.goto('/search');
    await page.getByRole('textbox').fill('anthropic');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible({ timeout: 3000 });
  });

  test('shows empty search state before typing', async ({ page }) => {
    await page.route('/api/search**', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    );
    await page.goto('/search');
    // Before typing, no results
    await expect(page.getByText(SAMPLE_ARTICLE.title)).not.toBeVisible();
  });
});

test.describe('Archive page', () => {
  test('shows Archive heading', async ({ page }) => {
    await page.goto('/archive');
    await expect(page.locator('h1').filter({ hasText: 'Archive' })).toBeVisible();
  });
});

test.describe('Ask page', () => {
  test('shows Ask AI heading', async ({ page }) => {
    await page.goto('/ask');
    await expect(page.locator('h1').filter({ hasText: 'Ask AI' })).toBeVisible();
  });

  test('shows the question textarea', async ({ page }) => {
    await page.goto('/ask');
    await expect(page.getByRole('textbox')).toBeVisible();
  });

  test('Ask button is disabled when input empty', async ({ page }) => {
    await page.goto('/ask');
    const btn = page.getByRole('button', { name: /ask/i });
    await expect(btn).toBeDisabled();
  });

  test('Ask button enables after typing', async ({ page }) => {
    await page.goto('/ask');
    await page.getByRole('textbox').fill('What is the latest AI news?');
    const btn = page.getByRole('button', { name: /ask/i });
    await expect(btn).toBeEnabled();
  });

  test('submitting shows AI response', async ({ page }) => {
    await page.goto('/ask');
    await page.getByRole('textbox').fill('What is the latest AI news?');
    await page.getByRole('button', { name: /ask/i }).click();
    await expect(
      page.getByText(/Based on the articles, AI safety research is progressing rapidly/)
    ).toBeVisible({ timeout: 3000 });
  });

  test('response shows citation sources', async ({ page }) => {
    await page.goto('/ask');
    await page.getByRole('textbox').fill('Tell me about AI safety');
    await page.getByRole('button', { name: /ask/i }).click();
    await expect(
      page.getByText('AI Safety Researchers Publish New Framework')
    ).toBeVisible({ timeout: 3000 });
  });
});

test.describe('Article reader (/a/:id)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/articles/1', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SAMPLE_ARTICLE),
      })
    );
    await page.route('/api/articles/1/body', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...SAMPLE_ARTICLE, body: 'Full article body content.', body_status: 'ok' }),
      })
    );
  });

  test('navigates to /a/:id and shows article', async ({ page }) => {
    await page.goto('/a/1');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
  });

  test('shows article source', async ({ page }) => {
    await page.goto('/a/1');
    await expect(page.getByText('Anthropic Blog')).toBeVisible();
  });

  test('shows article body when loaded', async ({ page }) => {
    await page.goto('/a/1');
    await expect(page.getByText('Full article body content.')).toBeVisible({ timeout: 5000 });
  });

  test('back navigation returns to previous page', async ({ page }) => {
    await page.goto('/today');
    await page.goto('/a/1');
    await page.goBack();
    await expect(page).toHaveURL('/today');
  });
});
