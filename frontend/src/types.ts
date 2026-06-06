export type ArticleStatus = 'new' | 'read' | 'saved' | 'skipped' | 'archived'

export interface Article {
  id: number
  url: string
  title: string
  source_name: string
  category: string
  kind: string
  published_at?: string | null
  discovered_at: string
  status: ArticleStatus
  importance_score: number
  summary: string
  reason: string
  tags: string
  read_at?: string | null
  saved_at?: string | null
  skipped_at?: string | null
  archived_at?: string | null
  also_from?: string[]
  canonical_id?: number | null
}

export interface Source {
  slug: string
  name: string
  url: string
  category: string
  kind: string
  priority: number
  enabled: number
  last_checked_at?: string | null
  last_success_at?: string | null
  last_error?: string | null
  last_fetched_count?: number
  last_inserted_count?: number
}

export interface SourceHealth {
  slug: string
  name: string
  category: string
  enabled: number
  last_checked_at?: string | null
  last_error?: string | null
  error_streak: number
  articles_last_run: number
  status: 'OK' | 'ERROR'
}

export interface Summary {
  byStatus: Record<string, number>
  byCategory: Record<string, number>
}

export interface StatsOverview {
  total_articles: number
  total_new: number
  total_errors: number
  avg_duration_ms: number
  healthy_sources: number
  erroring_sources: number
}

export interface ArticlesOverTimePoint {
  date: string
  new_articles: number
}

export interface SourceVolumePoint {
  source_name: string
  total_new: number
}

export interface AskSource {
  id: number
  title: string
  url: string
}

export interface AskResponse {
  answer: string
  sources: AskSource[]
}
