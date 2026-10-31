import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

let session: typeof import('../lib/privateSession');
const controller = new EventTarget();
const postMessage = vi.fn();
const worker = { postMessage };
const registration = { active: worker as typeof worker | null };
let acknowledge: (data: { epoch: string | null; error?: string }) => void;
const close = vi.fn();

function installWorker() {
  vi.stubEnv('PROD', true);
  vi.stubGlobal('navigator', {
    serviceWorker: {
      ready: Promise.resolve(registration),
      addEventListener: controller.addEventListener.bind(controller),
    },
  });
  vi.stubGlobal(
    'MessageChannel',
    class {
      port1 = { onmessage: null as ((event: unknown) => void) | null, close };
      port2 = { reply: (data: unknown) => this.port1.onmessage?.({ data }) };
    }
  );
}

beforeAll(async () => {
  installWorker();
  session = await import('../lib/privateSession');
});

beforeEach(async () => {
  installWorker();
  registration.active = worker;
  postMessage.mockImplementation((message, ports) =>
    ports[0].reply({ epoch: message.revoke ? null : 'worker-A' })
  );
  await session.changePrivateSession(null);
  await session.changePrivateSession(1);
  postMessage.mockImplementation((_message, ports) => {
    acknowledge = ports[0].reply;
  });
  postMessage.mockClear();
  close.mockClear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
afterAll(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('production private-session worker acknowledgement', () => {
  it('waits for the worker before exposing a new identity and clears prior private data', async () => {
    localStorage.setItem('offline-articles:index:v1', 'A index');
    sessionStorage.setItem('reader_list', 'A list');
    const pending = session.changePrivateSession(2);
    expect(session.privateSessionEpoch()).toBeNull();
    expect(localStorage.getItem('offline-articles:index:v1')).toBeNull();
    expect(sessionStorage.getItem('reader_list')).toBeNull();
    await vi.waitFor(() =>
      expect(postMessage).toHaveBeenLastCalledWith(
        { type: 'nd-private-session', user: 2, revoke: false, expected: 'worker-A' },
        expect.any(Array)
      )
    );
    acknowledge({ epoch: 'worker-B' });
    await pending;
    expect(session.privateSessionEpoch()).toBe('worker-B');
    expect(localStorage.getItem('nd-private-session:v2')).toBe('worker-B');
    expect(close).toHaveBeenCalledOnce();
  });

  it('clears an index when the worker replaces the epoch for the same account', async () => {
    localStorage.setItem('offline-articles:index:v1', 'old worker index');
    const pending = session.changePrivateSession(1);
    await vi.waitFor(() => expect(postMessage).toHaveBeenCalledOnce());
    acknowledge({ epoch: 'worker-new' });
    await pending;
    expect(localStorage.getItem('offline-articles:index:v1')).toBeNull();
    expect(session.privateSessionEpoch()).toBe('worker-new');
  });

  it('rejects missing active workers and allows the next transition to recover', async () => {
    registration.active = null;
    await expect(session.changePrivateSession(2)).rejects.toThrow('Offline session unavailable');
    expect(session.privateSessionEpoch()).toBeNull();
    registration.active = worker;
    postMessage.mockImplementation((_message, ports) => ports[0].reply({ epoch: 'recovered-B' }));
    await session.changePrivateSession(2);
    expect(session.privateSessionEpoch()).toBe('recovered-B');
  });

  it('propagates worker rejection without restoring a revoked identity', async () => {
    postMessage.mockImplementation((_message, ports) =>
      ports[0].reply({ epoch: null, error: 'stale client' })
    );
    await expect(session.changePrivateSession(2)).rejects.toThrow('stale client');
    expect(session.privateSessionEpoch()).toBeNull();
    expect(close).toHaveBeenCalledOnce();
  });

  it('times out unacknowledged transitions and closes the port', async () => {
    vi.useFakeTimers();
    const pending = expect(session.changePrivateSession(2)).rejects.toThrow(
      'Reload to update offline session protection'
    );
    await vi.advanceTimersByTimeAsync(10000);
    await pending;
    expect(close).toHaveBeenCalledOnce();
    expect(session.privateSessionEpoch()).toBeNull();
  });

  it('revokes page memory when a replacement controller cannot establish protection', async () => {
    const changed = vi.fn();
    window.addEventListener(session.privateSessionChanged, changed);
    postMessage.mockImplementation((_message, ports) =>
      ports[0].reply({ epoch: null, error: 'legacy worker' })
    );
    try {
      controller.dispatchEvent(new Event('controllerchange'));
      await vi.waitFor(() => expect(changed).toHaveBeenCalledOnce());
      expect(session.privateSessionEpoch()).toBeNull();
    } finally {
      window.removeEventListener(session.privateSessionChanged, changed);
    }
  });

  it('does not renew a controller session after logout', async () => {
    postMessage.mockImplementation((_message, ports) => ports[0].reply({ epoch: null }));
    await session.changePrivateSession(null);
    postMessage.mockClear();
    controller.dispatchEvent(new Event('controllerchange'));
    await Promise.resolve();
    expect(postMessage).not.toHaveBeenCalled();
    expect(session.privateSessionEpoch()).toBeNull();
  });
});
