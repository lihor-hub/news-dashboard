import { expect, test } from '@playwright/test';
import { mockApi, SAMPLE_ARTICLE } from './fixtures';
import { checkA11y } from './a11y-helper';

test('Arabic mirrors component controls while keeping dialogs centered', async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('i18nextLng', 'ar'));
  await page.goto('/a/1');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', { name: SAMPLE_ARTICLE.title })).toBeVisible();
  const back = page.getByRole('button', { name: 'Back', exact: true });
  await expect(back).toHaveCSS('margin-inline-start', '-4px');
  await checkA11y(page);

  await page.goto('/today');
  await page.waitForLoadState('networkidle');
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  const close = dialog.getByRole('button', { name: 'Close', exact: true });
  const dialogBox = await dialog.boundingBox();
  const closeBox = await close.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(closeBox).not.toBeNull();
  if (!dialogBox || !closeBox) throw new Error('Dialog controls must have layout boxes');
  expect(
    Math.abs(dialogBox.x + dialogBox.width / 2 - (page.viewportSize()?.width ?? 0) / 2)
  ).toBeLessThan(2);
  expect(closeBox.x + closeBox.width).toBeLessThan(dialogBox.x + dialogBox.width / 2);
  await checkA11y(page);
});
