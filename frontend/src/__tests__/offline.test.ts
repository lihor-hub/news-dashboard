// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getOfflineArticle,
  isArticleSavedOffline,
  listOfflineArticles,
  removeOfflineArticle,
  saveOfflineArticle,
} from '../lib/offline';

const addedUrls: string[] = [];
const deletedUrls: string[] = [];

beforeEach(() => {
  window.localStorage.clear();
  addedUrls.length = 0;
  deletedUrls.length = 0;
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-07-08T09:30:00Z'));
  Object.defineProperty(window, 'caches', {
    configurable: true,
    value: {
      open: vi.fn().mockResolvedValue({
        add: vi.fn((url: string) => {
          addedUrls.push(url);
          return Promise.resolve();
        }),
        delete: vi.fn((url: string) => {
          deletedUrls.push(url);
          return Promise.resolve(true);
        }),
      }),
    },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('offline article index', () => {
  it('records metadata after caching an article body', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Offline title',
      source: 'Example Feed',
      url: 'https://example.com/article',
    });

    expect(addedUrls).toEqual(['/api/articles/42/body']);
    expect(listOfflineArticles()).toEqual([
      {
        id: '42',
        title: 'Offline title',
        source: 'Example Feed',
        url: 'https://example.com/article',
        savedAt: '2026-07-08T09:30:00.000Z',
        bodyCacheKey: '/api/articles/42/body',
      },
    ]);
    expect(isArticleSavedOffline(42)).toBe(true);
  });

  it('does not duplicate existing saves', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Offline title',
      source: 'Example Feed',
      url: 'https://example.com/article',
    });
    await saveOfflineArticle({
      id: 42,
      title: 'Changed title',
      source: 'Other Feed',
      url: 'https://example.com/other',
    });

    expect(listOfflineArticles()).toHaveLength(1);
    expect(getOfflineArticle(42)?.title).toBe('Offline title');
  });

  it('removes the local index entry and cached body', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Offline title',
      source: 'Example Feed',
      url: 'https://example.com/article',
    });

    await removeOfflineArticle(42);

    expect(listOfflineArticles()).toEqual([]);
    expect(deletedUrls).toEqual(['/api/articles/42/body']);
  });
});
