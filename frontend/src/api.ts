import type { Article, ArticleStatus, AskResponse, Source, Summary } from './types'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function fetchArticles(status?: ArticleStatus, category?: string, offset = 0, limit = 100): Promise<Article[]> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (category) params.set('category', category)
  if (offset > 0) params.set('offset', String(offset))
  if (limit !== 100) params.set('limit', String(limit))
  const suffix = params.size ? `?${params}` : ''
  const data = await requestJson<{ items: Article[] }>(`/api/articles${suffix}`)
  return data.items
}

export async function searchArticles(q: string, limit = 50): Promise<Article[]> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  const data = await requestJson<{ items: Article[] }>(`/api/search?${params}`)
  return data.items
}

export async function fetchSources(): Promise<Source[]> {
  const data = await requestJson<{ items: Source[] }>('/api/sources')
  return data.items
}

export async function fetchSummary(): Promise<Summary> {
  return requestJson<Summary>('/api/summary')
}

export async function ingestNow(): Promise<{ inserted: number; results: Record<string, number> }> {
  return requestJson('/api/ingest', { method: 'POST' })
}

export async function updateArticleStatus(id: number, status: ArticleStatus): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export async function askAI(query: string): Promise<AskResponse> {
  return requestJson<AskResponse>('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
}

export async function updateSourceEnabled(slug: string, enabled: boolean): Promise<Source> {
  return requestJson<Source>(`/api/sources/${slug}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}
