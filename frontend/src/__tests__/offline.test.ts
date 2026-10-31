// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getOfflineArticle,
  cacheArticleBodies,
  isArticleSavedOffline,
  listOfflineArticles,
  removeOfflineArticle,
  saveOfflineArticle,
} from '../lib/offline';

import { changePrivateSession } from '../lib/privateSession';

const addedUrls: string[] = [];
const deletedUrls: string[] = [];

beforeEach(() => {
  window.localStorage.clear();
  void changePrivateSession(1);
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      addedUrls.push(url);
      return Promise.resolve(new Response('{}'));
    })
  );
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
  vi.unstubAllGlobals();
});

describe('offline article index', () => {
  it('forgets metadata on logout and denies anonymous saves', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Private A',
      source: 'A',
      url: 'https://example.com',
    });
    await changePrivateSession(null);
    expect(listOfflineArticles()).toEqual([]);
    expect(localStorage.getItem('offline-articles:index:v1')).toBeNull();
    await expect(
      saveOfflineArticle({ id: 42, title: 'A', source: 'A', url: '' })
    ).rejects.toThrow();
  });

  it('does not resurrect the index when a manual save finishes after switching account', async () => {
    let release!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    const save = saveOfflineArticle({ id: 42, title: 'Private A', source: 'A', url: '' });
    const rejected = expect(save).rejects.toThrow();
    await changePrivateSession(null);
    await changePrivateSession(2);
    release(new Response('{}'));
    await rejected;
    expect(listOfflineArticles()).toEqual([]);
  });

  it('stops the background queue when logout happens during a fetch', async () => {
    let release!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    const queue = cacheArticleBodies([1, 2, 3]);
    await changePrivateSession(null);
    release(new Response('{}'));
    expect(await queue).toBe(0);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
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
