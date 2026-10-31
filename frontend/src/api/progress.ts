import { requestJson } from './core';

export interface DailyStreak {
  available: boolean;
  recent_reward?: ProgressReward | null;
  timezone: string;
  local_date: string;
  server_now: string;
  next_local_boundary_at: string;
  current_streak_days: number;
  best_streak_days: number;
  visit_kind: 'first' | 'continuing' | 'restart' | null;
  seven_days: { date: string; visited: boolean; credited: boolean }[];
  welcome_target: { expected_visit_date: string } | null;
}
export interface ProgressPreferences {
  progress_timezone: string;
  timezone_initialized: boolean;
  daily_welcome_enabled: boolean;
  reward_animations_enabled: boolean;
}
export interface ProgressReward {
  key: string;
  href?: string;
  metadata?: unknown;
  retired?: boolean;
  topic_id?: string | null;
  title: string;
  description: string;
  unlocked: boolean;
  target: number | null;
  earned_at: string | null;
  recorded_at: string | null;
  origin: string | null;
}
export interface TopicTrack {
  id: string;
  name: string;
  count: number;
  level: string | null;
  next_target: number | null;
  next_level: string | null;
  earned_levels: ProgressReward[];
}
export interface TopicProgress {
  taxonomy_version: number;
  rule_version: number;
  attribution_cap: number;
  tracks: TopicTrack[];
  top_track_ids: string[];
  breadth_count: number;
}
export interface Presentation {
  show: boolean;
  authorization: { welcome: boolean; history: boolean; rewards: boolean };
  welcome: DailyStreak | null;
  history?: { group_id: string; credited_reads: number; exact_earned_dates_known: boolean } | null;
  rewards?: ProgressReward[];
}
const base = '/api/users/me';
export const fetchDailyStreak = () => requestJson<DailyStreak>(`${base}/daily-streak`);
export const recordDailyVisit = () =>
  requestJson<DailyStreak>(`${base}/daily-visit`, { method: 'POST', body: '{}' });
export const claimPresentation = (
  expected_visit_date: string | null,
  historical_group_id?: string
) =>
  requestJson<Presentation>(`${base}/presentation/claim`, {
    method: 'POST',
    body: JSON.stringify({ expected_visit_date, historical_group_id }),
  });
export const claimDailyWelcome = (date: string, history?: string) =>
  claimPresentation(date, history);
export const claimRewardGroup = (id: string) =>
  requestJson<Presentation>(`${base}/reward-events/${encodeURIComponent(id)}/claim`, {
    method: 'POST',
    body: '{}',
  });
export const acknowledgeRewardGroup = (id: string) =>
  requestJson(`${base}/reward-events/${encodeURIComponent(id)}/ack`, {
    method: 'POST',
    body: '{}',
  });
export const rewardHref = (key: string) =>
  `/reading-dna?reward=${encodeURIComponent(key)}#progress`;
export const fetchProgressPreferences = () =>
  requestJson<ProgressPreferences>(`${base}/progress-preferences`);
export const saveProgressPreferences = (
  patch: Partial<Omit<ProgressPreferences, 'timezone_initialized'>>
) =>
  requestJson<ProgressPreferences>(`${base}/progress-preferences`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
export const fetchProgressRewards = () =>
  requestJson<{
    items: ProgressReward[];
    pending_reward_group_ids?: string[];
    historical_group_id?: string | null;
    topics?: TopicProgress;
    reading_total?: number;
    next_reading_target?: number | null;
    history_status?: 'reconciliation_pending';
  }>(`${base}/progress-rewards`);
