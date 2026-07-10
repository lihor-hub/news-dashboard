// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LessonSuggestions } from '../components/LessonSuggestions';
import type { Lesson, LessonSuggestion } from '../api';
import * as api from '../api';
import * as workflowApi from '../api/workflowApi';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { changeLanguage: () => Promise.resolve() },
  }),
}));

const SUGGESTION_ONE: LessonSuggestion = {
  article_id: 1,
  title: 'A deep dive into caching',
  url: 'https://example.com/caching',
  source_name: 'Example Journal',
  category: 'tech',
  score: 0.9,
  reasons: ['You starred this article'],
};

const SUGGESTION_TWO: LessonSuggestion = {
  article_id: 2,
  title: 'Notes on distributed systems',
  url: 'https://example.com/distsys',
  source_name: 'Another Source',
  category: 'tech',
  score: 0.7,
  reasons: ['High editorial importance score'],
};

const GENERATED_LESSON: Lesson = {
  id: 10,
  user_id: 1,
  original_url: SUGGESTION_ONE.url,
  normalized_url: SUGGESTION_ONE.url,
  title: SUGGESTION_ONE.title,
  source_name: SUGGESTION_ONE.source_name,
  author: null,
  published_at: null,
  source_content: null,
  generation_status: 'pending',
  generation_error: null,
  depth: 'normal',
  persona: 'developer',
  podcast_status: null,
  podcast_error: null,
  slide_deck: null,
  slide_deck_status: null,
  slide_deck_error: null,
  lesson_detail: null,
  study_artifacts: null,
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T10:00:00Z',
};

function renderSuggestions(onGenerated: (lesson: Lesson) => void = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LessonSuggestions onGenerated={onGenerated} />
    </QueryClientProvider>
  );
}

describe('LessonSuggestions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing while loading and nothing when there are no suggestions', async () => {
    vi.spyOn(api, 'listLessonSuggestions').mockResolvedValue([]);

    const { container } = renderSuggestions();

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('lists suggestions with their reasons', async () => {
    vi.spyOn(api, 'listLessonSuggestions').mockResolvedValue([SUGGESTION_ONE, SUGGESTION_TWO]);

    renderSuggestions();

    expect(await screen.findByText('A deep dive into caching')).toBeInTheDocument();
    expect(screen.getByText('Notes on distributed systems')).toBeInTheDocument();
    expect(screen.getByText('You starred this article')).toBeInTheDocument();
    expect(screen.getByText('High editorial importance score')).toBeInTheDocument();
  });

  it('removes a suggestion from the list when dismissed', async () => {
    vi.spyOn(api, 'listLessonSuggestions').mockResolvedValue([SUGGESTION_ONE]);
    const dismissSpy = vi
      .spyOn(api, 'dismissLessonSuggestion')
      .mockResolvedValue({ dismissed: true, article_id: SUGGESTION_ONE.article_id });

    renderSuggestions();
    await screen.findByText('A deep dive into caching');

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(dismissSpy).toHaveBeenCalledWith(SUGGESTION_ONE.article_id));
    await waitFor(() =>
      expect(screen.queryByText('A deep dive into caching')).not.toBeInTheDocument()
    );
  });

  it('stars the article and removes it from the list when saved', async () => {
    vi.spyOn(api, 'listLessonSuggestions').mockResolvedValue([SUGGESTION_ONE]);
    const starSpy = vi.spyOn(workflowApi, 'patchArticleStar').mockResolvedValue(undefined);

    renderSuggestions();
    await screen.findByText('A deep dive into caching');

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(starSpy).toHaveBeenCalledWith(String(SUGGESTION_ONE.article_id), true)
    );
    await waitFor(() =>
      expect(screen.queryByText('A deep dive into caching')).not.toBeInTheDocument()
    );
  });

  it('generates a lesson from a suggestion and notifies the caller', async () => {
    vi.spyOn(api, 'listLessonSuggestions').mockResolvedValue([SUGGESTION_ONE]);
    const createSpy = vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(GENERATED_LESSON);
    const onGenerated = vi.fn();

    renderSuggestions(onGenerated);
    await screen.findByText('A deep dive into caching');

    await userEvent.click(screen.getByRole('button', { name: /Generate lesson/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalledWith(SUGGESTION_ONE.url));
    await waitFor(() => expect(onGenerated).toHaveBeenCalledWith(GENERATED_LESSON));
    await waitFor(() =>
      expect(screen.queryByText('A deep dive into caching')).not.toBeInTheDocument()
    );
  });
});
