/**
 * Shared API mock data and helpers for E2E tests.
 * All tests intercept /api/* with page.route() so no real backend is needed.
 */
import type { Page, Route } from '@playwright/test';

// ── Sample data ───────────────────────────────────────────────────────────────

export const SAMPLE_ARTICLE = {
  id: 1,
  url: 'https://example.com/article-1',
  canonical_url: 'https://example.com/article-1',
  title: 'AI Safety Researchers Publish New Framework',
  source_slug: 'anthropic-blog',
  source_name: 'Anthropic Blog',
  category: 'ai',
  kind: 'rss_feed',
  published_at: '2026-06-13T10:00:00+00:00',
  discovered_at: '2026-06-13T11:00:00+00:00',
  status: 'new',
  state: 'today',
  importance_score: 85,
  summary: 'Researchers at Anthropic publish a comprehensive safety framework for LLMs.',
  reason: 'High relevance to AI safety research.',
  tags: '[]',
  starred: false,
  read_at: null,
  saved_at: null,
  skipped_at: null,
  archived_at: null,
  done_at: null,
  starred_at: null,
  later_until: null,
  restored_at: null,
  body: null,
  body_status: 'missing',
};

export const SAMPLE_ARTICLE_2 = {
  ...SAMPLE_ARTICLE,
  id: 2,
  title: 'OpenAI Releases GPT-5 Technical Report',
  source_name: 'OpenAI Blog',
  source_slug: 'openai-blog',
  importance_score: 90,
};

export const SAMPLE_ARTICLE_3 = {
  ...SAMPLE_ARTICLE,
  id: 3,
  title: 'Google DeepMind Publishes Gemini 2.0 Benchmarks',
  source_name: 'DeepMind Blog',
  source_slug: 'deepmind-blog',
  importance_score: 75,
  state: 'later',
  later_until: '2026-06-20T00:00:00+00:00',
};

export const SAMPLE_STARRED_ARTICLE = {
  ...SAMPLE_ARTICLE,
  id: 4,
  title: 'The Future of Agentic AI Systems',
  source_name: 'MIT Tech Review',
  source_slug: 'mit-tech',
  status: 'saved',
  state: 'done',
  starred: true,
  saved_at: '2026-06-12T09:00:00+00:00',
};

export const SAMPLE_SOURCE = {
  slug: 'anthropic-blog',
  name: 'Anthropic Blog',
  url: 'https://www.anthropic.com/news/rss',
  category: 'ai',
  kind: 'rss_feed',
  priority: 80,
  enabled: 1,
  last_checked_at: '2026-06-13T11:00:00+00:00',
  last_success_at: '2026-06-13T11:00:00+00:00',
  last_error: null,
  last_fetched_count: 3,
  last_inserted_count: 2,
};

export const SAMPLE_BRIEFING_ARTICLE = {
  id: 1,
  title: 'AI Safety Researchers Publish New Framework',
  url: 'https://example.com/article-1',
  source_name: 'Anthropic Blog',
  category: 'ai',
  section_index: 0,
  citation_index: 0,
  importance_score: 85,
};

export const SAMPLE_BRIEFING_ARTICLE_WORTH = {
  id: 2,
  title: 'OpenAI Releases GPT-5 Technical Report',
  url: 'https://example.com/article-2',
  source_name: 'OpenAI Blog',
  category: 'ai',
  section_index: null,
  citation_index: null,
  importance_score: 90,
};

export const SAMPLE_BRIEFING = {
  id: 1,
  created_at: '2026-06-13T12:00:00+00:00',
  scope: 'since_last_briefing',
  since_at: '2026-06-12T12:00:00+00:00',
  until_at: '2026-06-13T12:00:00+00:00',
  status: 'complete',
  title: 'AI Safety Takes Center Stage',
  summary:
    'New safety frameworks and model releases dominated today\'s AI news, signaling a maturing field.',
  content: {
    sections: [
      {
        title: 'Safety Research',
        body: 'Anthropic published a new safety framework that sets benchmarks for responsible AI deployment.',
        citations: [1],
      },
      {
        title: 'Model Releases',
        body: 'OpenAI and Google both released significant model updates with improved reasoning.',
        citations: [2],
      },
    ],
    worth_opening: [2],
  },
  model: 'gpt-4o-mini',
  error: null,
  articles: [SAMPLE_BRIEFING_ARTICLE, SAMPLE_BRIEFING_ARTICLE_WORTH],
};

export const SUMMARY_DATA = {
  byStatus: { new: 12, read: 45, saved: 8, skipped: 3, archived: 20 },
  byCategory: { ai: 25, tech: 18, science: 10 },
};

export const SCHEDULER_STATUS = {
  interval_minutes: 60,
  paused: false,
  next_run_at: '2026-06-13T13:00:00+00:00',
};

export const SAMPLE_USER = {
  id: 1,
  username: 'e2e-user',
  email: 'e2e@example.com',
  is_admin: true,
};

// ── Mock setup helpers ────────────────────────────────────────────────────────

function json(data: unknown, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(data) };
}

/**
 * Install default API mocks for all routes. Individual tests can override
 * by calling page.route() before navigate() — Playwright uses the last
 * matching handler.
 */
