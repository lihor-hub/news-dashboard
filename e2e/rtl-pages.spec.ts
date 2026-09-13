import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';
import { checkA11y } from './a11y-helper';

test('Arabic search pages reserve the correct edge for search and clear controls', async ({
  page,
}) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('i18nextLng', 'ar'));
  await page.goto('/search');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const search = page.getByPlaceholder('Search titles, summaries, tags, full text…');
  await expect(search).toHaveCSS('padding-inline-start', '36px');
  await expect(search).toHaveCSS('padding-inline-end', '12px');
  const inputBox = await search.boundingBox();
  const iconBox = await search.locator('..').locator('svg').boundingBox();
  if (!inputBox || !iconBox) throw new Error('Search input and icon must have layout boxes');
  expect(iconBox.x).toBeGreaterThan(inputBox.x + inputBox.width / 2);
  await checkA11y(page);

  await page.goto('/reading-list');
  await page.waitForLoadState('networkidle');
  const savedSearch = page.getByPlaceholder('Search saved links');
  await savedSearch.fill('article');
  const clear = page.getByRole('button', { name: 'Clear search' });
  const savedBox = await savedSearch.boundingBox();
  const clearBox = await clear.boundingBox();
  if (!savedBox || !clearBox) throw new Error('Saved search controls must have layout boxes');
  expect(clearBox.x + clearBox.width).toBeLessThan(savedBox.x + savedBox.width / 2);
  await clear.click();
  await expect(savedSearch).toHaveValue('');
});
