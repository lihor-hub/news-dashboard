// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LessonLibraryPage } from '../pages/LessonLibraryPage';
import type { Lesson } from '../api';
import * as api from '../api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { changeLanguage: () => Promise.resolve() },
  }),
}));

const COMPLETE_LESSON: Lesson = {
  id: 1,
  user_id: 1,
  original_url: 'https://example.com/article-one',
  normalized_url: 'https://example.com/article-one',
  title: 'A careful article',
  source_name: 'Example Journal',
  author: 'Jane Example',
  published_at: '2026-07-08T10:00:00Z',
  source_content: 'body',
  generation_status: 'complete',
  generation_error: null,
  depth: 'normal',
  persona: 'developer',
  podcast_status: null,
  podcast_error: null,
  slide_deck: null,
  slide_deck_status: null,
  slide_deck_error: null,
  infographic: null,
  infographic_status: null,
  infographic_error: null,
  graph_context_available: false,
  lesson_detail: {
    gist: 'The article argues that strong source selection matters more than raw volume.',
    explanation: 'explanation',
    key_claims: ['claim one'],
    prerequisite_concepts: ['concept one'],
    why_it_matters: 'matters',
    read_worthiness: { verdict: 'study', rationale: 'rationale' },
    who_should_read: ['everyone'],
    questions_to_keep_in_mind: ['question one'],
    citations: [{ label: '1', snippet: 'snippet', source: 'source' }],
  },
  study_artifacts: null,
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T10:01:00Z',
};

const FAILED_LESSON: Lesson = {
  ...COMPLETE_LESSON,
  id: 2,
  title: null,
  lesson_detail: null,
  generation_status: 'failed',
  generation_error: 'Could not extract readable article content.',
  original_url: 'https://example.com/article-two',
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/learn/library']}>
        <LessonLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('LessonLibraryPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('lists lessons with links to their detail page', async () => {
    vi.spyOn(api, 'listLessons').mockResolvedValue([COMPLETE_LESSON, FAILED_LESSON]);

    renderPage();

    expect(await screen.findByText('A careful article')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /A careful article/i })).toHaveAttribute(
      'href',
      '/learn/1'
    );
    expect(screen.getByText('Could not extract readable article content.')).toBeInTheDocument();
  });

  it('shows an empty state when there are no lessons', async () => {
    vi.spyOn(api, 'listLessons').mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText(/no lessons yet/i)).toBeInTheDocument();
  });

  it('re-queries with search text after debounce', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const listSpy = vi.spyOn(api, 'listLessons').mockResolvedValue([COMPLETE_LESSON]);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    renderPage();
    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith({ q: undefined, status: undefined, verdict: undefined })
    );

    await user.type(screen.getByLabelText(/search lessons/i), 'signal');

    await vi.advanceTimersByTimeAsync(300);

    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith({ q: 'signal', status: undefined, verdict: undefined })
    );
  });

  it('filters by status and verdict', async () => {
    const listSpy = vi.spyOn(api, 'listLessons').mockResolvedValue([COMPLETE_LESSON]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());

    await user.selectOptions(screen.getByLabelText(/filter by status/i), 'complete');
    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith({ q: undefined, status: 'complete', verdict: undefined })
    );

    await user.selectOptions(screen.getByLabelText(/filter by read-worthiness/i), 'study');
    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith({ q: undefined, status: 'complete', verdict: 'study' })
    );
  });

  it('shows an error state when loading fails', async () => {
    vi.spyOn(api, 'listLessons').mockRejectedValue(new Error('boom'));

    renderPage();

    expect(await screen.findByText(/failed to load your lesson library/i)).toBeInTheDocument();
  });
});
