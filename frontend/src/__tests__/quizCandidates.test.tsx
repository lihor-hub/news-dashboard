// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReadingDnaPage } from '../pages/ReadingDnaPage';
import * as api from '../api';

vi.mock('../api', () => ({
  fetchGoals: vi.fn(),
  fetchLatestQuiz: vi.fn(),
  fetchQuizCandidates: vi.fn(),
  fetchReadingDna: vi.fn(),
  fetchRecommendationPreferences: vi.fn(),
  createGoal: vi.fn(),
  deleteGoal: vi.fn(),
  generateQuiz: vi.fn(),
  submitQuiz: vi.fn(),
  saveRecommendationPreferences: vi.fn(),
}));

const mockedApi = vi.mocked(api, true);

async function renderLearningTab() {
  render(
    <MemoryRouter>
      <ReadingDnaPage />
    </MemoryRouter>
  );
  // Wait for the top-level page to finish loading, then switch to the Learning tab.
  await waitFor(() => {
    expect(screen.getByText('Learning Center')).toBeInTheDocument();
  });
  fireEvent.click(screen.getByText('Learning Center'));
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedApi.fetchGoals.mockResolvedValue([]);
  mockedApi.fetchLatestQuiz.mockResolvedValue(null);
  mockedApi.fetchReadingDna.mockResolvedValue({
    range_days: 30,
    generated_at: '2026-06-27T00:00:00Z',
    categories: [],
    sources: [],
    monthly_time: [],
    average_dwell_seconds: 0,
  });
  mockedApi.fetchRecommendationPreferences.mockResolvedValue({
    category_weights: {},
    novelty_weight: 0.5,
  });
});

describe('quiz candidate preview', () => {
  it('shows candidate articles before generation when candidates exist', async () => {
    mockedApi.fetchQuizCandidates.mockResolvedValue([
      {
        id: 1,
        title: 'AI Transformer Deep Dive',
        category: 'tech',
        source_name: 'Source One',
        done_at: '2026-06-27T10:00:00Z',
        goal_matched: false,
        matched_keywords: [],
      },
    ]);

    await renderLearningTab();

    await waitFor(() => {
      expect(screen.getByText('AI Transformer Deep Dive')).toBeInTheDocument();
    });
    expect(screen.getByText(/quiz will draw from/i)).toBeInTheDocument();
  });

  it('shows goal match indicator when candidate matches a goal', async () => {
    mockedApi.fetchQuizCandidates.mockResolvedValue([
      {
        id: 2,
        title: 'Quantum Computing Basics',
        category: 'science',
        source_name: 'Science Weekly',
        done_at: '2026-06-27T09:00:00Z',
        goal_matched: true,
        matched_keywords: ['quantum'],
      },
    ]);

    await renderLearningTab();

    await waitFor(() => {
      expect(screen.getByText('Quantum Computing Basics')).toBeInTheDocument();
    });
    expect(screen.getByText(/✓ goal/)).toBeInTheDocument();
  });

  it('shows empty state explaining how to create quiz material when no candidates', async () => {
    mockedApi.fetchQuizCandidates.mockResolvedValue([]);

    await renderLearningTab();

    await waitFor(() => {
      expect(screen.getByText(/Mark articles as done/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Generate quiz/)).not.toBeInTheDocument();
  });

  it('shows generate button alongside candidate preview when candidates exist', async () => {
    mockedApi.fetchQuizCandidates.mockResolvedValue([
      {
        id: 3,
        title: 'Some Article',
        category: 'tech',
        source_name: null,
        done_at: '2026-06-27T08:00:00Z',
        goal_matched: false,
        matched_keywords: [],
      },
    ]);

    await renderLearningTab();

    await waitFor(() => {
      expect(screen.getByText('Some Article')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Generate quiz/i })).toBeInTheDocument();
  });
});
