import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const sentryInit = vi.fn();
vi.mock('@sentry/react', () => ({ init: sentryInit }));

describe('initErrorTracking', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    sentryInit.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('does not init Sentry when the backend returns no DSN', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ sentry_dsn: null }),
    });

    const { initErrorTracking } = await import('../lib/errorTracking');
    await initErrorTracking();

    expect(sentryInit).not.toHaveBeenCalled();
  });

  it('inits Sentry with the DSN returned by the backend', async () => {
    const dsn = 'https://example@o0.ingest.sentry.io/1';
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ sentry_dsn: dsn }),
    });

    const { initErrorTracking } = await import('../lib/errorTracking');
    await initErrorTracking();

    expect(sentryInit).toHaveBeenCalledWith({ dsn, sendDefaultPii: true });
  });

  it('does not throw when the config fetch fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network down'));

    const { initErrorTracking } = await import('../lib/errorTracking');
    await expect(initErrorTracking()).resolves.toBeUndefined();
    expect(sentryInit).not.toHaveBeenCalled();
  });
});
