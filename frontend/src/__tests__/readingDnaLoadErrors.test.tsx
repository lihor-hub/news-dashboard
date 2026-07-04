// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as api from '../api';
import { HttpError } from '../api';
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
  vi.spyOn(api, 'fetchGoals').mockResolvedValue([]);
  vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue(null);
  vi.spyOn(api, 'fetchQuizCandidates').mockResolvedValue([]);
  vi.spyOn(api, 'fetchQuizHistory').mockResolvedValue([]);
}

async function renderLearningCenter() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ReadingDnaPage />
    </QueryClientProvider>
  );
  await waitFor(() => expect(screen.getByRole('button', { name: 'Learning Center' })).toBeTruthy());
  await userEvent.click(screen.getByRole('button', { name: 'Learning Center' }));
}

describe('ReadingDnaPage load error surfaces', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockBasics();
  });

  describe('fetchLatestQuiz error differentiation', () => {
    it('shows normal "No quiz yet" path when latest quiz returns 404', async () => {
      vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue(null);
      vi.spyOn(api, 'fetchQuizCandidates').mockResolvedValue([
        {
          id: 1,
          title: 'Some Article',
          category: 'tech',
          source_name: null,
          done_at: '2026-06-21T10:00:00Z',
          goal_matched: false,
          matched_keywords: [],
        },
      ]);

      await renderLearningCenter();

      expect(
        await screen.findByText('No quiz yet. Generate one based on your recent reading.')
      ).toBeTruthy();
      expect(screen.queryByText('Failed to load quiz.')).toBeNull();
    });

    it('shows quiz error state when latest quiz request fails with non-404', async () => {
      vi.spyOn(api, 'fetchLatestQuiz').mockRejectedValue(
        new HttpError(500, 'Internal Server Error')
      );

      await renderLearningCenter();

      expect(await screen.findByText('Failed to load quiz.')).toBeTruthy();
      expect(
        screen.queryByText('No quiz yet. Generate one based on your recent reading.')
      ).toBeNull();
    });

    it('shows quiz error state when latest quiz request is rejected (network failure)', async () => {
      vi.spyOn(api, 'fetchLatestQuiz').mockRejectedValue(new Error('Network error'));

      await renderLearningCenter();

      expect(await screen.findByText('Failed to load quiz.')).toBeTruthy();
    });
  });

  it('shows goals error when goals request fails', async () => {
    vi.spyOn(api, 'fetchGoals').mockRejectedValue(new Error('Unauthorized'));

    await renderLearningCenter();

    expect(await screen.findByText('Failed to load goals.')).toBeTruthy();
    expect(screen.queryByText('No goals yet. Add one to boost relevant articles.')).toBeNull();
  });

  it('shows history error when quiz history request fails', async () => {
    vi.spyOn(api, 'fetchQuizHistory').mockRejectedValue(new Error('server error'));

    await renderLearningCenter();

    expect(await screen.findByText('Failed to load quiz history.')).toBeTruthy();
  });

  it('shows candidates error when quiz candidates request fails', async () => {
    vi.spyOn(api, 'fetchQuizCandidates').mockRejectedValue(new Error('Forbidden'));

    await renderLearningCenter();

    expect(await screen.findByText('Failed to load quiz material.')).toBeTruthy();
  });

  it('preserves generate button when only candidates fail', async () => {
    vi.spyOn(api, 'fetchQuizCandidates').mockRejectedValue(new Error('Forbidden'));

    await renderLearningCenter();

    await screen.findByText('Failed to load quiz material.');
    expect(screen.getByRole('button', { name: 'Generate quiz' })).toBeTruthy();
  });
});
