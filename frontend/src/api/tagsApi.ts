/** API layer for user-defined tags/collections (#652). */

import { requestJson } from '../api';
import { adaptArticle } from './workflowApi';
import type { Article as LegacyArticle } from '../types';
import type { TriageArticlePage } from './workflowApi';

export interface UserTag {
  id: number;
  user_id: number;
  name: string;
  color: string | null;
  created_at: string;
  article_count?: number;
}

interface TagListResponse {
  items: UserTag[];
}

interface ArticleTagApiPage {
  items: LegacyArticle[];
  limit?: number;
  offset?: number;
  has_more?: boolean;
}

export async function fetchTags(): Promise<UserTag[]> {
  const data = await requestJson<TagListResponse>('/api/tags');
  return data.items;
}

export async function createTag(name: string, color?: string): Promise<UserTag> {
  return requestJson<UserTag>('/api/tags', {
    method: 'POST',
    body: JSON.stringify({ name, color: color ?? null }),
  });
}

export async function renameTag(tagId: number, name: string): Promise<UserTag> {
  return requestJson<UserTag>(`/api/tags/${tagId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export async function deleteTag(tagId: number): Promise<void> {
  await requestJson(`/api/tags/${tagId}`, { method: 'DELETE' });
}

export async function fetchArticleTags(articleId: string | number): Promise<UserTag[]> {
  const data = await requestJson<TagListResponse>(`/api/articles/${articleId}/tags`);
  return data.items;
}

export async function addArticleTag(articleId: string | number, tagId: number): Promise<void> {
  await requestJson(`/api/articles/${articleId}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag_id: tagId }),
  });
}

export async function removeArticleTag(articleId: string | number, tagId: number): Promise<void> {
  await requestJson(`/api/articles/${articleId}/tags/${tagId}`, { method: 'DELETE' });
}

export async function fetchArticlesByTag(
  tagId: number,
  options: { limit?: number; offset?: number } = {}
): Promise<TriageArticlePage> {
  const params = new URLSearchParams();
  if (options.limit) params.set('limit', String(options.limit));
  if (options.offset) params.set('offset', String(options.offset));
  const suffix = params.size ? `?${params}` : '';
  const data = await requestJson<ArticleTagApiPage>(`/api/tags/${tagId}/articles${suffix}`);
  return {
    items: data.items.map(adaptArticle),
    limit: data.limit ?? options.limit ?? data.items.length,
    offset: data.offset ?? options.offset ?? 0,
    hasMore: Boolean(data.has_more),
  };
}
