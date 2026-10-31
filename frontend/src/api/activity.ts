import { requestJson } from './core';

export interface Activity {
  available: boolean;
  measurement_enabled: boolean;
  total_ms: number;
  approximate: true;
  measured_since: string | null;
  coverage: { status: 'partial' | 'unknown' | 'unavailable'; reasons: string[] };
  next_target_ms: number | null;
}
export interface ActivityWindow {
  available: boolean;
  window_id: string;
  duration_ms: number;
}
const base = '/api/users/me/activity';
export const fetchActivity = () => requestJson<Activity>(base);
export const openActivityWindow = () =>
  requestJson<ActivityWindow>(`${base}/window`, { method: 'POST', body: '{}' });
export const sendActivityHeartbeat = (
  body: { window_id: string; start_ms: number; end_ms: number },
  keepalive = false
) =>
  requestJson<Activity>(`${base}/heartbeat`, {
    method: 'POST',
    body: JSON.stringify(body),
    keepalive,
  });
