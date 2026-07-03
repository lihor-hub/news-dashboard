/**
 * E2E coverage for human-approved agent action plans on the Ask AI page.
 */
import { test, expect } from '@playwright/test';
import { mockApi, json } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test.describe('Ask AI — actionable requests propose a plan', () => {
  test('shows a proposed plan and approves it', async ({ page }) => {
    await page.route('/api/agent/actions/plan', (r) =>
      r.fulfill(
        json({
          actionable: true,
          run_id: 42,
          status: 'proposed',
          steps: [
            {
              id: 1,
              run_id: 42,
              ordinal: 0,
              tool: 'archive_article',
              article_id: 1,
              article_title: 'AI Safety Researchers Publish New Framework',
              status: 'pending',
              result_summary: null,
            },
          ],
        })
      )
    );
    await page.route('/api/agent/actions/42/approve', (r) =>
      r.fulfill(
        json({
          id: 42,
          user_id: 1,
          query: 'archive the AI safety story',
          status: 'executed',
          created_at: '',
          updated_at: '',
          steps: [
            {
              id: 1,
              run_id: 42,
              ordinal: 0,
              tool: 'archive_article',
              article_id: 1,
              article_title: 'AI Safety Researchers Publish New Framework',
              status: 'executed',
              result_summary: 'archive_article applied to article 1',
            },
          ],
        })
      )
    );

    await page.goto('/ask');
    await page.getByRole('textbox').fill('archive the AI safety story');
    await page.getByRole('button', { name: /ask/i }).click();

    await expect(page.getByText('Proposed actions')).toBeVisible();
    await expect(page.getByText('AI Safety Researchers Publish New Framework')).toBeVisible();

    await page.getByRole('button', { name: /approve/i }).click();
    await expect(page.getByText('Actions completed')).toBeVisible();
  });

  test('cancelling a plan performs no action', async ({ page }) => {
    await page.route('/api/agent/actions/plan', (r) =>
      r.fulfill(
        json({
          actionable: true,
          run_id: 43,
          status: 'proposed',
          steps: [
            {
              id: 2,
              run_id: 43,
              ordinal: 0,
              tool: 'star_article',
              article_id: 1,
              article_title: 'AI Safety Researchers Publish New Framework',
              status: 'pending',
              result_summary: null,
            },
          ],
        })
      )
    );
    await page.route('/api/agent/actions/43/cancel', (r) =>
      r.fulfill(
        json({
          id: 43,
          user_id: 1,
          query: 'star it',
          status: 'cancelled',
          created_at: '',
          updated_at: '',
          steps: [],
        })
      )
    );

    await page.goto('/ask');
    await page.getByRole('textbox').fill('star it');
    await page.getByRole('button', { name: /ask/i }).click();

    await expect(page.getByText('Proposed actions')).toBeVisible();
    await page.getByRole('button', { name: /cancel/i }).click();
    await expect(page.getByText(/Plan cancelled/)).toBeVisible();
  });

  test('non-actionable questions still answer normally', async ({ page }) => {
    await page.goto('/ask');
    await page.getByRole('textbox').fill('What is the latest AI news?');
    await page.getByRole('button', { name: /ask/i }).click();
    await expect(
      page.getByText(/Based on the articles, AI safety research is progressing rapidly/)
    ).toBeVisible({ timeout: 3000 });
  });
});
