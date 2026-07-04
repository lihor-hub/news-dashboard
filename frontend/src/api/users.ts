import type {
  Achievement,
  AiMemory,
  McpToken,
  ReadingDna,
  ReadingGoal,
  ReadingStreak,
  RecommendationPreferences,
  Summary,
  WeeklyRecap,
} from '../types';
import { requestJson } from './core';

export async function fetchSummary(): Promise<Summary> {
  return requestJson<Summary>('/api/summary');
}

export async function fetchReadingDna(): Promise<ReadingDna> {
  return requestJson<ReadingDna>('/api/users/me/reading-dna');
}

export async function fetchReadingStreak(): Promise<ReadingStreak> {
  return requestJson<ReadingStreak>('/api/users/me/streak');
}

export async function fetchAchievements(): Promise<Achievement[]> {
  const data = await requestJson<{ items: Achievement[] }>('/api/users/me/achievements');
  return data.items;
}

export async function fetchRecaps(): Promise<WeeklyRecap[]> {
  const data = await requestJson<{ items: WeeklyRecap[] }>('/api/recaps');
  return data.items;
}

export async function fetchRecommendationPreferences(): Promise<RecommendationPreferences> {
  return requestJson<RecommendationPreferences>('/api/users/me/recommendation-preferences');
}

export async function saveRecommendationPreferences(
  preferences: Partial<RecommendationPreferences>
): Promise<RecommendationPreferences> {
  return requestJson<RecommendationPreferences>('/api/users/me/recommendation-preferences', {
    method: 'PATCH',
    body: JSON.stringify(preferences),
  });
}

export async function fetchAiMemories(): Promise<AiMemory[]> {
  const data = await requestJson<{ items: AiMemory[] }>('/api/users/me/ai-memories');
  return data.items;
}

export async function createAiMemory(content: string): Promise<AiMemory> {
  return requestJson<AiMemory>('/api/users/me/ai-memories', {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function updateAiMemory(
  memoryId: number,
  payload: Partial<Pick<AiMemory, 'content' | 'memory_type' | 'confidence' | 'active'>>
): Promise<AiMemory> {
  return requestJson<AiMemory>(`/api/users/me/ai-memories/${memoryId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deactivateAiMemory(memoryId: number): Promise<AiMemory> {
  return requestJson<AiMemory>(`/api/users/me/ai-memories/${memoryId}`, {
    method: 'DELETE',
  });
}

export async function learnAiMemoriesFromReading(): Promise<AiMemory[]> {
  const data = await requestJson<{ items: AiMemory[] }>(
    '/api/users/me/ai-memories/learn-from-reading',
    { method: 'POST' }
  );
  return data.items;
}

export async function fetchMcpTokens(): Promise<{ items: McpToken[]; enabled: boolean }> {
  return requestJson('/api/users/me/mcp-tokens');
}

export async function createMcpToken(name: string): Promise<McpToken> {
  return requestJson<McpToken>('/api/users/me/mcp-tokens', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function revokeMcpToken(tokenId: number): Promise<McpToken> {
  return requestJson<McpToken>(`/api/users/me/mcp-tokens/${tokenId}`, {
    method: 'DELETE',
  });
}

export async function recalculateMyRecommendations(): Promise<{ scored: number }> {
  return requestJson<{ scored: number }>('/api/recommendations/recalculate-mine', {
    method: 'POST',
  });
}

export async function downloadUserExport(): Promise<void> {
  const data = await requestJson<unknown>('/api/users/me/export');
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `reading-archive-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function deleteOwnAccount(confirmation: string): Promise<void> {
  await requestJson<{ status: string }>('/api/users/me', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation }),
  });
}

export async function fetchGoals(): Promise<ReadingGoal[]> {
  const data = await requestJson<{ items: ReadingGoal[] }>('/api/goals');
  return data.items;
}

export async function createGoal(description: string, keywords: string): Promise<ReadingGoal> {
  return requestJson<ReadingGoal>('/api/goals', {
    method: 'POST',
    body: JSON.stringify({ description, keywords }),
  });
}

export async function deleteGoal(goalId: number): Promise<void> {
  await requestJson(`/api/goals/${goalId}`, { method: 'DELETE' });
}
