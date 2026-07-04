import type { Article, ArticleHighlight, ArticleStatus, TopicMapResponse } from '../types';
import { readErrorMessage, requestJson } from './core';

export async function fetchArticles(
  status?: ArticleStatus,
  category?: string,
  offset = 0,
  limit = 100
): Promise<Article[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (category) params.set('category', category);
  if (offset > 0) params.set('offset', String(offset));
  if (limit !== 100) params.set('limit', String(limit));
  const suffix = params.size ? `?${params}` : '';
  const data = await requestJson<{ items: Article[] }>(`/api/articles${suffix}`);
  return data.items;
}

export async function searchArticles(q: string, limit = 50): Promise<Article[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const data = await requestJson<{ items: Article[] }>(`/api/search?${params}`);
  return data.items;
}

export async function fetchArticle(id: number | string): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}`);
}

export async function fetchArticleBody(id: number | string): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}/body`);
}

export async function saveSharedUrl(payload: {
  url: string;
  title?: string | null;
  text?: string | null;
}): Promise<Article> {
  return requestJson<Article>('/api/articles/save-url', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchArticleHighlights(id: number | string): Promise<ArticleHighlight[]> {
  const data = await requestJson<{ items: ArticleHighlight[] }>(`/api/articles/${id}/highlights`);
  return data.items;
}

export async function createArticleHighlight(
  id: number | string,
  payload: { highlighted_text: string; offset_chars?: number; note?: string | null }
): Promise<ArticleHighlight> {
  return requestJson<ArticleHighlight>(`/api/articles/${id}/highlights`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteArticleHighlight(
  articleId: number | string,
  highlightId: number | string
): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/articles/${articleId}/highlights/${highlightId}`, {
    method: 'DELETE',
  });
}

export async function fetchSharedArticle(shareId: number | string): Promise<Article> {
  return requestJson<Article>(`/api/shares/${shareId}/article`);
}

export async function fetchSharedArticleBody(shareId: number | string): Promise<Article> {
  return requestJson<Article>(`/api/shares/${shareId}/article/body`, { method: 'POST' });
}

export async function fetchArticleAudioUrl(id: number | string): Promise<string> {
  const response = await fetch(`/api/articles/${id}/audio`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function fetchArticleInsights(id: number | string): Promise<string[]> {
  const data = await requestJson<{ bullets: string[] }>(`/api/articles/${id}/insights`);
  return data.bullets;
}

export interface PerspectiveAnalysis {
  verified_facts: string[];
  omissions: string[];
  alternative_perspectives: string[];
}

export async function fetchArticlePerspectives(id: number | string): Promise<PerspectiveAnalysis> {
  return requestJson<PerspectiveAnalysis>(`/api/articles/${id}/perspectives`);
}

export async function updateArticleStatus(id: number, status: ArticleStatus): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export async function fetchTopicMap(): Promise<TopicMapResponse> {
  return requestJson<TopicMapResponse>('/api/articles/topic-map');
}
