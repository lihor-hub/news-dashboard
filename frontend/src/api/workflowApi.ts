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
    tags: parseTags(a.tags),
    body: a.body ?? undefined,
    bodyStatus: a.body_status ?? 'missing',
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

export async function fetchTriageArticles(
  view: TriageView,
  category?: string
): Promise<WorkflowArticle[]> {
  const params = new URLSearchParams();
  if (view === 'starred') {
    params.set('starred', 'true');
  } else {
    params.set('state', view);
  }
  if (category) params.set('category', category);
  const suffix = params.size ? `?${params}` : '';
  const data = await requestJson<{ items: LegacyArticle[] }>(`/api/articles${suffix}`);
  return data.items.map(adaptArticle);
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
