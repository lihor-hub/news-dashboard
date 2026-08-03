import type {
  AnalyticsSettings,
  AnalyticsSettingsUpdate,
  AutomaticAiEnrichmentSettings,
  AutomaticAiEnrichmentSettingsUpdate,
} from '../types';
import { requestJson } from './core';

export async function fetchAnalyticsSettings(): Promise<AnalyticsSettings> {
  return requestJson<AnalyticsSettings>('/api/settings/analytics');
}

export async function fetchAutomaticAiEnrichmentSettings(): Promise<AutomaticAiEnrichmentSettings> {
  return requestJson('/api/settings/automatic-ai-enrichment');
}

export async function updateAutomaticAiEnrichmentSettings(
  update: AutomaticAiEnrichmentSettingsUpdate
): Promise<AutomaticAiEnrichmentSettings> {
  return requestJson('/api/settings/automatic-ai-enrichment', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

export async function updateAnalyticsSettings(
  update: AnalyticsSettingsUpdate
): Promise<AnalyticsSettings> {
  return requestJson('/api/settings/analytics', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}
