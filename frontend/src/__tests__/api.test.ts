// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';

// A small fetch harness: capture the last call and return a canned response.
interface Call {
  url: string;
  init?: RequestInit;
}

function stubFetch(impl: (url: string, init?: RequestInit) => unknown): { calls: Call[] } {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(impl(url, init));
    })
  );
  return { calls };
}

function jsonOk(body: unknown) {
  return { ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('requestJson', () => {
  it('sends JSON headers and same-origin credentials', async () => {
    const { calls } = stubFetch(() => jsonOk({ ok: 1 }));
    const result = await api.requestJson<{ ok: number }>('/api/thing');
    expect(result).toEqual({ ok: 1 });
    expect(calls[0].url).toBe('/api/thing');
    expect(calls[0].init?.credentials).toBe('same-origin');
    expect((calls[0].init?.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json'
    );
  });

  it('throws on non-ok responses with status text when no body', async () => {
    stubFetch(() => ({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: () => Promise.reject(new SyntaxError('no json')),
      text: () => Promise.resolve(''),
    }));
    await expect(api.requestJson('/api/boom')).rejects.toThrow('500 Server Error');
  });

  it('includes FastAPI detail string in thrown error', async () => {
    stubFetch(() => ({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: () => Promise.resolve({ detail: 'Invalid briefing time' }),
      text: () => Promise.resolve('{"detail":"Invalid briefing time"}'),
    }));
    await expect(api.requestJson('/api/briefings')).rejects.toThrow('Invalid briefing time');
  });

  it('joins Pydantic validation error array into readable message', async () => {
    stubFetch(() => ({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: () =>
        Promise.resolve({
          detail: [
            { msg: 'field required', loc: ['body', 'name'] },
            { msg: 'value is not a valid email', loc: ['body', 'email'] },
          ],
        }),
      text: () => Promise.resolve(''),
    }));
    const err = await api.requestJson('/api/thing').catch((e: Error) => e);
    expect((err as Error).message).toContain('field required');
    expect((err as Error).message).toContain('value is not a valid email');
  });

  it('uses message field as fallback detail shape', async () => {
    stubFetch(() => ({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ message: 'Username already taken' }),
      text: () => Promise.resolve(''),
    }));
    await expect(api.requestJson('/api/auth/register')).rejects.toThrow('Username already taken');
  });

  it('falls back to status text for non-JSON error bodies', async () => {
    stubFetch(() => ({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: () => Promise.reject(new SyntaxError('not json')),
      text: () => Promise.resolve('upstream error'),
    }));
    await expect(api.requestJson('/api/thing')).rejects.toThrow('503 Service Unavailable');
  });

  it('honors caller-provided headers', async () => {
    const { calls } = stubFetch(() => jsonOk({}));
    await api.requestJson('/api/x', { headers: { 'X-Custom': 'v' } });
    const headers = calls[0].init?.headers as Record<string, string>;
    expect(headers['X-Custom']).toBe('v');
  });
});

describe('article list endpoints', () => {
  it('fetchArticles builds query params only when set', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [{ id: 1 }] }));
    const items = await api.fetchArticles('read', 'ai-llm', 20, 50);
    expect(items).toEqual([{ id: 1 }]);
    expect(calls[0].url).toContain('status=read');
    expect(calls[0].url).toContain('category=ai-llm');
    expect(calls[0].url).toContain('offset=20');
    expect(calls[0].url).toContain('limit=50');
  });

  it('fetchArticles omits default offset/limit', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await api.fetchArticles();
    expect(calls[0].url).toBe('/api/articles');
  });

  it('searchArticles encodes the query', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await api.searchArticles('hello world', 10);
    expect(calls[0].url).toContain('q=hello+world');
    expect(calls[0].url).toContain('limit=10');
  });

  it('fetchArticle hits the article path', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 7 }));
    const a = await api.fetchArticle(7);
    expect(a).toEqual({ id: 7 });
    expect(calls[0].url).toBe('/api/articles/7');
  });

  it('fetchArticleBody POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 7 }));
    await api.fetchArticleBody(7);
    expect(calls[0].init?.method).toBe('POST');
    expect(calls[0].url).toBe('/api/articles/7/body');
  });

  it('fetchArticleInsights unwraps bullets', async () => {
    stubFetch(() => jsonOk({ bullets: ['a', 'b'] }));
    expect(await api.fetchArticleInsights(1)).toEqual(['a', 'b']);
  });
});

