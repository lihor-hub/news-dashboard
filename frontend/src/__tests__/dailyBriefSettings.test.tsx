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
    const input = await screen.findByLabelText('Generation time (UTC)');
    expect(input).toHaveValue('09:00');
  });

  it('shows a custom time from settings', async () => {
    mockFetchSettings.mockResolvedValue({ ...defaultSettings, briefing_time: '07:30' });
    renderSettings();
    const input = await screen.findByLabelText('Generation time (UTC)');
    expect(input).toHaveValue('07:30');
  });

  it('calls updateNotificationSettings on time input blur', async () => {
    const user = userEvent.setup();
    renderSettings();
    const input = await screen.findByLabelText('Generation time (UTC)');
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
    mockFetchSettings.mockResolvedValue({
      ...defaultSettings,
      push_enabled: true,
      vapid_public_key: 'BFakeKey',
    });
    renderSettings();
    const disableBtn = await screen.findByRole('button', { name: /disable/i });
    await user.click(disableBtn);
    await waitFor(() => expect(mockUnsubscribePush).toHaveBeenCalled());
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
});
