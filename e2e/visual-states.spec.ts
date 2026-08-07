/**
 * Visual regression matrix for auth and core app states.
 *
 * This suite uses Playwright screenshot assertions with deterministic API mocks.
 * It is intentionally separate from scripts/capture-screenshots.spec.ts, which
 * only writes docs/README artifacts.
 */
import { expect, test, type Page } from '@playwright/test';
import { mockApi, json, SAMPLE_ARTICLE, SAMPLE_BRIEFING } from './fixtures';

const ERROR_JSON = json({ detail: 'Visual state fixture error' }, 500);

const RECEIVED_SHARE = {
  id: 31,
  article_id: 1,
  from_user_id: 2,
  from_username: 'ada',
  article_title: SAMPLE_ARTICLE.title,
  article_source_name: SAMPLE_ARTICLE.source_name,
  article_url: SAMPLE_ARTICLE.url,
  note: 'Worth reading before planning tomorrow.',
  created_at: '2026-06-13T09:00:00+00:00',
  read_at: null,
  revoked_at: null,
};

const READING_LIST_ITEM = {
  id: 41,
  user_id: 1,
  url: 'https://example.com/reading-list',
  normalized_url: 'https://example.com/reading-list',
  title: 'Designing calm AI reading workflows',
  description: 'A practical guide to keeping AI-assisted reading tools focused.',
  image_url: null,
  site_name: 'Example Research',
  kind: 'article',
  fetch_status: 'ok',
  fetch_error: null,
  fetched_at: '2026-06-13T09:10:00+00:00',
  summary: 'Use a small queue, clear triage states, and intentional review loops.',
  summary_status: 'ok',
  status: 'unread',
  priority: 0,
  note: null,
  created_at: '2026-06-13T09:00:00+00:00',
  done_at: null,
};

async function prepareVisualPage(page: Page, theme: 'light' | 'dark' = 'light') {
  await page.addInitScript((selectedTheme) => {
    const fixedNow = new Date('2026-06-14T12:00:00Z').valueOf();
    const RealDate = Date;
    class FixedDate extends RealDate {
      constructor(...args: ConstructorParameters<typeof Date>) {
        if (args.length === 0) {
          super(fixedNow);
        } else {
          super(...args);
        }
      }

      static now() {
        return fixedNow;
      }
    }
    window.Date = FixedDate as DateConstructor;
    window.localStorage.setItem('theme', selectedTheme);
    window.sessionStorage.setItem('onboarding-skipped', '1');
    window.localStorage.setItem('news-dashboard:last-seen-version', 'visual-tests');
  }, theme);
  await page.route('/api/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/config') {
      return route.fulfill(json({}));
    }
    if (url.pathname === '/api/changelog') {
      return route.fulfill(json({ version: 'visual-tests', items: [] }));
    }
    if (url.pathname === '/api/settings/analytics') {
      return route.fulfill(json({ enabled: false }));
    }
    if (url.pathname === '/api/shares/unread_count') {
      return route.fulfill(json({ unread: 0 }));
    }
    if (url.pathname === '/api/personalization/nudges') {
      return route.fulfill(json({ items: [] }));
    }
    if (url.pathname === '/api/ai-feedback') {
      return route.fulfill(json({ items: [] }));
    }
    return route.fulfill(json({}));
  });
}

async function screenshot(page: Page, name: string) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      )
  );
  await expect(page).toHaveScreenshot(name, {
    fullPage: true,
    animations: 'disabled',
    caret: 'hide',
  });
}

async function mockLoggedInApp(page: Page, theme: 'light' | 'dark' = 'light') {
  await prepareVisualPage(page, theme);
  await mockApi(page);
  await page.route('/api/shares', (route) =>
    route.fulfill(json({ items: [RECEIVED_SHARE], unread: 1 }))
  );
  await page.route('/api/shares/*/read', (route) => route.fulfill(json({ status: 'ok' })));
  await page.route('/api/shares/sent', (route) => route.fulfill(json({ items: [] })));
  await page.route('/api/tags', (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: 7,
            user_id: 1,
            name: 'AI Research',
            color: '#3b82f6',
            created_at: '2026-06-13T09:00:00+00:00',
            article_count: 2,
          },
        ],
      })
    )
  );
  await page.route('/api/reading-list**', (route) =>
    route.fulfill(json({ items: [READING_LIST_ITEM] }))
  );
  await page.route('/api/articles/*/tags', (route) => route.fulfill(json({ items: [] })));
}

