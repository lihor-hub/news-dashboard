// @vitest-environment happy-dom
/**
 * Unit tests for the push-handler.js service worker logic.
 *
 * We load the JS file in a mocked service worker global context and verify
 * that push payloads are handled correctly and notification clicks route to
 * the right URL.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createContext, runInContext } from 'node:vm';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Minimal SW global mocks ────────────────────────────────────────────────────

type EventHandler = (event: MockEvent) => void;

interface MockEvent {
  type: string;
  data?: { json: () => unknown };
  notification?: { close: () => void; data?: { url?: string } };
  waitUntil: (p: Promise<unknown>) => void;
}

const handlers: Record<string, EventHandler[]> = {};

const mockSelf = {
  addEventListener(type: string, handler: EventHandler) {
    if (!handlers[type]) handlers[type] = [];
    handlers[type].push(handler);
  },
  registration: {
    showNotification: vi.fn().mockResolvedValue(undefined),
  },
};

const mockClients = {
  matchAll: vi.fn(),
  openWindow: vi.fn().mockResolvedValue(null),
};

// Install globals before loading the script
Object.assign(globalThis, {
  self: mockSelf,
  clients: mockClients,
});

// Load the push handler script once
const handlerCode = readFileSync(resolve(process.cwd(), 'public/push-handler.js'), 'utf-8');

// Execute the service worker script in an isolated VM context with our mocks.
const ctx = createContext({ self: mockSelf, clients: mockClients });
runInContext(handlerCode, ctx);

function fireEvent(type: string, event: MockEvent): void {
  for (const h of handlers[type] ?? []) h(event);
}

function makePushEvent(payload: unknown): MockEvent {
  return {
    type: 'push',
    data: { json: () => payload },
    waitUntil: vi.fn(),
  };
}

function makeNotificationClickEvent(notificationData: { url?: string }): MockEvent {
  return {
    type: 'notificationclick',
    notification: { close: vi.fn(), data: notificationData },
    waitUntil: vi.fn(),
  };
}

// ── push event tests ───────────────────────────────────────────────────────────

describe('push event — payload handling', () => {
  beforeEach(() => {
    mockSelf.registration.showNotification.mockClear();
  });

  it('shows notification with title and body from payload', () => {
    const ev = makePushEvent({ title: 'Hello', body: 'World', url: '/briefs/99' });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'Hello',
      expect.objectContaining({ body: 'World', data: { url: '/briefs/99' } })
    );
  });

  it('uses default title and body when payload has none', () => {
    const ev = makePushEvent({});
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'Daily Brief',
      expect.objectContaining({ body: 'Your daily brief is ready.' })
    );
  });

  it('stores / in notification data when no url in payload', () => {
    const ev = makePushEvent({ title: 'T', body: 'B' });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'T',
      expect.objectContaining({ data: { url: '/' } })
    );
  });

  it('rejects external URL in payload and falls back to /', () => {
    const ev = makePushEvent({ title: 'T', body: 'B', url: 'https://evil.example.com/' });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'T',
      expect.objectContaining({ data: { url: '/' } })
    );
  });

  it('uses explicit notification tag from payload', () => {
    const ev = makePushEvent({
      title: 'Shared',
      body: 'Article',
      url: '/shared',
      tag: 'shared-article',
    });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'Shared',
      expect.objectContaining({ tag: 'shared-article', data: { url: '/shared' } })
    );
  });

  it('keeps daily brief tag when payload has no tag', () => {
    const ev = makePushEvent({ title: 'Brief', body: 'Ready', url: '/briefs/99' });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'Brief',
      expect.objectContaining({ tag: 'daily-brief' })
    );
  });

  it('rejects unsafe notification tag and falls back to daily brief', () => {
    const ev = makePushEvent({ title: 'T', body: 'B', tag: '../../bad' });
    fireEvent('push', ev);
    expect(mockSelf.registration.showNotification).toHaveBeenCalledWith(
      'T',
      expect.objectContaining({ tag: 'daily-brief' })
    );
  });
});

// ── notificationclick event tests ─────────────────────────────────────────────

describe('notificationclick — URL routing', () => {
  beforeEach(() => {
    mockClients.matchAll.mockClear();
    mockClients.openWindow.mockClear();
  });

  it('opens the target URL when no matching window exists', async () => {
    mockClients.matchAll.mockResolvedValue([]);
    const ev = makeNotificationClickEvent({ url: '/briefs/42' });
    fireEvent('notificationclick', ev);
    await (ev.waitUntil as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(mockClients.openWindow).toHaveBeenCalledWith('/briefs/42');
  });

  it('focuses an existing client whose URL ends with the target', async () => {
    const focusMock = vi.fn().mockResolvedValue(null);
    mockClients.matchAll.mockResolvedValue([
      { url: 'http://localhost/briefs/42', focus: focusMock },
    ]);
    const ev = makeNotificationClickEvent({ url: '/briefs/42' });
    fireEvent('notificationclick', ev);
    await (ev.waitUntil as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(focusMock).toHaveBeenCalled();
    expect(mockClients.openWindow).not.toHaveBeenCalled();
  });

  it('falls back to / when notification has no url data', async () => {
    mockClients.matchAll.mockResolvedValue([]);
    const ev = makeNotificationClickEvent({});
    fireEvent('notificationclick', ev);
    await (ev.waitUntil as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(mockClients.openWindow).toHaveBeenCalledWith('/');
  });
});
