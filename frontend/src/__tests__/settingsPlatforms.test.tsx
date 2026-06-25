// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/api', () => ({
  recalculateMyRecommendations: vi.fn(),
  fetchNotificationSettings: vi.fn().mockResolvedValue({
    briefing_time: '09:00',
    push_enabled: false,
    vapid_public_key: null,
  }),
  updateNotificationSettings: vi
    .fn()
    .mockResolvedValue({ briefing_time: '09:00', push_enabled: false }),
  subscribePush: vi.fn().mockResolvedValue({ subscribed: true }),
  unsubscribePush: vi.fn().mockResolvedValue({ unsubscribed: true }),
}));

import { SettingsPage } from '../pages/SettingsPage';

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  // Remove the electron shim between tests.
  delete (window as unknown as { electronAPI?: unknown }).electronAPI;
  sessionStorage.clear();
});

// ── Electron platform ────────────────────────────────────────────────────────

describe('SettingsPage on Electron', () => {
  type Cb<T> = (arg: T) => void;

  function installElectron(overrides: Record<string, unknown> = {}) {
    const handlers: Record<string, Cb<unknown>> = {};
    const api = {
      appVersion: '2.3.4',
      removeUpdateListeners: vi.fn(),
      onUpdateAvailable: (cb: Cb<{ version: string }>) => (handlers.available = cb as Cb<unknown>),
      onUpdateNotAvailable: (cb: Cb<void>) => (handlers.notAvailable = cb as Cb<unknown>),
      onDownloadProgress: (cb: Cb<{ percent: number }>) => (handlers.progress = cb as Cb<unknown>),
      onUpdateDownloaded: (cb: Cb<void>) => (handlers.downloaded = cb as Cb<unknown>),
      onUpdateError: (cb: Cb<string>) => (handlers.error = cb as Cb<unknown>),
      checkForUpdate: vi.fn(),
      downloadUpdate: vi.fn(),
      quitAndInstall: vi.fn(),
      ...overrides,
    };
    (window as unknown as { electronAPI: unknown }).electronAPI = api;
    return { api, handlers };
  }

  it('shows the current version and an up-to-date state', async () => {
    const { handlers } = installElectron();
    renderSettings();
    expect(screen.getByText('2.3.4')).toBeTruthy();
    handlers.notAvailable?.(undefined);
    await waitFor(() => expect(screen.getByText(/latest version/)).toBeTruthy());
  });

  it('walks the available → download → ready flow', async () => {
    const { api, handlers } = installElectron();
    renderSettings();

    handlers.available?.({ version: '9.9.9' });
    const download = await screen.findByText('Download update');
    fireEvent.click(download);
    expect(api.downloadUpdate).toHaveBeenCalled();

    handlers.progress?.({ percent: 42 });
    await waitFor(() => expect(screen.getByText(/42%/)).toBeTruthy());

    handlers.downloaded?.(undefined);
    const restart = await screen.findByText('Restart and install');
    fireEvent.click(restart);
    expect(api.quitAndInstall).toHaveBeenCalled();
  });

  it('shows an error and allows retry', async () => {
    const { api, handlers } = installElectron();
    renderSettings();
    handlers.error?.('update boom');
    await waitFor(() => expect(screen.getByText('update boom')).toBeTruthy());
    fireEvent.click(screen.getByText('Try again'));
    expect(api.checkForUpdate).toHaveBeenCalledTimes(2); // mount + retry
  });
});

// ── TWA platform ─────────────────────────────────────────────────────────────

describe('SettingsPage on TWA', () => {
  beforeEach(() => {
    sessionStorage.setItem('nd_platform', 'twa');
  });

  it('checks for updates and offers an APK download', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/api/version')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ version: '1.0.0' }) });
        }
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                tag_name: 'android-v2.0.0',
                html_url: 'https://gh/release',
                assets: [{ name: 'app.apk', browser_download_url: 'https://gh/app.apk' }],
              },
            ]),
        });
      })
    );
    renderSettings();
    fireEvent.click(screen.getByText('Check for updates'));
    const apk = await screen.findByText('Download APK');
    expect(apk.getAttribute('href')).toBe('https://gh/app.apk');
  });
});