async function mockAuthConfig(
  page: Page,
  config: {
    provider: 'password' | 'keycloak';
    keycloak_enabled: boolean;
    login_url: string | null;
    registration_url?: string | null;
  }
) {
  await prepareVisualPage(page);
  await page.route('/api/auth/config', (route) =>
    route.fulfill(json({ logout_url: '/api/auth/logout', ...config }))
  );
}

test.describe('@visual auth states', () => {
  test('password login', async ({ page }) => {
    await mockAuthConfig(page, {
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
    });

    await page.goto('/login');
    await expect(page.getByLabel('Username')).toBeVisible();
    await screenshot(page, 'auth-password-login.png');
  });

  test('auth config loading and error', async ({ page }) => {
    await prepareVisualPage(page);
    let resolveConfig: (() => void) | null = null;
    await page.route('/api/auth/config', async (route) => {
      await new Promise<void>((resolve) => {
        resolveConfig = resolve;
      });
      await route.fulfill(ERROR_JSON);
    });

    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('status')).toContainText('Checking sign-in options');
    await screenshot(page, 'auth-config-loading.png');

    resolveConfig?.();
    await expect(page.getByRole('alert')).toBeVisible();
    await screenshot(page, 'auth-config-error.png');
  });

  test('otp email and code steps', async ({ page }) => {
    await mockAuthConfig(page, {
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
    });
    await page.route('/api/auth/otp/request', (route) => route.fulfill(json({ status: 'sent' })));

    await page.goto('/login');
    await page.getByRole('button', { name: 'Use email code instead' }).click();
    await expect(page.getByLabel('Email address')).toBeVisible();
    await screenshot(page, 'auth-otp-email.png');

    await page.getByLabel('Email address').fill('reader@example.com');
    await page.getByRole('button', { name: 'Send code' }).click();
    await expect(page.getByLabel('6-digit code')).toBeVisible();
    await screenshot(page, 'auth-otp-code.png');
  });

  test('keycloak login and oauth recovery', async ({ page }) => {
    await mockAuthConfig(page, {
      provider: 'keycloak',
      keycloak_enabled: true,
      login_url: '/api/auth/keycloak/login',
      registration_url: '/register',
    });

    await page.goto('/login?auth_error=oauth_state');
    await expect(page.getByRole('link', { name: 'Sign in with Keycloak' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Create account' })).toBeVisible();
    await expect(page.getByRole('alert')).toBeVisible();
    await screenshot(page, 'auth-keycloak-oauth-recovery.png');
  });

  test('session expired message on mobile', async ({ page }) => {
    await mockAuthConfig(page, {
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
    });

    await page.goto('/login');
    await page.evaluate(() => {
      window.history.replaceState({ usr: { sessionExpired: true, from: '/today' } }, '', '/login');
      window.location.reload();
    });
    await expect(page.getByRole('alert')).toContainText('Your session expired');
    await screenshot(page, 'auth-session-expired-mobile.png');
  });
});

test.describe('@visual core app surfaces', () => {
  test('article list happy in light and dark themes', async ({ page }) => {
    await mockLoggedInApp(page);
    await page.goto('/today');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    await screenshot(page, 'today-happy-light.png');

    await page.evaluate(() => {
      window.localStorage.setItem('theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
    await screenshot(page, 'today-happy-dark.png');
  });

  test('article list loading, empty, and error states', async ({ page }) => {
    await mockLoggedInApp(page);
    let resolveArticles: (() => void) | null = null;
    await page.route('/api/articles**', async (route) => {
      await new Promise<void>((resolve) => {
        resolveArticles = resolve;
      });
      await route.fulfill(json({ items: [] }));
    });

    await page.goto('/today', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.animate-pulse').first()).toBeVisible();
    await screenshot(page, 'today-loading.png');

    resolveArticles?.();
    await expect(page.getByText('Queue clear')).toBeVisible();
    await screenshot(page, 'today-empty.png');

    await page.route('/api/articles**', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/today');
    await expect(page.getByText('Could not load articles')).toBeVisible();
    await screenshot(page, 'today-error.png');
  });

  test('article reader happy, body loading, not found, and error states', async ({ page }) => {
    await mockLoggedInApp(page);
    let resolveBody: (() => void) | null = null;
    await page.route('/api/articles/1/body', async (route) => {
      await new Promise<void>((resolve) => {
        resolveBody = resolve;
      });
      await route.fulfill(
        json({
          ...SAMPLE_ARTICLE,
          body: 'Stable article body for visual checks.',
          body_status: 'ok',
        })
      );
    });

    await page.goto('/a/1', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    await screenshot(page, 'article-body-loading.png');

    resolveBody?.();
    await expect(page.getByText('Stable article body for visual checks.')).toBeVisible();
    await screenshot(page, 'article-happy.png');

    await page.route('/api/articles/404**', (route) =>
      route.fulfill(json({ detail: 'Not found' }, 404))
    );
    await page.goto('/a/404');
    await expect(page.getByText('Article not found')).toBeVisible();
    await screenshot(page, 'article-not-found.png');

    await page.route('/api/articles/500**', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/a/500');
    await expect(page.getByText('Could not load article')).toBeVisible();
    await screenshot(page, 'article-error.png');
  });

  test('brief happy, empty, initial-load error, and generation error states', async ({ page }) => {
    await mockLoggedInApp(page);
    await page.goto('/');
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
    await screenshot(page, 'brief-happy.png');

    await page.route('/api/briefings**', (route) => {
      const request = route.request();
      if (request.method() === 'POST') return route.fulfill(ERROR_JSON);
      return route.fulfill(json({ status: 'empty' }));
    });
    await page.goto('/');
    await expect(page.getByText('No briefing yet')).toBeVisible();
    await screenshot(page, 'brief-empty.png');

    await page.getByRole('button', { name: 'Generate briefing' }).click();
    await expect(page.getByText('Generation failed')).toBeVisible();
    await screenshot(page, 'brief-generation-error.png');

    await page.route('/api/briefings**', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/');
    await expect(page.getByText('Could not load the latest briefing')).toBeVisible();
    await screenshot(page, 'brief-initial-load-error.png');
  });

  test('shared, collections, and reading list empty and error states', async ({ page }) => {
    await mockLoggedInApp(page);
    await page.route('/api/shares', (route) => route.fulfill(json({ items: [], unread: 0 })));
    await page.goto('/shared');
    await expect(page.getByText('Nothing shared yet')).toBeVisible();
    await screenshot(page, 'shared-empty.png');

    await page.route('/api/shares', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/shared');
    await expect(page.getByText('Could not load received shares')).toBeVisible();
    await screenshot(page, 'shared-error.png');

    await page.route('/api/tags', (route) => route.fulfill(json({ items: [] })));
    await page.goto('/collections');
    await expect(page.getByText('No collections yet')).toBeVisible();
    await screenshot(page, 'collections-empty.png');

    await page.route('/api/tags', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/collections');
    await expect(page.getByText('Could not load collections')).toBeVisible();
    await screenshot(page, 'collections-error.png');

    await page.route('/api/reading-list**', (route) => route.fulfill(json({ items: [] })));
    await page.goto('/reading-list');
    await expect(page.getByText('Your reading list is empty')).toBeVisible();
    await screenshot(page, 'reading-list-empty.png');

    await page.route('/api/reading-list**', (route) => route.fulfill(ERROR_JSON));
    await page.goto('/reading-list');
    await expect(page.getByText('Could not load reading list')).toBeVisible();
    await screenshot(page, 'reading-list-error.png');
  });

  test('core app shell on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockLoggedInApp(page);
    await page.goto('/today');
    await expect(page.locator('nav.fixed')).toBeVisible();
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    await screenshot(page, 'app-shell-mobile.png');
  });

  test('404 recovery surface', async ({ page }) => {
    await mockLoggedInApp(page);
    await page.goto('/does-not-exist');
    await expect(page.getByText('Page not found')).toBeVisible();
    await screenshot(page, 'not-found.png');
  });
});
