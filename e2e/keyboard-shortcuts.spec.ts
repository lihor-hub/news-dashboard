/**
 * E2E tests for keyboard shortcuts (g-sequences, ?, ⌘K).
 * All shortcuts are defined in AppShell.tsx.
 */
import { test, expect } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  // Ensure no input is focused
  await page.keyboard.press('Escape');
});

test.describe('g-key navigation shortcuts', () => {
  test('g then b navigates to / (Brief)', async ({ page }) => {
    await page.goto('/today');
    await page.keyboard.press('g');
    await page.keyboard.press('b');
    await expect(page).toHaveURL('/');
  });

  test('g then t navigates to /today (Today)', async ({ page }) => {
    await page.keyboard.press('g');
    await page.keyboard.press('t');
    await expect(page).toHaveURL('/today');
  });

  test('g then l navigates to /later', async ({ page }) => {
    await page.keyboard.press('g');
    await page.keyboard.press('l');
    await expect(page).toHaveURL('/later');
  });

  test('g then s navigates to /starred', async ({ page }) => {
    await page.keyboard.press('g');
    await page.keyboard.press('s');
    await expect(page).toHaveURL('/starred');
  });

  test('g then a navigates to /ask', async ({ page }) => {
    await page.keyboard.press('g');
    await page.keyboard.press('a');
    await expect(page).toHaveURL('/ask');
  });

  test('g then f navigates to /feeds', async ({ page }) => {
    await page.keyboard.press('g');
    await page.keyboard.press('f');
    await expect(page).toHaveURL('/feeds');
  });

  test('shortcuts are ignored when input is focused', async ({ page }) => {
    await page.goto('/ask');
    // Focus the ask textarea
    const textarea = page.getByRole('textbox');
    await textarea.focus();
    await page.keyboard.press('g');
    await page.keyboard.press('t');
    // Should NOT navigate away
    await expect(page).toHaveURL('/ask');
  });
});

test.describe('? shortcut — keyboard shortcuts overlay', () => {
  test('? opens the shortcut overlay', async ({ page }) => {
    await page.keyboard.press('?');
    await expect(page.getByText('Keyboard shortcuts')).toBeVisible();
  });

  test('overlay shows g b / g t for Brief / Today', async ({ page }) => {
    await page.keyboard.press('?');
    await expect(page.getByText(/g b.*g t|g b \/ g t/)).toBeVisible();
  });

  test('overlay shows g l / g s', async ({ page }) => {
    await page.keyboard.press('?');
    await expect(page.getByText(/g l.*g s|g l \/ g s/)).toBeVisible();
  });

  test('overlay shows article action shortcuts', async ({ page }) => {
    await page.keyboard.press('?');
    await expect(page.getByText(/mark done/i)).toBeVisible();
    await expect(page.getByText(/send to later/i)).toBeVisible();
  });

  test('overlay closes with Escape', async ({ page }) => {
    await page.keyboard.press('?');
    await expect(page.getByText('Keyboard shortcuts')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByText('Keyboard shortcuts')).not.toBeVisible();
  });
});

test.describe('⌘K shortcut', () => {
  test('opens command palette', async ({ page }) => {
    await page.keyboard.press('Meta+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
  });

  test('toggles palette closed on second ⌘K', async ({ page }) => {
    await page.keyboard.press('Meta+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).toBeVisible();
    await page.keyboard.press('Meta+k');
    await expect(page.getByPlaceholder(/jump to a view/i)).not.toBeVisible();
  });
});
