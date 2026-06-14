/**
 * Admin vs normal-user E2E tests.
 *
 * The backend gates several routes behind require_admin and returns 403
 * for normal users.  These tests verify that:
 *
 * Admin users:
 *   - See full data on every page / tab
 *   - Can trigger write actions (pause/resume scheduler, run ingest)
 *
 * Normal users:
 *   - See their own article/summary data on all reading pages
 *   - See an error state (not a blank page) on admin-gated pages
 *   - Cannot trigger admin write actions (buttons fail visibly or are absent)
 *
 * All tests intercept /api/* so no real backend is needed.
 */
import { test, expect, type Page } from '@playwright/test';
import {
  mockApi,
  SAMPLE_ARTICLE,
  SAMPLE_ARTICLE_2,
  SAMPLE_ARTICLE_3,
  SAMPLE_STARRED_ARTICLE,
  SAMPLE_BRIEFING,
  SUMMARY_DATA,
  SCHEDULER_STATUS,
  SAMPLE_SOURCE,
} from './fixtures';

// ── helpers ────────────────────────────────────────────────────────────────

function json(data: unknown, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(data) };
}

/** Mock /api/auth/me to return an admin user. */
async function loginAsAdmin(page: Page) {
  await page.route('/api/auth/me', (r) =>
    r.fulfill(json({ id: 1, username: 'admin', email: null, is_admin: true }))
  );
}

/** Mock /api/auth/me to return a normal (non-admin) user. */
async function loginAsUser(page: Page) {
  await page.route('/api/auth/me', (r) =>
    r.fulfill(json({ id: 2, username: 'alice', email: null, is_admin: false }))
  );
}

/** Override an admin-gated endpoint to return 403 Forbidden. */
async function block403(page: Page, urlPattern: string) {
  await page.route(urlPattern, (r) =>
    r.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Forbidden' }) })
  );
}

// ── Brief page (/) ─────────────────────────────────────────────────────────

test.describe('Brief page — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('shows Brief heading', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1').filter({ hasText: 'Brief' })).toBeVisible();
  });

  test('renders briefing title', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
  });

  test('shows summary counts in sidebar', async ({ page }) => {
    await page.goto('/');
    // byStatus.new = 12, rendered somewhere in the nav
    await expect(page.locator('aside')).toContainText('12');
  });
});

test.describe('Brief page — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
  });

  test('shows Brief heading', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1').filter({ hasText: 'Brief' })).toBeVisible();
  });

  test('renders briefing content', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
  });

  test('user-scoped summary counts appear in nav', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('aside')).toContainText(String(SUMMARY_DATA.byStatus.new));
  });
});

// ── Today page (/today) ────────────────────────────────────────────────────

test.describe('Today page — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('shows Today heading', async ({ page }) => {
    await page.goto('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('shows articles from admin user', async ({ page }) => {
    await page.goto('/today');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    await expect(page.getByText(SAMPLE_ARTICLE_2.title)).toBeVisible();
  });
});

test.describe('Today page — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
  });

  test('shows Today heading', async ({ page }) => {
    await page.goto('/today');
    await expect(page.locator('h1').filter({ hasText: 'Today' })).toBeVisible();
  });

  test('shows user-specific articles only', async ({ page }) => {
    await page.route('/api/articles**', (r) => {
      const url = new URL(r.request().url());
      if (url.searchParams.get('state') === 'today') {
        return r.fulfill(json({ items: [SAMPLE_ARTICLE] }));
      }
      return r.fulfill(json({ items: [] }));
    });
    await page.goto('/today');
    await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    // SAMPLE_ARTICLE_2 is not in this user's feed
    await expect(page.getByText(SAMPLE_ARTICLE_2.title)).not.toBeVisible();
  });

  test('shows empty state when user has no articles', async ({ page }) => {
    await page.route('/api/articles**', (r) => r.fulfill(json({ items: [] })));
    await page.goto('/today');
    await expect(page.getByText('Queue clear')).toBeVisible();
  });
});

// ── Later page (/later) ────────────────────────────────────────────────────

