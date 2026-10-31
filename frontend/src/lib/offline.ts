import { privateSessionEpoch } from './privateSession';

const OFFLINE_ARTICLE_CACHE = 'nd-private-v2-';
const OFFLINE_ARTICLE_INDEX_KEY = 'offline-articles:index:v1';

export interface OfflineArticle {
  id: string;
  title: string;
  source: string;
  url: string;
  savedAt: string;
  bodyCacheKey: string;
}

export interface OfflineArticleInput {
  id: string | number;
  title: string;
  source: string;
  url: string;
}

export function isOfflineCacheSupported(): boolean {
  return typeof window !== 'undefined' && 'caches' in window;
}

function articleBodyCacheKey(articleId: string | number): string {
  return `/api/articles/${articleId}/body`;
}

function readOfflineArticleIndex(): OfflineArticle[] {
  if (typeof window === 'undefined' || !privateSessionEpoch()) return [];
  const raw = window.localStorage.getItem(OFFLINE_ARTICLE_INDEX_KEY);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isOfflineArticle);
  } catch {
    return [];
  }
}

function writeOfflineArticleIndex(articles: OfflineArticle[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(OFFLINE_ARTICLE_INDEX_KEY, JSON.stringify(articles));
}

function isOfflineArticle(value: unknown): value is OfflineArticle {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<Record<keyof OfflineArticle, unknown>>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.title === 'string' &&
    typeof candidate.source === 'string' &&
    typeof candidate.url === 'string' &&
    typeof candidate.savedAt === 'string' &&
    typeof candidate.bodyCacheKey === 'string'
  );
}

export async function cacheArticleBody(articleId: string | number): Promise<void> {
  if (!isOfflineCacheSupported()) return;
  const epoch = privateSessionEpoch();
  if (!epoch) throw new Error('Sign in again to save articles offline');
  // The service worker owns cache writes and fences them against session revocation.
  const response = await fetch(articleBodyCacheKey(articleId), { credentials: 'same-origin' });
  if (!response.ok || privateSessionEpoch() !== epoch) throw new Error('Offline save unavailable');
}

export async function cacheArticleBodies(articleIds: (string | number)[]): Promise<number> {
  if (!isOfflineCacheSupported()) return 0;
  const epoch = privateSessionEpoch();
  if (!epoch) return 0;
  let cached = 0;
  for (const articleId of articleIds) {
    try {
      if (privateSessionEpoch() !== epoch) break;
      await cacheArticleBody(articleId);
      cached += 1;
    } catch {
      // Keep caching the rest of the queue when one article body is unavailable.
    }
  }
  return cached;
}

export function listOfflineArticles(): OfflineArticle[] {
  return readOfflineArticleIndex().sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

export function getOfflineArticle(articleId: string | number): OfflineArticle | null {
  const id = String(articleId);
  return readOfflineArticleIndex().find((article) => article.id === id) ?? null;
}

export function isArticleSavedOffline(articleId: string | number): boolean {
  return getOfflineArticle(articleId) !== null;
}

export async function saveOfflineArticle(input: OfflineArticleInput): Promise<OfflineArticle> {
  const epoch = privateSessionEpoch();
  await cacheArticleBody(input.id);
  if (!epoch || privateSessionEpoch() !== epoch) throw new Error('Session changed');
  const id = String(input.id);
  const existing = getOfflineArticle(id);
  if (existing) return existing;
  const saved: OfflineArticle = {
    id,
    title: input.title,
    source: input.source,
    url: input.url,
    savedAt: new Date().toISOString(),
    bodyCacheKey: articleBodyCacheKey(input.id),
  };
  writeOfflineArticleIndex([
    saved,
    ...readOfflineArticleIndex().filter((article) => article.id !== id),
  ]);
  return saved;
}

export async function removeOfflineArticle(articleId: string | number): Promise<void> {
  const id = String(articleId);
  const existing = getOfflineArticle(id);
  const epoch = privateSessionEpoch();
  if (isOfflineCacheSupported() && epoch) {
    const cache = await caches.open(OFFLINE_ARTICLE_CACHE + epoch + '-bodies');
    await cache.delete(existing?.bodyCacheKey ?? articleBodyCacheKey(id));
  }
  writeOfflineArticleIndex(readOfflineArticleIndex().filter((article) => article.id !== id));
}
