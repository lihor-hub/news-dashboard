export type WorkflowState = 'today' | 'later' | 'done' | 'skipped' | 'archived';

export type Signal = 'high' | 'mid' | 'low';

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
