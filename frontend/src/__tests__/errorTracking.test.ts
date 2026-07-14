import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { ErrorEvent, EventHint } from '@sentry/react';

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

  it('inits Sentry with the DSN returned by the backend without default PII', async () => {
    const dsn = 'https://example@o0.ingest.sentry.io/1';
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ sentry_dsn: dsn }),
    });

    const { initErrorTracking } = await import('../lib/errorTracking');
    await initErrorTracking();

    expect(sentryInit).toHaveBeenCalledWith({
      dsn,
      sendDefaultPii: false,
      beforeSend: expect.any(Function),
    });
  });

  it('scrubs obvious PII before Sentry sends browser events', async () => {
    const dsn = 'https://example@o0.ingest.sentry.io/1';
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ sentry_dsn: dsn }),
    });

    const { initErrorTracking } = await import('../lib/errorTracking');
    await initErrorTracking();

    const options = sentryInit.mock.calls[0]?.[0] as
      { beforeSend?: (event: ErrorEvent, hint: EventHint) => ErrorEvent | null } | undefined;
    const event = {
      type: undefined,
      user: { email: 'reader@example.com' },
      request: {
        cookies: { session: 'secret' },
        headers: {
          Authorization: 'Bearer secret',
          Cookie: 'session=secret',
          Accept: 'application/json',
        },
      },
    } satisfies ErrorEvent;

    const scrubbed = options?.beforeSend?.(event, {});

    expect(scrubbed).toEqual({
      request: {
        headers: {
          Accept: 'application/json',
        },
      },
    });
  });

  it('does not throw when the config fetch fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network down'));

    const { initErrorTracking } = await import('../lib/errorTracking');
    await expect(initErrorTracking()).resolves.toBeUndefined();
    expect(sentryInit).not.toHaveBeenCalled();
  });
});
