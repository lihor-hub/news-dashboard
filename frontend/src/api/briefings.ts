import type { Briefing, BriefingCreateResponse, BriefingLatestResponse } from '../types';
import { requestJson } from './core';

export async function fetchLatestBriefing(): Promise<BriefingLatestResponse> {
  return requestJson<BriefingLatestResponse>('/api/briefings/latest');
}

export async function createBriefing(focusPrompt?: string): Promise<BriefingCreateResponse> {
  return requestJson<BriefingCreateResponse>('/api/briefings', {
    method: 'POST',
    ...(focusPrompt ? { body: JSON.stringify({ focus_prompt: focusPrompt }) } : {}),
  });
}

export async function fetchBriefing(id: number): Promise<Briefing> {
  return requestJson<Briefing>(`/api/briefings/${id}`);
}

export async function fetchBriefings(limit = 50, offset = 0): Promise<{ items: Briefing[] }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return requestJson<{ items: Briefing[] }>(`/api/briefings?${params}`);
}

export async function generateBriefingPodcast(id: number): Promise<{ url: string }> {
  return requestJson<{ url: string }>(`/api/briefings/${id}/podcast`, { method: 'POST' });
}

export interface PodcastFeedToken {
  token: string;
  url: string;
}

export async function fetchPodcastFeedToken(): Promise<PodcastFeedToken> {
  return requestJson<PodcastFeedToken>('/api/briefings/podcast-feed-token');
}

export async function regeneratePodcastFeedToken(): Promise<PodcastFeedToken> {
  return requestJson<PodcastFeedToken>('/api/briefings/podcast-feed-token/regenerate', {
    method: 'POST',
  });
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function chatWithBriefing(
  briefingId: number,
  message: string,
  history: ChatMessage[]
): Promise<{ reply: string }> {
  return requestJson<{ reply: string }>(`/api/briefings/${briefingId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  });
}
