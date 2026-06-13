/**
 * E2E tests for the Brief page (/) — the default home.
 */
import { test, expect } from '@playwright/test';
import { mockApi, SAMPLE_BRIEFING } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Brief page — layout and content', () => {
  test('renders the briefing title', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('AI Safety Takes Center Stage')).toBeVisible();
  });

  test('renders the executive summary', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByText(/New safety frameworks and model releases/)
    ).toBeVisible();
  });

  test('renders section headings', async ({ page }) => {
    await page.goto('/');
    // Use exact match: 'Safety Research' also appears inside the article title string
    await expect(page.getByText('Safety Research', { exact: true })).toBeVisible();
    await expect(page.getByText('Model Releases', { exact: true })).toBeVisible();
  });

  test('renders section body text', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/Anthropic published a new safety framework/)).toBeVisible();
  });

  test('renders citation chip for cited article', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByText('AI Safety Researchers Publish New Framework').first()
    ).toBeVisible();
  });

  test('renders "Also worth a look" section', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Also worth a look')).toBeVisible();
    await expect(page.getByText('OpenAI Releases GPT-5 Technical Report').first()).toBeVisible();
  });

  test('shows generated timestamp metadata', async ({ page }) => {
    await page.goto('/');
    // Should show article count
    await expect(page.getByText(/2 articles|1 article/)).toBeVisible();
  });

  test('has a Refresh button', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: /refresh|generate new/i })).toBeVisible();
  });
});

test.describe('Brief page — citation navigation', () => {
  test('citation chip links to /a/:id', async ({ page }) => {
    await page.goto('/');
    const chip = page
      .locator('a[href="/a/1"]')
      .filter({ hasText: 'AI Safety Researchers Publish New Framework' })
      .first();
    await expect(chip).toBeVisible();
  });

  test('worth-opening article links to /a/:id', async ({ page }) => {
    await page.goto('/');
    const link = page
      .locator('a[href="/a/2"]')
      .filter({ hasText: 'OpenAI Releases GPT-5 Technical Report' })
      .first();
    await expect(link).toBeVisible();
  });
});

test.describe('Brief page — empty state', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/briefings/latest', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'empty' }) })
    );
  });

  test('shows empty state message', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('No briefing yet')).toBeVisible();
  });

  test('shows Generate briefing button', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: /generate briefing/i })).toBeVisible();
  });

  test('shows Review Today feed button', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: /review today feed/i })).toBeVisible();
  });

  test('Review Today feed navigates to /today', async ({ page }) => {
    await page.route('/api/articles**', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    );
    await page.goto('/');
    await page.getByRole('button', { name: /review today feed/i }).click();
    await expect(page).toHaveURL('/today');
  });
});

test.describe('Brief page — generating state', () => {
  test('Generate button shows loading state while generating', async ({ page }) => {
    // Make POST take a long time
    await page.route('/api/briefings/latest', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'empty' }) })
    );
    await page.route('/api/briefings', async (r) => {
      if (r.request().method() === 'POST') {
        await new Promise((res) => setTimeout(res, 3000));
        return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(SAMPLE_BRIEFING) });
      }
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    });

    await page.goto('/');
    await page.getByRole('button', { name: /generate briefing/i }).click();
    // During generation, button should be disabled with loading text
    await expect(page.getByRole('button', { name: /generating/i })).toBeDisabled();
  });
});

test.describe('Brief page — AI not configured error', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/briefings/latest', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'empty' }) })
    );
    await page.route('/api/briefings', async (r) => {
      if (r.request().method() === 'POST') {
        return r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'OPENAI_API_KEY not set' }) });
      }
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    });
  });

  test('shows AI not configured error', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /generate briefing/i }).click();
    await expect(page.getByText('AI not configured')).toBeVisible();
  });

  test('shows Review Today feed path after error', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /generate briefing/i }).click();
    await expect(page.getByRole('button', { name: /review today feed/i })).toBeVisible();
  });
});

test.describe('Brief page — no console errors', () => {
  test('no unhandled console errors on load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    await page.waitForTimeout(500);
    // Filter out React hydration warnings which are expected in dev
    const realErrors = errors.filter(
      (e) => !e.includes('React') && !e.includes('Warning') && !e.includes('favicon')
    );
    expect(realErrors).toHaveLength(0);
  });
});
