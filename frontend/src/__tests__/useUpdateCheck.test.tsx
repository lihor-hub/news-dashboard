// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useUpdateCheck } from '../hooks/useUpdateCheck';

// detectPlatform reads navigator/window; default (no electronAPI, no TWA) is 'web',
// which maps to the 'desktop-v' release prefix.

function mockFetch(handlers: Record<string, unknown>) {
  return vi.fn((url: string) => {
    const key = Object.keys(handlers).find((k) => url.includes(k));
    if (!key) return Promise.resolve({ ok: false, status: 404 });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(handlers[key]) });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('useUpdateCheck — web/GitHub flow', () => {
  it('reports an available update when the latest tag is newer', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/api/version': { version: '1.0.0' },
        '/releases': [
          { tag_name: 'desktop-v2.0.0', html_url: 'https://gh/r/2', assets: [] },
          { tag_name: 'android-v9.0.0', html_url: 'https://gh/r/a', assets: [] },
        ],
      })
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.info?.updateAvailable).toBe(true);
    expect(result.current.info?.latestVersion).toBe('2.0.0');
    expect(result.current.info?.releaseUrl).toBe('https://gh/r/2');
    expect(result.current.loading).toBe(false);
  });

  it('reports no update when there is no matching release', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/api/version': { version: '1.0.0' },
        '/releases': [{ tag_name: 'android-v9.0.0', html_url: 'https://gh/r/a', assets: [] }],
      })
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.info?.updateAvailable).toBe(false);
    expect(result.current.info?.latestVersion).toBe('1.0.0');
  });

  it('records an error when the version API fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.error).toBeTruthy();
    expect(result.current.loading).toBe(false);
  });
});

describe('useUpdateCheck — TWA flow', () => {
  beforeEach(() => {
    // Simulate TWA platform via sessionStorage
    sessionStorage.setItem('nd_platform', 'twa');
  });

  afterEach(() => {
    sessionStorage.removeItem('nd_platform');
  });

  it('reports update available when an APK asset exists (regardless of server version)', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/releases': [
          {
            tag_name: 'android-v2.0.0',
            html_url: 'https://gh/r/android',
            assets: [{ name: 'app.apk', browser_download_url: 'https://gh/app.apk' }],
          },
        ],
      })
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.info?.updateAvailable).toBe(true);
    expect(result.current.info?.apkUrl).toBe('https://gh/app.apk');
    expect(result.current.info?.currentVersion).toBeNull();
    expect(result.current.info?.installedVersionKnown).toBe(false);
    // The API should NOT have called /api/version for TWA
    expect(
      vi.mocked(fetch).mock.calls.filter(([url]) => (url as string).includes('/api/version'))
    ).toHaveLength(0);
  });

  it('reports no update when no matching Android release exists', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/releases': [{ tag_name: 'desktop-v9.9.9', html_url: 'https://gh/r/d', assets: [] }],
      })
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.info?.updateAvailable).toBe(false);
    expect(result.current.info?.apkUrl).toBeNull();
    expect(result.current.info?.currentVersion).toBeNull();
    expect(result.current.info?.installedVersionKnown).toBe(false);
  });

  it('reports no update when Android release has no APK asset', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        '/releases': [
          {
            tag_name: 'android-v3.0.0',
            html_url: 'https://gh/r/android',
            assets: [],
          },
        ],
      })
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.info?.updateAvailable).toBe(false);
    expect(result.current.info?.apkUrl).toBeNull();
    expect(result.current.info?.currentVersion).toBeNull();
    expect(result.current.info?.installedVersionKnown).toBe(false);
  });

  it('never fetches /api/version for TWA', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }))
    );
    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await result.current.check();
    });
    const calls = vi.mocked(fetch).mock.calls as [string][];
    const versionCalls = calls.filter(([url]) => url.includes('/api/version'));
    expect(versionCalls).toHaveLength(0);
  });
});

describe('useUpdateCheck — Electron IPC flow', () => {
  type Cb<T> = (arg: T) => void;
  let listeners: Record<string, Cb<unknown>>;

  beforeEach(() => {
    listeners = {};
    const api = {
      removeUpdateListeners: vi.fn(),
      onUpdateAvailable: vi.fn((cb: Cb<{ version: string }>) => {
        listeners.available = cb as Cb<unknown>;
      }),
      onUpdateNotAvailable: vi.fn((cb: Cb<void>) => {
        listeners.notAvailable = cb as Cb<unknown>;
      }),
      onDownloadProgress: vi.fn((cb: Cb<{ percent: number }>) => {
        listeners.progress = cb as Cb<unknown>;
      }),
      onUpdateDownloaded: vi.fn((cb: Cb<void>) => {
        listeners.downloaded = cb as Cb<unknown>;
      }),
      onUpdateError: vi.fn((cb: Cb<string>) => {
        listeners.error = cb as Cb<unknown>;
      }),
      checkForUpdate: vi.fn(),
      downloadUpdate: vi.fn(),
      quitAndInstall: vi.fn(),
    };
    vi.stubGlobal('electronAPI', api);
    (window as unknown as { electronAPI: typeof api }).electronAPI = api;
  });

  afterEach(() => {
    delete (window as unknown as { electronAPI?: unknown }).electronAPI;
  });

  it('drives stage transitions from IPC events', () => {
    const { result } = renderHook(() => useUpdateCheck());

    act(() => result.current.checkElectron());
    expect(result.current.electronStage).toBe('checking');

    act(() => listeners.available({ version: '3.1.0' }));
    expect(result.current.electronStage).toBe('available');
    expect(result.current.electronLatestVersion).toBe('3.1.0');

    act(() => (listeners.progress as Cb<{ percent: number }>)({ percent: 42.6 }));
    expect(result.current.electronStage).toBe('downloading');
    expect(result.current.downloadPercent).toBe(43);

    act(() => listeners.downloaded(undefined));
    expect(result.current.electronStage).toBe('ready');

    act(() => (listeners.error as Cb<string>)('boom'));
    expect(result.current.electronStage).toBe('error');
    expect(result.current.error).toBe('boom');
  });

  it('forwards download and install actions to the Electron API', () => {
    const { result } = renderHook(() => useUpdateCheck());
    const api = (
      window as unknown as {
        electronAPI: { downloadUpdate: () => void; quitAndInstall: () => void };
      }
    ).electronAPI;

    act(() => result.current.downloadElectronUpdate());
    expect(api.downloadUpdate).toHaveBeenCalled();
    expect(result.current.electronStage).toBe('downloading');

    act(() => result.current.installElectronUpdate());
    expect(api.quitAndInstall).toHaveBeenCalled();
  });
});