export async function mockApi(page: Page) {
  // Auth
  await page.route('/api/auth/config', (r) =>
    r.fulfill(
      json({
        provider: 'password',
        keycloak_enabled: false,
        login_url: null,
        logout_url: '/api/auth/logout',
      })
    )
  );
  await page.route('/api/auth/me', (r) => r.fulfill(json(SAMPLE_USER)));
  await page.route('/api/auth/logout', (r) => r.fulfill(json({ status: 'logged_out' })));

  // Summary / counts
  await page.route('/api/summary', (r) => r.fulfill(json(SUMMARY_DATA)));

  // Briefings — single handler dispatches by path/method to avoid glob ambiguity
  await page.route('/api/briefings**', async (r: Route) => {
    const url = new URL(r.request().url());
    const method = r.request().method();
    const path = url.pathname;

    if (method === 'GET' && path === '/api/briefings') {
      return r.fulfill(json({ items: [SAMPLE_BRIEFING] }));
    }
    if (method === 'POST' && path === '/api/briefings') {
      return r.fulfill(json(SAMPLE_BRIEFING));
    }
    // /api/briefings/latest, /api/briefings/:id, etc.
    return r.fulfill(json(SAMPLE_BRIEFING));
  });

  // Articles
  await page.route('/api/articles**', async (r: Route) => {
    const url = new URL(r.request().url());
    const state = url.searchParams.get('state');
    if (state === 'today') {
      return r.fulfill(json({ items: [SAMPLE_ARTICLE, SAMPLE_ARTICLE_2] }));
    }
    if (state === 'later') {
      return r.fulfill(json({ items: [SAMPLE_ARTICLE_3] }));
    }
    if (url.searchParams.get('starred') === 'true') {
      return r.fulfill(json({ items: [SAMPLE_STARRED_ARTICLE] }));
    }
    return r.fulfill(json({ items: [SAMPLE_ARTICLE, SAMPLE_ARTICLE_2, SAMPLE_ARTICLE_3] }));
  });

  // Individual article
  await page.route('/api/articles/1', (r) => r.fulfill(json(SAMPLE_ARTICLE)));
  await page.route('/api/articles/2', (r) => r.fulfill(json(SAMPLE_ARTICLE_2)));
  await page.route('/api/articles/*/body', (r) =>
    r.fulfill(json({ ...SAMPLE_ARTICLE, body: 'Full article body text here.', body_status: 'ok' }))
  );
  await page.route('/api/articles/*/status', (r) =>
    r.fulfill(json({ ...SAMPLE_ARTICLE, status: 'read' }))
  );
  await page.route('/api/articles/*/star', (r) =>
    r.fulfill(json({ ...SAMPLE_ARTICLE, starred: true }))
  );
  await page.route('/api/articles/*/state', (r) =>
    r.fulfill(json({ ...SAMPLE_ARTICLE, state: 'done' }))
  );
  await page.route('/api/articles/*/later', (r) =>
    r.fulfill(json({ ...SAMPLE_ARTICLE, state: 'later' }))
  );

  // Search
  await page.route('/api/search**', (r) =>
    r.fulfill(json({ items: [SAMPLE_ARTICLE, SAMPLE_ARTICLE_2] }))
  );

  // Sources
  await page.route('/api/sources', async (r: Route) => {
    if (r.request().method() === 'GET') return r.fulfill(json({ items: [SAMPLE_SOURCE] }));
    return r.fulfill(json(SAMPLE_SOURCE));
  });
  await page.route('/api/sources/health', (r) =>
    r.fulfill(
      json({
        items: [
          {
            slug: 'anthropic-blog',
            name: 'Anthropic Blog',
            category: 'ai',
            enabled: 1,
            last_checked_at: '2026-06-13T11:00:00+00:00',
            last_error: null,
            error_streak: 0,
            articles_last_run: 2,
            status: 'OK',
          },
        ],
      })
    )
  );
  await page.route('/api/sources/*/enabled', (r) => r.fulfill(json(SAMPLE_SOURCE)));

  // Scheduler
  await page.route('/api/scheduler/status', (r) => r.fulfill(json(SCHEDULER_STATUS)));
  await page.route('/api/scheduler/**', (r) => r.fulfill(json(SCHEDULER_STATUS)));

  // Ingest
  await page.route('/api/ingest', async (r: Route) => {
    if (r.request().method() === 'POST') {
      return r.fulfill(json({ inserted: 5, results: { 'Anthropic Blog': 5 } }));
    }
    return r.fulfill(json({}));
  });
  await page.route('/api/ingest/runs**', (r) =>
    r.fulfill(
      json({
        items: [
          {
            id: 1,
            started_at: '2026-06-13T10:00:00+00:00',
            finished_at: '2026-06-13T10:01:00+00:00',
            duration_ms: 60000,
            sources_run: 1,
            total_new: 5,
            total_errors: 0,
          },
        ],
        page: 1,
        per_page: 10,
        total: 1,
        has_more: false,
      })
    )
  );

  // Ask
  await page.route('/api/ask', (r) =>
    r.fulfill(
      json({
        answer: 'Based on the articles, AI safety research is progressing rapidly [1].',
        sources: [{ id: 1, title: 'AI Safety Researchers Publish New Framework', url: 'https://example.com/article-1' }],
      })
    )
  );

  // Stats
  await page.route('/api/stats/**', (r) =>
    r.fulfill(
      json({
        items: [],
        total_articles: 88,
        total_new: 12,
        total_errors: 0,
        avg_duration_ms: 1200,
        healthy_sources: 1,
        erroring_sources: 0,
      })
    )
  );

  // Health
  await page.route('/api/health', (r) =>
    r.fulfill(json({ status: 'ok', database: 'PostgreSQL', next_ingest_at: null }))
  );
}
