// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { Toaster, toast } from 'sonner';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as api from '@/api/progress';
import { DailyProgress } from '@/components/DailyProgress';
import { RewardFeedback } from '@/components/RewardFeedback';
import { ProgressSection } from '@/components/ProgressSection';
import { RewardDetail } from '@/components/RewardDetail';

const state = vi.hoisted(() => ({ id: 42, onboarding: false }));
vi.mock('@/contexts/auth', () => ({ useAuth: () => ({ user: { id: state.id } }) }));
vi.mock('@/hooks/useOnboardingWizard', () => ({
  useOnboardingWizard: () => ({ ready: true, open: state.onboarding, skip: vi.fn() }),
}));
vi.mock('@/hooks/useWhatsNew', () => ({ useWhatsNew: () => ({ ready: true, open: false }) }));
vi.mock('@/components/OnboardingWizard', () => ({ OnboardingWizard: () => null }));
vi.mock('@/components/WhatsNewDialog', () => ({ WhatsNewDialog: () => null }));
vi.mock('@/lib/activity', () => ({ startActivity: () => vi.fn() }));
vi.mock('@/api/activity', () => ({
  fetchActivity: vi.fn().mockResolvedValue({ available: false }),
}));
const daily: api.DailyStreak = {
  available: true,
  timezone: 'UTC',
  local_date: '2026-01-10',
  server_now: '2026-01-10T12:00:00Z',
  next_local_boundary_at: '2026-01-11T00:00:00Z',
  current_streak_days: 1,
  best_streak_days: 1,
  visit_kind: 'first',
  seven_days: [],
  welcome_target: null,
};
const prefs = {
  progress_timezone: 'UTC',
  timezone_initialized: true,
  daily_welcome_enabled: false,
  reward_animations_enabled: false,
};
const rewards: api.ProgressReward[] = Array.from({ length: 5 }, (_, i) => ({
  key: `award_${i}`,
  title: `Award ${i}`,
  description: `Requirement ${i}`,
  unlocked: true,
  target: 3,
  earned_at: null,
  recorded_at: '2026-01-01T12:00:00Z',
  origin: 'legacy',
}));
function host(entry = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <DailyProgress key={state.id}>
            <button>Reader control</button>
            <ProgressSection />
          </DailyProgress>
          <Toaster />
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}
beforeEach(() => {
  state.id = 42;
  state.onboarding = false;
  vi.spyOn(api, 'fetchDailyStreak').mockResolvedValue(daily);
  vi.spyOn(api, 'recordDailyVisit').mockResolvedValue(daily);
  vi.spyOn(api, 'fetchProgressPreferences').mockResolvedValue(prefs);
  vi.spyOn(api, 'fetchProgressRewards').mockResolvedValue({
    items: rewards,
    pending_reward_group_ids: ['group-1'],
  });
  vi.spyOn(api, 'claimRewardGroup').mockResolvedValue({
    show: true,
    authorization: { welcome: false, history: false, rewards: true },
    welcome: null,
    rewards,
  });
  vi.spyOn(api, 'acknowledgeRewardGroup').mockResolvedValue({ acknowledged: true });
});
afterEach(() => {
  cleanup();
  toast.dismiss();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it('groups <=3 names +N in one static slot, preserves Undo and reader focus, navigation focuses detail', async () => {
  host();
  screen.getByRole('button', { name: 'Reader control' }).focus();
  toast('Done', { id: 'triage', action: { label: 'Undo', onClick: vi.fn() }, duration: Infinity });
  await screen.findByText('Progress earned');
  expect(document.querySelectorAll('[data-reward-feedback]')).toHaveLength(1);
  expect(screen.getByText('Award 0 · Award 1 · Award 2 and 2 more')).toBeTruthy();
  expect(screen.queryByText('Award 3 ·')).toBeNull();
  expect(screen.getByRole('button', { name: 'Reader control' })).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Undo' })).toBeTruthy();
  expect(document.querySelector('[data-sonner-toast].progress-static')).not.toBeNull();
  fireEvent.click(screen.getByRole('link', { name: 'View achievement' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Award 0' })).toHaveFocus());
  expect(await screen.findByText('Provenance: legacy.')).toBeTruthy();
  expect(api.acknowledgeRewardGroup).toHaveBeenCalledExactlyOnceWith('group-1');
  expect(screen.getByRole('button', { name: 'Undo' })).toBeTruthy();
});

it('8 second clock pauses on hover and keyboard focus, then dismisses without touching records', async () => {
  vi.useFakeTimers();
  const close = vi.fn();
  render(<RewardFeedback rewards={rewards} onClose={close} onView={vi.fn()} />);
  const card = document.querySelector('[data-reward-feedback]')!;
  await act(() => vi.advanceTimersByTimeAsync(3000));
  fireEvent.mouseEnter(card);
  await act(() => vi.advanceTimersByTimeAsync(9000));
  expect(close).not.toHaveBeenCalled();
  screen.getByRole('link', { name: 'View achievement' }).focus();
  fireEvent.mouseLeave(card);
  await act(() => vi.advanceTimersByTimeAsync(9000));
  expect(close).not.toHaveBeenCalled();
  act(() => (document.activeElement as HTMLElement).blur());
  await act(() => vi.advanceTimersByTimeAsync(4999));
  expect(close).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(close).toHaveBeenCalledTimes(1);
});

it('does not claim before onboarding closes; a lost response never retries an implicit next target', async () => {
  state.onboarding = true;
  vi.mocked(api.claimRewardGroup).mockRejectedValue(new Error('lost response'));
  const { client } = host();
  await screen.findByRole('link', { name: /Daily streak/ });
  expect(api.claimRewardGroup).not.toHaveBeenCalled();
  state.onboarding = false;
  await act(async () => {
    client.setQueryData(['daily-streak', 42], { ...daily, best_streak_days: 2 });
  });
  await waitFor(() => expect(api.claimRewardGroup).toHaveBeenCalledExactlyOnceWith('group-1'));
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['progress-rewards'] });
  });
  expect(api.claimRewardGroup).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('Progress earned')).toBeNull();
});