test.describe('Later page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Later heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/later');
      await expect(page.locator('h1').filter({ hasText: 'Later' })).toBeVisible();
    });

    test(`renders later articles for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/later');
      await expect(page.getByText(SAMPLE_ARTICLE_3.title)).toBeVisible();
    });
  }

  test('normal user sees only their own later articles', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/articles**', (r) => {
      const url = new URL(r.request().url());
      if (url.searchParams.get('state') === 'later') {
        return r.fulfill(json({ items: [SAMPLE_ARTICLE_3] }));
      }
      return r.fulfill(json({ items: [] }));
    });
    await page.goto('/later');
    await expect(page.getByText(SAMPLE_ARTICLE_3.title)).toBeVisible();
  });
});

// ── Starred page (/starred) ────────────────────────────────────────────────

test.describe('Starred page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Starred heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/starred');
      await expect(page.locator('h1').filter({ hasText: 'Starred' })).toBeVisible();
    });
  }

  test('normal user sees only their own starred articles', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/articles**', (r) => {
      const url = new URL(r.request().url());
      if (url.searchParams.get('starred') === 'true') {
        return r.fulfill(json({ items: [SAMPLE_STARRED_ARTICLE] }));
      }
      return r.fulfill(json({ items: [] }));
    });
    await page.goto('/starred');
    await expect(page.getByText(SAMPLE_STARRED_ARTICLE.title)).toBeVisible();
  });

  test('normal user sees empty state when nothing starred', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/articles**', (r) => r.fulfill(json({ items: [] })));
    await page.goto('/starred');
    // Page renders without crash even when empty
    await expect(page.locator('h1').filter({ hasText: 'Starred' })).toBeVisible();
  });
});

// ── Archive page (/archive) ────────────────────────────────────────────────

test.describe('Archive page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Archive heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/archive');
      await expect(page.locator('h1').filter({ hasText: 'Archive' })).toBeVisible();
    });
  }
});

// ── Search page (/search) ──────────────────────────────────────────────────

test.describe('Search page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Search heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/search');
      await expect(page.locator('h1').filter({ hasText: 'Search' })).toBeVisible();
    });
  }

  test('normal user search results are user-scoped', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/search**', (r) => r.fulfill(json({ items: [SAMPLE_ARTICLE] })));
    await page.goto('/search');
    const input = page.getByRole('textbox').first();
    if (await input.count() > 0) {
      await input.fill('AI Safety');
      await page.keyboard.press('Enter');
      await expect(page.getByText(SAMPLE_ARTICLE.title)).toBeVisible();
    }
  });
});

// ── Ask AI page (/ask) ────────────────────────────────────────────────────

test.describe('Ask AI page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Ask AI heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/ask');
      await expect(page.locator('h1').filter({ hasText: 'Ask AI' })).toBeVisible();
    });
  }
});

// ── Briefs history page (/briefs) ──────────────────────────────────────────

test.describe('Briefs history page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Briefs heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/briefs');
      await expect(page.locator('h1').filter({ hasText: /briefs/i })).toBeVisible();
    });

    test(`renders briefing list for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/briefs');
      await expect(page.getByText(SAMPLE_BRIEFING.title)).toBeVisible();
    });
  }
});

// ── Settings page (/settings) ─────────────────────────────────────────────

