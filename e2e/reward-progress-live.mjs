// Actual password-cookie auth, built SPA and PostgreSQL. No API/auth success mocks.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const base = process.env.LIVE_PROGRESS_URL;
const storage = process.env.BB_THREAD_STORAGE;
const browser = await chromium.launch({ headless: true });
async function login(context) {
  await context.addInitScript(() => {
    sessionStorage.setItem('onboarding-skipped', '1');
    localStorage.setItem('i18nextLng', 'en');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  await page.goto(`${base}/today`);
  await page.getByLabel('Username', { exact: true }).fill('live-reward-test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-not-production');
  const version = (await (await context.request.get('/api/changelog')).json()).version;
  await page.evaluate((v) => localStorage.setItem('lastSeenVersion', v), version);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/today');
  return page;
}
const context = await browser.newContext({ baseURL: base, reducedMotion: 'reduce' });
const page = await login(context);
const feedback = page.locator('[data-reward-feedback]');
try {
  await page.getByRole('dialog').waitFor();
  assert.equal(await feedback.count(), 0, 'welcome has priority over its daily reward');
  assert.match(await page.getByRole('dialog').innerText(), /Daily streak: 3 days/);
  await page.getByRole('button', { name: 'Continue reading' }).click();
  await feedback.getByText('Progress earned').waitFor();
  await feedback.getByRole('button', { name: 'Dismiss celebration' }).focus();
  await page.keyboard.press('Enter');
  await feedback.waitFor({ state: 'detached' });
  await page.getByRole('link', { name: /Python CSS reward article/ }).click();
  await page.locator('[data-qualifying-read-body]').waitFor();
  const done = page.getByRole('button', { name: 'Done', exact: true }).first();
  await done.focus();
  await done.click();
  await feedback.getByText('Progress earned').waitFor();
  assert.equal(await feedback.count(), 1);
  assert.match(await feedback.innerText(), /50 articles read/);
  assert.match(await feedback.innerText(), /Python · Enthusiast/);
  assert.match(await feedback.innerText(), /3-topic breadth/);
  assert.equal(await page.getByRole('button', { name: 'Undo', exact: true }).count(), 1);
  assert.equal(await feedback.evaluate((el) => el.contains(document.activeElement)), false);
  assert.equal(await page.locator('[data-sonner-toast].progress-static').count(), 1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    document.documentElement.dir = 'rtl';
  });
  await feedback.getByRole('link', { name: 'View achievement' }).focus();
  await page.waitForTimeout(8300);
  assert.equal(await feedback.count(), 1, 'keyboard focus pauses the eight-second clock');
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  const violations = await page.evaluate(
    async () =>
      (
        await window.axe.run(document.querySelector('[data-reward-feedback]'), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations
  );
  assert.deepEqual(
    violations.map((v) => v.id),
    []
  );
  assert.equal(
    await feedback.evaluate(
      (el) => el.getBoundingClientRect().right <= innerWidth && el.getBoundingClientRect().left >= 0
    ),
    true
  );
  if (storage) await page.screenshot({ path: `${storage}/reward-mobile-rtl.png` });
  await page.keyboard.press('Enter');
  await page.waitForURL('**/reading-dna?reward=*#progress');
  await page.locator('#reward-detail-heading').waitFor();
  assert.equal(
    await page.locator('#reward-detail-heading').evaluate((el) => el === document.activeElement),
    true
  );
  assert.match(await page.locator('#progress').innerText(), /Provenance: live/);
  assert.equal(
    (await (await context.request.get('/api/users/me/progress-rewards')).json()).reading_total,
    50
  );
  await page.reload();
  await page.locator('#reward-detail-heading').waitFor();
  await page.waitForTimeout(600);
  assert.equal(await feedback.count(), 0);
  const otherContext = await browser.newContext({ baseURL: base });
  const other = await login(otherContext);
  await other.getByRole('link', { name: /Daily streak/ }).waitFor();
  await other.waitForTimeout(600);
  assert.equal(await other.getByRole('dialog').count(), 0);
  assert.equal(await other.locator('[data-reward-feedback]').count(), 0);
  await otherContext.close();
  // Animations on cannot override the system's reduced-motion preference.
  assert.equal(
    (
      await context.request.patch('/api/users/me/progress-preferences', {
        data: { reward_animations_enabled: true },
      })
    ).ok(),
    true
  );
  await page.goto(`${base}/today`);
  await page.getByRole('link', { name: /Cybersecurity reward article/ }).click();
  await page.getByRole('button', { name: 'More actions', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Done', exact: true }).click();
  await feedback.getByText('Progress earned').waitFor();
  assert.equal(
    await feedback.locator('..').evaluate((el) => getComputedStyle(el).transitionDuration),
    '0s'
  );
  await feedback.getByRole('button', { name: 'Dismiss celebration' }).focus();
  await page.keyboard.press('Enter');
  await feedback.waitFor({ state: 'detached' });
  await page.goto(`${base}/reading-dna#progress`);
  await page.getByText('Tracked qualifying reads:', { exact: false }).waitFor();
  assert.match(await page.locator('#progress').innerText(), /Tracked qualifying reads: 51/);
  await page.getByRole('button', { name: 'Show all topics' }).click();
  assert.equal(await page.locator('#topic-tracks > li').count(), 11);
  const catalog = (await (await context.request.get('/api/users/me/progress-rewards')).json())
    .items;
  const rubyLevels = page.getByRole('list', { name: 'Ruby levels', exact: true });
  for (const target of [1, 10, 30, 100, 250]) {
    const reward = catalog.find((item) => item.key === `topic_ruby_${target}`);
    assert.ok(reward, `Ruby ${target} is in the server catalog`);
    assert.equal(reward.unlocked, target === 1, 'Ruby fixture has three qualifying reads');
    const link = rubyLevels.getByRole('link', { name: reward.title, exact: true });
    await link.waitFor();
    assert.equal(await link.getAttribute('href'), reward.href);
    const level = link.locator('..').locator('..');
    assert.match(await level.innerText(), target === 1 ? /✓ Earned:/ : /◇ Locked:/);
    assert.ok((await level.innerText()).includes(reward.description));
    assert.equal(
      await page.locator(`#progress a[href="${reward.href}"]`).count(),
      1,
      `${reward.key} has exactly one collection link`
    );
  }
  assert.equal(await rubyLevels.getByRole('link').count(), 5);
  await rubyLevels.getByRole('link', { name: 'Ruby · Pathfinder', exact: true }).click();
  await page.locator('#reward-detail-heading').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('reward'), 'topic_ruby_250');
  assert.match(await page.getByRole('region', { name: 'Ruby · Pathfinder' }).innerText(), /250/);
  await page.evaluate(readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'));
  const collectionViolations = await page.evaluate(
    async () =>
      (
        await window.axe.run(document.querySelector('#progress'), {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
        })
      ).violations
  );
  assert.deepEqual(
    collectionViolations.map((v) => v.id),
    []
  );
  await page.emulateMedia({ colorScheme: 'dark', forcedColors: 'active' });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '200%';
  });
  console.log(
    'REFLOW_DIAGNOSTICS',
    await page.locator('#progress').evaluate((root) =>
      [...root.querySelectorAll('*')]
        .filter(
          (el) =>
            el.getBoundingClientRect().left < root.getBoundingClientRect().left ||
            el.getBoundingClientRect().right > root.getBoundingClientRect().right
        )
        .map((el) => ({
          tag: el.tagName,
          text: el.textContent.slice(0, 60),
          cls: el.className,
          width: el.getBoundingClientRect().width,
        }))
    )
  );
  assert.equal(
    await page.locator('#progress').evaluate((el) => el.scrollWidth <= el.clientWidth),
    true
  );
  assert.equal(
    await page.getByRole('heading', { name: 'Progress & achievements' }).isVisible(),
    true
  );
  if (storage) await page.screenshot({ path: `${storage}/reward-collection.png` });
  console.log(
    'REWARD_PROGRESS_LIVE_OK daily-overlap; real manual read=50/three simultaneous awards/one static celebration; Undo preserved; keyboard focus pause>8s; 390px RTL/scoped axe=0; explicit detail focus; persisted reload/other-device no replay; animations-on+system-reduce static; dismiss+permanent collection=51/all11/Ruby-all5-earned-and-locked-unique-links/locked250-detail/axe=0'
  );
} catch (error) {
  console.log('FAILED_PAGE', await page.locator('body').innerText());
  if (storage) await page.screenshot({ path: `${storage}/reward-failure.png` });
  throw error;
} finally {
  await browser.close();
}
