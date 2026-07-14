import type { IngestRunPage, IngestRunSource } from '../types';
import { requestJson } from './core';

export async function ingestNow(): Promise<{
  inserted: number;
  results: Record<string, number>;
  run_id: number;
  total_errors: number;
  failed_sources: string[];
}> {
  return requestJson('/api/ingest', { method: 'POST' });
}

export interface SchedulerStatus {
  interval_minutes: number;
  paused: boolean;
  next_run_at: string | null;
  interval_ingest_enabled?: boolean;
  ingest_authority?: 'in_process' | 'external';
}

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return requestJson<SchedulerStatus>('/api/scheduler/status');
}

export async function setSchedulerInterval(
  minutes: number
): Promise<{ interval_minutes: number; next_run_at: string | null }> {
  return requestJson('/api/scheduler/interval', {
    method: 'POST',
    body: JSON.stringify({ minutes }),
  });
}

export async function pauseScheduler(): Promise<{ paused: boolean }> {
  return requestJson('/api/scheduler/pause', { method: 'POST' });
}

export async function resumeScheduler(): Promise<{ paused: boolean; next_run_at: string | null }> {
  return requestJson('/api/scheduler/resume', { method: 'POST' });
}

export interface EmbeddingDedupResult {
  status: 'success';
  embedded: number;
  merged: number;
}

export async function runEmbeddingDedup(): Promise<EmbeddingDedupResult> {
  return requestJson<EmbeddingDedupResult>('/api/scheduler/jobs/embedding-dedup/run', {
    method: 'POST',
  });
}

export interface ScheduledJobRun {
  id: number;
  job_name: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: 'success' | 'skipped' | 'failure';
  message: string | null;
}

export async function fetchLatestJobRuns(): Promise<ScheduledJobRun[]> {
  const data = await requestJson<{ items: ScheduledJobRun[] }>('/api/scheduler/job-runs');
  return data.items;
}

export async function fetchIngestRuns(page = 1, perPage = 10): Promise<IngestRunPage> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  return requestJson<IngestRunPage>(`/api/ingest/runs?${params}`);
}

export async function fetchIngestRunSources(runId: number): Promise<IngestRunSource[]> {
  const data = await requestJson<{ items: IngestRunSource[] }>(`/api/ingest/runs/${runId}`);
  return data.items;
}