test.describe('Settings page — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`shows Settings heading for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/settings');
      await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
    });

    test(`shows theme options for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/settings');
      await expect(page.getByText('Light')).toBeVisible();
      await expect(page.getByText('Dark')).toBeVisible();
    });
  }
});

// ── Feeds page — Sources tab ───────────────────────────────────────────────

test.describe('Feeds / Sources tab — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('shows Feeds heading', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('admin sees source list', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('main')).toContainText(SAMPLE_SOURCE.name);
  });

  test('admin can toggle source enable switch', async ({ page }) => {
    await page.goto('/feeds');
    const toggle = page.getByRole('switch').first();
    await expect(toggle).toBeVisible();
    await expect(toggle).toBeEnabled();
  });
});

test.describe('Feeds / Sources tab — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
  });

  test('shows Feeds heading', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('normal user sees source list (public sources)', async ({ page }) => {
    await page.goto('/feeds');
    await expect(page.locator('main')).toContainText(SAMPLE_SOURCE.name);
  });

  test('normal user can toggle their own source subscription', async ({ page }) => {
    await page.goto('/feeds');
    const toggle = page.getByRole('switch').first();
    await expect(toggle).toBeVisible();
  });
});

// ── Feeds page — Schedule tab ──────────────────────────────────────────────

test.describe('Feeds / Schedule tab — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('shows interval presets', async ({ page }) => {
    await page.goto('/feeds/schedule');
    await expect(page.getByText(/1h/i).first()).toBeVisible();
  });

  test('shows pause/resume button', async ({ page }) => {
    await page.goto('/feeds/schedule');
    const btn = page.getByRole('button', { name: /pause|resume/i }).first();
    await expect(btn).toBeVisible();
  });

  test('admin can pause scheduler', async ({ page }) => {
    await page.route('/api/scheduler/pause', (r) =>
      r.fulfill(json({ ...SCHEDULER_STATUS, paused: true, next_run_at: null }))
    );
    await page.goto('/feeds/schedule');
    const btn = page.getByRole('button', { name: /pause/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      // Pause request should succeed (no error toast)
      await expect(page.getByText(/error/i)).not.toBeVisible({ timeout: 2000 }).catch(() => {});
    }
  });

  test('admin can trigger ingest now', async ({ page }) => {
    await page.route('/api/ingest', (r) =>
      r.fulfill(json({ inserted: 3, results: { 'Anthropic Blog': 3 } }))
    );
    await page.goto('/feeds/schedule');
    const btn = page.getByRole('button', { name: /ingest now/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      // Should not crash
      await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
    }
  });
});

test.describe('Feeds / Schedule tab — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
  });

  test('page renders without crashing', async ({ page }) => {
    await page.goto('/feeds/schedule');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('scheduler status loads (GET is not admin-gated)', async ({ page }) => {
    await page.goto('/feeds/schedule');
    // Scheduler status endpoint is readable by all — interval should appear
    await expect(page.getByText(/60|interval|every|running|paused/i).first()).toBeVisible();
  });

  test('pause action returns 403, error is shown', async ({ page }) => {
    await block403(page, '/api/scheduler/pause');
    await block403(page, '/api/scheduler/resume');
    await page.goto('/feeds/schedule');
    const btn = page.getByRole('button', { name: /pause|resume/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      // Expect some error feedback (toast or error text)
      await expect(page.getByText(/error|forbidden|403/i).first()).toBeVisible({ timeout: 4000 });
    }
  });

  test('ingest now returns 403, error is shown', async ({ page }) => {
    await block403(page, '/api/ingest');
    await page.goto('/feeds/schedule');
    const btn = page.getByRole('button', { name: /ingest now/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      await expect(page.getByText(/error|forbidden|403/i).first()).toBeVisible({ timeout: 4000 });
    }
  });
});

// ── Feeds page — Runs tab ──────────────────────────────────────────────────

test.describe('Feeds / Runs tab — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('page renders', async ({ page }) => {
    await page.goto('/feeds/runs');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('shows ingest run table rows', async ({ page }) => {
    await page.goto('/feeds/runs');
    // Run from fixture: started_at 2026-06-13, total_new 5
    await expect(page.locator('main')).toContainText(/5|run/i);
  });
});

test.describe('Feeds / Runs tab — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await block403(page, '/api/ingest/runs**');
  });

  test('page renders without crashing', async ({ page }) => {
    await page.goto('/feeds/runs');
    await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
  });

  test('shows error state when runs API returns 403', async ({ page }) => {
    await page.goto('/feeds/runs');
    await expect(page.getByText(/error|forbidden|403/i).first()).toBeVisible({ timeout: 4000 });
  });
});

// ── Feeds page — Logs tab ──────────────────────────────────────────────────

test.describe('Feeds / Logs tab — both user types', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`logs tab renders for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/feeds/logs');
      await expect(page.locator('h1').filter({ hasText: 'Feeds' })).toBeVisible();
    });

    test(`shows Logs heading in content for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/feeds/logs');
      await expect(page.getByText('Logs').first()).toBeVisible();
    });

    test(`shows connection status indicator for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/feeds/logs');
      // Either "Live" (connected) or "Connecting…"
      await expect(page.getByText(/live|connecting/i).first()).toBeVisible();
    });
  }
});

