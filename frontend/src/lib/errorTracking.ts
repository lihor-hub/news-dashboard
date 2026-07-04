// Optional, opt-in Sentry/GlitchTip error tracking. The DSN is served by the
// backend's public GET /api/config (self-hosters set SENTRY_DSN_FRONTEND);
// when unset, the SDK is never imported and no telemetry leaves the browser.

interface PublicConfig {
  sentry_dsn: string | null;
}

let sentryEnabled = false;

export async function initErrorTracking(): Promise<void> {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    const config = (await res.json()) as PublicConfig;
    if (!config.sentry_dsn) return;

    const Sentry = await import('@sentry/react');
    Sentry.init({ dsn: config.sentry_dsn, sendDefaultPii: true });
    sentryEnabled = true;
  } catch {
    // Network/parse failures must never block app startup.
  }
}

// Reports a caught error to Sentry when it's enabled, otherwise logs to the
// console. Never throws, since this is called from render-error handlers.
export function reportError(error: unknown, context?: Record<string, unknown>): void {
  if (!sentryEnabled) {
    console.error(error, context);
    return;
  }
  void import('@sentry/react')
    .then((Sentry) => {
      Sentry.captureException(error, context ? { extra: context } : undefined);
    })
    .catch(() => {
      // Reporting must never throw from an error boundary.
    });
}
