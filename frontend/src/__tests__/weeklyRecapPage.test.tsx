// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import * as api from '../api';
import { WeeklyRecapPage } from '../pages/WeeklyRecapPage';
import type { WeeklyRecap } from '../types';

vi.mock('../api', () => ({
  fetchRecaps: vi.fn(),
  fetchPersonalizationNudges: vi.fn(),
  applyPersonalizationNudge: vi.fn(),
  dismissPersonalizationNudge: vi.fn(),
}));

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={makeQc()}>{children}</QueryClientProvider>;
}

const ENRICHED_RECAP: WeeklyRecap = {
  id: 1,
  user_id: 1,
  week_start: '2026-06-29',
  created_at: '2026-07-06T00:00:00+00:00',
  narrative: null,
  data: {
    week_start: '2026-06-29',
    week_end: '2026-07-06',
    generated_at: '2026-07-06T00:00:00+00:00',
    articles_read: 4,
    categories: [],
    sources: [],
    minutes_read: 15.0,
    current_streak_days: 3,
    saved: { starred_this_week: 2, read_from_backlog: 1, backlog_total: 5 },
    dwell: { skims: 3, reads: 2, average_seconds: 22.5 },
    nudges: [
      {
        id: 'source:noise-feed',
        kind: 'source',
        title: 'Noisy source: Noise Feed',
        message: "You've skipped 90% of recent articles from 'Noise Feed'.",
        reason: 'low_signal',
        skip_rate: 0.9,
        articles_last_30_days: 50,
        action: 'disable_source',
        target: 'noise-feed',
        target_label: 'Noise Feed',
      },
    ],
  },
};

const LEGACY_RECAP: WeeklyRecap = {
  id: 2,
  user_id: 1,
  week_start: '2026-06-22',
  created_at: '2026-06-29T00:00:00+00:00',
  narrative: 'Nice reading week',
  data: {
    week_start: '2026-06-22',
    week_end: '2026-06-29',
    generated_at: '2026-06-29T00:00:00+00:00',
    articles_read: 4,
    categories: [],
    sources: [],
    minutes_read: 15.0,
    current_streak_days: 3,
  },
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe('WeeklyRecapPage', () => {
  it('renders saved backlog, dwell profile, and nudges for an enriched recap', async () => {
    vi.mocked(api.fetchRecaps).mockResolvedValue([ENRICHED_RECAP]);
    render(<WeeklyRecapPage />, { wrapper: Wrapper });

    await screen.findByText('Saved backlog');
    expect(screen.getByText('Skim vs deep read')).toBeInTheDocument();
    expect(screen.getByText('Suggested changes')).toBeInTheDocument();
    expect(screen.getByText('Noisy source: Noise Feed')).toBeInTheDocument();
    expect(screen.getByText('22.5s')).toBeInTheDocument();
  });

  it('renders a legacy recap without the enriched fields without crashing', async () => {
    vi.mocked(api.fetchRecaps).mockResolvedValue([LEGACY_RECAP]);
    render(<WeeklyRecapPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText('4')).toBeInTheDocument();
    });
    expect(screen.queryByText('Saved backlog')).not.toBeInTheDocument();
    expect(screen.queryByText('Skim vs deep read')).not.toBeInTheDocument();
    expect(screen.queryByText('Suggested changes')).not.toBeInTheDocument();
  });

  it('renders a multi-paragraph narrative as separate paragraph elements', async () => {
    const first = 'You read 4 articles in 15 minutes this week.';
    const second = 'Keep up the great momentum with your 3 day streak.';
    vi.mocked(api.fetchRecaps).mockResolvedValue([
      { ...LEGACY_RECAP, narrative: `${first}\n\n${second}` },
    ]);
    render(<WeeklyRecapPage />, { wrapper: Wrapper });

    const firstParagraph = await screen.findByText(first);
    const secondParagraph = await screen.findByText(second);
    expect(firstParagraph.tagName).toBe('P');
    expect(secondParagraph.tagName).toBe('P');
    expect(firstParagraph).not.toBe(secondParagraph);
  });
});