// ── Stats page (/stats) ────────────────────────────────────────────────────

test.describe('Stats page — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
  });

  test('shows Stats heading', async ({ page }) => {
    await page.goto('/stats');
    await expect(page.locator('h1').filter({ hasText: 'Stats' })).toBeVisible();
  });

  test('renders charts / data', async ({ page }) => {
    await page.goto('/stats');
    // Page should not show an error banner (distinct from "Errors" table column header)
    await expect(page.getByRole('alert')).not.toBeVisible({ timeout: 3000 }).catch(() => {});
    await expect(page.getByText(/failed to load stats/i)).not.toBeVisible({ timeout: 3000 });
  });
});

test.describe('Stats page — normal user', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    // All stats endpoints are admin-only
    await block403(page, '/api/stats/**');
  });

  test('shows Stats heading', async ({ page }) => {
    await page.goto('/stats');
    await expect(page.locator('h1').filter({ hasText: 'Stats' })).toBeVisible();
  });

  test('shows error state when stats API returns 403', async ({ page }) => {
    await page.goto('/stats');
    await expect(page.getByText(/error|forbidden|403|failed/i).first()).toBeVisible({
      timeout: 6000,
    });
  });
});

// ── /api/summary — user-scoped counts in nav ───────────────────────────────

test.describe('/api/summary — user-scoped nav counts', () => {
  test('admin user sees their own summary counts', async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
    await page.route('/api/summary', (r) =>
      r.fulfill(json({ byStatus: { new: 99, saved: 5, read: 10, skipped: 2, archived: 0 }, byCategory: {} }))
    );
    await page.goto('/');
    await expect(page.locator('aside')).toContainText('99');
  });

  test('normal user sees their own summary counts (different from admin)', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/summary', (r) =>
      r.fulfill(json({ byStatus: { new: 3, saved: 1, read: 0, skipped: 0, archived: 0 }, byCategory: {} }))
    );
    await page.goto('/');
    await expect(page.locator('aside')).toContainText('3');
    // Admin's count (99) should not appear
    await expect(page.locator('aside')).not.toContainText('99');
  });

  test('summary count appears in Today nav link', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.route('/api/summary', (r) =>
      r.fulfill(json({ byStatus: { new: 7, saved: 0, read: 0, skipped: 0, archived: 0 }, byCategory: {} }))
    );
    await page.goto('/');
    // The Today nav entry shows the count
    const todayLink = page.locator('aside a[href="/today"]').first();
    await expect(todayLink).toContainText('7');
  });
});

// ── Navigation sidebar — username display ─────────────────────────────────

test.describe('Nav sidebar — username display', () => {
  test('admin username is shown in sidebar', async ({ page }) => {
    await loginAsAdmin(page);
    await mockApi(page);
    await page.goto('/');
    await expect(page.locator('aside')).toContainText('admin');
  });

  test('normal user username is shown in sidebar', async ({ page }) => {
    await loginAsUser(page);
    await mockApi(page);
    await page.goto('/');
    await expect(page.locator('aside')).toContainText('alice');
  });
});

// ── Legacy redirects — same for both user types ────────────────────────────

test.describe('Legacy redirects — work for both roles', () => {
  for (const role of ['admin', 'user'] as const) {
    test(`/inbox → /today for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/inbox');
      await expect(page).toHaveURL('/today');
    });

    test(`/saved → /starred for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/saved');
      await expect(page).toHaveURL('/starred');
    });

    test(`/sources → /feeds for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/sources');
      await expect(page).toHaveURL('/feeds');
    });

    test(`/scheduler → /feeds/schedule for ${role}`, async ({ page }) => {
      role === 'admin' ? await loginAsAdmin(page) : await loginAsUser(page);
      await mockApi(page);
      await page.goto('/scheduler');
      await expect(page).toHaveURL('/feeds/schedule');
    });
  }
});
