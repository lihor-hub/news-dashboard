import type {
  AdminAnalytics,
  Article,
  ArticleCountsResult,
  ArticleStatus,
  ArticlesOverTimePoint,
  AskResponse,
  Briefing,
  BriefingCreateResponse,
  BriefingLatestResponse,
  CategoryMixPoint,
  IngestedVsHandledPoint,
  NotificationSettings,
  NotificationSettingsUpdate,
  PushSubscribeRequest,
  Quiz,
  QuizResult,
  ReadingDna,
  ReadingGoal,
  RecommendationPreferences,
  ReceivedShare,
  ShareableUser,
  Source,
  SourceCleanupSuggestion,
  SourceHealth,
  SourceQualityRow,
  SourceVolumePoint,
  StatsOverview,
  Summary,
  TriageMetrics,
  IngestRunPage,
  IngestRunSource,
  TopicMapResponse,
  User,
} from './types';

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await (response.json() as Promise<unknown>);
    if (body && typeof body === 'object') {
      const { detail, message } = body as Record<string, unknown>;
      if (typeof detail === 'string' && detail) return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const msgs = detail
          .map((d) => (d && typeof d === 'object' ? (d as Record<string, unknown>).msg : null))
          .filter((m): m is string => typeof m === 'string');
        if (msgs.length > 0) return msgs.join('; ');
      }
      if (typeof message === 'string' && message) return message;
    }
  } catch {
    // non-JSON body — fall through
  }
  return `${response.status} ${response.statusText}`;
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    credentials: 'same-origin',
    ...init,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

export async function fetchArticles(
  status?: ArticleStatus,
  category?: string,
  offset = 0,
  limit = 100
): Promise<Article[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (category) params.set('category', category);
  if (offset > 0) params.set('offset', String(offset));
  if (limit !== 100) params.set('limit', String(limit));
  const suffix = params.size ? `?${params}` : '';
  const data = await requestJson<{ items: Article[] }>(`/api/articles${suffix}`);
  return data.items;
}

export async function searchArticles(q: string, limit = 50): Promise<Article[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const data = await requestJson<{ items: Article[] }>(`/api/search?${params}`);
  return data.items;
}

export async function fetchArticle(id: number | string): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}`);
}

export async function fetchArticleBody(id: number | string): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}/body`, { method: 'POST' });
}