it('atomic welcome/history waits before live feedback; summary is not live authorization', async () => {
  vi.mocked(api.fetchProgressPreferences).mockResolvedValue({
    ...prefs,
    daily_welcome_enabled: true,
  });
  const pendingWelcome = { ...daily, welcome_target: { expected_visit_date: daily.local_date } };
  vi.mocked(api.recordDailyVisit).mockResolvedValue(pendingWelcome);
  vi.mocked(api.fetchDailyStreak).mockResolvedValue(pendingWelcome);
  vi.mocked(api.fetchProgressRewards).mockResolvedValue({
    items: rewards,
    pending_reward_group_ids: ['group-1'],
    historical_group_id: 'intro',
  });
  vi.spyOn(api, 'claimDailyWelcome').mockResolvedValue({
    show: true,
    authorization: { welcome: true, history: true, rewards: false },
    welcome: { ...daily, recent_reward: rewards[0] },
    history: { group_id: 'intro', credited_reads: 42, exact_earned_dates_known: false },
  });
  host();
  await screen.findByRole('dialog');
  expect(api.claimDailyWelcome).toHaveBeenCalledExactlyOnceWith(daily.local_date, 'intro');
  expect(api.claimRewardGroup).not.toHaveBeenCalled();
  expect(screen.getByText(/Historical credit: 42/)).toBeTruthy();
  expect(screen.queryByText(/From your recent collection/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Continue reading' }));
  await screen.findByText('Progress earned');
  expect(api.claimRewardGroup).toHaveBeenCalledTimes(1);
});

it('drops in-flight old-account authorization after logout and clears its slot', async () => {
  let resolve!: (value: api.Presentation) => void;
  vi.mocked(api.claimRewardGroup).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      })
  );
  const first = host();
  await waitFor(() => expect(api.claimRewardGroup).toHaveBeenCalledTimes(1));
  first.unmount();
  state.id = 43;
  vi.mocked(api.fetchProgressRewards).mockResolvedValue({ items: [] });
  host();
  await act(async () =>
    resolve({
      show: true,
      authorization: { welcome: false, history: false, rewards: true },
      welcome: null,
      rewards,
    })
  );
  await screen.findByRole('link', { name: /Daily streak/ });
  expect(screen.queryByText('Progress earned')).toBeNull();
  expect(api.acknowledgeRewardGroup).not.toHaveBeenCalled();
});

it('hidden documents and focus moving within feedback preserve the remaining dismissal time', async () => {
  vi.useFakeTimers();
  const close = vi.fn();
  const visibility = vi.spyOn(document, 'visibilityState', 'get');
  render(<RewardFeedback rewards={rewards.slice(0, 1)} onClose={close} onView={vi.fn()} />);
  expect(screen.getByText('Award 0')).toBeInTheDocument();
  expect(screen.queryByText(/and .* more/)).toBeNull();
  await act(() => vi.advanceTimersByTimeAsync(2000));
  visibility.mockReturnValue('hidden');
  fireEvent(document, new Event('visibilitychange'));
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(close).not.toHaveBeenCalled();
  visibility.mockReturnValue('visible');
  fireEvent(document, new Event('visibilitychange'));
  act(() => screen.getByRole('link', { name: 'View achievement' }).focus());
  act(() => screen.getByRole('button', { name: 'Dismiss celebration' }).focus());
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(close).not.toHaveBeenCalled();
  act(() => (document.activeElement as HTMLElement).blur());
  await act(() => vi.advanceTimersByTimeAsync(5999));
  expect(close).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(close).toHaveBeenCalledTimes(1);
});

it('unknown reward destinations give a focused not-found state and a safe collection link', () => {
  render(
    <MemoryRouter>
      <RewardDetail requestedKey={'unknown?key&#/'} />
    </MemoryRouter>
  );
  expect(screen.getByRole('heading', { name: 'Achievement not found' })).toHaveFocus();
  expect(
    screen.getByText('No matching achievement is available in your collection.')
  ).toBeVisible();
  expect(screen.getByRole('link', { name: 'Back to collection' })).toHaveAttribute(
    'href',
    '/reading-dna#progress'
  );
});

