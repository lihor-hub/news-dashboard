// Actual password auth + PostgreSQL + built SPA. No success/auth/API mocks.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const base = process.env.LIVE_PROGRESS_URL;
const popup = process.env.HISTORY_POPUP === 'True';
const browser = await chromium.launch({ headless: true });
async function login(context) {
  await context.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  await page.goto(`${base}/today`);
  await page.getByLabel('Username', { exact: true }).fill('live-history-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/today');
  return page;
}
async function axe(page, selector) {
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  assert.deepEqual(await page.evaluate(async (selector) => (await window.axe.run(
    document.querySelector(selector), { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa'] } }
  )).violations.map(v => v.id), selector), []);
}
try {
  const context = await browser.newContext({ baseURL: base, reducedMotion: 'reduce', viewport: { width: 390, height: 844 } });
  const page = await login(context);
  const intro = popup ? page.getByRole('dialog') : page.getByRole('complementary', { name: 'Progress history introduction' });
  await intro.getByText(/Historical credit: 1 qualifying reads added/).waitFor();
  assert.equal(await page.locator('[data-reward-feedback]').count(), 0, 'no per-history reward toasts');
  assert.equal(await page.getByRole('dialog').count(), popup ? 1 : 0);
  if (popup) assert.match(await intro.innerText(), /Daily streak: 1 days/);
  await axe(page, popup ? '[role="dialog"]' : 'aside[aria-label="Progress history introduction"]');
  if (process.env.BB_THREAD_STORAGE) await page.screenshot({ path: `${process.env.BB_THREAD_STORAGE}/history-${popup ? 'merged' : 'inline'}.png` });
  if (popup) {
    await intro.getByRole('button', { name: 'View my progress' }).click();
  } else {
    await intro.getByRole('button', { name: 'Dismiss history summary' }).click();
    await intro.waitFor({ state: 'detached' });
    await page.goto(`${base}/reading-dna#progress`);
  }
  await page.getByRole('region', { name: 'Historical reading summary' }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /1 qualifying reads added/);
  assert.match(await page.locator('#progress').innerText(), /Deleted evidence cannot be recovered/);
  await axe(page, '#progress');
  await page.getByRole('link', { name: 'Python · Explorer', exact: true }).click();
  await page.locator('#reward-detail-heading').waitFor();
  assert.match(await page.locator('#progress').innerText(), /Provenance: historical/);
  assert.match(await page.locator('#progress').innerText(), /Original earned date unknown/);
  await page.reload();
  await page.locator('#reward-detail-heading').waitFor();
  await page.waitForTimeout(500);
  assert.equal(await page.getByRole('dialog').count(), 0);
  assert.equal(await page.getByRole('complementary', { name: 'Progress history introduction' }).count(), 0);
  const otherContext = await browser.newContext({ baseURL: base });
  const other = await login(otherContext);
  await other.getByRole('link', { name: /Daily streak/ }).waitFor();
  await other.waitForTimeout(500);
  assert.equal(await other.getByRole('dialog').count(), 0);
  assert.equal(await other.getByRole('complementary', { name: 'Progress history introduction' }).count(), 0);
  const collection = await (await otherContext.request.get('/api/users/me/progress-rewards')).json();
  assert.equal(collection.reading_total, 1);
  assert.equal(collection.historical_group_id, null);
  assert.equal(collection.history_status, 'complete');
  await otherContext.close();
  await context.close();
  console.log('HISTORY_PROGRESS_LIVE_OK', { popup });
} finally {
  await browser.close();
}
