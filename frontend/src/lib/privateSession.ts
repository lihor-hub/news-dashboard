const SESSION_KEY = 'nd-private-session:v2';
const INDEX_KEY = 'offline-articles:index:v1';
export const privateSessionChanged = 'nd-private-session-changed';
let epoch: string | null = null;
let revision = 0;
let transition = Promise.resolve();
let currentUser: number | null = null;

export function privateSessionRevision(): number {
  return revision;
}

function storedEpoch(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function storeEpoch(value: string | null): void {
  try {
    localStorage.setItem(SESSION_KEY, value ?? crypto.randomUUID());
  } catch {
    // Offline index access stays disabled; still revoke the worker and other tabs.
  }
}

export function privateSessionEpoch(): string | null {
  return epoch && storedEpoch() === epoch ? epoch : null;
}

function forgetLocal(): void {
  epoch = null;
  revision += 1;
  try {
    localStorage.removeItem(INDEX_KEY);
  } catch {
    /* Storage unavailable. */
  }
  try {
    sessionStorage.removeItem('reader_list');
  } catch {
    /* Storage unavailable. */
  }
  window.dispatchEvent(new Event('nd-private-data-cleared'));
}

export function forgetPrivatePage(): void {
  currentUser = null;
  forgetLocal();
  window.dispatchEvent(new Event(privateSessionChanged));
}

export function changePrivateSession(user: number | null): Promise<void> {
  const previousUser = currentUser;
  currentUser = user;
  const expected = epoch;
  if (user === null || (previousUser !== null && previousUser !== user)) {
    forgetLocal();
    storeEpoch(null);
  }
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) {
    if (user !== previousUser || !privateSessionEpoch()) {
      forgetLocal();
      epoch = user === null ? null : crypto.randomUUID();
      storeEpoch(epoch);
    }
    return Promise.resolve();
  }
  const operation = async () => {
    const registration = await navigator.serviceWorker.ready;
    const worker = registration.active;
    if (!worker) throw new Error('Offline session unavailable');
    const next = await new Promise<string | null>((resolve, reject) => {
      const channel = new MessageChannel();
      const timeout = setTimeout(() => {
        channel.port1.close();
        reject(new Error('Reload to update offline session protection'));
      }, 10000);
      channel.port1.onmessage = (event: MessageEvent<{ epoch: string | null; error?: string }>) => {
        clearTimeout(timeout);
        channel.port1.close();
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data.epoch);
      };
      worker.postMessage(
        {
          type: 'nd-private-session',
          user,
          revoke: user === null,
          expected: user === null ? null : expected,
        },
        [channel.port2]
      );
    });
    if (next && storedEpoch() !== next) forgetLocal();
    epoch = next;
    storeEpoch(next);
  };
  transition = transition.catch(() => {}).then(operation);
  return transition;
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (currentUser !== null)
      void changePrivateSession(currentUser).catch(() => {
        forgetLocal();
        window.dispatchEvent(new Event(privateSessionChanged));
      });
  });
}

window.addEventListener('storage', (event) => {
  if (event.key !== SESSION_KEY) return;
  forgetPrivatePage();
});