describe('fetchArticleAudioUrl', () => {
  it('returns an object URL from the audio blob', async () => {
    const blob = new Blob(['x']);
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, blob: () => Promise.resolve(blob) }))
    );
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:abc') });
    expect(await api.fetchArticleAudioUrl(3)).toBe('blob:abc');
  });

  it('throws on a failed audio response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          statusText: 'Not Found',
          json: () => Promise.reject(new SyntaxError('no json')),
          text: () => Promise.resolve(''),
        })
      )
    );
    await expect(api.fetchArticleAudioUrl(3)).rejects.toThrow('404 Not Found');
  });

  it('includes backend detail in audio error when JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          statusText: 'Not Found',
          json: () => Promise.resolve({ detail: 'Article has no audio' }),
          text: () => Promise.resolve(''),
        })
      )
    );
    await expect(api.fetchArticleAudioUrl(3)).rejects.toThrow('Article has no audio');
  });
});

describe('sources, summary, ingest', () => {
  it('fetchSources unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [{ slug: 's' }] }));
    expect(await api.fetchSources()).toEqual([{ slug: 's' }]);
  });

  it('fetchSourceHealth unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [{ slug: 's' }] }));
    expect(await api.fetchSourceHealth()).toEqual([{ slug: 's' }]);
  });

  it('fetchSourceCleanupSuggestions unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [{ source_slug: 's' }] }));
    expect(await api.fetchSourceCleanupSuggestions()).toEqual([{ source_slug: 's' }]);
  });

  it('applySourceCleanup POSTs selected slugs', async () => {
    const { calls } = stubFetch(() => jsonOk({ updated: ['s'], skipped: [] }));
    await api.applySourceCleanup(['s']);
    expect(calls[0].url).toBe('/api/sources/cleanup');
    expect(calls[0].init?.method).toBe('POST');
    expect(calls[0].init?.body).toBe(JSON.stringify({ source_slugs: ['s'] }));
  });

  it('fetchSummary returns the summary', async () => {
    stubFetch(() => jsonOk({ total: 5 }));
    expect(await api.fetchSummary()).toEqual({ total: 5 });
  });

  it('ingestNow POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ inserted: 2, results: {} }));
    const r = await api.ingestNow();
    expect(r.inserted).toBe(2);
    expect(calls[0].init?.method).toBe('POST');
  });

  it('updateArticleStatus PATCHes a status body', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 1 }));
    await api.updateArticleStatus(1, 'read');
    expect(calls[0].init?.method).toBe('PATCH');
    expect(calls[0].init?.body).toBe(JSON.stringify({ status: 'read' }));
  });

  it('askAI POSTs the query and include_all', async () => {
    const { calls } = stubFetch(() => jsonOk({ answer: 'x' }));
    await api.askAI('q', true);
    expect(calls[0].init?.body).toBe(JSON.stringify({ query: 'q', include_all: true }));
  });

  it('updateSourceEnabled PATCHes enabled', async () => {
    const { calls } = stubFetch(() => jsonOk({ slug: 's' }));
    await api.updateSourceEnabled('s', false);
    expect(calls[0].url).toBe('/api/sources/s/enabled');
    expect(calls[0].init?.body).toBe(JSON.stringify({ enabled: false }));
  });
});

describe('scheduler endpoints', () => {
  it('fetchSchedulerStatus GETs status', async () => {
    const { calls } = stubFetch(() =>
      jsonOk({ interval_minutes: 30, paused: false, next_run_at: null })
    );
    const s = await api.fetchSchedulerStatus();
    expect(s.interval_minutes).toBe(30);
    expect(calls[0].url).toBe('/api/scheduler/status');
  });

  it('setSchedulerInterval POSTs minutes', async () => {
    const { calls } = stubFetch(() => jsonOk({ interval_minutes: 15, next_run_at: null }));
    await api.setSchedulerInterval(15);
    expect(calls[0].init?.body).toBe(JSON.stringify({ minutes: 15 }));
  });

  it('pauseScheduler POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ paused: true }));
    expect((await api.pauseScheduler()).paused).toBe(true);
    expect(calls[0].init?.method).toBe('POST');
  });

  it('resumeScheduler POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ paused: false, next_run_at: null }));
    expect((await api.resumeScheduler()).paused).toBe(false);
    expect(calls[0].init?.method).toBe('POST');
  });
});

