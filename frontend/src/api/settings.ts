import type { AnalyticsSettings, AnalyticsSettingsUpdate } from '../types';
import { requestJson } from './core';

export async function fetchAnalyticsSettings(): Promise<AnalyticsSettings> {
  return requestJson<AnalyticsSettings>('/api/settings/analytics');
}

export async function updateAnalyticsSettings(
  update: AnalyticsSettingsUpdate
): Promise<AnalyticsSettings> {
  return requestJson('/api/settings/analytics', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}
