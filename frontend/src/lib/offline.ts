const OFFLINE_ARTICLE_CACHE = 'offline-articles-v1';

export function isOfflineCacheSupported(): boolean {
  return typeof window !== 'undefined' && 'caches' in window;
}

export async function cacheArticleBody(articleId: string | number): Promise<void> {
  if (!isOfflineCacheSupported()) return;
  const cache = await caches.open(OFFLINE_ARTICLE_CACHE);
  await cache.add(`/api/articles/${articleId}/body`);
}

export async function cacheArticleBodies(articleIds: (string | number)[]): Promise<number> {
  if (!isOfflineCacheSupported()) return 0;
  const cache = await caches.open(OFFLINE_ARTICLE_CACHE);
  let cached = 0;
  for (const articleId of articleIds) {
    try {
      await cache.add(`/api/articles/${articleId}/body`);
      cached += 1;
    } catch {
      // Keep caching the rest of the queue when one article body is unavailable.
    }
  }
  return cached;
}
