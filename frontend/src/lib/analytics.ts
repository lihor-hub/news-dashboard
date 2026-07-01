// Lightweight client telemetry: batches user-behavior events and ships them to
// POST /api/events. Captures time-on-app (foreground heartbeats), route views,
// per-article dwell, and feature usage. No third-party deps; flushes on a timer
// and on page hide via sendBeacon so events survive tab close.

export type AnalyticsEventType =
  'heartbeat' | 'route' | 'article_open' | 'article_close' | 'feature';

export interface AnalyticsEvent {
  type: AnalyticsEventType;
  route?: string;
  article_id?: number;
  feature?: string;
  duration_ms?: number;
}

const HEARTBEAT_MS = 15_000;
const FLUSH_MS = 30_000;
const ENDPOINT = '/api/events';

let queue: AnalyticsEvent[] = [];
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let flushTimer: ReturnType<typeof setInterval> | null = null;
let lastBeatAt = Date.now();
let started = false;

// Open articles mapped to the timestamp they were opened, for dwell on close.
const openArticles = new Map<number, number>();

function enqueue(event: AnalyticsEvent): void {
  queue.push(event);
  if (queue.length >= 50) flush();
}

function isVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

function beat(): void {
  const now = Date.now();
  if (isVisible()) {
    enqueue({ type: 'heartbeat', duration_ms: now - lastBeatAt });
  }
  lastBeatAt = now;
}

export function trackRoute(route: string): void {
  enqueue({ type: 'route', route });
}

export function trackFeature(feature: string): void {
  enqueue({ type: 'feature', feature });
}

export function trackArticleOpen(articleId: number): void {
  openArticles.set(articleId, Date.now());
  enqueue({ type: 'article_open', article_id: articleId });
}

export function trackArticleClose(articleId: number): void {
  const openedAt = openArticles.get(articleId);
  if (openedAt === undefined) return;
  openArticles.delete(articleId);
  enqueue({
    type: 'article_close',
    article_id: articleId,
    duration_ms: Date.now() - openedAt,
  });
}

export function flush(useBeacon = false): void {
  if (queue.length === 0) return;
  const events = queue;
  queue = [];
  const body = JSON.stringify({ events });

  if (useBeacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
    return;
  }

  void fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body,
    keepalive: true,
  }).catch(() => {
    // Telemetry is best-effort; drop on failure rather than disrupt the app.
  });
}

function handleVisibility(): void {
  if (isVisible()) {
    lastBeatAt = Date.now();
  } else {
    beat();
    flush(true);
  }
}

function handlePageHide(): void {
  flush(true);
}

export function startAnalytics(): void {
  // Never emit telemetry under the test runner — it would issue real network
  // calls from any component test that mounts the app shell.
  if (started || typeof window === 'undefined' || import.meta.env.MODE === 'test') return;
  started = true;
  lastBeatAt = Date.now();
  heartbeatTimer = setInterval(beat, HEARTBEAT_MS);
  flushTimer = setInterval(() => flush(), FLUSH_MS);
  document.addEventListener('visibilitychange', handleVisibility);
  window.addEventListener('pagehide', handlePageHide);
}

export function stopAnalytics(): void {
  if (!started) return;
  started = false;
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (flushTimer) clearInterval(flushTimer);
  heartbeatTimer = null;
  flushTimer = null;
  document.removeEventListener('visibilitychange', handleVisibility);
  window.removeEventListener('pagehide', handlePageHide);
  flush(true);
}
