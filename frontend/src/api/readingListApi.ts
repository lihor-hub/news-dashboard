/** API layer for the reading list (#893). */

import { HttpError, readErrorMessage, requestJson } from './core';

export type ReadingListStatus = 'unread' | 'done' | 'archived';
export type ReadingListKind = 'article' | 'video' | 'channel' | 'link';
export type ReadingListFetchStatus = 'pending' | 'ok' | 'error';
export type ReadingListSummaryStatus = 'pending' | 'ok' | 'error' | 'skipped';

export interface ReadingListItem {
  id: number;
  user_id: number;
  url: string;
  normalized_url: string;
  title: string | null;
  description: string | null;
  image_url: string | null;
  site_name: string | null;
  kind: ReadingListKind;
  fetch_status: ReadingListFetchStatus;
  fetch_error: string | null;
  fetched_at: string | null;
  summary: string | null;
  summary_status: ReadingListSummaryStatus;
  status: ReadingListStatus;
  priority: number;
  note: string | null;
  created_at: string;
  done_at: string | null;
}

interface ReadingListResponse {
  items: ReadingListItem[];
}

export interface ReadingListFilters {
  status?: ReadingListStatus;
  q?: string;
  kind?: ReadingListKind;
}

export async function fetchReadingList(
  filters: ReadingListFilters = {}
): Promise<ReadingListItem[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  if (filters.kind) params.set('kind', filters.kind);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const data = await requestJson<ReadingListResponse>(`/api/reading-list${suffix}`);
  return data.items;
}

export async function addReadingListItem(url: string, note?: string): Promise<ReadingListItem> {
  return requestJson<ReadingListItem>('/api/reading-list', {
    method: 'POST',
    body: JSON.stringify(note === undefined ? { url } : { url, note }),
  });
}

export async function updateReadingListItem(
  id: number,
  changes: { status?: ReadingListStatus; note?: string }
): Promise<ReadingListItem> {
  return requestJson<ReadingListItem>(`/api/reading-list/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
}

export async function reorderReadingList(orderedIds: number[]): Promise<ReadingListItem[]> {
  const data = await requestJson<ReadingListResponse>('/api/reading-list/reorder', {
    method: 'POST',
    body: JSON.stringify({ ordered_ids: orderedIds }),
  });
  return data.items;
}

export async function deleteReadingListItem(id: number): Promise<void> {
  await requestJson(`/api/reading-list/${id}`, { method: 'DELETE' });
}

export type ReadingListImportSource = 'pocket' | 'instapaper' | 'omnivore';

export interface ReadingListImportResult {
  added: number;
  skipped: number;
  failed: number;
}

export async function importReadingList(
  file: File,
  source: ReadingListImportSource
): Promise<ReadingListImportResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('source', source);
  const response = await fetch('/api/reading-list/import', {
    method: 'POST',
    credentials: 'same-origin',
    body: form,
  });
  if (!response.ok) throw new HttpError(response.status, await readErrorMessage(response));
  return response.json() as Promise<ReadingListImportResult>;
}
