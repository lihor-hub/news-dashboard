// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LessonDetailPage } from '../pages/LessonDetailPage';
import type { Lesson } from '../api';
import * as api from '../api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { changeLanguage: () => Promise.resolve() },
  }),
}));

const COMPLETE_LESSON: Lesson = {
  id: 5,
  user_id: 1,
  original_url: 'https://example.com/article',
  normalized_url: 'https://example.com/article',
  title: 'A careful article',
  source_name: 'Example Journal',
  author: 'Jane Example',
  published_at: '2026-07-08T10:00:00Z',
  source_content: 'body content',
  generation_status: 'complete',
  generation_error: null,
  depth: 'normal',
  persona: 'developer',
  podcast_status: null,
  podcast_error: null,
  lesson_detail: {
    gist: 'gist text',
    explanation: 'explanation text',
    key_claims: ['claim one'],
    prerequisite_concepts: ['concept one'],
    why_it_matters: 'matters text',
    read_worthiness: { verdict: 'study', rationale: 'rationale text' },
    who_should_read: ['everyone'],
    questions_to_keep_in_mind: ['question one'],
    citations: [{ label: '1', snippet: 'snippet', source: 'source' }],
  },
  study_artifacts: null,
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T10:01:00Z',
};

const PENDING_LESSON: Lesson = {
  ...COMPLETE_LESSON,
  id: 6,
  title: null,
  lesson_detail: null,
  generation_status: 'pending',
};

function renderPage(lessonId: number) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/learn/${lessonId}`]}>
        <Routes>
          <Route path="/learn/:id" element={<LessonDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('LessonDetailPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fetches and renders a lesson by id', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);

    renderPage(5);

    expect(await screen.findByText('A careful article')).toBeInTheDocument();
    expect(api.fetchLesson).toHaveBeenCalledWith(5);
    expect(screen.getByRole('link', { name: /back to library/i })).toHaveAttribute(
      'href',
      '/learn/library'
    );
  });

  it('shows an error state when the lesson cannot be loaded', async () => {
    vi.spyOn(api, 'fetchLesson').mockRejectedValue(new Error('lesson fetch failed'));

    renderPage(999);

    expect(await screen.findByText('lesson fetch failed')).toBeInTheDocument();
  });

  it('polls a pending lesson until it completes', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'fetchLesson')
      .mockResolvedValueOnce(PENDING_LESSON)
      .mockResolvedValueOnce(COMPLETE_LESSON);

    renderPage(6);

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getAllByText('learn.status.pending').length).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(screen.getByText('A careful article')).toBeInTheDocument();
  });

  it('shows a create-podcast button, then the player once generation succeeds', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonPodcast').mockResolvedValue({
      ...COMPLETE_LESSON,
      podcast_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    const createButton = screen.getByRole('button', { name: 'Create podcast' });
    expect(createButton).toBeInTheDocument();

    await userEvent.click(createButton);

    await waitFor(() => {
      expect(api.generateLessonPodcast).toHaveBeenCalledWith(5, false);
    });
    expect(await screen.findByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
    const player = document.querySelector('audio');
    expect(player).toHaveAttribute('src', '/api/learn/lessons/5/podcast');
  });

  it('shows a friendly error and keeps the create button when podcast generation fails', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonPodcast').mockRejectedValue(
      new api.HttpError(503, 'AI not configured')
    );

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Create podcast' }));

    expect(await screen.findByText('AI not configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create podcast' })).toBeInTheDocument();
  });

  it('shows the failed-podcast banner from persisted lesson state', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      podcast_status: 'failed',
      podcast_error: 'Could not generate podcast audio.',
    });

    renderPage(5);

    expect(await screen.findByText('Could not generate podcast audio.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
  });

  it('forces regeneration when clicking regenerate on an existing podcast', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      podcast_status: 'complete',
    });
    vi.spyOn(api, 'generateLessonPodcast').mockResolvedValue({
      ...COMPLETE_LESSON,
      podcast_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

    await waitFor(() => {
      expect(api.generateLessonPodcast).toHaveBeenCalledWith(5, true);
    });
  });
});
