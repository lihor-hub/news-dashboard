// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { RecapProgress } from '../components/RecapProgress';
import { formatCalendarDate as recapDate } from '../lib/format';
import { WeeklyRecapPage } from '../pages/WeeklyRecapPage';
import * as api from '../api';
import type { WeeklyRecap } from '../types';

vi.mock('../api', () => ({ fetchRecaps: vi.fn(), fetchRecap: vi.fn() }));
const coverage = {
  status: 'partial' as const,
  measured_from: null,
  reasons: ['global_gap_or_unknown'],
};
function fixture(seconds: number | null = 59, visits: number | null = 0): WeeklyRecap {
  return {
    id: 99,
    user_id: 1,
    week_start: '2026-03-02',
    created_at: '2026-03-09T09:00:00Z',
    narrative: null,
    data: {
      snapshot_version: 2,
      week_start: '2026-03-02',
      week_end: '2026-03-08',
      generated_at: '2026-03-09T09:00:00Z',
      period: {
        timezone: 'America/New_York',
        start_local_date: '2026-03-02',
        end_local_date: '2026-03-09',
        start_at: '2026-03-02T05:00:00Z',
        end_at: '2026-03-09T04:00:00Z',
        scheduled_for: '2026-03-09T09:00:00Z',
        snapshot_at: '2026-03-09T09:00:00Z',
      },
      articles_read: 2,
      categories: [],
      sources: [],
      minutes_read: 999,
      current_streak_days: 8,
      progress: {
        active_seconds: seconds,
        days_visited: visits,
        coverage: { visits: coverage, active_time: coverage, rewards: coverage },
        rewards: [
          'reward with & spaces',
          'topic_python_1',
          'daily_streak_3',
          'articles_read_1',
        ].map((key) => ({
          key,
          title: key,
          description: `Frozen ${key}`,
          topic_id: null,
          earned_at: '2026-03-03T12:00:00Z',
        })),
      },
    },
  };
}
function show(recap: WeeklyRecap, full = false, rewardKey?: string) {
  return render(
    <MemoryRouter>
      <RecapProgress recap={recap} full={full} rewardKey={rewardKey} />
    </MemoryRouter>
  );
}

describe('frozen recap progress', () => {
  it.each([
    [null, 'Unavailable'],
    [0, '0 minutes measured'],
    [59, 'Less than a minute measured'],
    [120, '2 minutes measured'],
  ] as const)('distinguishes %s active seconds', (seconds, expected) => {
    show(fixture(seconds));
    expect(screen.getByText(new RegExp(expected))).toBeInTheDocument();
    expect(screen.getByText(/0 of 7/)).toBeInTheDocument();
    expect(screen.getAllByText(/partial coverage/)).toHaveLength(3);
    expect(screen.queryByText('999')).not.toBeInTheDocument();
  });
  it('shows unavailable without invented zeros and keeps a shared destination', () => {
    show(fixture(null, null));
    expect(
      screen.getByText('Progress tracking was not available for this period.')
    ).toBeInTheDocument();
    expect(screen.queryByText('0 of 7')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View all 4/ })).toHaveAttribute(
      'href',
      '/reading-dna?recap=99#progress'
    );
  });
  it('caps highlights, encodes stable keys, and renders all frozen names on detail with focus', () => {
    const compact = show(fixture());
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('link', { name: 'reward with & spaces' })).toHaveAttribute(
      'href',
      '/reading-dna?recap=99&reward=reward%20with%20%26%20spaces#progress'
    );
    compact.unmount();
    show(fixture(), true, 'reward with & spaces');
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
    expect(screen.getByRole('heading', { name: 'reward with & spaces' })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Back to this recap' })).toHaveAttribute(
      'href',
      '/recap?recap=99'
    );
  });
  it('loads selected detail even when not in the last 12 list and hides legacy minutes for v2', async () => {
    vi.mocked(api.fetchRecaps).mockResolvedValue([]);
    vi.mocked(api.fetchRecap).mockResolvedValue(fixture());
    render(
      <MemoryRouter initialEntries={['/recap?recap=99']}>
        <WeeklyRecapPage />
      </MemoryRouter>
    );
    await screen.findByRole('heading', { name: 'Your week in progress' });
    expect(api.fetchRecap).toHaveBeenCalledWith(99);
    expect(screen.queryByText('999m')).not.toBeInTheDocument();
    expect(screen.getByText(/Legacy reading streak at generation/)).toBeInTheDocument();
  });
  it('formats calendar dates without browser timezone rebucketing', () => {
    expect(recapDate('2026-03-02')).toMatch(/Mar 2, 2026/);
  });
});
