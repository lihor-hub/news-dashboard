// Optional, opt-in Sentry/GlitchTip error tracking. The DSN is served by the
// backend's public GET /api/config (self-hosters set SENTRY_DSN_FRONTEND);
// when unset, the SDK is never imported and no telemetry leaves the browser.

interface PublicConfig {
  sentry_dsn: string | null;
}

export async function initErrorTracking(): Promise<void> {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    const config = (await res.json()) as PublicConfig;
    if (!config.sentry_dsn) return;

    const Sentry = await import('@sentry/react');
    Sentry.init({ dsn: config.sentry_dsn, sendDefaultPii: true });
  } catch {
    // Network/parse failures must never block app startup.
  }
}
