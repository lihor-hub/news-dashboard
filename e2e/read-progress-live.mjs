// Real Uvicorn + PostgreSQL + password cookie, no API/auth mocks or clock acceleration.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const base = process.env.LIVE_PROGRESS_URL;
const storage = process.env.BB_THREAD_STORAGE;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ baseURL: base, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  sessionStorage.setItem('onboarding-skipped', '1');
  localStorage.setItem('i18nextLng', 'en');
});
const page = await context.newPage();
page.setDefaultTimeout(15000);
try {
  await page.goto(`${base}/reading-dna#progress`);
  await page.getByLabel('Username', { exact: true }).fill('live-read-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/reading-dna#progress');
  await page.getByText('Tracked qualifying reads:', { exact: false }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /Tracked qualifying reads: 13/);
  const manual = process.env.LIVE_READ_MANUAL_ID;
  const auto = process.env.LIVE_READ_AUTO_ID;
  await page.goto(`${base}/a/${manual}`);
  await page.getByRole('button', { name: 'Done', exact: true }).first().click();
  // Direct-reader Back crosses documents: the small workflow mutation must survive it.
  let manualTotal = 0;
  for (let attempt = 0; attempt < 30 && manualTotal !== 14; attempt++) {
    await page.waitForTimeout(100);
    manualTotal = (await (await context.request.get('/api/users/me/progress-rewards')).json())
      .reading_total;
  }
  assert.equal(manualTotal, 14);
  await page.goto(`${base}/reading-dna#progress`);
  await page.getByText('✓ Earned: Python · Enthusiast.', { exact: false }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /Tracked qualifying reads: 14/);
  assert.match(await page.locator('#progress').innerText(), /10 of 30 toward Regular/);
  await page.reload();
  await page.getByText('✓ Earned: Python · Enthusiast.', { exact: false }).waitFor();
  // Explicit unread is a real authenticated compatibility call; it never revokes credit.
  assert.equal(
    (
      await context.request.patch(`/api/articles/${manual}/state`, { data: { state: 'today' } })
    ).ok(),
    true
  );
  await page.goto(`${base}/today`);
  await page.getByRole('link', { name: /Live read article 1/ }).click();
  const remarked = page.waitForResponse(
    (r) => r.url().endsWith(`/api/articles/${manual}/state`) && r.request().method() === 'PATCH'
  );
  await page.getByRole('button', { name: 'Done', exact: true }).first().click();
  assert.equal((await remarked).ok(), true);
  const undone = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/articles/${manual}/state`) &&
      r.request().method() === 'PATCH' &&
      r.request().postDataJSON().state === 'today'
  );
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  assert.equal((await undone).ok(), true);
  const one = await (await context.request.get('/api/users/me/progress-rewards')).json();
  assert.equal(one.reading_total, 14);
  assert.equal(one.topics.tracks.find((t) => t.id === 'python').count, 10);
  await page.goto(`${base}/a/${auto}`);
  await page.locator('[data-qualifying-read-body]').waitFor();
  await page.bringToFront();
  await page.locator('[data-qualifying-read-body]').scrollIntoViewIfNeeded();
  // Short body fits; opening alone still does not count. No accelerated client/server clocks.
  await page.waitForTimeout(2500);
  assert.equal(
    (await (await context.request.get('/api/users/me/progress-rewards')).json()).reading_total,
    14
  );
  await page.getByText('Qualifying read recorded.', { exact: false }).waitFor({ timeout: 65000 });
  assert.match(page.url(), new RegExp(`/a/${auto}$`));
  // Desktop split pane uses the same loaded-body protocol; rereading cannot farm credit.
  await page.goto(`${base}/today`);
  await page.getByRole('link', { name: /Live read article 1/ }).click();
  assert.match(page.url(), /\/today/);
  await page.locator('[data-qualifying-read-body]').scrollIntoViewIfNeeded();
  await page.getByText('Qualifying read recorded.', { exact: false }).waitFor({ timeout: 90000 });
  assert.match(page.url(), /\/today/);
  assert.equal(
    (await (await context.request.get('/api/users/me/progress-rewards')).json()).reading_total,
    15
  );
  const emailPath = `/api/articles/${process.env.LIVE_READ_EMAIL_ID}/read?token=${encodeURIComponent(process.env.LIVE_READ_EMAIL_TOKEN)}`;
  assert.equal((await context.request.get(emailPath)).ok(), true);
  assert.equal(
    (await (await context.request.get('/api/users/me/progress-rewards')).json()).reading_total,
    15
  );
  await page.goto(`${base}${emailPath}`);
  await page.getByRole('button', { name: 'Confirm Done', exact: true }).click();
  await page.getByRole('heading', { name: 'Read recorded', exact: true }).waitFor();
  await page.getByRole('link', { name: 'View progress', exact: true }).click();
  await page.getByText('Tracked qualifying reads:', { exact: false }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /Tracked qualifying reads: 16/);
  await page.getByText('✓ Earned: 3-topic breadth', { exact: true }).waitFor();
  const allTopics = page.getByRole('button', { name: 'Show all topics' });
  await allTopics.focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#topic-tracks > li').count(), 11);
  await page.getByRole('button', { name: 'Show top three topics' }).click();
  assert.equal(await page.locator('#topic-tracks > li').count(), 3);
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  const violations = await page.evaluate(
    async () =>
      (
        await window.axe.run(document.querySelector('#progress'), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations
  );
  assert.deepEqual(
    violations.map((v) => ({ id: v.id, impact: v.impact })),
    []
  );
  if (storage) await page.screenshot({ path: `${storage}/read-collection-desktop.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#progress').scrollIntoViewIfNeeded();
  if (storage) await page.screenshot({ path: `${storage}/read-collection-mobile.png` });
  console.log(
    'READ_PROGRESS_LIVE_OK fixtures=13; manual=14/Python-Enthusiast; unread/SPA-retry/Undo=14; actual-time standalone automatic=15; actual-time pane reread=15; signed GET=15/human form POST=16/breadth3; all11/top3 keyboard; collection axe=0'
  );
} catch (error) {
  console.log('FAILED_PAGE', await page.locator('body').innerText());
  if (storage) await page.screenshot({ path: `${storage}/read-failure.png` });
  throw error;
} finally {
  await browser.close();
}
