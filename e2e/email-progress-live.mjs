// Real app/API/auth cookies; SMTP and external SSO provider are scoped server fixtures.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createInterface } from 'node:readline';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const input = createInterface({ input: process.stdin });
const replies = input[Symbol.asyncIterator]();
async function handshake(event) {
  console.log(event);
  return (await replies.next()).value;
}
const base = process.env.LIVE_PROGRESS_URL;
const browser = await chromium.launch({ headless: true });
async function context() {
  const context = await browser.newContext({
    baseURL: base,
    viewport: { width: 600, height: 900 },
  });
  await context.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  return context;
}
async function prepareLogin(page, context) {
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
}
async function checkDestination(page, path, reward = false) {
  await page.waitForURL(`${base}${path}`);
  await page.locator('#progress').waitFor();
  if (reward) {
    await page.getByRole('heading', { name: 'Python · Explorer', exact: true }).waitFor();
    await page.waitForFunction(() => document.activeElement?.textContent === 'Python · Explorer');
  } else {
    await page.waitForFunction(
      () => document.activeElement?.textContent === 'Progress & achievements'
    );
  }
}
try {
  const password = await context();
  const page = await password.newPage();
  page.setDefaultTimeout(15000);
  let activity = 0;
  page.on('request', (r) => {
    if (/daily-visit|activity\/|reading-evidence/.test(r.url())) activity++;
  });
  await page.goto('/__email_fixture');
  const destination = await page
    .getByRole('link', { name: 'View my progress', exact: true })
    .getAttribute('href');
  assert.equal(destination, `${base}/reading-dna#progress`);
  for (const width of [320, 600]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false
    );
    await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
    const violations = await page.evaluate(async () =>
      (
        await window.axe.run(document.querySelector('section'), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations.map((v) => v.id)
    );
    assert.deepEqual(violations, []);
    if (process.env.BB_THREAD_STORAGE)
      await page.screenshot({
        path: `${process.env.BB_THREAD_STORAGE}/email-${width}.png`,
        fullPage: true,
      });
  }
  assert.equal(activity, 0);
  // Raw GET and mail layout/opening grant no session or measurement.
  assert.equal((await password.request.get('/api/users/me/progress-rewards')).status(), 401);
  const raw = await password.request.get('/reading-dna?reward=topic_python_1#progress');
  assert.equal(raw.status(), 200);
  await handshake('MAIL_OPENED');
  await page.getByRole('link', { name: 'View my progress', exact: true }).click();
  await page.getByLabel('Username', { exact: true }).fill('live-email-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  await prepareLogin(page, password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await checkDestination(page, '/reading-dna#progress');
  await page.reload();
  await checkDestination(page, '/reading-dna#progress');
  const rewardPath = '/reading-dna?reward=topic_python_1#progress';
  for (const username of ['live-email-test', 'live-email-viewer']) {
    const fresh = await context();
    const direct = await fresh.newPage();
    await direct.goto(rewardPath);
    await direct.getByLabel('Username', { exact: true }).fill(username);
    await direct.getByLabel('Password', { exact: true }).fill('test-password-not-production');
    await prepareLogin(direct, fresh);
    await direct.getByRole('button', { name: 'Sign in', exact: true }).click();
    await checkDestination(direct, rewardPath, true);
    const collection = await (await fresh.request.get('/api/users/me/progress-rewards')).json();
    assert.equal(
      collection.items.find((item) => item.key === 'topic_python_1').unlocked,
      username === 'live-email-test'
    );
    await fresh.close();
  }
  const otp = await context();
  const otpPage = await otp.newPage();
  await otpPage.goto(rewardPath);
  await otpPage.getByRole('button', { name: 'Use email code instead' }).click();
  await otpPage.getByLabel('Email address', { exact: true }).fill('live-email@example.test');
  await otpPage.getByRole('button', { name: 'Send code', exact: true }).click();
  await otpPage.getByLabel('6-digit code', { exact: true }).waitFor();
  const code = await handshake('OTP_CODE');
  await otpPage.getByLabel('6-digit code', { exact: true }).fill(code);
  await prepareLogin(otpPage, otp);
  await otpPage.getByRole('button', { name: 'Verify code', exact: true }).click();
  await checkDestination(otpPage, rewardPath, true);
  await otp.close();
  await handshake('ENABLE_SSO');
  const sso = await context();
  const ssoPage = await sso.newPage();
  await ssoPage.goto(rewardPath);
  await prepareLogin(ssoPage, sso);
  const link = ssoPage.getByRole('link', { name: /Keycloak/ }).first();
  const href = await link.getAttribute('href');
  assert.equal(new URL(href, base).searchParams.get('next'), rewardPath);
  await link.click();
  await checkDestination(ssoPage, rewardPath, true);
  assert.ok((await sso.cookies()).some((c) => c.httpOnly && c.name.includes('session')));
  await sso.close();
  await password.close();
  console.log(
    'EMAIL_PROGRESS_LIVE_OK mail320/600/scoped-axe/no-open-credit/password/OTP/SSO-fixture/path-query-hash/focus/reload'
  );
} finally {
  input.close();
  await browser.close();
}
