// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReadingDnaPage } from '../pages/ReadingDnaPage';
import * as api from '../api';
import type { Quiz, QuizHistoryItem, QuizResult, ReadingDna } from '../types';

const dna: ReadingDna = {
  range_days: 30,
  generated_at: '2026-06-21T10:00:00Z',
  categories: [],
  sources: [],
  monthly_time: [],
  average_dwell_seconds: 0,
};

const quiz: Quiz = {
  id: 7,
  user_id: 1,
  created_at: '2026-06-21T10:00:00Z',
  score: null,
  questions: [
    {
      question: 'Which model uses attention?',
      options: ['Transformer', 'Database', 'Queue', 'Cache'],
      correct_index: 0,
      explanation: 'Transformers use attention.',
      article_id: 10,
    },
  ],
};

const quizResult: QuizResult = {
  quiz_id: 7,
  score: 1,
  total: 1,
  questions: [{ ...quiz.questions[0], your_answer: 0 }],
};

const history: QuizHistoryItem[] = [
  {
    id: 7,
    user_id: 1,
    created_at: '2026-06-21T10:00:00Z',
    score: 1,
    total: 1,
    completed: true,
    submitted_at: '2026-06-21T10:05:00Z',
  },
  {
    id: 6,
    user_id: 1,
    created_at: '2026-06-14T10:00:00Z',
    score: null,
    total: 3,
    completed: false,
    submitted_at: null,
  },
];

function mockBasics() {
  vi.spyOn(api, 'fetchReadingDna').mockResolvedValue(dna);
  vi.spyOn(api, 'fetchRecommendationPreferences').mockResolvedValue({
    category_weights: {},
    novelty_weight: 1,
  });
  vi.spyOn(api, 'fetchGoals').mockResolvedValue([]);
  vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue(null);
  vi.spyOn(api, 'fetchQuizCandidates').mockRejectedValue(new Error('not available'));
  vi.spyOn(api, 'fetchQuizHistory').mockResolvedValue([]);
}

async function renderLearningCenter() {
  render(<ReadingDnaPage />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Learning Center' })).toBeTruthy());
  await userEvent.click(screen.getByRole('button', { name: 'Learning Center' }));
}

describe('ReadingDnaPage quiz history', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockBasics();
  });

  it('renders quiz progress when history exists', async () => {
    vi.spyOn(api, 'fetchQuizHistory').mockResolvedValue(history);

    await renderLearningCenter();

    await waitFor(() => expect(screen.getByText('Quiz Progress')).toBeTruthy());
    expect(screen.getByText('Attempts')).toBeTruthy();
    expect(screen.getByText('Average')).toBeTruthy();
    expect(screen.getByText('1/1')).toBeTruthy();
    expect(screen.getByText('—/3')).toBeTruthy();
  });

  it('does not render quiz progress for empty history', async () => {
    await renderLearningCenter();

    await waitFor(() =>
      expect(
        screen.getByText('No quiz yet. Generate one based on your recent reading.')
      ).toBeTruthy()
    );
    expect(screen.queryByText('Quiz Progress')).toBeNull();
  });

  it('refreshes quiz history after generating a quiz', async () => {
    const fetchHistory = vi
      .spyOn(api, 'fetchQuizHistory')
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(history);
    vi.spyOn(api, 'generateQuiz').mockResolvedValue(quiz);

    await renderLearningCenter();
    await userEvent.click(screen.getByRole('button', { name: 'Generate quiz' }));

    await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Quiz Progress')).toBeTruthy();
  });

  it('refreshes quiz history after submitting a quiz', async () => {
    const fetchHistory = vi
      .spyOn(api, 'fetchQuizHistory')
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(history);
    vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue(quiz);
    vi.spyOn(api, 'submitQuiz').mockResolvedValue(quizResult);

    await renderLearningCenter();
    await userEvent.click(await screen.findByLabelText('Transformer'));
    await userEvent.click(screen.getByRole('button', { name: 'Submit final answers' }));

    await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Quiz Progress')).toBeTruthy();
  });
});
