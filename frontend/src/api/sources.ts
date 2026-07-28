import type { OpmlImportResult, Source, SourceCleanupSuggestion, SourceHealth } from '../types';
import { readErrorMessage, requestJson, HttpError } from './core';

export async function fetchSources(): Promise<Source[]> {
  const data = await requestJson<{ items: Source[] }>('/api/sources');
  return data.items;
}

export async function fetchSourceHealth(): Promise<SourceHealth[]> {
  const data = await requestJson<{ items: SourceHealth[] }>('/api/sources/health');
  return data.items;
}

export async function fetchSourceCleanupSuggestions(): Promise<SourceCleanupSuggestion[]> {
  const data = await requestJson<{ items: SourceCleanupSuggestion[] }>(
    '/api/sources/cleanup-suggestions'
  );
  return data.items;
}

export async function applySourceCleanup(sourceSlugs: string[]): Promise<{
  updated: string[];
  skipped: string[];
}> {
  return requestJson('/api/sources/cleanup', {
    method: 'POST',
    body: JSON.stringify({ source_slugs: sourceSlugs }),
  });
}

export interface CreateSourcePayload {
  url: string;
  name: string;
  category?: string;
  slug?: string;
  kind?: string;
  high_priority?: boolean;
}

export async function createSource(payload: CreateSourcePayload): Promise<Source> {
  return requestJson<Source>('/api/sources', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface PreviewSourcePayload {
  url: string;
  kind?: string;
}

export interface SourcePreviewItem {
  title: string;
  url: string;
  date: string | null;
}

export interface SourcePreviewResult {
  kind: string;
  entry_count: number;
  items: SourcePreviewItem[];
}

export async function previewSource(payload: PreviewSourcePayload): Promise<SourcePreviewResult> {
  return requestJson<SourcePreviewResult>('/api/sources/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteSource(slug: string): Promise<{ status: string }> {
  return requestJson<{ status: string }>(`/api/sources/${slug}`, { method: 'DELETE' });
}

export async function updateSourceEnabled(slug: string, enabled: boolean): Promise<Source> {
  return requestJson<Source>(`/api/sources/${slug}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export async function updateSourcePriority(slug: string, highPriority: boolean): Promise<Source> {
  return requestJson<Source>(`/api/sources/${slug}/priority`, {
    method: 'PATCH',
    body: JSON.stringify({ high_priority: highPriority }),
  });
}

export async function toggleSourceSubscription(
  slug: string,
  enabled: boolean
): Promise<{ subscribed: boolean }> {
  return requestJson<{ subscribed: boolean }>(`/api/sources/${slug}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export async function exportOpml(): Promise<void> {
  const response = await fetch('/api/sources/export.opml', { credentials: 'same-origin' });
  if (!response.ok) throw new Error(await readErrorMessage(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'subscriptions.opml';
  a.click();
  URL.revokeObjectURL(url);
}

export async function importOpml(file: File): Promise<OpmlImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/api/sources/import', {
    method: 'POST',
    credentials: 'same-origin',
    body: form,
  });
  if (!response.ok) throw new HttpError(response.status, await readErrorMessage(response));
  return response.json() as Promise<OpmlImportResult>;
}
