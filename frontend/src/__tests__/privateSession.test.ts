import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  changePrivateSession,
  privateSessionEpoch,
  privateSessionChanged,
} from '../lib/privateSession';
import { requestJson, sessionExpiredEvent } from '../api/core';
import { logoutUser } from '../api/auth';

beforeEach(async () => {
  localStorage.clear();
  await changePrivateSession(1);
});
afterEach(() => vi.restoreAllMocks());

describe('private session boundary', () => {
  it('does not let unavailable browser storage prevent local revocation', async () => {
    const fail = () => {
      throw new Error('storage denied');
    };
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(fail);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(fail);
    await expect(changePrivateSession(null)).resolves.toBeUndefined();
    expect(privateSessionEpoch()).toBeNull();
  });
  it('keeps an established account index until identity changes, and clears the reader list', async () => {
    const epoch = privateSessionEpoch();
    localStorage.setItem('offline-articles:index:v1', 'private A index');
    sessionStorage.setItem('reader_list', 'private A list');
    await changePrivateSession(1);
    expect(privateSessionEpoch()).toBe(epoch);
    expect(localStorage.getItem('offline-articles:index:v1')).toBe('private A index');
    await changePrivateSession(2);
    expect(privateSessionEpoch()).not.toBe(epoch);
    expect(localStorage.getItem('offline-articles:index:v1')).toBeNull();
    expect(sessionStorage.getItem('reader_list')).toBeNull();
  });

  it('revokes reads and notifies in-memory consumers when another tab changes identity', () => {
    const changed = vi.fn();
    window.addEventListener(privateSessionChanged, changed);
    localStorage.setItem('nd-private-session:v2', 'other-tab-session');
    window.dispatchEvent(new StorageEvent('storage', { key: 'nd-private-session:v2' }));
    expect(privateSessionEpoch()).toBeNull();
    expect(changed).toHaveBeenCalledOnce();
    window.removeEventListener(privateSessionChanged, changed);
  });

  it.each([200, 401])(
    'rejects delayed A responses (%s) without expiring the new B session',
    async (status) => {
      let release!: (response: Response) => void;
      vi.spyOn(globalThis, 'fetch').mockImplementation(
        () =>
          new Promise((resolve) => {
            release = resolve;
          })
      );
      const expired = vi.fn();
      window.addEventListener(sessionExpiredEvent, expired);
      const request = requestJson('/api/articles');
      const rejected = expect(request).rejects.toThrow('Session changed');
      await changePrivateSession(null);
      await changePrivateSession(2);
      release(new Response('{}', { status }));
      await rejected;
      expect(expired).not.toHaveBeenCalled();
      expect(privateSessionEpoch()).not.toBeNull();
      window.removeEventListener(sessionExpiredEvent, expired);
    }
  );

  it('does not expire B when an old A 401 body finishes decoding after identity changes', async () => {
    let finish!: () => void;
    let decoding!: () => void;
    const started = new Promise<void>((resolve) => {
      decoding = resolve;
    });
    const response = new Response('', { status: 401 });
    vi.spyOn(response, 'json').mockImplementation(() => {
      decoding();
      return new Promise((resolve) => {
        finish = () => resolve({ detail: 'A expired' });
      });
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
    const expired = vi.fn();
    window.addEventListener(sessionExpiredEvent, expired);
    try {
      const rejected = expect(requestJson('/api/sources')).rejects.toThrow('Session changed');
      await started;
      await changePrivateSession(null);
      await changePrivateSession(2);
      const b = privateSessionEpoch();
      finish();
      await rejected;
      expect(expired).not.toHaveBeenCalled();
      expect(privateSessionEpoch()).toBe(b);
      expect(b).not.toBeNull();
    } finally {
      window.removeEventListener(sessionExpiredEvent, expired);
    }
  });

  it('forgets local private state even when remote logout fails offline', async () => {
    localStorage.setItem('offline-articles:index:v1', 'private A index');
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ provider: 'password' })))
      .mockRejectedValueOnce(new Error('offline'));
    await expect(logoutUser()).rejects.toThrow('offline');
    expect(privateSessionEpoch()).toBeNull();
    expect(localStorage.getItem('offline-articles:index:v1')).toBeNull();
  });
});
