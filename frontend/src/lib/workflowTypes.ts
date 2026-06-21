export type WorkflowState = 'today' | 'later' | 'done' | 'skipped' | 'archived';

export type Signal = 'high' | 'mid' | 'low';

/**
 * Per-factor recommendation breakdown persisted alongside the blended score.
 * Each `*_adjustment` is the signed point contribution that factor made to the
 * final score; fields are optional because older rows or cold-start scoring may
 * omit factors that did not apply.
 */
export interface RecommendationSignals {
  base_score?: number;
  affinity_adjustment?: number;
  semantic_adjustment?: number;
  freshness_adjustment?: number;
  novelty_adjustment?: number;
  source_slug?: string | null;
  category?: string | null;
}

export interface WorkflowArticle {
  id: string;
  title: string;
  sourceId: string;
  sourceName: string;
  category: string;
  url: string;
  publishedAt: string;
  ingestedAt: string;
  reason: string;
  summary: string;
  signal: Signal;
  /** Per-user recommendation score (0–100); undefined when not yet ranked. */
  recommendationScore?: number;
  /** Model version that produced the score; undefined when not yet ranked. */
  recommendationModel?: string;
  /** Per-factor breakdown powering on-demand explanations; undefined when unranked. */
  recommendationSignals?: RecommendationSignals;
  tags: string[];
  body?: string;
  bodyStatus: 'ok' | 'missing' | 'error';
  state: WorkflowState;
  starred: boolean;
  done_at?: string;
  skipped_at?: string;
  archived_at?: string;
  starred_at?: string;
  later_until?: string;
  restored_at?: string;
}

export interface UndoSnapshot {
  article: WorkflowArticle;
}
