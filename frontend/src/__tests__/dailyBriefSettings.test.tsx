// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const {
  mockFetchSettings,
  mockUpdateSettings,
  mockSubscribePush,
  mockUnsubscribePush,
  mockRecalculate,
} = vi.hoisted(() => ({
  mockFetchSettings: vi.fn(),
  mockUpdateSettings: vi.fn(),
  mockSubscribePush: vi.fn(),
  mockUnsubscribePush: vi.fn(),
  mockRecalculate: vi.fn(),
}));

vi.mock('@/api', () => ({
  fetchNotificationSettings: mockFetchSettings,
  updateNotificationSettings: mockUpdateSettings,
  subscribePush: mockSubscribePush,
  unsubscribePush: mockUnsubscribePush,
  recalculateMyRecommendations: mockRecalculate,
}));

import { SettingsPage } from '../pages/SettingsPage';
import type { PushSubscribeRequest } from '../types';

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  );
}

const defaultSettings = {
  briefing_time: '09:00',
  briefing_timezone: 'UTC',
  push_enabled: false,
  vapid_public_key: null as string | null,
};

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
  mockFetchSettings.mockResolvedValue({ ...defaultSettings });
  mockUpdateSettings.mockResolvedValue({ briefing_time: '09:00', push_enabled: false });
  mockSubscribePush.mockResolvedValue({ subscribed: true });
  mockUnsubscribePush.mockResolvedValue({ unsubscribed: true });
  mockRecalculate.mockResolvedValue({ scored: 0 });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  delete (window as unknown as { electronAPI?: unknown }).electronAPI;
});

describe('DailyBriefSection', () => {
  it('renders the Daily Brief heading', async () => {
    renderSettings();
    await waitFor(() => expect(screen.getByText('Daily Brief')).toBeInTheDocument());
  });

  it('shows the time loaded from settings', async () => {
    renderSettings();
    const input = await screen.findByLabelText('Generation time');
    expect(input).toHaveValue('09:00');
  });

  it('shows a custom time from settings', async () => {
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_time: '07:30' });
    renderSettings();
    const input = await screen.findByLabelText('Generation time');
    expect(input).toHaveValue('07:30');
  });

  it('calls updateNotificationSettings on time input blur', async () => {
    const user = userEvent.setup();
    renderSettings();
    const input = await screen.findByLabelText('Generation time');
    await user.clear(input);
    await user.type(input, '08:00');
    await user.tab();
    await waitFor(() => {
      expect(mockUpdateSettings).toHaveBeenCalledWith({ briefing_time: '08:00' });
    });
  });

  it('shows push notifications section', async () => {
    renderSettings();
    await waitFor(() => expect(screen.getByText('Push notifications')).toBeInTheDocument());
  });

  it('hides Enable button when PushManager is absent (browser/non-Electron)', async () => {
    renderSettings();
    await waitFor(() => expect(screen.getByText('Push notifications')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /enable push/i })).not.toBeInTheDocument();
  });

  it('shows Enabled state and Disable button when push_enabled is true', async () => {
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      push_enabled: true,
      vapid_public_key: 'BFakeKey',
    });
    renderSettings();
    await waitFor(() => expect(screen.getByText('Enabled')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /disable/i })).toBeInTheDocument();
  });

  it('calls unsubscribePush and updateNotificationSettings on Disable click', async () => {
    const user = userEvent.setup();
    const localUnsubscribe = vi.fn().mockResolvedValue(true);
    const getSubscription = vi.fn().mockResolvedValue({
      endpoint: 'https://push.example.com/current',
      unsubscribe: localUnsubscribe,
    });
    vi.stubGlobal('navigator', {
      serviceWorker: {
        ready: Promise.resolve({
          pushManager: { getSubscription },
        }),
      },
    });
    vi.stubGlobal('PushManager', {});
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      push_enabled: true,
      vapid_public_key: 'BFakeKey',
    });
    renderSettings();
    const disableBtn = await screen.findByRole('button', { name: /disable/i });
    await user.click(disableBtn);
    await waitFor(() =>
      expect(mockUnsubscribePush).toHaveBeenCalledWith('https://push.example.com/current')
    );
    expect(getSubscription).toHaveBeenCalled();
    expect(localUnsubscribe).toHaveBeenCalled();
    await waitFor(() => expect(mockUpdateSettings).toHaveBeenCalledWith({ push_enabled: false }));
  });

  it('keeps Electron disable working without a browser PushManager subscription', async () => {
    const user = userEvent.setup();
    (window as unknown as { electronAPI: unknown }).electronAPI = {
      platform: 'electron',
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
    };
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      push_enabled: true,
      vapid_public_key: null,
    });
    renderSettings();
    const disableBtn = await screen.findByRole('button', { name: /disable/i });
    await user.click(disableBtn);
    await waitFor(() => expect(mockUnsubscribePush).toHaveBeenCalledWith(undefined));
    await waitFor(() => expect(mockUpdateSettings).toHaveBeenCalledWith({ push_enabled: false }));
  });

  it('shows Enable button on Electron (no PushManager needed)', async () => {
    (window as unknown as { electronAPI: unknown }).electronAPI = {
      platform: 'electron',
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
    };
    renderSettings();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /enable push notifications/i })).toBeInTheDocument()
    );
  });

  it('enables push via Electron IPC path and shows Enabled', async () => {
    const user = userEvent.setup();
    (window as unknown as { electronAPI: unknown }).electronAPI = {
      platform: 'electron',
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
    };
    renderSettings();
    const enableBtn = await screen.findByRole('button', { name: /enable push notifications/i });
    await user.click(enableBtn);
    await waitFor(() => expect(mockUpdateSettings).toHaveBeenCalledWith({ push_enabled: true }));
    await waitFor(() => expect(screen.getByText('Enabled')).toBeInTheDocument());
  });

  it('serializes browser push subscription keys as URL-safe base64', async () => {
    const user = userEvent.setup();
    const keyBytes = new Uint8Array([251, 255, 190, 239]);
    const authBytes = new Uint8Array([255, 239, 190, 251]);
    const getKey = vi.fn((name: string) =>
      name === 'p256dh' ? keyBytes.buffer : authBytes.buffer
    );
    const subscribe = vi.fn().mockResolvedValue({
      endpoint: 'https://push.example.com/new',
      getKey,
    });
    vi.stubGlobal('navigator', {
      serviceWorker: {
        ready: Promise.resolve({ pushManager: { subscribe } }),
      },
    });
    vi.stubGlobal('PushManager', {});
    vi.stubGlobal('Notification', { requestPermission: vi.fn().mockResolvedValue('granted') });
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      vapid_public_key: 'BFakeKey',
    });
    renderSettings();
    const enableBtn = await screen.findByRole('button', { name: /enable push notifications/i });
    await user.click(enableBtn);

    await waitFor(() => expect(mockSubscribePush).toHaveBeenCalled());
    const payload = mockSubscribePush.mock.calls[0][0] as PushSubscribeRequest;
    expect(payload.endpoint).toBe('https://push.example.com/new');
    expect(payload.p256dh).not.toMatch(/[+/]/);
    expect(payload.auth).not.toMatch(/[+/]/);
    expect(payload.p256dh).toBe('-_--7w');
    expect(payload.auth).toBe('_----w');
  });

  it('hides Enable button and shows server-configuration warning when PushManager is present but VAPID key is missing', async () => {
    vi.stubGlobal('navigator', { serviceWorker: {} });
    vi.stubGlobal('PushManager', {});
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      vapid_public_key: null,
    });
    renderSettings();
    await waitFor(() => expect(screen.getByText('Push notifications')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /enable push/i })).not.toBeInTheDocument();
    expect(
      screen.queryByText('Push notifications are not supported in this environment.')
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('Push notifications require server configuration (VAPID keys).')
    ).toBeInTheDocument();
  });
});

