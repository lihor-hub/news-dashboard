/**
 * Workflow API layer — backed by the #87 state model.
 *
 * The backend now exposes state/starred/later_until directly.
 * This adapter maps snake_case API fields to WorkflowArticle.
 */

import type { Article as LegacyArticle, ArticleStatus } from '../types';
import type { WorkflowArticle, WorkflowState, Signal, UndoSnapshot } from '../lib/workflowTypes';
import { requestJson } from '../api';

// ─── Adapter ────────────────────────────────────────────────────────────────

function parseTags(raw: string): string[] {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) return (parsed as unknown[]).map(String);
  } catch {
    // fall through
  }
  return raw
    ? raw
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
    : [];
}

function scoreToSignal(score: number): Signal {
  if (score >= 0.7) return 'high';
  if (score >= 0.4) return 'mid';
  return 'low';
}

function legacyStatusToState(status: ArticleStatus): WorkflowState {
  switch (status) {
    case 'read':
      return 'done';
    case 'skipped':
      return 'skipped';
    case 'archived':
      return 'archived';
    default:
      return 'today';
  }
}

export function adaptArticle(a: LegacyArticle): WorkflowArticle {
  const state: WorkflowState = a.state ?? legacyStatusToState(a.status);
  const starred = a.state != null ? Boolean(a.starred) : a.status === 'saved';
  const starred_at = a.starred_at ?? (a.status === 'saved' ? (a.saved_at ?? undefined) : undefined);
  const done_at = a.done_at ?? (a.status === 'read' ? (a.read_at ?? undefined) : undefined);

  return {
    id: String(a.id),
    title: a.title,
    sourceId: a.source_slug ?? a.source_name,
    sourceName: a.source_name,
    category: a.category,
    url: a.url,
    publishedAt: a.published_at ?? a.discovered_at,
    ingestedAt: a.discovered_at,
    reason: a.reason,
    summary: a.summary,
    signal: scoreToSignal(a.importance_score),
    recommendationScore: a.recommendation_score ?? undefined,
    recommendationModel: a.recommendation_model ?? undefined,
    recommendationSignals: a.recommendation_signals ?? undefined,
    recommendationExplanation: a.recommendation_explanation ?? undefined,
    tags: parseTags(a.tags),
    body: a.body ?? undefined,
    bodyStatus: a.body_status ?? 'missing',
    originalTitle: a.original_title ?? undefined,
    originalBody: a.original_body ?? undefined,
    detectedLang: a.detected_lang ?? undefined,
    state,
    starred,
    done_at,
    skipped_at: a.skipped_at ?? undefined,
    archived_at: a.archived_at ?? undefined,
    starred_at,
    later_until: a.later_until ?? undefined,
    restored_at: a.restored_at ?? undefined,
  };
}

// ─── Queries ────────────────────────────────────────────────────────────────

type TriageView = 'today' | 'later' | 'starred' | 'archived';

export interface TriageArticlePage {
  items: WorkflowArticle[];
  limit: number;
  offset: number;
  hasMore: boolean;
}

interface TriageArticleApiPage {
  items: LegacyArticle[];
  limit?: number;
  offset?: number;
  has_more?: boolean;
}

export async function fetchTriageArticles(
  view: TriageView,
  category?: string,
  options: { limit?: number; offset?: number } = {}
): Promise<TriageArticlePage> {
  const params = new URLSearchParams();
  if (view === 'starred') {
    params.set('starred', 'true');
  } else {
    params.set('state', view);
  }
  if (category) params.set('category', category);
  if (options.limit) params.set('limit', String(options.limit));
  if (options.offset) params.set('offset', String(options.offset));
  const suffix = params.size ? `?${params}` : '';
  const data = await requestJson<TriageArticleApiPage>(`/api/articles${suffix}`);
  return {
    items: data.items.map(adaptArticle),
    limit: data.limit ?? options.limit ?? data.items.length,
    offset: data.offset ?? options.offset ?? 0,
    hasMore: Boolean(data.has_more),
  };
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** PATCH the article's workflow state. */
export async function patchArticleState(
  id: string,
  newState: WorkflowState,
  _wasStarred: boolean
): Promise<void> {
  await requestJson(`/api/articles/${id}/state`, {
    method: 'PATCH',
    body: JSON.stringify({ state: newState }),
  });
}

/** PATCH the article's later_until snooze date. */
export async function patchArticleLater(id: string, days = 1): Promise<void> {
  await requestJson(`/api/articles/${id}/later`, {
    method: 'PATCH',
    body: JSON.stringify({ days }),
  });
}

/** PATCH the article's starred flag. */
export async function patchArticleStar(id: string, starred: boolean): Promise<void> {
  await requestJson(`/api/articles/${id}/star`, {
    method: 'PATCH',
    body: JSON.stringify({ starred }),
  });
}

/** Build a snapshot for undo from a WorkflowArticle. */
export function snapshot(article: WorkflowArticle): UndoSnapshot {
  return { article: { ...article } };
}

// ─── Search ─────────────────────────────────────────────────────────────────

export interface SearchFilters {
  q?: string;
  states?: WorkflowState[];
  categories?: string[];
  sources?: string[];
  starredOnly?: boolean;
  includeArchived?: boolean;
  dateRange?: 'all' | 'today' | 'week' | 'month';
  tagId?: number;
  limit?: number;
  offset?: number;
}

export interface SearchArticlePage {
  items: WorkflowArticle[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

interface SearchArticleApiPage {
  items: LegacyArticle[];
  total?: number;
  limit?: number;
  offset?: number;
  has_more?: boolean;
}

export async function searchArticlesFiltered(filters: SearchFilters): Promise<SearchArticlePage> {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.limit) params.set('limit', String(filters.limit));
  if (filters.offset) params.set('offset', String(filters.offset));
  if (filters.starredOnly) params.set('starred_only', 'true');
  if (filters.includeArchived) params.set('include_archived', 'true');
  if (filters.dateRange && filters.dateRange !== 'all') params.set('date_range', filters.dateRange);
  if (filters.tagId != null) params.set('tag_id', String(filters.tagId));
  filters.states?.forEach((s) => params.append('states', s));
  filters.categories?.forEach((c) => params.append('categories', c));
  filters.sources?.forEach((s) => params.append('sources', s));

  const data = await requestJson<SearchArticleApiPage>(`/api/search?${params}`);
  return {
    items: data.items.map(adaptArticle),
    total: data.total ?? data.items.length,
    limit: data.limit ?? filters.limit ?? data.items.length,
    offset: data.offset ?? filters.offset ?? 0,
    hasMore: Boolean(data.has_more),
  };
}
