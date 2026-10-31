// Real password/cookies, built SPA and PostgreSQL. Only clocks are test-controlled.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createInterface } from 'node:readline';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const input = createInterface({ input: process.stdin });
const replies = [];
input.on('line', (line) => replies.shift()?.(line));
async function serverAdvance(ms) {
  const reply = new Promise((resolve) => replies.push(resolve));
  console.log(`ADVANCE_MS ${ms}`);
  assert.equal(await reply, 'ADVANCED');
}
const base = process.env.LIVE_PROGRESS_URL;
const storage = process.env.BB_THREAD_STORAGE;
const browser = await chromium.launch({
  headless: false,
  ignoreDefaultArgs: [
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
  ],
});
const context = await browser.newContext({ baseURL: base, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  sessionStorage.setItem('onboarding-skipped', '1');
  localStorage.setItem('i18nextLng', 'en');
});
const page = await context.newPage();
// Playwright forces focus on every page by default; disable that test emulation.
await (
  await context.newCDPSession(page)
).send('Emulation.setFocusEmulationEnabled', { enabled: false });
page.setDefaultTimeout(15000);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let windows = 0;
let heartbeats = 0;
page.on('response', (response) => {
  if (response.url().endsWith('/activity/window') && response.ok()) windows++;
  if (response.url().endsWith('/activity/heartbeat')) {
    if (response.ok()) heartbeats++;
    void response
      .json()
      .then((body) => console.log('HEARTBEAT', response.status(), JSON.stringify(body)))
      .catch(() => {});
  }
});
async function step(ms) {
  await serverAdvance(ms);
  if (ms > 30000) await page.clock.fastForward(ms);
  else await page.clock.runFor(ms);
  await delay(120);
  await page.clock.runFor(1); // Flush React/query notifications after the real network response.
  await delay(30);
}
async function total() {
  return (await (await context.request.get('/api/users/me/activity')).json()).total_ms;
}
async function login(target, ctx) {
  await target.goto(`${base}/reading-dna#progress`);
  await target.getByLabel('Username', { exact: true }).fill('live-activity-test');
  await target.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await ctx.request.get('/api/changelog')).json()).version;
  await target.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await target.getByRole('button', { name: 'Sign in', exact: true }).click();
  await target.waitForURL('**/reading-dna#progress');
  await target.getByRole('heading', { name: 'Approximate active time', exact: true }).waitFor();
}
try {
  await page.clock.install();
  await login(page, context);
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  const focusReset = await context.newPage();
  await (
    await context.newCDPSession(focusReset)
  ).send('Emulation.setFocusEmulationEnabled', { enabled: false });
  await focusReset.goto('about:blank');
  await focusReset.bringToFront();
  await page.bringToFront();
  await focusReset.close();
  windows = 0;
  heartbeats = 0;
  assert.equal(
    await page.evaluate(() => document.hasFocus() && document.visibilityState === 'visible'),
    true
  );
  await step(250);
  console.log(
    'INITIAL_WINDOWS',
    windows,
    JSON.stringify(
      await page.evaluate(() => ({
        perf: performance.now(),
        focus: document.hasFocus(),
        online: navigator.onLine,
        visible: document.visibilityState,
      }))
    )
  );
  await step(15000);
  assert.equal(heartbeats, 1);
  assert.equal(await total(), 914000);
  await page.getByText('✓ Earned: 15 minutes active time', { exact: true }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /Measured active time: 15 minutes/);
  // Quiet reading counts; then a genuine timer/suspension gap crosses the 5-minute idle limit.
  for (let index = 0; index < 2; index++) {
    await step(250);
    await step(15000);
  }
  const idleTotal = await total();
  assert.ok(idleTotal > 914000 && idleTotal <= 959000);
  const idleBeats = heartbeats;
  await step(300000);
  assert.equal(await total(), idleTotal);
  assert.equal(heartbeats, idleBeats);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await step(16000);
  assert.equal(await total(), idleTotal); // Browser-generated programmatic scroll is not interaction.
  // A genuine second foreground tab removes focus; no injected focus/visibility result.
  const other = await context.newPage();
  await (
    await context.newCDPSession(other)
  ).send('Emulation.setFocusEmulationEnabled', { enabled: false });
  await other.goto('about:blank');
  await (
    await context.newCDPSession(page)
  ).send('Emulation.setFocusEmulationEnabled', { enabled: false });
  await other.bringToFront();
  await delay(500);
  const background = await page.evaluate(() => ({
    visible: document.visibilityState,
    focused: document.hasFocus(),
  }));
  console.log('BACKGROUND_STATE', JSON.stringify(background));
  assert.equal(background.focused, false);
  await step(60000);
  assert.equal(await total(), idleTotal);
  await page.bringToFront();
  await delay(120);
  console.log(
    'RESUME_STATE',
    JSON.stringify(
      await page.evaluate(() => ({
        focus: document.hasFocus(),
        visible: document.visibilityState,
        perf: performance.now(),
      }))
    )
  );
  await step(250);
  await step(15000);
  await step(250);
  assert.ok((await total()) > idleTotal);
  await context.setOffline(true);
  await delay(120);
  const offlineTotal = await total().catch(() => null);
  await step(120000);
  await context.setOffline(false);
  await delay(120);
  const reconnected = await total();
  if (offlineTotal !== null) assert.equal(reconnected, offlineTotal);
  await step(250);
  await step(15000);
  await step(250);
  assert.ok((await total()) - reconnected <= 15250);
  // Two separately authenticated devices submit the same server-anchored interval.
  const device = await browser.newContext({ baseURL: base });
  const devicePage = await device.newPage();
  await devicePage.goto(`${base}/login`);
  await devicePage.getByLabel('Username', { exact: true }).fill('live-activity-test');
  await devicePage.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  await devicePage.getByRole('button', { name: 'Sign in', exact: true }).click();
  await devicePage.waitForURL((url) => !url.pathname.includes('/login'));
  await page.bringToFront();
  const a = await (
    await context.request.post('/api/users/me/activity/window', { data: {} })
  ).json();
  const b = await (await device.request.post('/api/users/me/activity/window', { data: {} })).json();
  const beforeUnion = await total();
  await serverAdvance(15000);
  console.log('DEVICE_SERVER_ADVANCED');
  const responses = await Promise.all(
    [
      [context, a],
      [device, b],
    ].map(async ([ctx, window]) => {
      const response = await ctx.request.post('/api/users/me/activity/heartbeat', {
        timeout: 10000,
        data: { window_id: window.window_id, start_ms: 0, end_ms: 15000 },
      });
      assert.equal(response.ok(), true);
      return response.json();
    })
  );
  console.log('DEVICE_RESPONSES', JSON.stringify(responses));
  assert.equal(
    responses.reduce((sum, r) => sum + r.accepted_ms, 0),
    15000
  );
  assert.equal((await total()) - beforeUnion, 15000);
  console.log('DEVICE_CLOSING');
  await device.close();
  console.log('DEVICE_CLOSED');
  // Separate mobile Chromium/touch context, real auth and online/offline lifecycle.
  const mobile = await browser.newContext({
    baseURL: base,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    reducedMotion: 'reduce',
  });
  await mobile.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  const mobilePage = await mobile.newPage();
  await mobilePage.clock.install();
  await login(mobilePage, mobile);
  await mobilePage.clock.pauseAt(new Date(Date.now() + 1000));
  // Drop the real-time pre-pause lease; measurement starts on a fresh synchronized anchor.
  await serverAdvance(31000);
  await mobilePage.clock.fastForward(31000);
  await delay(150);
  const beforeMobile = await total();
  await serverAdvance(16000);
  await mobilePage.clock.runFor(16000);
  await delay(150);
  const mobileMeasured = await total();
  assert.ok(mobileMeasured > beforeMobile && mobileMeasured - beforeMobile <= 16000);
  await mobile.setOffline(true);
  await serverAdvance(120000);
  await mobilePage.clock.fastForward(120000);
  await delay(150);
  assert.equal(await total(), mobileMeasured);
  await mobile.setOffline(false);
  await mobilePage.clock.resume();
  await mobilePage.locator('#progress').scrollIntoViewIfNeeded();
  if (storage) await mobilePage.screenshot({ path: `${storage}/activity-mobile-touch.png` });
  await mobile.close();
  await page.bringToFront();
  // Let rendering/axe use actual rAF/timers after the clock-controlled measurement phase.
  await page.clock.resume();
  // Responsive Chromium viewport; not Safari/TWA/native-device parity.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#progress').scrollIntoViewIfNeeded();
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
  if (storage) await page.screenshot({ path: `${storage}/activity-mobile.png` });
  await page.setViewportSize({ width: 1280, height: 900 });
  if (storage) await page.screenshot({ path: `${storage}/activity-desktop.png` });
  // Real UI logout stops the recorder before the request and cannot inflate afterward.
  const beforeLogout = await total();
  await page.getByTitle('Account menu', { exact: true }).click();
  await page.getByRole('button', { name: /Log out|Sign out/ }).click();
  await page.waitForURL('**/login');
  const atLogout = heartbeats;
  await step(60000);
  assert.equal(heartbeats, atLogout);
  console.log(
    `ACTIVITY_PROGRESS_LIVE_OK focus-visible→15m-badge; quiet≤5min; idle/background/offline no catchup; two devices union; logout; axe0; initial899000; beforeLogout=${beforeLogout}`
  );
} catch (error) {
  console.log('FAILED_PAGE', await page.locator('body').innerText());
  if (storage) await page.screenshot({ path: `${storage}/activity-failure.png` });
  throw error;
} finally {
  input.close();
  await browser.close();
}
