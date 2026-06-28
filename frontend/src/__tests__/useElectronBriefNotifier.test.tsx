// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const { mockFetchSettings, mockFetchLatestBriefing } = vi.hoisted(() => ({
  mockFetchSettings: vi.fn(),
  mockFetchLatestBriefing: vi.fn(),
}));

vi.mock('@/api', () => ({
  fetchNotificationSettings: mockFetchSettings,
  fetchLatestBriefing: mockFetchLatestBriefing,
}));

import { useElectronBriefNotifier } from '../hooks/useElectronBriefNotifier';

const completeBriefing = {
  id: 42,
  status: 'complete' as const,
  title: 'Morning Brief',
  summary: 'Headlines for today',
  created_at: '',
  scope: 'global',
  since_at: '',
  until_at: '',
  content: null,
  model: 'gpt-4',
  error: null,
  articles: [],
};

function makeElectronAPI() {
  return {
    platform: 'electron' as const,
    appVersion: '1.0.0',
    checkForUpdate: vi.fn(),
    downloadUpdate: vi.fn(),
    quitAndInstall: vi.fn(),
    onUpdateAvailable: vi.fn(),
    onUpdateNotAvailable: vi.fn(),
    onUpdateDownloaded: vi.fn(),
    onUpdateError: vi.fn(),
    onDownloadProgress: vi.fn(),
    removeUpdateListeners: vi.fn(),
    showNotification: vi.fn(),
    onNotificationClick: vi.fn(),
    removeNotificationClickListener: vi.fn(),
  };
}

beforeEach(() => {
  localStorage.clear();
  mockFetchSettings.mockResolvedValue({
    briefing_time: '09:00',
    push_enabled: true,
    vapid_public_key: null,
  });
  mockFetchLatestBriefing.mockResolvedValue(completeBriefing);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  delete (window as unknown as { electronAPI?: unknown }).electronAPI;
  localStorage.clear();
});

describe('useElectronBriefNotifier', () => {
  it('does nothing when not running in Electron', async () => {
    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));
    await vi.waitFor(() => expect(mockFetchSettings).not.toHaveBeenCalled());
    expect(mockFetchLatestBriefing).not.toHaveBeenCalled();
  });

  it('shows a notification for a new complete briefing', async () => {
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    await vi.waitFor(() => expect(api.showNotification).toHaveBeenCalledOnce());
    expect(api.showNotification).toHaveBeenCalledWith(
      'Morning Brief',
      'Headlines for today',
      '/briefs/42'
    );
  });

  it('does not notify twice for the same briefing id', async () => {
    localStorage.setItem('nd_electron_last_brief_id', '42');
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    // Give it time to poll
    await new Promise((r) => setTimeout(r, 50));
    expect(api.showNotification).not.toHaveBeenCalled();
  });

  it('does not show a notification when push_enabled is false', async () => {
    mockFetchSettings.mockResolvedValue({
      briefing_time: '09:00',
      push_enabled: false,
      vapid_public_key: null,
    });
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    await new Promise((r) => setTimeout(r, 50));
    expect(api.showNotification).not.toHaveBeenCalled();
  });

  it('does not show a notification when the latest briefing is empty', async () => {
    mockFetchLatestBriefing.mockResolvedValue({ status: 'empty' });
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    await new Promise((r) => setTimeout(r, 50));
    expect(api.showNotification).not.toHaveBeenCalled();
  });

  it('registers onNotificationClick and navigates on click', async () => {
    const api = makeElectronAPI();
    let clickHandler: ((url: string) => void) | undefined;
    api.onNotificationClick = vi.fn((cb: (url: string) => void) => {
      clickHandler = cb;
    });
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    await vi.waitFor(() => expect(api.onNotificationClick).toHaveBeenCalled());
    clickHandler?.('/briefs/42');
    expect(navigate).toHaveBeenCalledWith('/briefs/42');
  });

  it('removes notification click listener on unmount', () => {
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    const { unmount } = renderHook(() => useElectronBriefNotifier(navigate));
    unmount();

    expect(api.removeNotificationClickListener).toHaveBeenCalled();
  });

  it('stores the notified briefing id in localStorage', async () => {
    const api = makeElectronAPI();
    (window as unknown as { electronAPI: unknown }).electronAPI = api;

    const navigate = vi.fn();
    renderHook(() => useElectronBriefNotifier(navigate));

    await vi.waitFor(() => expect(api.showNotification).toHaveBeenCalledOnce());
    expect(localStorage.getItem('nd_electron_last_brief_id')).toBe('42');
  });
});
