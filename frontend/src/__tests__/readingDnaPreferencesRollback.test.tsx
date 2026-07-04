// @vitest-environment happy-dom
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as api from '../api';
import { ReadingDnaPage } from '../pages/ReadingDnaPage';
import type { ReadingDna } from '../types';

const dna: ReadingDna = {
  range_days: 30,
  generated_at: '2026-06-21T10:00:00Z',
  categories: [],
  sources: [],
  monthly_time: [],
  average_dwell_seconds: 0,
};

function mockBasics() {
  vi.spyOn(api, 'fetchReadingDna').mockResolvedValue(dna);
  vi.spyOn(api, 'fetchRecommendationPreferences').mockResolvedValue({
    category_weights: {},
    novelty_weight: 1,
  });
  vi.spyOn(api, 'fetchReadingStreak').mockRejectedValue(new Error('no streak'));
  vi.spyOn(api, 'fetchAchievements').mockRejectedValue(new Error('no achievements'));
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReadingDnaPage />
    </QueryClientProvider>
  );
}

describe('ReadingDnaPage preferences optimistic rollback', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockBasics();
  });

  it('restores the previous preference value when saving fails', async () => {
    let rejectSave!: (err: Error) => void;
    vi.spyOn(api, 'saveRecommendationPreferences').mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectSave = reject;
      })
    );

    renderPage();

    const noveltyRow = (await screen.findByText('novelty')).closest('label');
    if (!noveltyRow) throw new Error('novelty slider not found');
    const slider = within(noveltyRow).getByRole('slider');

    expect(within(noveltyRow).getByText('1.0x')).toBeTruthy();

    fireEvent.input(slider, { target: { value: '2.5' } });

    await waitFor(() => expect(within(noveltyRow).getByText('2.5x')).toBeTruthy());

    rejectSave(new Error('save failed'));

    await waitFor(() => expect(within(noveltyRow).getByText('1.0x')).toBeTruthy());
    expect(await screen.findByText('save failed')).toBeTruthy();
  });
});
