// Real password/cookies, PostgreSQL and built SPA; no mocked API or authentication.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const base = process.env.LIVE_PROGRESS_URL;
const id = process.env.RECAP_ID;
const browser = await chromium.launch({ headless: true });
async function signIn(page, context) {
  await page.getByLabel('Username', { exact: true }).fill('live-recap-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}
async function axe(page, selector) {
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  const violations = await page.evaluate(
    async (selector) =>
      (
        await window.axe.run(document.querySelector(selector), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations.map((v) => v.id),
    selector
  );
  assert.deepEqual(violations, []);
}
try {
  const context = await browser.newContext({
    baseURL: base,
    timezoneId: 'Pacific/Honolulu',
    viewport: { width: 1280, height: 800 },
  });
  await context.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  await page.goto(`${base}/recap`);
  await signIn(page, context);
  await page.waitForURL('**/recap');
  const card = () => page.getByRole('region', { name: 'Your week in progress', exact: true });
  await card().getByText('Unavailable', { exact: false }).waitFor();
  await card().getByText('0 of 7', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'Load older recaps' }).click();
  const oldLink = page.locator(`a[href="/recap?recap=${id}"]`);
  await oldLink.waitFor();
  await oldLink.focus();
  await page.keyboard.press('Enter');
  await page.waitForURL(`**/recap?recap=${id}`);
  await card().getByText('Less than a minute measured', { exact: false }).waitFor();
  assert.match(await card().innerText(), /Jan 5, 2026 – Jan 11, 2026 · America\/New_York/);
  assert.equal(await card().getByRole('listitem').count(), 3);
  await axe(page, 'section[aria-label="Your week in progress"]');
  const all = card().getByRole('link', { name: 'View all 4 rewards and weekly progress' });
  await all.focus();
  await page.keyboard.press('Enter');
  await page.waitForURL(`**/reading-dna?recap=${id}#progress`);
  await card().getByText('4 rewards earned in this period', { exact: false }).waitFor();
  await card().getByRole('link', { name: 'Back to this recap' }).waitFor();
  assert.equal(await card().getByRole('listitem').count(), 4);
  await page.waitForFunction(() => document.activeElement?.textContent === 'Your week in progress');
  assert.match(
    await page.locator('#progress').innerText(),
    /Lifetime progress \(separate from weekly snapshots\)/
  );
  await card().getByRole('link', { name: 'Python · Explorer', exact: true }).click();
  await page.waitForFunction(() => document.activeElement?.textContent === 'Python · Explorer');
  await page.reload();
  await card().getByRole('heading', { name: 'Python · Explorer', exact: true }).waitFor();
  assert.match(await card().innerText(), /Complete 1 qualifying reads in Python/);
  await page.setViewportSize({ width: 390, height: 844 });
  await axe(page, '#progress');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  if (process.env.BB_THREAD_STORAGE)
    await page.screenshot({ path: `${process.env.BB_THREAD_STORAGE}/recap-mobile.png` });
  await card().getByRole('link', { name: 'Back to this recap' }).click();
  await page.waitForURL(`**/recap?recap=${id}`);
  await page.reload();
  await card().getByText('1 of 7', { exact: false }).waitFor();
  await page.goBack();
  await card().getByRole('heading', { name: 'Python · Explorer', exact: true }).waitFor();
  const frozen = await (await context.request.get(`/api/recaps/${id}`)).json();
  assert.equal(frozen.data.progress.active_seconds, 59);
  // A second signed-out context must authenticate; recap query parameters grant nothing.
  const signedOut = await browser.newContext({ baseURL: base });
  await signedOut.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  assert.equal((await signedOut.request.get(`/api/recaps/${id}`)).status(), 401);
  const direct = await signedOut.newPage();
  await direct.goto(`${base}/reading-dna?recap=${id}&reward=topic_python_1#progress`);
  await signIn(direct, signedOut);
  await direct.waitForURL(`**/reading-dna?recap=${id}&reward=topic_python_1#progress`);
  await direct
    .getByRole('region', { name: 'Your week in progress', exact: true })
    .getByRole('heading', { name: 'Python · Explorer', exact: true })
    .waitFor();
  await signedOut.close();
  await context.close();
  console.log(
    'RECAP_PROGRESS_LIVE_OK desktop/mobile/keyboard/history>12/auth/back/reload/scoped-axe'
  );
} finally {
  await browser.close();
}
