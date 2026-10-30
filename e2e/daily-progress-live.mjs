// Invoked by test_daily_visits_browser.py: real API, cookies and PostgreSQL, no route mocks.
import assert from 'node:assert/strict';
import { createInterface } from 'node:readline';
import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const input = createInterface({ input: process.stdin });
const lines = input[Symbol.asyncIterator]();
async function nextDay() {
  console.log('ADVANCE_DAY');
  assert.equal((await lines.next()).value, 'ADVANCED');
}
const base = process.env.LIVE_PROGRESS_URL;
const storage = process.env.BB_THREAD_STORAGE;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ baseURL: base, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  sessionStorage.setItem('onboarding-skipped', '1');
  localStorage.setItem('i18nextLng', 'en');
});
const page = await context.newPage();
page.setDefaultTimeout(12000);
try {
  // No mocked auth: protected destination -> login UI -> same path, query and hash.
  await page.goto(`${base}/reading-dna?reward=daily_streak_3#progress`);
  await page.getByLabel('Username', { exact: true }).fill('live-progress-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/reading-dna?reward=daily_streak_3#progress');
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /new streak starts here/);
  assert.equal(
    await page
      .getByRole('button', { name: 'Continue reading' })
      .evaluate((el) => el === document.activeElement),
    true
  );
  // Actual Radix keyboard trap, not a jsdom-only assertion.
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    assert.equal(await dialog.evaluate((el) => el.contains(document.activeElement)), true);
  }
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  const violations = await page.evaluate(
    async () =>
      (
        await window.axe.run(document.querySelector('[role=dialog]'), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations
  );
  assert.deepEqual(
    violations.map((v) => ({ id: v.id, impact: v.impact })),
    []
  );
  assert.equal(await dialog.evaluate((el) => getComputedStyle(el).animationName), 'none');
  if (storage) await page.screenshot({ path: `${storage}/daily-desktop.png`, fullPage: false });
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
  await page.waitForFunction(
    () =>
      document.activeElement?.id === 'progress-heading' ||
      document.activeElement?.getAttribute('aria-label')?.startsWith('Daily streak:')
  );
  await page.reload();
  await page.getByRole('link', { name: /Daily streak: 1 days/ }).waitFor();
  assert.equal(await dialog.count(), 0);
  const second = await browser.newContext({
    baseURL: base,
    storageState: await context.storageState(),
  });
  await second.addInitScript(() => sessionStorage.setItem('onboarding-skipped', '1'));
  const page2 = await second.newPage();
  await page2.goto(`${base}/reading-dna#progress`);
  await page2.getByRole('link', { name: /Daily streak: 1 days/ }).waitFor();
  assert.equal(await page2.getByRole('dialog').count(), 0);
  await second.close();
  await nextDay();
  await page.reload();
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /Daily streak: 2 days/);
  // Outside dismissal on desktop and focus restore.
  await page.mouse.click(5, 5);
  await dialog.waitFor({ state: 'hidden' });
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith('/progress-preferences') && r.request().method() === 'PATCH' && r.ok()
    ),
    page.getByLabel('Daily welcome popup').uncheck(),
  ]);
  await nextDay();
  await page.reload();
  await page.getByRole('link', { name: /Daily streak: 3 days/ }).waitFor();
  assert.equal(await dialog.count(), 0);
  await page.getByText('✓ Earned: 3-day daily streak', { exact: true }).waitFor();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith('/progress-preferences') && r.request().method() === 'PATCH' && r.ok()
    ),
    page.getByLabel('Daily welcome popup').check(),
  ]);
  await page.reload();
  await page.getByRole('link', { name: /Daily streak: 3 days/ }).waitFor();
  assert.equal(await dialog.count(), 0);
  await nextDay();
  await page.setViewportSize({ width: 390, height: 844 });
  // Direct protected reader outside AppShell must still track and host the sheet.
  await page.goto(`${base}/a/${process.env.LIVE_PROGRESS_ARTICLE_ID}`);
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /Daily streak: 4 days/);
  assert.ok(await page.locator('[data-slot="sheet-handle"]').count());
  assert.equal(await dialog.evaluate((el) => getComputedStyle(el).animationName), 'none');
  if (storage) await page.screenshot({ path: `${storage}/daily-mobile.png`, fullPage: false });
  await page.getByRole('button', { name: 'Continue reading' }).click();
  await dialog.waitFor({ state: 'hidden' });
  await page.getByText('A locally stored browser test article.', { exact: false }).waitFor();
  await nextDay();
  await page.goto(`${base}/shared/${process.env.LIVE_PROGRESS_SHARE_ID}/article`);
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /Daily streak: 5 days/);
  await page.getByRole('button', { name: 'Continue reading' }).click();
  await dialog.waitFor({ state: 'hidden' });
  await page.getByRole('link', { name: /Daily streak: 5 days/ }).click();
  await page.getByRole('heading', { name: 'Progress & achievements' }).waitFor();
  const exported = await (await context.request.get('/api/users/me/export')).json();
  assert.equal(exported.progress.daily_visits.length, 5);
  assert.match(exported.progress.restore_notice, /not restored/);
  // A timezone PATCH/GET must replace the timer without itself recording a visit.
  await page.getByLabel('Daily welcome popup').uncheck();
  await page.getByLabel('Progress timezone (IANA)').fill('Pacific/Honolulu');
  await page.getByRole('button', { name: 'Save timezone', exact: true }).click();
  await page.getByText(/Visits in Pacific\/Honolulu/).waitFor();
  console.log('TRAVEL_START');
  assert.equal((await lines.next()).value, 'ADVANCED');
  await page.clock.install({ time: new Date('2026-01-06T01:00:00Z') });
  await page.reload();
  await page.getByRole('link', { name: /Daily streak: 5 days/ }).waitFor();
  await page.getByText(/Visits in Pacific\/Honolulu/).waitFor();
  let visits = 0;
  const countVisit = (request) => {
    if (request.url().endsWith('/daily-visit') && request.method() === 'POST') visits++;
  };
  page.on('request', countVisit);
  await page.getByLabel('Progress timezone (IANA)').fill('America/New_York');
  await page.getByRole('button', { name: 'Save timezone', exact: true }).click();
  await page.getByText(/Visits in America\/New_York/).waitFor();
  assert.equal(visits, 0);
  const beforeMidnight = await (await context.request.get('/api/users/me/daily-streak')).json();
  assert.equal(beforeMidnight.current_streak_days, 5);
  assert.equal(beforeMidnight.local_date, '2026-01-05');
  // Original Jan 5 UTC credit froze Jan 6 00:00Z, already elapsed at the new midnight.
  console.log('TRAVEL_MIDNIGHT');
  assert.equal((await lines.next()).value, 'ADVANCED');
  await page.clock.fastForward(4 * 60 * 60 * 1000 + 1000);
  await page.getByRole('link', { name: /Daily streak: 6 days/ }).waitFor();
  assert.equal(visits, 1);
  await page.getByText('6 days', { exact: true }).waitFor();
  const afterMidnight = await (await context.request.get('/api/users/me/daily-streak')).json();
  assert.equal(afterMidnight.current_streak_days, 6);
  assert.equal(afterMidnight.local_date, '2026-01-06');
  assert.equal(afterMidnight.timezone, 'America/New_York');
  page.off('request', countVisit);
  await page.goto(`${base}/settings/notifications?from=mail#progress`);
  await page.waitForURL('**/settings?from=mail#progress');
  await page.goto(`${base}/briefings/999?from=mail#progress`);
  await page.waitForURL('**/briefs/999?from=mail#progress');
  console.log(
    'LIVE_ACCEPTANCE_OK: auth continuation, first/return/refresh/two-context visits, daily award, popup preference, direct reader, desktop/mobile, keyboard/focus, outside/Escape, reduced motion, dialog axe, export, saved-timezone visible-midnight rescheduling without PATCH/GET visit credit'
  );
} finally {
  input.close();
  await browser.close();
}
