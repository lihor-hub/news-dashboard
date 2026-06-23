// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Article as LegacyArticle } from '../types';
import {
  adaptArticle,
  fetchTriageArticles,
  patchArticleState,
  patchArticleLater,
  patchArticleStar,
  snapshot,
  searchArticlesFiltered,
} from '../api/workflowApi';

interface Call {
  url: string;
  init?: RequestInit;
}

function stubFetch(impl: (url: string) => unknown): { calls: Call[] } {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(impl(url));
    })
  );
  return { calls };
}

function jsonOk(body: unknown) {
  return { ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body) };
}

function legacy(overrides: Partial<LegacyArticle> = {}): LegacyArticle {
  return {
    id: 1,
    title: 'T',
    source_name: 'Src',
    category: 'ai-llm',
    url: 'https://e.com',
    discovered_at: '2026-06-01T00:00:00Z',
    reason: 'r',
    summary: 's',
    importance_score: 0.5,
    tags: '',
    status: 'new',
    ...overrides,
  } as LegacyArticle;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('adaptArticle', () => {
  it('maps signal from importance score buckets', () => {
    expect(adaptArticle(legacy({ importance_score: 0.9 })).signal).toBe('high');
    expect(adaptArticle(legacy({ importance_score: 0.5 })).signal).toBe('mid');
    expect(adaptArticle(legacy({ importance_score: 0.1 })).signal).toBe('low');
  });

  it('derives state from legacy status when state is absent', () => {
    expect(adaptArticle(legacy({ status: 'read' })).state).toBe('done');
    expect(adaptArticle(legacy({ status: 'skipped' })).state).toBe('skipped');
    expect(adaptArticle(legacy({ status: 'archived' })).state).toBe('archived');
    expect(adaptArticle(legacy({ status: 'new' })).state).toBe('today');
  });

  it('prefers an explicit state field', () => {
    expect(adaptArticle(legacy({ state: 'later' })).state).toBe('later');
  });

  it('treats legacy saved status as starred', () => {
    const a = adaptArticle(legacy({ status: 'saved', saved_at: '2026-06-02T00:00:00Z' }));
    expect(a.starred).toBe(true);
    expect(a.starred_at).toBe('2026-06-02T00:00:00Z');
  });

  it('uses the starred flag when state model is present', () => {
    expect(adaptArticle(legacy({ state: 'today', starred: true })).starred).toBe(true);
  });

  it('parses JSON-array tags', () => {
    expect(adaptArticle(legacy({ tags: '["a","b"]' })).tags).toEqual(['a', 'b']);
  });

  it('parses comma-separated tags', () => {
    expect(adaptArticle(legacy({ tags: 'a, b , c' })).tags).toEqual(['a', 'b', 'c']);
  });

  it('returns no tags for an empty string', () => {
    expect(adaptArticle(legacy({ tags: '' })).tags).toEqual([]);
  });

  it('falls back to source_name when slug is absent', () => {
    expect(adaptArticle(legacy({ source_name: 'Src' })).sourceId).toBe('Src');
  });

  it('prefers published_at over discovered_at', () => {
    const a = adaptArticle(legacy({ published_at: '2026-05-01T00:00:00Z' }));
    expect(a.publishedAt).toBe('2026-05-01T00:00:00Z');
  });
});

describe('fetchTriageArticles', () => {
  it('queries starred=true for the starred view', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [legacy()] }));
    const items = await fetchTriageArticles('starred');
    expect(items).toHaveLength(1);
    expect(calls[0].url).toContain('starred=true');
  });

  it('queries state for non-starred views and forwards category', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await fetchTriageArticles('today', 'ai-llm');
    expect(calls[0].url).toContain('state=today');
    expect(calls[0].url).toContain('category=ai-llm');
  });
});

describe('mutations', () => {
  it('patchArticleState PATCHes the new state', async () => {
    const { calls } = stubFetch(() => jsonOk({}));
    await patchArticleState('5', 'done', false);
    expect(calls[0].url).toBe('/api/articles/5/state');
    expect(calls[0].init?.method).toBe('PATCH');
    expect(calls[0].init?.body).toBe(JSON.stringify({ state: 'done' }));
  });

  it('patchArticleLater sends the day count', async () => {
    const { calls } = stubFetch(() => jsonOk({}));
    await patchArticleLater('5', 3);
    expect(calls[0].init?.body).toBe(JSON.stringify({ days: 3 }));
  });

  it('patchArticleLater defaults to one day', async () => {
    const { calls } = stubFetch(() => jsonOk({}));
    await patchArticleLater('5');
    expect(calls[0].init?.body).toBe(JSON.stringify({ days: 1 }));
  });

  it('patchArticleStar sends the starred flag', async () => {
    const { calls } = stubFetch(() => jsonOk({}));
    await patchArticleStar('5', true);
    expect(calls[0].url).toBe('/api/articles/5/star');
    expect(calls[0].init?.body).toBe(JSON.stringify({ starred: true }));
  });
});

describe('snapshot', () => {
  it('clones the article into an undo snapshot', () => {
    const article = adaptArticle(legacy());
    const snap = snapshot(article);
    expect(snap.article).toEqual(article);
    expect(snap.article).not.toBe(article);
  });
});

describe('searchArticlesFiltered', () => {
  it('builds query params from all filters', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [legacy()] }));
    const items = await searchArticlesFiltered({
      q: 'term',
      limit: 25,
      starredOnly: true,
      includeArchived: true,
      dateRange: 'week',
      states: ['today', 'later'],
      categories: ['ai-llm'],
      sources: ['src'],
    });
    expect(items).toHaveLength(1);
    const url = calls[0].url;
    expect(url).toContain('q=term');
    expect(url).toContain('limit=25');
    expect(url).toContain('starred_only=true');
    expect(url).toContain('include_archived=true');
    expect(url).toContain('date_range=week');
    expect(url).toContain('states=today');
    expect(url).toContain('states=later');
    expect(url).toContain('categories=ai-llm');
    expect(url).toContain('sources=src');
  });

  it('omits date_range when set to all', async () => {
    const { calls } = stubFetch(() => jsonOk({ items: [] }));
    await searchArticlesFiltered({ q: 'x', dateRange: 'all' });
    expect(calls[0].url).not.toContain('date_range');
  });
});