export async function fetchArticleAudioUrl(id: number | string): Promise<string> {
  const response = await fetch(`/api/articles/${id}/audio`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function fetchArticleInsights(id: number | string): Promise<string[]> {
  const data = await requestJson<{ bullets: string[] }>(`/api/articles/${id}/insights`);
  return data.bullets;
}

export interface PerspectiveAnalysis {
  verified_facts: string[];
  omissions: string[];
  alternative_perspectives: string[];
}

export async function fetchArticlePerspectives(id: number | string): Promise<PerspectiveAnalysis> {
  return requestJson<PerspectiveAnalysis>(`/api/articles/${id}/perspectives`);
}

export async function fetchSources(): Promise<Source[]> {
  const data = await requestJson<{ items: Source[] }>('/api/sources');
  return data.items;
}

export async function fetchSourceHealth(): Promise<SourceHealth[]> {
  const data = await requestJson<{ items: SourceHealth[] }>('/api/sources/health');
  return data.items;
}

export async function fetchSourceCleanupSuggestions(): Promise<SourceCleanupSuggestion[]> {
  const data = await requestJson<{ items: SourceCleanupSuggestion[] }>(
    '/api/sources/cleanup-suggestions'
  );
  return data.items;
}

export async function applySourceCleanup(sourceSlugs: string[]): Promise<{
  updated: string[];
  skipped: string[];
}> {
  return requestJson('/api/sources/cleanup', {
    method: 'POST',
    body: JSON.stringify({ source_slugs: sourceSlugs }),
  });
}

export async function fetchSummary(): Promise<Summary> {
  return requestJson<Summary>('/api/summary');
}

export async function fetchReadingDna(): Promise<ReadingDna> {
  return requestJson<ReadingDna>('/api/users/me/reading-dna');
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

export async function ingestNow(): Promise<{ inserted: number; results: Record<string, number> }> {
  return requestJson('/api/ingest', { method: 'POST' });
}

export async function updateArticleStatus(id: number, status: ArticleStatus): Promise<Article> {
  return requestJson<Article>(`/api/articles/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export async function askAI(query: string, includeAll = false): Promise<AskResponse> {
  return requestJson<AskResponse>('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query, include_all: includeAll }),
  });
}

export async function submitFeedback(
  traceId: string,
  helpful: boolean,
  comment?: string
): Promise<{ recorded: boolean }> {
  return requestJson<{ recorded: boolean }>('/api/feedback', {
    method: 'POST',
    body: JSON.stringify({ trace_id: traceId, helpful, comment }),
  });
}

export async function updateSourceEnabled(slug: string, enabled: boolean): Promise<Source> {
  return requestJson<Source>(`/api/sources/${slug}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
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

function statsParams(from: string, to: string): string {
  return new URLSearchParams({ from, to }).toString();
}

export async function fetchStatsOverview(from: string, to: string): Promise<StatsOverview> {
  return requestJson<StatsOverview>(`/api/stats/overview?${statsParams(from, to)}`);
}

export async function fetchArticlesOverTime(
  from: string,
  to: string
): Promise<ArticlesOverTimePoint[]> {
  const data = await requestJson<{ items: ArticlesOverTimePoint[] }>(
    `/api/stats/articles-over-time?${statsParams(from, to)}`
  );
  return data.items;
}

export async function fetchSourcesVolume(from: string, to: string): Promise<SourceVolumePoint[]> {
  const data = await requestJson<{ items: SourceVolumePoint[] }>(
    `/api/stats/sources-volume?${statsParams(from, to)}`
  );
  return data.items;
}

export async function fetchArticleCounts(): Promise<ArticleCountsResult> {
  return requestJson<ArticleCountsResult>('/api/stats/article-counts');
}

export async function fetchTriageMetrics(): Promise<TriageMetrics> {
  return requestJson<TriageMetrics>('/api/stats/triage-metrics');
}

export async function fetchSourceQuality(): Promise<SourceQualityRow[]> {
  const data = await requestJson<{ items: SourceQualityRow[] }>('/api/stats/source-quality');
  return data.items;
}

export async function fetchCategoryMix(): Promise<CategoryMixPoint[]> {
  const data = await requestJson<{ items: CategoryMixPoint[] }>('/api/stats/category-mix');
  return data.items;
}

export async function fetchIngestedVsHandled(): Promise<IngestedVsHandledPoint[]> {
  const data = await requestJson<{ items: IngestedVsHandledPoint[] }>(
    '/api/stats/ingested-vs-handled'
  );
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

export async function fetchLatestBriefing(): Promise<BriefingLatestResponse> {
  return requestJson<BriefingLatestResponse>('/api/briefings/latest');
}

export async function createBriefing(): Promise<BriefingCreateResponse> {
  return requestJson<BriefingCreateResponse>('/api/briefings', { method: 'POST' });
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

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface AuthConfig {
  provider: 'password' | 'keycloak';
  keycloak_enabled: boolean;
  login_url: string | null;
  logout_url: string;
  registration_url?: string | null;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  return requestJson<AuthConfig>('/api/auth/config');
}

export async function fetchMe(): Promise<User> {
  return requestJson<User>('/api/auth/me');
}

export async function fetchAdminAnalytics(days = 30): Promise<AdminAnalytics> {
  return requestJson<AdminAnalytics>(`/api/admin/analytics?days=${days}`);
}

export async function loginUser(username: string, password: string): Promise<User> {
  return requestJson<User>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export interface GeneratedUser {
  id: number | string | null;
  username: string;
  email?: string | null;
  is_admin?: boolean;
  password: string;
  provider: 'keycloak' | 'password';
  temporary?: boolean;
  created_at?: string | null;
}

export async function fetchAdminUsers(): Promise<User[]> {
  const data = await requestJson<{ items: User[] }>('/api/admin/users');
  return data.items;
}

export async function generateAdminUser(
  username: string,
  options?: { email?: string | null; is_admin?: boolean }
): Promise<GeneratedUser> {
  return requestJson<GeneratedUser>('/api/admin/users/generate', {
    method: 'POST',
    body: JSON.stringify({
      username,
      email: options?.email ?? null,
      is_admin: options?.is_admin ?? false,
    }),
  });
}

export async function deleteAdminUser(userId: number): Promise<void> {
  await requestJson<{ status: string }>(`/api/admin/users/${userId}`, {
    method: 'DELETE',
  });
}

export async function logoutUser(): Promise<void> {
  const config = await fetchAuthConfig().catch(() => null);
  if (config?.provider === 'keycloak' && config.logout_url) {
    window.location.assign(config.logout_url);
    return;
  }
  await fetch('/api/auth/logout', { credentials: 'same-origin' });
}

export async function toggleSourceSubscription(
  slug: string,
  enabled: boolean
): Promise<{ subscribed: boolean }> {
  return requestJson<{ subscribed: boolean }>(`/api/sources/${slug}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

/**
 * Recompute the current user's personalized recommendation scores on demand.
 * Returns how many articles were scored — zero means there's no interaction
 * history (starred/done/skipped) to learn from yet.
 */
export async function recalculateMyRecommendations(): Promise<{ scored: number }> {
  return requestJson<{ scored: number }>('/api/recommendations/recalculate-mine', {
    method: 'POST',
  });
}

// ── Notification settings & push subscriptions ────────────────────────────────

export async function fetchNotificationSettings(): Promise<NotificationSettings> {
  return requestJson<NotificationSettings>('/api/settings/notifications');
}

export async function updateNotificationSettings(
  update: NotificationSettingsUpdate
): Promise<Omit<NotificationSettings, 'vapid_public_key'>> {
  return requestJson('/api/settings/notifications', {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

export async function subscribePush(
  payload: PushSubscribeRequest
): Promise<{ subscribed: boolean }> {
  return requestJson('/api/notifications/subscribe', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function unsubscribePush(): Promise<{ unsubscribed: boolean }> {
  return requestJson('/api/notifications/subscribe', { method: 'DELETE' });
}

// ─── In-platform sharing ──────────────────────────────────────────────────────

export async function fetchShareableUsers(): Promise<ShareableUser[]> {
  const data = await requestJson<{ items: ShareableUser[] }>('/api/users');
  return data.items;
}

export async function shareArticle(
  articleId: number,
  toUserId: number,
  note?: string
): Promise<void> {
  await requestJson(`/api/articles/${articleId}/share`, {
    method: 'POST',
    body: JSON.stringify({ to_user_id: toUserId, note: note ?? null }),
  });
}

export async function fetchReceivedShares(): Promise<{
  items: ReceivedShare[];
  unread: number;
}> {
  return requestJson('/api/shares');
}

export async function fetchSharesUnreadCount(): Promise<number> {
  const data = await requestJson<{ unread: number }>('/api/shares/unread_count');
  return data.unread;
}

// ── Reading Goals & Quizzes ───────────────────────────────────────────────────

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

export async function fetchLatestQuiz(): Promise<Quiz | null> {
  try {
    return await requestJson<Quiz>('/api/quizzes/latest');
  } catch {
    return null;
  }
}

export async function generateQuiz(): Promise<Quiz> {
  return requestJson<Quiz>('/api/quizzes/generate', { method: 'POST' });
}

export async function submitQuiz(quizId: number, answers: number[]): Promise<QuizResult> {
  return requestJson<QuizResult>(`/api/quizzes/${quizId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}

export async function markShareRead(shareId: number): Promise<void> {
  await requestJson(`/api/shares/${shareId}/read`, { method: 'POST' });
}

export async function fetchTopicMap(): Promise<TopicMapResponse> {
  return requestJson<TopicMapResponse>('/api/articles/topic-map');
}
