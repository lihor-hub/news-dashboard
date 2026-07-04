import type { PersonalizationNudge } from '../types';
import { requestJson } from './core';

export async function fetchPersonalizationNudges(): Promise<PersonalizationNudge[]> {
  const data = await requestJson<{ items: PersonalizationNudge[] }>('/api/personalization/nudges');
  return data.items;
}

export async function applyPersonalizationNudge(nudgeId: string): Promise<{ applied: boolean }> {
  return requestJson('/api/personalization/nudges/apply', {
    method: 'POST',
    body: JSON.stringify({ nudge_id: nudgeId }),
  });
}

export async function dismissPersonalizationNudge(
  nudgeId: string,
  cooldownDays = 7
): Promise<{ dismissed: boolean }> {
  return requestJson('/api/personalization/nudges/dismiss', {
    method: 'POST',
    body: JSON.stringify({ nudge_id: nudgeId, cooldown_days: cooldownDays }),
  });
}