describe('stats endpoints', () => {
  it('fetchStatsOverview passes from/to', async () => {
    const { calls } = stubFetch(() => jsonOk({ total: 1 }));
    await api.fetchStatsOverview('2026-01-01', '2026-02-01');
    expect(calls[0].url).toContain('from=2026-01-01');
    expect(calls[0].url).toContain('to=2026-02-01');
  });

  it('fetchArticlesOverTime unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [{ date: 'd', count: 1 }] }));
    expect(await api.fetchArticlesOverTime('a', 'b')).toEqual([{ date: 'd', count: 1 }]);
  });

  it('fetchSourcesVolume unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [] }));
    expect(await api.fetchSourcesVolume('a', 'b')).toEqual([]);
  });

  it('fetchArticleCounts returns the result', async () => {
    stubFetch(() => jsonOk({ total: 10 }));
    expect(await api.fetchArticleCounts()).toEqual({ total: 10 });
  });

  it('fetchTriageMetrics returns metrics', async () => {
    stubFetch(() => jsonOk({ today: 3 }));
    expect(await api.fetchTriageMetrics()).toEqual({ today: 3 });
  });

  it('fetchSourceQuality unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [] }));
    expect(await api.fetchSourceQuality()).toEqual([]);
  });

  it('fetchCategoryMix unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [] }));
    expect(await api.fetchCategoryMix()).toEqual([]);
  });

  it('fetchIngestedVsHandled unwraps items', async () => {
    stubFetch(() => jsonOk({ items: [] }));
    expect(await api.fetchIngestedVsHandled()).toEqual([]);
  });
});

describe('ingest runs & briefings', () => {
  it('fetchIngestRuns passes pagination', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [], total: 0 }));
    await api.fetchIngestRuns(2, 25);
    expect(calls[0].url).toContain('page=2');
    expect(calls[0].url).toContain('per_page=25');
  });

  it('fetchIngestRunSources unwraps items', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await api.fetchIngestRunSources(9);
    expect(calls[0].url).toBe('/api/ingest/runs/9');
  });

  it('fetchLatestBriefing GETs latest', async () => {
    const { calls } = stubFetch(() => jsonOk({ briefing: null }));
    await api.fetchLatestBriefing();
    expect(calls[0].url).toBe('/api/briefings/latest');
  });

  it('createBriefing POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 1 }));
    await api.createBriefing();
    expect(calls[0].init?.method).toBe('POST');
  });

  it('createBriefing sends focus_prompt when provided', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 1 }));
    await api.createBriefing('tech policy');
    expect(calls[0].init?.body).toBe(JSON.stringify({ focus_prompt: 'tech policy' }));
  });

  it('fetchBriefing GETs by id', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 4 }));
    await api.fetchBriefing(4);
    expect(calls[0].url).toBe('/api/briefings/4');
  });

  it('fetchBriefings passes limit/offset', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await api.fetchBriefings(20, 5);
    expect(calls[0].url).toContain('limit=20');
    expect(calls[0].url).toContain('offset=5');
  });
});

describe('auth endpoints', () => {
  it('fetchAuthConfig returns config', async () => {
    stubFetch(() => jsonOk({ provider: 'password' }));
    expect((await api.fetchAuthConfig()).provider).toBe('password');
  });

  it('fetchMe returns the user', async () => {
    stubFetch(() => jsonOk({ id: 1, username: 'a' }));
    expect((await api.fetchMe()).username).toBe('a');
  });

  it('loginUser POSTs credentials', async () => {
    const { calls } = stubFetch(() => jsonOk({ id: 1 }));
    await api.loginUser('u', 'p');
    expect(calls[0].init?.body).toBe(JSON.stringify({ username: 'u', password: 'p' }));
  });

  it('logoutUser redirects to keycloak logout url when configured', async () => {
    stubFetch(() => jsonOk({ provider: 'keycloak', logout_url: 'https://kc/logout' }));
    const assign = vi.fn();
    vi.stubGlobal('location', { assign });
    await api.logoutUser();
    expect(assign).toHaveBeenCalledWith('https://kc/logout');
  });

  it('logoutUser falls back to local logout for password provider', async () => {
    const { calls } = stubFetch((url) =>
      url.includes('/config') ? jsonOk({ provider: 'password', logout_url: '' }) : jsonOk({})
    );
    await api.logoutUser();
    expect(calls.some((c) => c.url === '/api/auth/logout')).toBe(true);
  });

  it('logoutUser still logs out locally when config fetch fails', async () => {
    const { calls } = stubFetch((url) =>
      url.includes('/config') ? { ok: false, status: 500, statusText: 'err' } : jsonOk({})
    );
    await api.logoutUser();
    expect(calls.some((c) => c.url === '/api/auth/logout')).toBe(true);
  });
});

describe('subscriptions & recommendations', () => {
  it('toggleSourceSubscription PATCHes enabled', async () => {
    const { calls } = stubFetch(() => jsonOk({ subscribed: true }));
    await api.toggleSourceSubscription('s', true);
    expect(calls[0].url).toBe('/api/sources/s/enabled');
    expect(calls[0].init?.body).toBe(JSON.stringify({ enabled: true }));
  });

  it('recalculateMyRecommendations POSTs', async () => {
    const { calls } = stubFetch(() => jsonOk({ scored: 12 }));
    expect((await api.recalculateMyRecommendations()).scored).toBe(12);
    expect(calls[0].init?.method).toBe('POST');
  });
});
