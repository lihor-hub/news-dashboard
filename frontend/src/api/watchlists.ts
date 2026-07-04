import type { AiWatchlist, AiWatchlistMatch, AiWatchlistNudge } from '../types';
import { requestJson } from './core';

export async function fetchWatchlists(): Promise<AiWatchlist[]> {
  const data = await requestJson<{ items: AiWatchlist[] }>('/api/watchlists');
  return data.items;
}

export interface CreateWatchlistRequest {
  label: string;
  query: string;
  threshold?: number;
  enabled?: boolean;
  notify_push?: boolean;
}

export async function createWatchlist(payload: CreateWatchlistRequest): Promise<AiWatchlist> {
  return requestJson('/api/watchlists', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface UpdateWatchlistRequest {
  label?: string;
  query?: string;
  threshold?: number;
  enabled?: boolean;
  notify_push?: boolean;
}

export async function updateWatchlist(
  watchlistId: number,
  payload: UpdateWatchlistRequest
): Promise<AiWatchlist> {
  return requestJson(`/api/watchlists/${watchlistId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deleteWatchlist(watchlistId: number): Promise<{ deleted: boolean }> {
  return requestJson(`/api/watchlists/${watchlistId}`, { method: 'DELETE' });
}

export async function previewWatchlist(
  query: string,
  threshold?: number
): Promise<AiWatchlistMatch[]> {
  const data = await requestJson<{ items: AiWatchlistMatch[] }>('/api/watchlists/preview', {
    method: 'POST',
    body: JSON.stringify({ query, threshold }),
  });
  return data.items;
}

export async function fetchWatchlistNudges(): Promise<AiWatchlistNudge[]> {
  const data = await requestJson<{ items: AiWatchlistNudge[] }>('/api/watchlists/nudges');
  return data.items;
}
