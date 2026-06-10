/**
 * Workflow API layer for #78 triage queue views.
 *
 * Adapter maps the current API (status: new/read/saved/skipped/archived) to the
 * new workflow model (state: today/later/done/skipped/archived + starred flag).
 *
 * Missing backend capabilities (sticky starred, later_until persistence) require
 * issue #87. Until then: starred is proxied via status=saved, later is client-only.
 */

import type { Article as LegacyArticle, ArticleStatus } from '../types';
import type { WorkflowArticle, WorkflowState, Signal, UndoSnapshot } from '../lib/workflowTypes';
import { fetchArticles, updateArticleStatus } from '../api';

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
    case 'new':
      return 'today';
    case 'read':
      return 'done';
    case 'saved':
      // saved is used as starred proxy; articles appear in Today with starred=true
      return 'today';
    case 'skipped':
      return 'skipped';
    case 'archived':
      return 'archived';
    default:
      return 'today';
  }
}

export function adaptArticle(a: LegacyArticle): WorkflowArticle {
  return {
    id: String(a.id),
    title: a.title,
    sourceId: a.source_name,
    sourceName: a.source_name,
    category: a.category,
    url: a.url,
    publishedAt: a.published_at ?? a.discovered_at,
    ingestedAt: a.discovered_at,
    reason: a.reason,
    summary: a.summary,
    signal: scoreToSignal(a.importance_score),
    tags: parseTags(a.tags),
    body: undefined,
    bodyStatus: 'missing',
    state: legacyStatusToState(a.status),
    starred: a.status === 'saved',
    done_at: a.read_at ?? undefined,
    skipped_at: a.skipped_at ?? undefined,
    archived_at: a.archived_at ?? undefined,
    starred_at: a.saved_at ?? undefined,
    later_until: undefined,
    restored_at: undefined,
  };
}

// ─── Queries ────────────────────────────────────────────────────────────────

type TriageView = 'today' | 'later' | 'starred' | 'archived';

const VIEW_STATUS: Record<Exclude<TriageView, 'later'>, ArticleStatus> = {
  today: 'new',
  starred: 'saved',
  archived: 'archived',
};

export async function fetchTriageArticles(
  view: TriageView,
  category?: string
): Promise<WorkflowArticle[]> {
  // Later has no backend support until #87 — return empty list
  if (view === 'later') return [];

  const status = VIEW_STATUS[view];
  const articles = await fetchArticles(status, category ?? undefined);
  return articles.map(adaptArticle);
}

// ─── Mutations ──────────────────────────────────────────────────────────────

function stateToLegacyStatus(state: WorkflowState, wasStarred: boolean): ArticleStatus {
  switch (state) {
    case 'today':
      return wasStarred ? 'saved' : 'new';
    case 'done':
      return 'read';
    case 'skipped':
      return 'skipped';
    case 'archived':
      return 'archived';
    case 'later':
      // No backend support; caller handles optimistic-only
      return 'new';
    default:
      return 'new';
  }
}

/** PATCH the article's state. Returns updated article or throws. */
export async function patchArticleState(
  id: string,
  newState: WorkflowState,
  wasStarred: boolean
): Promise<void> {
  const legacyStatus = stateToLegacyStatus(newState, wasStarred);
  await updateArticleStatus(Number(id), legacyStatus);
}

/** Toggle star. Proxied via status=saved until #87. */
export async function patchArticleStar(id: string, starred: boolean): Promise<void> {
  // starring → saved; unstarring → new (lossy — original pre-star state is lost)
  const legacyStatus: ArticleStatus = starred ? 'saved' : 'new';
  await updateArticleStatus(Number(id), legacyStatus);
}

/** Build a snapshot for undo from a WorkflowArticle. */
export function snapshot(article: WorkflowArticle): UndoSnapshot {
  return { article: { ...article } };
}

export { VIEW_STATUS };
