// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/api/progress';
import { DailyProgress, SevenDayStrip } from '@/components/DailyProgress';
import { ProgressSection } from '@/components/ProgressSection';

vi.mock('@/contexts/auth', () => ({
  useAuth: () => ({ user: { id: 42 }, status: 'authenticated' }),
}));
const blockers = vi.hoisted(() => ({ onboarding: false, ready: true }));
vi.mock('@/hooks/useOnboardingWizard', () => ({
  useOnboardingWizard: () => ({ open: blockers.onboarding, ready: blockers.ready, skip: vi.fn() }),
}));
vi.mock('@/hooks/useWhatsNew', () => ({
  useWhatsNew: () => ({ open: false, ready: true, dismiss: vi.fn(), items: [], version: 'test' }),
}));
vi.mock('@/components/OnboardingWizard', () => ({ OnboardingWizard: () => null }));
vi.mock('@/components/WhatsNewDialog', () => ({ WhatsNewDialog: () => null }));
// Activity has its own clock/lifecycle suite; don't run its 250ms loop across nine fake hours.
vi.mock('@/lib/activity', () => ({ startActivity: () => vi.fn() }));
vi.mock('@/api/activity', () => ({
  fetchActivity: vi.fn().mockResolvedValue({ available: false }),
}));

const daily: api.DailyStreak = {
  available: true,
  timezone: 'Pacific/Kiritimati',
  local_date: '2026-01-02',
  server_now: '2026-01-01T12:00:00Z',
  next_local_boundary_at: '2026-01-02T10:00:00Z',
  current_streak_days: 1,
  best_streak_days: 3,
  visit_kind: 'first',
  seven_days: Array.from({ length: 7 }, (_, i) => ({
    date: `2025-12-${26 + i}`,
    visited: i === 6,
    credited: i === 6,
  })),
  welcome_target: { expected_visit_date: '2026-01-02' },
};
const prefs = {
  progress_timezone: 'Pacific/Kiritimati',
  timezone_initialized: true,
  daily_welcome_enabled: true,
  reward_animations_enabled: false,
};
function renderHost(initialEntry = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <DailyProgress>
          <Routes>
            <Route path="/" element={<button>Reader control</button>} />
            <Route path="/reading-dna" element={<ProgressSection />} />
          </Routes>
        </DailyProgress>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  blockers.onboarding = false;
  blockers.ready = true;
  vi.spyOn(api, 'recordDailyVisit').mockResolvedValue(daily);
  vi.spyOn(api, 'fetchDailyStreak').mockResolvedValue(daily);
  vi.spyOn(api, 'fetchProgressPreferences').mockResolvedValue(prefs);
  vi.spyOn(api, 'fetchProgressRewards').mockResolvedValue({ items: [] });
  vi.spyOn(api, 'saveProgressPreferences').mockImplementation(async (patch) => ({
    ...prefs,
    ...patch,
  }));
  vi.spyOn(api, 'claimDailyWelcome').mockResolvedValue({
    show: true,
    authorization: { welcome: true, history: false, rewards: false },
    welcome: daily,
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('daily visit protected host and home', () => {
  it('shows permanent reading totals, next target, textual locked requirements and real dates', async () => {
    vi.mocked(api.fetchProgressRewards).mockResolvedValue({
      reading_total: 1,
      next_reading_target: 10,
      history_status: 'reconciliation_pending',
      items: [
        {
          key: 'articles_read_1',
          title: '1 articles read',
          description: 'Complete 1 qualifying article reads.',
          unlocked: true,
          target: 1,
          earned_at: '2026-01-01T12:00:00Z',
          recorded_at: '2026-01-01T12:00:00Z',
          origin: 'live',
        },
        {
          key: 'articles_read_10',
          title: '10 articles read',
          description: 'Complete 10 qualifying article reads.',
          unlocked: false,
          target: 10,
          earned_at: null,
          recorded_at: null,
          origin: null,
        },
      ],
    });
    renderHost('/reading-dna#progress');
    expect(await screen.findByText('✓ Earned: 1 articles read')).toBeInTheDocument();
    expect(screen.getByText('◇ Locked: 10 articles read')).toBeInTheDocument();
    expect(screen.getByText('Complete 10 qualifying article reads.')).toBeInTheDocument();
    expect(screen.getByText('Next reading milestone: 10 articles.')).toBeInTheDocument();
    expect(screen.getByText(/not your complete lifetime total/)).toBeInTheDocument();
    expect(
      document.querySelector('time[datetime="2026-01-01T12:00:00Z"]')?.getAttribute('datetime')
    ).toBe('2026-01-01T12:00:00Z');
    expect(document.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  });

  it('distinguishes empty tracked reads and retryable errors instead of fabricating zero', async () => {
    vi.mocked(api.fetchProgressRewards)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ items: [], reading_total: 0, next_reading_target: 1 });
    renderHost('/reading-dna#progress');
    const retry = await screen.findByRole('button', { name: 'Retry rewards' });
    expect(screen.queryByText(/No qualifying reads tracked yet/)).not.toBeInTheDocument();
    fireEvent.click(retry);
    expect(await screen.findByText(/No qualifying reads tracked yet/)).toBeInTheDocument();
  });

  it('shows a named static welcome, seven labeled dates, and Escape restores focus', async () => {
    renderHost();
    const control = screen.getByRole('button', { name: 'Reader control' });
    control.focus();
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('A new streak starts here');
    expect(dialog.classList.contains('progress-static')).toBe(true);
    expect(screen.getByRole('list', { name: /Seven days in/ })).toBeTruthy();
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Continue reading' }))
    );
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(control));
    expect(api.claimDailyWelcome).toHaveBeenCalledExactlyOnceWith('2026-01-02');
    expect(screen.getByRole('link', { name: /Daily streak/ })).toBeTruthy();
  });

  it('View my progress navigates and focuses the authenticated destination', async () => {
    renderHost();
    fireEvent.click(await screen.findByRole('button', { name: 'View my progress' }));
    const heading = await screen.findByRole('heading', { name: 'Progress & achievements' });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByLabelText('Daily welcome popup')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Daily welcome popup'));
    await waitFor(() =>
      expect(api.saveProgressPreferences).toHaveBeenCalledWith({ daily_welcome_enabled: false })
    );
    expect(screen.getByLabelText('Reward animations')).toBeTruthy();
  });

  it('a failed preference save restores the prior value and reports the error', async () => {
    vi.mocked(api.saveProgressPreferences).mockRejectedValue(new Error('Save unavailable'));
    renderHost();
    fireEvent.click(await screen.findByRole('button', { name: 'View my progress' }));
    const checkbox = await screen.findByLabelText('Daily welcome popup');
    fireEvent.click(checkbox);
    await screen.findByRole('alert');
    expect((checkbox as HTMLInputElement).checked).toBe(true);
  });

  it('disabled popup retains the visit recorder and persistent indicator', async () => {
    vi.mocked(api.fetchProgressPreferences).mockResolvedValue({
      ...prefs,
      daily_welcome_enabled: false,
    });
    renderHost();
    await screen.findByRole('link', { name: /Daily streak/ });
    expect(api.recordDailyVisit).toHaveBeenCalled();
    expect(api.claimDailyWelcome).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('does not consume welcome before onboarding placement is ready', async () => {
    blockers.ready = false;
    renderHost();
    await screen.findByRole('link', { name: /Daily streak/ });
    expect(api.claimDailyWelcome).not.toHaveBeenCalled();
  });

  it('hidden startup records nothing until visible resume', async () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    renderHost();
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.recordDailyVisit).not.toHaveBeenCalled();
    visibility.mockReturnValue('visible');
    fireEvent(document, new Event('visibilitychange'));
    await screen.findByRole('link', { name: /Daily streak/ });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(1);
  });

  it('visible midnight uses the server boundary and transport failure retries only once', async () => {
    vi.useFakeTimers();
    blockers.ready = false;
    vi.mocked(api.recordDailyVisit)
      .mockResolvedValueOnce({ ...daily, next_local_boundary_at: '2026-01-01T12:00:01Z' })
      .mockRejectedValue(new Error('offline'));
    renderHost();
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(3);
  });

  it('a timezone save replaces the visible midnight schedule without recording a visit', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-02T01:00:00Z'));
    // Jan 1 UTC credit froze Jan 2 00:00Z: the guard has already elapsed.
    const honolulu = {
      ...daily,
      timezone: 'Pacific/Honolulu',
      local_date: '2026-01-01',
      server_now: '2026-01-02T01:00:00Z',
      next_local_boundary_at: '2026-01-02T10:00:00Z',
      current_streak_days: 1,
      welcome_target: null,
    };
    const newYork = {
      ...honolulu,
      timezone: 'America/New_York',
      next_local_boundary_at: '2026-01-02T05:00:00Z',
      // A read-only refresh can also change the displayed stale streak.
      current_streak_days: 0,
    };
    const midnight = {
      ...newYork,
      local_date: '2026-01-02',
      server_now: '2026-01-02T05:00:00Z',
      next_local_boundary_at: '2026-01-03T05:00:00Z',
      current_streak_days: 2,
    };
    vi.mocked(api.fetchProgressPreferences).mockResolvedValue({
      ...prefs,
      progress_timezone: honolulu.timezone,
      daily_welcome_enabled: false,
    });
    vi.mocked(api.fetchDailyStreak).mockResolvedValue(honolulu);
    vi.mocked(api.recordDailyVisit).mockResolvedValueOnce(honolulu).mockResolvedValue(midnight);
    renderHost('/reading-dna#progress');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: /Daily streak: 1 days/ })).toBeTruthy();
    vi.mocked(api.fetchDailyStreak).mockResolvedValue(newYork);
    fireEvent.change(screen.getByLabelText('Progress timezone (IANA)'), {
      target: { value: newYork.timezone },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save timezone' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(screen.getByText(/Visits in America\/New_York/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /Daily streak: 0 days/ })).toBeTruthy();
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000 - 1000);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(screen.getByRole('link', { name: /Daily streak: 2 days/ })).toBeTruthy();
    expect(screen.getByText('2 days')).toBeTruthy();
    // The superseded Honolulu timer must not fire at 10:00Z.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60 * 60 * 1000);
    });
    expect(api.recordDailyVisit).toHaveBeenCalledTimes(2);
    expect(api.claimDailyWelcome).not.toHaveBeenCalled();
  });

  it('date labels are literal dates, never viewer-timezone instants', () => {
    render(<SevenDayStrip daily={daily} />);
    expect(screen.getByText('12-26').getAttribute('dateTime')).toBe('2025-12-26');
    expect(screen.getByLabelText('Credited visit')).toBeTruthy();
  });
});
