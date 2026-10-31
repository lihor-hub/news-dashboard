// @vitest-environment node
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { randomUUID } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';

function worker() {
  const stores = new Map<string, Map<string, Response>>();
  let quotaFailure = false;
  const cacheStorage = {
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    open: async (name: string) => {
      if (!stores.has(name)) stores.set(name, new Map());
      const entries = stores.get(name)!;
      const key = (request: string | Request) =>
        typeof request === 'string' ? request : request.url;
      return {
        match: async (request: string | Request) => entries.get(key(request))?.clone(),
        put: async (request: string | Request, response: Response) => {
          if (quotaFailure && name === 'nd-private-session-v2') throw new Error('quota');
          entries.set(key(request), new Response(await response.arrayBuffer(), response));
        },
        delete: async (request: string | Request) => entries.delete(key(request)),
        keys: async () => [...entries.keys()],
      };
    },
  };
  const listeners = new Map<string, (event: unknown) => void>();
  let pending = Promise.resolve();
  const fetch = vi.fn<() => Promise<Response>>().mockResolvedValue(new Response('PRIVATE_A'));
  runInNewContext(readFileSync('public/private-cache-worker.js', 'utf8'), {
    caches: cacheStorage,
    fetch,
    Response,
    Headers,
    Date,
    URL,
    crypto: { randomUUID },
    self: {
      location: { origin: 'https://fixture.test' },
      clients: { matchAll: async () => [] },
      navigator: {
        locks: {
          request: (_name: string, fn: () => Promise<void>) => {
            const next = pending.then(fn);
            pending = next.catch(() => {});
            return next;
          },
        },
      },
      addEventListener: (name: string, fn: (event: unknown) => void) => listeners.set(name, fn),
    },
  });
  const bind = (user: number | null, client = 'tab-a', expected?: string) =>
    new Promise<{ epoch: string; error?: string }>((resolve) => {
      listeners.get('message')!({
        data: { type: 'nd-private-session', user, revoke: user === null, expected },
        source: { id: client },
        ports: [{ postMessage: resolve }],
        waitUntil: () => {},
      });
    });
  const get = (clientId = 'tab-a', path = '/api/articles/991/body') =>
    new Promise<Response>((resolve) => {
      listeners.get('fetch')!({
        request: new Request('https://fixture.test' + path),
        clientId,
        respondWith: (response: Promise<Response>) => resolve(response),
        stopImmediatePropagation: () => {},
      });
    });
  return {
    stores,
    fetch,
    bind,
    get,
    failWrites: () => {
      quotaFailure = true;
    },
  };
}

describe('generated worker private cache handler', () => {
  it('revokes all private caches when the server reports session expiry', async () => {
    const w = worker();
    await w.bind(1);
    await w.get();
    await w.get('tab-a', '/api/articles');
    w.fetch.mockResolvedValue(new Response('', { status: 401 }));
    expect((await w.get()).status).toBe(401);
    w.fetch.mockRejectedValue(new Error('offline'));
    expect((await w.get('tab-a', '/api/articles')).status).toBe(401);
    expect([...w.stores.keys()].some((name) => name.startsWith('nd-private-v2-'))).toBe(false);
  });

  it('preserves the existing 30-day body and 7-day list expiration', async () => {
    const w = worker();
    await w.bind(1);
    await w.get();
    await w.get('tab-a', '/api/articles');
    w.fetch.mockRejectedValue(new Error('offline'));
    const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 8 * 86400000);
    try {
      expect((await w.get()).status).toBe(200);
      expect((await w.get('tab-a', '/api/articles')).status).toBe(503);
      clock.mockReturnValue(Date.now() + 31 * 86400000);
      expect((await w.get()).status).toBe(503);
    } finally {
      clock.mockRestore();
    }
  });
  it('revokes old authority even when persisting the new state fails', async () => {
    const w = worker();
    await w.bind(1);
    await w.get();
    w.failWrites();
    expect((await w.bind(null)).error).toBeTruthy();
    expect((await w.get()).status).toBe(401);
    expect([...w.stores.keys()].some((name) => name.startsWith('nd-private-v2-'))).toBe(false);
  });
  it('keeps same-account offline reads, forgets legacy/body/list caches on logout, preserves static assets', async () => {
    const w = worker();
    w.stores.set('pwa-images', new Map());
    w.stores.set('offline-articles-v1', new Map());
    w.stores.set('pwa-article-lists', new Map());
    await w.bind(1);
    expect(w.stores.has('offline-articles-v1')).toBe(false);
    expect(await (await w.get()).text()).toBe('PRIVATE_A');
    await w.get('tab-a', '/api/articles');
    w.fetch.mockRejectedValue(new Error('offline'));
    expect(await (await w.get()).text()).toBe('PRIVATE_A');
    await w.bind(null);
    expect((await w.get()).status).toBe(401);
    expect([...w.stores.keys()].filter((key) => key.startsWith('nd-private-v2-'))).toEqual([]);
    expect(w.stores.has('pwa-images')).toBe(true);
    await w.bind(1);
    expect((await w.get()).status).toBe(503); // Signing back in requires a fresh download.
  });

  it('denies B and unbound/old tabs, including when A network writes finish after logout', async () => {
    const w = worker();
    const a = await w.bind(1);
    await w.bind(1, 'tab-old');
    let release!: (response: Response) => void;
    w.fetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    const delayed = w.get();
    await vi.waitFor(() => expect(release).toBeDefined());
    await w.bind(null);
    await w.bind(2, 'tab-b');
    release(new Response('PRIVATE_A'));
    expect((await delayed).status).toBe(401);
    expect((await w.get('tab-old')).status).toBe(401);
    expect((await w.get('anonymous')).status).toBe(401);
    expect((await w.bind(1, 'tab-old', a.epoch)).error).toBeTruthy();
    w.fetch.mockResolvedValue(new Response('', { status: 404 }));
    expect((await w.get('tab-b')).status).toBe(404);
    w.fetch.mockRejectedValue(new Error('offline'));
    expect((await w.get('tab-b')).status).toBe(503);
  });

  it.each(['/api/articles/991/body', '/api/articles'])(
    'allows logout while a response body is streaming for %s and denies its late publication',
    async (path) => {
      const w = worker();
      await w.bind(1);
      let finish!: () => void;
      w.fetch.mockResolvedValueOnce(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode('PRIVATE_A'));
              finish = () => controller.close();
            },
          })
        )
      );
      const delayed = w.get('tab-a', path);
      await vi.waitFor(() => expect(w.fetch).toHaveBeenCalledOnce());
      // Revocation and B establishment must finish before the network body does.
      await w.bind(null);
      await w.bind(2, 'tab-b');
      finish();
      expect((await delayed).status).toBe(401);
      expect([...w.stores.keys()].some((name) => name.startsWith('nd-private-v2-'))).toBe(false);
      w.fetch.mockRejectedValue(new Error('offline'));
      expect((await w.get('tab-b', path)).status).toBe(503);
    }
  );

  it('removes a previously cached success after an online permission denial', async () => {
    const w = worker();
    await w.bind(1);
    await w.get();
    w.fetch.mockResolvedValue(new Response('', { status: 404 }));
    expect((await w.get()).status).toBe(404);
    w.fetch.mockRejectedValue(new Error('offline'));
    expect((await w.get()).status).toBe(503);
  });
});
