// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as api from '../api';
import { FeedNudgeBanner } from '../components/FeedNudgeBanner';
import type { PersonalizationNudge } from '../types';

vi.mock('../api', () => ({
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

const SOURCE_NUDGE: PersonalizationNudge = {
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
};

const TOPIC_NUDGE: PersonalizationNudge = {
  id: 'topic:politics',
  kind: 'topic',
  title: 'Noisy topic: Politics',
  message: "You've skipped 80% of recent 'politics' articles. Reduce its weight in your feed?",
  reason: 'low_signal',
  skip_rate: 0.8,
  articles_last_30_days: 25,
  action: 'reduce_topic_weight',
  target: 'politics',
  target_label: 'Politics',
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe('FeedNudgeBanner', () => {
  it('renders nothing when there are no nudges', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([]);
    const { container } = render(<FeedNudgeBanner />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(vi.mocked(api.fetchPersonalizationNudges)).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });

  it('renders a source nudge card', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([SOURCE_NUDGE]);
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    await screen.findByText('Noisy source: Noise Feed');
    expect(screen.getByText(/90%/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unsubscribe' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Not now' })).toBeInTheDocument();
  });

  it('renders a topic nudge card', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([TOPIC_NUDGE]);
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    await screen.findByText('Noisy topic: Politics');
    expect(screen.getByRole('button', { name: 'Reduce weight' })).toBeInTheDocument();
  });

  it('calls applyPersonalizationNudge when apply button is clicked', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([SOURCE_NUDGE]);
    vi.mocked(api.applyPersonalizationNudge).mockResolvedValue({ applied: true });
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    const btn = await screen.findByRole('button', { name: 'Unsubscribe' });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(vi.mocked(api.applyPersonalizationNudge)).toHaveBeenCalledWith('source:noise-feed');
    });
  });

  it('calls dismissPersonalizationNudge when dismiss button is clicked', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([SOURCE_NUDGE]);
    vi.mocked(api.dismissPersonalizationNudge).mockResolvedValue({ dismissed: true });
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    const btn = await screen.findByRole('button', { name: 'Not now' });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(vi.mocked(api.dismissPersonalizationNudge)).toHaveBeenCalledWith(
        'source:noise-feed',
        7
      );
    });
  });

  it('hides the card after dismissal', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([SOURCE_NUDGE]);
    vi.mocked(api.dismissPersonalizationNudge).mockResolvedValue({ dismissed: true });
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    const btn = await screen.findByRole('button', { name: 'Not now' });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.queryByText('Noisy source: Noise Feed')).not.toBeInTheDocument();
    });
  });

  it('calls dismissPersonalizationNudge when the X button is clicked', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([SOURCE_NUDGE]);
    vi.mocked(api.dismissPersonalizationNudge).mockResolvedValue({ dismissed: true });
    render(<FeedNudgeBanner />, { wrapper: Wrapper });
    await screen.findByText('Noisy source: Noise Feed');
    const xBtn = screen.getByRole('button', { name: 'Dismiss' });
    fireEvent.click(xBtn);
    await waitFor(() => {
      expect(vi.mocked(api.dismissPersonalizationNudge)).toHaveBeenCalled();
    });
  });
});

describe('FeedNudgeBanner — regression: no nudge when query returns empty', () => {
  it('does not render anything if nudges list is empty', async () => {
    vi.mocked(api.fetchPersonalizationNudges).mockResolvedValue([]);
    const { container } = render(<FeedNudgeBanner />, { wrapper: Wrapper });
    await waitFor(() => expect(vi.mocked(api.fetchPersonalizationNudges)).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });
});
