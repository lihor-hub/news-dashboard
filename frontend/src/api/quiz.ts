import type { Quiz, QuizCandidate, QuizHistoryItem, QuizResult } from '../types';
import { requestJson, HttpError } from './core';

export async function fetchQuizCandidates(): Promise<QuizCandidate[]> {
  const data = await requestJson<{ candidates: QuizCandidate[] }>('/api/quizzes/candidates');
  return data.candidates;
}

export async function fetchLatestQuiz(): Promise<Quiz | null> {
  try {
    return await requestJson<Quiz>('/api/quizzes/latest');
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function fetchQuizHistory(): Promise<QuizHistoryItem[]> {
  const data = await requestJson<{ items: QuizHistoryItem[] }>('/api/quizzes');
  return data.items;
}

export async function generateQuiz(): Promise<Quiz> {
  return requestJson<Quiz>('/api/quizzes/generate', { method: 'POST' });
}

export async function submitQuiz(quizId: number, answers: number[]): Promise<QuizResult> {
  return requestJson<QuizResult>(`/api/quizzes/${quizId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}
