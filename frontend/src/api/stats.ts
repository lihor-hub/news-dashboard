import type {
  ArticleCountsResult,
  ArticlesOverTimePoint,
  CategoryMixPoint,
  EmbeddingMapResponse,
  IngestedVsHandledPoint,
  KnowledgeGraphResponse,
  SourceQualityRow,
  SourceVolumePoint,
  StatsOverview,
  TriageMetrics,
  WordCloudResponse,
} from '../types';
import { requestJson } from './core';

function statsParams(from: string, to: string): string {
  return new URLSearchParams({ from, to }).toString();
}

export async function fetchStatsOverview(from: string, to: string): Promise<StatsOverview> {
  return requestJson<StatsOverview>(`/api/stats/overview?${statsParams(from, to)}`);
}

export async function fetchArticlesOverTime(
  from: string,
  to: string
): Promise<ArticlesOverTimePoint[]> {
  const data = await requestJson<{ items: ArticlesOverTimePoint[] }>(
    `/api/stats/articles-over-time?${statsParams(from, to)}`
  );
  return data.items;
}

export async function fetchSourcesVolume(from: string, to: string): Promise<SourceVolumePoint[]> {
  const data = await requestJson<{ items: SourceVolumePoint[] }>(
    `/api/stats/sources-volume?${statsParams(from, to)}`
  );
  return data.items;
}

export async function fetchArticleCounts(): Promise<ArticleCountsResult> {
  return requestJson<ArticleCountsResult>('/api/stats/article-counts');
}

export async function fetchTriageMetrics(): Promise<TriageMetrics> {
  return requestJson<TriageMetrics>('/api/stats/triage-metrics');
}

export async function fetchSourceQuality(): Promise<SourceQualityRow[]> {
  const data = await requestJson<{ items: SourceQualityRow[] }>('/api/stats/source-quality');
  return data.items;
}

export async function fetchCategoryMix(): Promise<CategoryMixPoint[]> {
  const data = await requestJson<{ items: CategoryMixPoint[] }>('/api/stats/category-mix');
  return data.items;
}

export async function fetchIngestedVsHandled(): Promise<IngestedVsHandledPoint[]> {
  const data = await requestJson<{ items: IngestedVsHandledPoint[] }>(
    '/api/stats/ingested-vs-handled'
  );
  return data.items;
}

export async function fetchAiWordCloud(days = 7): Promise<WordCloudResponse> {
  return requestJson<WordCloudResponse>(`/api/ai-stats/word-cloud?days=${days}`);
}

export async function fetchAiEmbeddingMap(days = 7): Promise<EmbeddingMapResponse> {
  return requestJson<EmbeddingMapResponse>(`/api/ai-stats/embedding-map?days=${days}`);
}

export async function fetchKnowledgeGraph(days = 7): Promise<KnowledgeGraphResponse> {
  return requestJson<KnowledgeGraphResponse>(`/api/ai-stats/knowledge-graph?days=${days}`);
}