it('locked detail shows requirements, not invented earned dates or provenance', () => {
  render(
    <MemoryRouter>
      <RewardDetail
        requestedKey="daily_streak_7"
        reward={{
          ...rewards[0],
          key: 'daily_streak_7',
          title: '7-day daily streak',
          description: 'Visit on 7 consecutive saved-local dates.',
          target: 7,
          unlocked: false,
          recorded_at: null,
          origin: null,
        }}
      />
    </MemoryRouter>
  );
  expect(screen.getByRole('heading', { name: '7-day daily streak' })).toHaveFocus();
  expect(screen.getByText('◇ Locked · Visit on 7 consecutive saved-local dates.')).toBeVisible();
  expect(screen.queryByText(/Provenance:/)).toBeNull();
  expect(screen.queryByText(/Original earned date/)).toBeNull();
  expect(document.querySelector('time')).toBeNull();
});

it('live detail keeps earned and recorded instants separate without refocusing on background refresh', () => {
  const reward = { ...rewards[0], earned_at: '2026-01-02T12:00:00Z', origin: 'live' };
  const view = render(
    <MemoryRouter>
      <RewardDetail requestedKey={reward.key} reward={reward} />
    </MemoryRouter>
  );
  expect(screen.getByRole('heading', { name: reward.title })).toHaveFocus();
  expect(screen.getByText('Provenance: live.')).toBeVisible();
  expect([...document.querySelectorAll('time')].map((node) => node.dateTime)).toEqual([
    reward.earned_at,
    reward.recorded_at,
  ]);
  const back = screen.getByRole('link', { name: 'Back to collection' });
  back.focus();
  view.rerender(
    <MemoryRouter>
      <RewardDetail requestedKey={reward.key} reward={{ ...reward, title: 'Updated title' }} />
    </MemoryRouter>
  );
  expect(back).toHaveFocus();
  expect(screen.getByRole('heading', { name: 'Updated title' })).toBeVisible();
});

it('retired legacy detail preserves unknown earned time without manufacturing a recording date', () => {
  render(
    <MemoryRouter>
      <RewardDetail
        requestedKey={rewards[0].key}
        reward={{ ...rewards[0], origin: null, recorded_at: null, retired: true }}
      />
    </MemoryRouter>
  );
  expect(screen.getByText('Original earned date unknown; preserved reward.')).toBeVisible();
  expect(
    screen.getByText('Provenance: legacy. Retired or original reward; permanently preserved.')
  ).toBeVisible();
  expect(document.querySelector('time')).toBeNull();
});

it('collection separates daily, active-time, breadth and quiz rewards with canonical links', async () => {
  const items = [
    { ...rewards[0], key: 'daily_streak_3', target: 3 },
    { ...rewards[1], key: 'active_time_900', target: 900 },
    { ...rewards[2], key: 'breadth_3', target: 3 },
    { ...rewards[3], key: 'first_quiz_passed', target: 1 },
  ];
  vi.mocked(api.fetchProgressRewards).mockResolvedValue({ items });
  host();
  for (const [index, category] of [
    'Daily visits',
    'Approximate active time badges',
    'Topic breadth',
    'Learning',
  ].entries()) {
    const section = await screen.findByRole('region', { name: category });
    expect(section.querySelector('a')).toHaveAttribute('href', api.rewardHref(items[index].key));
    expect(section).toHaveTextContent(`✓ Earned: ${items[index].title}`);
    const emblem = section.querySelector('svg');
    expect(emblem).toHaveAttribute('aria-hidden', 'true');
    expect(emblem).toHaveAttribute('focusable', 'false');
  }
  expect(api.claimRewardGroup).not.toHaveBeenCalled();
});

it('a losing live claim cannot authorize feedback or acknowledgement', async () => {
  vi.mocked(api.claimRewardGroup).mockResolvedValue({
    show: false,
    authorization: { welcome: false, history: false, rewards: false },
    welcome: null,
    rewards: [],
  });
  host();
  await waitFor(() => expect(api.claimRewardGroup).toHaveBeenCalledExactlyOnceWith('group-1'));
  await act(async () => {});
  expect(screen.queryByText('Progress earned')).toBeNull();
  expect(api.acknowledgeRewardGroup).not.toHaveBeenCalled();
});

it('welcome disabled uses exact history inline mode, not a generic live toast', async () => {
  vi.mocked(api.fetchProgressRewards).mockResolvedValue({
    items: [],
    historical_group_id: 'intro',
  });
  vi.spyOn(api, 'claimPresentation').mockResolvedValue({
    show: true,
    authorization: { welcome: false, history: true, rewards: false },
    welcome: null,
    history: { group_id: 'intro', credited_reads: 42, exact_earned_dates_known: false },
  });
  host();
  await screen.findByRole('complementary', { name: 'Progress history introduction' });
  expect(api.claimPresentation).toHaveBeenCalledExactlyOnceWith(null, 'intro');
  expect(api.claimRewardGroup).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).toBeNull();
});
