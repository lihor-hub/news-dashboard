// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/auth';

const {
  mockFetchWatchlists,
  mockCreateWatchlist,
  mockUpdateWatchlist,
  mockDeleteWatchlist,
  mockPreviewWatchlist,
  mockFetchNotificationSettings,
} = vi.hoisted(() => ({
  mockFetchWatchlists: vi.fn(),
  mockCreateWatchlist: vi.fn(),
  mockUpdateWatchlist: vi.fn(),
  mockDeleteWatchlist: vi.fn(),
  mockPreviewWatchlist: vi.fn(),
  mockFetchNotificationSettings: vi.fn(),
}));

vi.mock('@/api', () => ({
  fetchWatchlists: mockFetchWatchlists,
  createWatchlist: mockCreateWatchlist,
  updateWatchlist: mockUpdateWatchlist,
  deleteWatchlist: mockDeleteWatchlist,
  previewWatchlist: mockPreviewWatchlist,
  fetchNotificationSettings: mockFetchNotificationSettings,
  recalculateMyRecommendations: vi.fn(),
}));

import { SettingsPage } from '../pages/SettingsPage';
import type { AiWatchlist } from '../types';

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const sampleWatchlist: AiWatchlist = {
  id: 1,
  user_id: 1,
  label: 'AI safety',
  query: 'artificial intelligence safety',
  threshold: 0.5,
  enabled: true,
  notify_push: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
  mockFetchWatchlists.mockResolvedValue([]);
  mockCreateWatchlist.mockResolvedValue(sampleWatchlist);
  mockUpdateWatchlist.mockResolvedValue({ ...sampleWatchlist, enabled: false });
  mockDeleteWatchlist.mockResolvedValue({ deleted: true });
  mockPreviewWatchlist.mockResolvedValue([]);
  mockFetchNotificationSettings.mockResolvedValue({
    briefing_time: '09:00',
    push_enabled: false,
    vapid_public_key: null,
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('WatchlistsSection', () => {
  it('renders the AI Watchlists heading', async () => {
    renderSettings();
    expect(await screen.findByText('AI Watchlists')).toBeInTheDocument();
  });

  it('lists existing watchlists', async () => {
    mockFetchWatchlists.mockResolvedValue([sampleWatchlist]);
    renderSettings();
    expect(await screen.findByText('AI safety')).toBeInTheDocument();
    expect(screen.getByText('artificial intelligence safety')).toBeInTheDocument();
  });

  it('creates a watchlist from the form', async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText('AI Watchlists');

    await user.type(screen.getByPlaceholderText(/Label, e.g. AI safety/), 'AI safety');
    await user.type(
      screen.getByPlaceholderText(/What should this watch for/),
      'artificial intelligence safety'
    );
    await user.click(screen.getByRole('button', { name: /Add watchlist/ }));

    await waitFor(() => {
      expect(mockCreateWatchlist).toHaveBeenCalledWith({
        label: 'AI safety',
        query: 'artificial intelligence safety',
      });
    });
  });

  it('previews matches for the current query', async () => {
    mockPreviewWatchlist.mockResolvedValue([
      {
        article: { id: 42, title: 'Quantum computing breakthrough' },
        score: 0.9,
        explanation: 'Matched terms: quantum, computing',
      },
    ]);
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText('AI Watchlists');

    await user.type(screen.getByPlaceholderText(/What should this watch for/), 'quantum computing');
    await user.click(screen.getByRole('button', { name: /Preview matches/ }));

    expect(await screen.findByText('Quantum computing breakthrough')).toBeInTheDocument();
    expect(mockPreviewWatchlist).toHaveBeenCalledWith('quantum computing');
  });

  it('toggles a watchlist enabled state', async () => {
    mockFetchWatchlists.mockResolvedValue([sampleWatchlist]);
    const user = userEvent.setup();
    renderSettings();
    const label = await screen.findByText('AI safety');
    const item = label.closest('li');
    if (!item) throw new Error('watchlist list item not found');

    const toggle = within(item).getByRole('switch');
    await user.click(toggle);

    await waitFor(() => {
      expect(mockUpdateWatchlist).toHaveBeenCalledWith(1, { enabled: false });
    });
  });

  it('deletes a watchlist', async () => {
    mockFetchWatchlists.mockResolvedValue([sampleWatchlist]);
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText('AI safety');

    await user.click(screen.getByRole('button', { name: /Delete watchlist AI safety/ }));

    await waitFor(() => {
      expect(mockDeleteWatchlist).toHaveBeenCalledWith(1);
    });
  });
});
