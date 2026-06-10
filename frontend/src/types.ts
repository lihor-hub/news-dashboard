export type ArticleStatus = 'new' | 'read' | 'saved' | 'skipped' | 'archived';

export interface Article {
  id: number;
  url: string;
  title: string;
  source_name: string;
  category: string;
  kind: string;
  published_at?: string | null;
  discovered_at: string;
  status: ArticleStatus;
  importance_score: number;
  summary: string;
  reason: string;
  tags: string;
  read_at?: string | null;
  saved_at?: string | null;
  skipped_at?: string | null;
  archived_at?: string | null;
  also_from?: string[];
  canonical_id?: number | null;
}

export interface Source {
  slug: string;
  name: string;
  url: string;
  category: string;
  kind: string;
  priority: number;
  enabled: number;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  last_fetched_count?: number;
  last_inserted_count?: number;
}

export interface SourceHealth {
  slug: string;
  name: string;
  category: string;
  enabled: number;
  last_checked_at?: string | null;
  last_error?: string | null;
  error_streak: number;
  articles_last_run: number;
  status: 'OK' | 'ERROR';
}

export interface Summary {
  byStatus: Record<string, number>;
  byCategory: Record<string, number>;
}

export interface StatsOverview {
  total_articles: number;
  total_new: number;
  total_errors: number;
  avg_duration_ms: number;
  healthy_sources: number;
  erroring_sources: number;
}

export interface ArticlesOverTimePoint {
  date: string;
  new_articles: number;
}

export interface SourceVolumePoint {
  source_name: string;
  total_new: number;
}

export interface ArticleCountsResult {
  new: number;
  saved: number;
  read: number;
  skipped: number;
  archived: number;
}

export interface TriageMetrics {
  articles_this_week: number;
  handled_rate: number;
  save_rate: number;
  avg_triage_hours: number;
}

export interface SourceQualityRow {
  source_name: string;
  total: number;
  skip_rate: number;
  save_rate: number;
  error_rate: number;
}

export interface CategoryMixPoint {
  day: string;
  [category: string]: string | number;
}

export interface IngestedVsHandledPoint {
  day: string;
  ingested: number;
  handled: number;
}

export interface AskSource {
  id: number;
  title: string;
  url: string;
}

export interface AskResponse {
  answer: string;
  sources: AskSource[];
}

export interface IngestRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  sources_run: number;
  total_new: number;
  total_errors: number;
}

export interface IngestRunSource {
  id: number;
  run_id: number;
  source_name: string;
  articles_found: number;
  articles_new: number;
  duplicates: number;
  error_message?: string | null;
}

export interface IngestRunPage {
  items: IngestRun[];
  page: number;
  per_page: number;
  total: number;
  has_more: boolean;
}
