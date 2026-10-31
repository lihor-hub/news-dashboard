/* Private responses belong to a revocable session, never to an origin-wide URL. */
const PRIVATE_META = 'nd-private-session-v2';
const PRIVATE_PREFIX = 'nd-private-v2-';
const PRIVATE_STATE = '/__nd_private_session';
const PRIVATE_LEGACY = ['offline-articles-v1', 'pwa-article-lists'];

async function privateState() {
  const response = await (await caches.open(PRIVATE_META)).match(PRIVATE_STATE);
  return response ? response.json() : { user: null, epoch: null };
}

async function privateCleanup(epoch) {
  await Promise.all((await caches.keys()).filter((name) =>
    PRIVATE_LEGACY.includes(name) ||
    (name.startsWith(PRIVATE_PREFIX) && !name.startsWith(PRIVATE_PREFIX + epoch + '-'))
  ).map((name) => caches.delete(name)));
}

function privateLock(fn) {
  // Fail closed on platforms without cross-context locking.
  if (!self.navigator.locks) return Promise.reject(new Error('Private offline storage unavailable'));
  return self.navigator.locks.request('nd-private-session', fn);
}

async function privateBinding(clientId) {
  const meta = await caches.open(PRIVATE_META);
  const response = await meta.match('/__nd_private_client/' + clientId);
  return response ? response.text() : null;
}

async function privateFetch(request, clientId) {
  const epoch = await privateLock(async () => {
    const state = await privateState();
    return state.epoch && await privateBinding(clientId) === state.epoch ? state.epoch : null;
  });
  if (!epoch) return new Response('', { status: 401 });
  let response;
  try {
    const network = await fetch(request);
    // Finish network streams before taking the lock needed to revoke this session.
    response = new Response(network.body ? await network.arrayBuffer() : null, network);
  } catch {
    response = null;
  }
  return privateLock(async () => {
    if ((await privateState()).epoch !== epoch) return new Response('', { status: 401 });
    if (response?.status === 401) {
      await (await caches.open(PRIVATE_META)).delete(PRIVATE_STATE);
      await privateCleanup(null);
      const tabs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      await Promise.all(tabs.map((tab) => tab.navigate('/login')));
      return response;
    }
    const body = new URL(request.url).pathname !== '/api/articles';
    const cache = await caches.open(PRIVATE_PREFIX + epoch + (body ? '-bodies' : '-lists'));
    if (response) {
      if (response.status === 200) {
        const headers = new Headers(response.headers);
        headers.set('X-ND-Cache-Time', String(Date.now()));
        await cache.put(request, new Response(response.clone().body, { status: 200, headers }));
        const keys = await cache.keys();
        if (keys.length > (body ? 100 : 24)) await cache.delete(keys[0]);
      } else {
        // A fresh denial must also revoke an older successful copy.
        await cache.delete(request);
      }
      return response;
    }
    const cached = await cache.match(request);
    const age = cached ? Date.now() - Number(cached.headers.get('X-ND-Cache-Time')) : Infinity;
    if (cached && age < (body ? 30 : 7) * 86400000) return cached;
    await cache.delete(request);
    return new Response('', { status: 503 });
  });
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (!(/^\/api\/articles\/\d+\/body$/.test(url.pathname) ||
    (url.pathname === '/api/articles' && !url.searchParams.has('include_archived')))) return;
  event.respondWith(privateFetch(event.request, event.clientId).catch(() => new Response('', { status: 503 })));
  event.stopImmediatePropagation();
});

self.addEventListener('message', (event) => {
  if (event.data?.type !== 'nd-private-session') return;
  const port = event.ports[0];
  event.waitUntil(privateLock(async () => {
    const previous = await privateState();
    const { user, revoke, expected } = event.data;
    // A tab whose session was revoked cannot bind itself to a newer account.
    if (!revoke && expected && previous.epoch && expected !== previous.epoch) throw new Error('Session changed');
    const state = !revoke && user !== null && previous.user === user && previous.epoch
      ? previous : { user: revoke ? null : user, epoch: !revoke && user !== null ? crypto.randomUUID() : null };
    const meta = await caches.open(PRIVATE_META);
    if (previous.epoch !== state.epoch || revoke) {
      // Delete the old authority before a replacement write that could fail (e.g. quota).
      await meta.delete(PRIVATE_STATE);
      await privateCleanup(null);
    }
    await meta.put(PRIVATE_STATE, new Response(JSON.stringify(state)));
    if (event.source?.id) {
      await meta.put('/__nd_private_client/' + event.source.id, new Response(state.epoch || ''));
    }
    await privateCleanup(state.epoch);
    if (previous.epoch !== state.epoch) {
      // Legacy pages have no revocation listener; navigation discards their old account memory.
      const tabs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      await Promise.all(tabs.filter((tab) => tab.id !== event.source?.id).map((tab) => tab.navigate('/login')));
    }
    port.postMessage({ epoch: state.epoch });
  }).catch(() => port.postMessage({ error: 'Private session transition failed' })));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(privateLock(async () => privateCleanup((await privateState()).epoch)));
});