describe('DailyBriefSection — timezone', () => {
  it('shows timezone loaded from settings', async () => {
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      briefing_timezone: 'Europe/Bucharest',
    });
    renderSettings();
    const input = await screen.findByLabelText('Timezone');
    expect(input).toHaveValue('Europe/Bucharest');
  });

  it('falls back to browser timezone when server returns UTC', async () => {
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_timezone: 'UTC' });
    renderSettings();
    const input = await screen.findByLabelText('Timezone');
    expect(input).toHaveValue('UTC');
  });

  it('calls updateNotificationSettings with briefing_timezone on blur', async () => {
    const user = userEvent.setup();
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_timezone: 'UTC' });
    renderSettings();
    const input = await screen.findByLabelText('Timezone');
    await user.clear(input);
    await user.type(input, 'America/New_York');
    await user.tab();
    await waitFor(() => {
      expect(mockUpdateSettings).toHaveBeenCalledWith({ briefing_timezone: 'America/New_York' });
    });
  });

  it('shows rejection feedback when the backend rejects an invalid timezone', async () => {
    const user = userEvent.setup();
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_timezone: 'UTC' });
    mockUpdateSettings.mockRejectedValueOnce(new Error('unknown timezone'));
    renderSettings();

    const input = await screen.findByLabelText('Timezone');
    await user.clear(input);
    await user.type(input, 'Mars/Olympus');
    await user.tab();

    expect(
      await screen.findByText('Unknown timezone. Choose a valid IANA timezone.')
    ).toBeVisible();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveValue('Mars/Olympus');
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
  });

  it('shows saved feedback after a successful timezone save', async () => {
    const user = userEvent.setup();
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_timezone: 'UTC' });
    renderSettings();

    const input = await screen.findByLabelText('Timezone');
    await user.clear(input);
    await user.type(input, 'Europe/Bucharest');
    await user.tab();

    expect(await screen.findByText('Saved')).toBeVisible();
    expect(input).toHaveAttribute('aria-invalid', 'false');
  });

  it('shows local-time wording without UTC suffix in label', async () => {
    renderSettings();
    await waitFor(() => expect(screen.getByLabelText('Generation time')).toBeInTheDocument());
    expect(screen.queryByLabelText('Generation time (UTC)')).not.toBeInTheDocument();
  });
});
