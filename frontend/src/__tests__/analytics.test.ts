import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  flush,
  startAnalytics,
  stopAnalytics,
  trackArticleClose,
  trackArticleOpen,
  trackFeature,
  trackRoute,
} from '../lib/analytics';
import { secondaryNavigationItemsFor } from '../lib/navigation';

describe('analytics tracker', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    flush(); // drain any leftover queue
    vi.unstubAllGlobals();
  });

  type FetchCall = [string, RequestInit];

  function calls(): FetchCall[] {
    return fetchMock.mock.calls as FetchCall[];
  }

  function lastBody(): { events: { type: string; [k: string]: unknown }[] } {
    const init = calls().at(-1)?.[1];
    return JSON.parse(init?.body as string) as {
      events: { type: string; [k: string]: unknown }[];
    };
  }

  it('posts queued events to /api/events on flush', () => {
    trackRoute('/today');
    trackFeature('ask');
    flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = calls()[0];
    expect(url).toBe('/api/events');
    expect(init.method).toBe('POST');
    const { events } = lastBody();
    expect(events).toEqual([
      { type: 'route', route: '/today' },
      { type: 'feature', feature: 'ask' },
    ]);
  });

  it('does not call fetch when the queue is empty', () => {
    flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('emits article_close with a dwell duration after open', () => {
    trackArticleOpen(42);
    trackArticleClose(42);
    flush();

    const { events } = lastBody();
    const close = events.find((e) => e.type === 'article_close');
    expect(close?.article_id).toBe(42);
    expect(typeof close?.duration_ms).toBe('number');
  });

  it('ignores a close for an article that was never opened', () => {
    trackArticleClose(999);
    flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('analytics pagehide lifecycle', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const registered: EventListener[] = [];
  const unregistered: EventListener[] = [];
  let origAdd: typeof window.addEventListener;
  let origRemove: typeof window.removeEventListener;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubEnv('MODE', 'production');
    registered.length = 0;
    unregistered.length = 0;
    origAdd = window.addEventListener.bind(window);
    origRemove = window.removeEventListener.bind(window);
    window.addEventListener = (
      type: string,
      listener: EventListenerOrEventListenerObject,
      options?: boolean | AddEventListenerOptions
    ): void => {
      if (type === 'pagehide') registered.push(listener as EventListener);
      origAdd(type, listener, options);
    };
    window.removeEventListener = (
      type: string,
      listener: EventListenerOrEventListenerObject,
      options?: boolean | EventListenerOptions
    ): void => {
      if (type === 'pagehide') unregistered.push(listener as EventListener);
      origRemove(type, listener, options);
    };
  });

  afterEach(() => {
    window.addEventListener = origAdd;
    window.removeEventListener = origRemove;
    stopAnalytics();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('registers a pagehide listener on start', () => {
    startAnalytics();
    expect(registered).toHaveLength(1);
    expect(typeof registered[0]).toBe('function');
  });

  it('removes the same pagehide handler on stop', () => {
    startAnalytics();
    const added = registered[0];
    stopAnalytics();
    expect(unregistered[0]).toBe(added);
  });

  it('does not accumulate pagehide listeners across start/stop cycles', () => {
    startAnalytics();
    stopAnalytics();
    registered.length = 0;
    startAnalytics();
    expect(registered).toHaveLength(1);
  });

  it('fires flush via beacon on pagehide after start', () => {
    const beaconMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal('navigator', { sendBeacon: beaconMock });
    trackRoute('/test');
    startAnalytics();
    window.dispatchEvent(new Event('pagehide'));
    expect(beaconMock).toHaveBeenCalledTimes(1);
  });

  it('does not fire flush on pagehide after stop', () => {
    const beaconMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal('navigator', { sendBeacon: beaconMock });
    startAnalytics();
    stopAnalytics();
    // beacon called once by stopAnalytics flush; reset counter
    beaconMock.mockClear();
    trackRoute('/test');
    window.dispatchEvent(new Event('pagehide'));
    expect(beaconMock).not.toHaveBeenCalled();
  });
});

describe('analytics navigation', () => {
  it('exposes the analytics route to admins only', () => {
    const adminRoutes = secondaryNavigationItemsFor(true).map((i) => i.to);
    const userRoutes = secondaryNavigationItemsFor(false).map((i) => i.to);
    expect(adminRoutes).toContain('/analytics');
    expect(userRoutes).not.toContain('/analytics');
  });
});
