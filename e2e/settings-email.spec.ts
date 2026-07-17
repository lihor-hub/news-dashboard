import { expect, test } from '@playwright/test';
import { mockApi, SAMPLE_USER } from './fixtures';

test('enables email briefing and sends a preview without external delivery', async ({ page }) => {
  await mockApi(page);
  await page.goto('/settings');

  const region = page.getByRole('region', { name: 'Email briefing' });
  await expect(region).toBeVisible();
  await expect(region.getByText(SAMPLE_USER.email)).toBeVisible();

  const enableRequest = page.waitForRequest(
    (request) => request.url().endsWith('/api/settings/notifications') && request.method() === 'PUT'
  );
  await region.getByRole('button', { name: 'Enable email briefing' }).click();
  expect((await enableRequest).postDataJSON()).toEqual({ email_enabled: true });

  await expect(region.getByText('Enabled')).toBeVisible();
  await expect(region.getByRole('button', { name: 'Disable email briefing' })).toBeVisible();

  const previewRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith('/api/settings/notifications/email/preview') &&
      request.method() === 'POST'
  );
  await region.getByRole('button', { name: 'Send preview email' }).click();
  await previewRequest;
  await expect(region.getByText('Preview email sent.')).toBeVisible();
});
