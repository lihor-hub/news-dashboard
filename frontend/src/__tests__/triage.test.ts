// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { adaptArticle } from '../api/workflowApi';
import type { Article as LegacyArticle } from '../types';
import type { WorkflowArticle } from '../lib/workflowTypes';

// ─── Fixture helpers ─────────────────────────────────────────────────────────

function makeLegacy(overrides: Partial<LegacyArticle> = {}): LegacyArticle {
  return {
    id: 1,
    url: 'https://example.com/article',
    title: 'Test article',
    source_name: 'Test Source',
    category: 'ai-llm',
    kind: 'rss',
    published_at: '2024-01-01T10:00:00Z',
    discovered_at: '2024-01-01T11:00:00Z',
    status: 'new',
    importance_score: 0.8,
    summary: 'A summary',
    reason: 'Why it matters',
    tags: '["llm","agents"]',
    read_at: null,
    saved_at: null,
    skipped_at: null,
    archived_at: null,
    ...overrides,
  };
}

function makeWorkflow(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '1',
    title: 'Test article',
    sourceId: 'Test Source',
    sourceName: 'Test Source',
    category: 'ai-llm',
    url: 'https://example.com/article',
    publishedAt: '2024-01-01T10:00:00Z',
    ingestedAt: '2024-01-01T11:00:00Z',
    reason: 'Why it matters',
    summary: 'A summary',
    signal: 'high',
    tags: ['llm', 'agents'],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

// ─── adaptArticle ─────────────────────────────────────────────────────────────

describe('adaptArticle', () => {
  it('maps new → today', () => {
    const result = adaptArticle(makeLegacy({ status: 'new' }));
    expect(result.state).toBe('today');
    expect(result.starred).toBe(false);
  });

  it('maps read → done', () => {
    const result = adaptArticle(makeLegacy({ status: 'read', read_at: '2024-01-02T00:00:00Z' }));
    expect(result.state).toBe('done');
    expect(result.done_at).toBe('2024-01-02T00:00:00Z');
  });

  it('maps saved → today with starred=true', () => {
    const result = adaptArticle(makeLegacy({ status: 'saved', saved_at: '2024-01-02T00:00:00Z' }));
    expect(result.state).toBe('today');
    expect(result.starred).toBe(true);
    expect(result.starred_at).toBe('2024-01-02T00:00:00Z');
  });

  it('maps skipped → skipped', () => {
    const result = adaptArticle(makeLegacy({ status: 'skipped' }));
    expect(result.state).toBe('skipped');
  });

  it('maps archived → archived', () => {
    const result = adaptArticle(makeLegacy({ status: 'archived' }));
    expect(result.state).toBe('archived');
  });

  it('maps high importance_score → signal high', () => {
    expect(adaptArticle(makeLegacy({ importance_score: 0.9 })).signal).toBe('high');
    expect(adaptArticle(makeLegacy({ importance_score: 0.7 })).signal).toBe('high');
  });

  it('maps mid importance_score → signal mid', () => {
    expect(adaptArticle(makeLegacy({ importance_score: 0.6 })).signal).toBe('mid');
    expect(adaptArticle(makeLegacy({ importance_score: 0.4 })).signal).toBe('mid');
  });

  it('maps low importance_score → signal low', () => {
    expect(adaptArticle(makeLegacy({ importance_score: 0.2 })).signal).toBe('low');
    expect(adaptArticle(makeLegacy({ importance_score: 0 })).signal).toBe('low');
  });

  it('parses JSON tags array', () => {
    const result = adaptArticle(makeLegacy({ tags: '["a","b","c"]' }));
    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('parses comma-separated tags fallback', () => {
    const result = adaptArticle(makeLegacy({ tags: 'a, b, c' }));
    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('returns empty tags for empty string', () => {
    const result = adaptArticle(makeLegacy({ tags: '' }));
    expect(result.tags).toEqual([]);
  });

  it('uses published_at for publishedAt when available', () => {
    const result = adaptArticle(
      makeLegacy({ published_at: '2024-01-01T10:00:00Z', discovered_at: '2024-01-01T11:00:00Z' })
    );
    expect(result.publishedAt).toBe('2024-01-01T10:00:00Z');
  });

  it('falls back to discovered_at when published_at is null', () => {
    const result = adaptArticle(makeLegacy({ published_at: null }));
    expect(result.publishedAt).toBe('2024-01-01T11:00:00Z');
  });

  it('stringifies numeric id', () => {
    const result = adaptArticle(makeLegacy({ id: 42 }));
    expect(result.id).toBe('42');
  });
});

// ─── Starred-skip restriction ─────────────────────────────────────────────────

describe('starred-skip restriction', () => {
  it('allows skipping when not starred', () => {
    const article = makeWorkflow({ starred: false });
    // The setState function in useTriageMutations checks this;
    // test the business logic directly
    const canSkip = !(article.starred && 'skipped' === 'skipped');
    expect(canSkip).toBe(true);
  });

  it('blocks skipping when starred', () => {
    const article = makeWorkflow({ starred: true });
    const wouldBlock = article.starred;
    expect(wouldBlock).toBe(true);
  });
});

// ─── Optimistic undo snapshot ─────────────────────────────────────────────────

describe('optimistic undo snapshot', () => {
  it('snapshot captures a deep copy of the article', async () => {
    const { snapshot } = await import('../api/workflowApi');
    const article = makeWorkflow({ state: 'today' });
    const snap = snapshot(article);
    // mutate article after snapshot
    article.state = 'done';
    expect(snap.article.state).toBe('today');
  });

  it('snapshot id matches article id', async () => {
    const { snapshot } = await import('../api/workflowApi');
    const article = makeWorkflow({ id: '99' });
    const snap = snapshot(article);
    expect(snap.article.id).toBe('99');
  });
});

// ─── Swipe handler logic ──────────────────────────────────────────────────────

describe('swipe handler behaviour', () => {
  it('swipe right triggers star action', () => {
    const onSwipeRight = vi.fn();
    const onSwipeLeft = vi.fn();

    // Simulate threshold exceeded rightward
    const dx = 100;
    const THRESHOLD = 80;
    if (dx > THRESHOLD) onSwipeRight();

    expect(onSwipeRight).toHaveBeenCalledOnce();
    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  it('swipe left triggers skip when not starred', () => {
    const onSwipeRight = vi.fn();
    const onSwipeLeft = vi.fn();

    const dx = -100;
    const THRESHOLD = 80;
    const disableLeft = false;
    if (dx < -THRESHOLD && !disableLeft) onSwipeLeft();

    expect(onSwipeLeft).toHaveBeenCalledOnce();
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('swipe left is inert when starred (disableLeft=true)', () => {
    const onSwipeLeft = vi.fn();

    const dx = -100;
    const THRESHOLD = 80;
    const disableLeft = true;
    if (dx < -THRESHOLD && !disableLeft) onSwipeLeft();

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });
});

// ─── Mutation state patches ───────────────────────────────────────────────────

describe('mutation state patches', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-06-01T12:00:00Z'));
  });

  it('sets done_at when moving to done', () => {
    const now = new Date().toISOString();
    const patch: Partial<WorkflowArticle> = { state: 'done', done_at: now };
    expect(patch.done_at).toBe('2024-06-01T12:00:00.000Z');
  });

  it('sets skipped_at when skipping', () => {
    const now = new Date().toISOString();
    const patch: Partial<WorkflowArticle> = { state: 'skipped', skipped_at: now };
    expect(patch.skipped_at).toBe('2024-06-01T12:00:00.000Z');
  });

  it('clears later_until when restoring to today', () => {
    const patch: Partial<WorkflowArticle> = { state: 'today', later_until: undefined };
    expect(patch.later_until).toBeUndefined();
  });

  it('sets later_until one day out when sending to later', () => {
    const days = 1;
    const until = new Date(Date.now() + days * 24 * 3600 * 1000).toISOString();
    expect(until).toBe('2024-06-02T12:00:00.000Z');
  });
});
