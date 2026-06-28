// @vitest-environment happy-dom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import { ReadingDnaPage } from '../pages/ReadingDnaPage';
import type { Quiz, QuizResult, ReadingDna } from '../types';

const dna: ReadingDna = {
  range_days: 30,
  generated_at: '2026-06-21T10:00:00Z',
  categories: [],
  sources: [],
  monthly_time: [],
  average_dwell_seconds: 0,
};

const quiz: Quiz = {
  id: 12,
  user_id: 1,
  created_at: '2026-06-21T10:00:00Z',
  score: null,
  questions: [
    {
      question: 'Which architecture uses self-attention for sequence modeling?',
      options: [
        'Transformer architecture with a deliberately long answer that should wrap cleanly',
        'Relational database index',
        'Message queue',
        'Static site generator',
      ],
      correct_index: 0,
      explanation: 'Transformers use self-attention to model token relationships.',
      article_id: 101,
    },
    {
      question: 'What should a good retrieval benchmark measure?',
      options: ['Latency only', 'Recall and usefulness', 'Logo color', 'Cache size'],
      correct_index: 1,
      explanation: 'Benchmarks need to measure whether useful evidence is retrieved.',
      article_id: 102,
    },
  ],
};

const result: QuizResult = {
  quiz_id: 12,
  score: 1,
  total: 2,
  questions: [
    { ...quiz.questions[0], your_answer: 0 },
    { ...quiz.questions[1], your_answer: 0 },
  ],
};

function mockBasics() {
  vi.spyOn(api, 'fetchReadingDna').mockResolvedValue(dna);
  vi.spyOn(api, 'fetchRecommendationPreferences').mockResolvedValue({
    category_weights: {},
    novelty_weight: 1,
  });
  vi.spyOn(api, 'fetchGoals').mockResolvedValue([]);
  vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue(quiz);
  vi.spyOn(api, 'fetchQuizCandidates').mockResolvedValue([]);
  vi.spyOn(api, 'fetchQuizHistory').mockResolvedValue([]);
  vi.spyOn(api, 'submitQuiz').mockResolvedValue(result);
  vi.spyOn(api, 'generateQuiz').mockResolvedValue(quiz);
}

async function renderLearningCenter() {
  render(<ReadingDnaPage />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Learning Center' })).toBeTruthy());
  await userEvent.click(screen.getByRole('button', { name: 'Learning Center' }));
}

describe('ReadingDnaPage quiz answering UX', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockBasics();
  });

  it('shows unanswered progress and explains why submit is disabled', async () => {
    await renderLearningCenter();

    expect(await screen.findByText('0 of 2 answered')).toBeTruthy();
    expect(screen.getByText('Answer 2 more questions to submit.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Answer all questions to submit' })).toBeDisabled();

    await userEvent.click(screen.getByLabelText(/Transformer architecture/));

    expect(screen.getByText('1 of 2 answered')).toBeTruthy();
    expect(screen.getByText('Answer 1 more question to submit.')).toBeTruthy();
  });

  it('uses accessible radio groups and submits the selected answer payload', async () => {
    const submitQuiz = vi.spyOn(api, 'submitQuiz').mockResolvedValue(result);

    await renderLearningCenter();

    const firstGroup = await screen.findByRole('radiogroup', {
      name: 'Question 1: Which architecture uses self-attention for sequence modeling?',
    });
    expect(
      within(firstGroup).getByRole('radio', { name: /Transformer architecture/ })
    ).toBeTruthy();

    await userEvent.click(
      within(firstGroup).getByRole('radio', { name: /Transformer architecture/ })
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Recall and usefulness' }));

    expect(screen.getByText('Ready to submit 2 final answers.')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Submit final answers' }));

    await waitFor(() => expect(submitQuiz).toHaveBeenCalledWith(12, [0, 1]));
  });

  it('renders result review details and an obvious regenerate action', async () => {
    vi.spyOn(api, 'fetchLatestQuiz').mockResolvedValue({ ...quiz, completed_result: result });

    await renderLearningCenter();

    expect(await screen.findByText('1/2')).toBeTruthy();
    expect(screen.getAllByText('Your answer')).toHaveLength(2);
    expect(screen.getAllByText('Correct answer')).toHaveLength(2);
    expect(
      screen.getByText('Transformers use self-attention to model token relationships.')
    ).toBeTruthy();
    expect(
      screen.getByText('Benchmarks need to measure whether useful evidence is retrieved.')
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Generate a new quiz' })).toBeTruthy();
  });
});
