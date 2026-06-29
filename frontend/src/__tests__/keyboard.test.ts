// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useArticleListNav } from '../hooks/useArticleListNav';
import type { useTriageMutations } from '../hooks/useTriageMutations';
import type { WorkflowArticle } from '../lib/workflowTypes';

type Mutations = ReturnType<typeof useTriageMutations>;

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: overrides.id ?? '1',
    title: overrides.title ?? 'Test article',
    sourceId: 'src',
    sourceName: 'Source',
    category: 'ai-llm',
    url: 'https://example.com/1',
    publishedAt: '2024-01-01T10:00:00Z',
    ingestedAt: '2024-01-01T11:00:00Z',
    reason: 'Reason',
    summary: 'Summary',
    signal: 'high',
    tags: [],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function makeMutations(): Mutations {
  return {
    setState: vi.fn(),
    toggleStar: vi.fn(),
    sendLater: vi.fn(),
  };
}

function fireKey(key: string, init: KeyboardEventInit = {}) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
}

// ─── useArticleListNav — j/k navigation ──────────────────────────────────────

describe('useArticleListNav — j/k navigation', () => {
  const articles = [makeArticle({ id: '1' }), makeArticle({ id: '2' }), makeArticle({ id: '3' })];

  it('starts at index 0', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    expect(result.current.focused).toBe(0);
  });

  it('j moves focus down', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    act(() => fireKey('j'));
    expect(result.current.focused).toBe(1);
  });

  it('k moves focus up', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    act(() => {
      fireKey('j');
      fireKey('j');
    });
    expect(result.current.focused).toBe(2);
    act(() => fireKey('k'));
    expect(result.current.focused).toBe(1);
  });

  it('j does not go past the last item', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    act(() => {
      fireKey('j');
      fireKey('j');
      fireKey('j');
      fireKey('j');
    });
    expect(result.current.focused).toBe(2);
  });

  it('k does not go below 0', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    act(() => fireKey('k'));
    expect(result.current.focused).toBe(0);
  });

  it('ignores modified navigation keys', () => {
    const { result } = renderHook(() => useArticleListNav(articles, vi.fn(), makeMutations()));
    act(() => fireKey('j', { metaKey: true }));
    act(() => fireKey('j', { ctrlKey: true }));
    act(() => fireKey('j', { altKey: true }));
    expect(result.current.focused).toBe(0);
  });
});

// ─── useArticleListNav — action keys ─────────────────────────────────────────

describe('useArticleListNav — action keys', () => {
  let mutations: Mutations;
  const article = makeArticle({ id: '42' });
  const articles = [article];

  beforeEach(() => {
    mutations = makeMutations();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('r marks article done', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('r'));
    expect(mutations.setState).toHaveBeenCalledWith(article, 'done', 'Done');
  });

  it('d marks article done', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('d'));
    expect(mutations.setState).toHaveBeenCalledWith(article, 'done', 'Done');
  });

  it('l sends to later', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('l'));
    expect(mutations.sendLater).toHaveBeenCalledWith(article);
  });

  it('s toggles star', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('s'));
    expect(mutations.toggleStar).toHaveBeenCalledWith(article);
  });

  it('x skips unstarred article', () => {
    const unstarred = makeArticle({ starred: false });
    renderHook(() => useArticleListNav([unstarred], vi.fn(), mutations));
    act(() => fireKey('x'));
    expect(mutations.setState).toHaveBeenCalledWith(unstarred, 'skipped', 'Skipped');
  });

  it('x is inert on starred article', () => {
    const starred = makeArticle({ starred: true });
    renderHook(() => useArticleListNav([starred], vi.fn(), mutations));
    act(() => fireKey('x'));
    expect(mutations.setState).not.toHaveBeenCalled();
  });

  it('e archives article', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('e'));
    expect(mutations.setState).toHaveBeenCalledWith(article, 'archived', 'Archived');
  });

  it('o opens original URL in new tab with noopener,noreferrer', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('o'));
    expect(openSpy).toHaveBeenCalledWith(article.url, '_blank', 'noopener,noreferrer');
  });

  it('Enter calls openArticle', () => {
    const openArticle = vi.fn();
    renderHook(() => useArticleListNav(articles, openArticle, mutations));
    act(() => fireKey('Enter'));
    expect(openArticle).toHaveBeenCalledWith(article);
  });

  it('ignores modified action keys', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    act(() => fireKey('s', { altKey: true }));
    act(() => fireKey('r', { ctrlKey: true }));
    act(() => fireKey('o', { metaKey: true }));
    expect(mutations.toggleStar).not.toHaveBeenCalled();
    expect(mutations.setState).not.toHaveBeenCalled();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('ignores keys when target is an INPUT', () => {
    renderHook(() => useArticleListNav(articles, vi.fn(), mutations));
    const input = document.createElement('input');
    document.body.appendChild(input);
    void act(() => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', bubbles: true })));
    expect(mutations.setState).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });
});
