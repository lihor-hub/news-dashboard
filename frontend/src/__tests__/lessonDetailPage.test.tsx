// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react';
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
  slide_deck: null,
  slide_deck_status: null,
  slide_deck_error: null,
  infographic: null,
  infographic_status: null,
  infographic_error: null,
  graph_context_available: true,
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
    vi.spyOn(api, 'fetchLessonTrails').mockResolvedValue({
      lesson_id: 5,
      groups: [
        { path: 'prerequisite', label: 'Prerequisite concepts', items: [] },
        { path: 'easier', label: 'Easier on-ramp', items: [] },
        { path: 'adjacent', label: 'Adjacent reads', items: [] },
        { path: 'deeper', label: 'Deeper path', items: [] },
      ],
      empty_message: 'No related lessons or articles are available in your corpus yet.',
    });
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
    expect(screen.getByText('Graph context')).toBeInTheDocument();
  });

  it('indicates when a completed lesson has graph context', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      lesson_detail: {
        ...COMPLETE_LESSON.lesson_detail!,
        graph_context: {
          available: true,
          entities: [{ id: 'concept:concept-one', name: 'concept one', type: 'concept' }],
          relationships: [],
          related_article_ids: [42],
          related_briefing_ids: [],
        },
      },
    });

    renderPage(5);

    expect(await screen.findByText('Graph context available')).toBeInTheDocument();
  });

  it('renders an interactive lesson concept graph and linked graph details', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      lesson_detail: {
        ...COMPLETE_LESSON.lesson_detail!,
        key_claims: ['Transformers use attention to route information.'],
        graph_context: {
          available: true,
          entities: [
            { id: 'concept:attention', name: 'Attention', type: 'concept' },
            { id: 'product:transformers', name: 'Transformers', type: 'product' },
          ],
          relationships: [
            {
              source: 'product:transformers',
              target: 'concept:attention',
              relationship_type: 'uses',
              label: 'uses',
              confidence: 0.91,
            },
          ],
          related_article_ids: [42],
          related_briefing_ids: [9],
        },
      },
    });

    const { container } = renderPage(5);

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
      expect(container.querySelectorAll('[data-testid="lesson-graph-node"]')).toHaveLength(2);
    });
    expect(container.querySelectorAll('[data-testid="lesson-graph-edge"]')).toHaveLength(1);
    expect(screen.getByText('Attention')).toBeInTheDocument();
    expect(
      screen.getAllByText('Transformers use attention to route information.').length
    ).toBeGreaterThan(1);
    expect(screen.getByRole('link', { name: 'Article #42' })).toHaveAttribute('href', '/a/42');
    expect(screen.getByRole('link', { name: 'Briefing #9' })).toHaveAttribute('href', '/briefs/9');
  });

  it('shows relationship details when a graph node is selected', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      lesson_detail: {
        ...COMPLETE_LESSON.lesson_detail!,
        graph_context: {
          available: true,
          entities: [
            { id: 'concept:attention', name: 'Attention', type: 'concept' },
            { id: 'product:transformers', name: 'Transformers', type: 'product' },
          ],
          relationships: [
            {
              source: 'product:transformers',
              target: 'concept:attention',
              relationship_type: 'uses',
              label: 'uses',
              confidence: 0.91,
            },
          ],
          related_article_ids: [],
          related_briefing_ids: [],
        },
      },
    });

    const { container } = renderPage(5);
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="lesson-graph-node"]')).toHaveLength(2);
    });
    const attention = [...container.querySelectorAll('[data-testid="lesson-graph-node"]')].find(
      (node) => node.getAttribute('data-entity') === 'concept:attention'
    );
    expect(attention).toBeTruthy();

    fireEvent.click(attention!.closest('.react-flow__node') ?? attention!);

    expect(await screen.findByText('uses')).toBeInTheDocument();
    expect(screen.getAllByText('Transformers').length).toBeGreaterThan(0);
  });

  it('shows an empty lesson graph state when extraction found no nodes', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      lesson_detail: {
        ...COMPLETE_LESSON.lesson_detail!,
        graph_context: {
          available: true,
          entities: [],
          relationships: [],
          related_article_ids: [],
          related_briefing_ids: [],
        },
      },
    });

    renderPage(5);

    expect(await screen.findByText(/No graph nodes were extracted/i)).toBeInTheDocument();
  });

  it('renders grouped learning trail recommendations', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'fetchLessonTrails').mockResolvedValue({
      lesson_id: 5,
      groups: [
        {
          path: 'prerequisite',
          label: 'Prerequisite concepts',
          items: [
            {
              item_type: 'lesson',
              id: 2,
              title: 'Embeddings basics',
              url: '/learn/2',
              source_name: 'Example Journal',
              explanation: 'Builds background around Embeddings before revisiting this lesson.',
              matched_signals: ['Embeddings'],
            },
          ],
        },
        { path: 'easier', label: 'Easier on-ramp', items: [] },
        {
          path: 'adjacent',
          label: 'Adjacent reads',
          items: [
            {
              item_type: 'article',
              id: 42,
              title: 'Vector search checklist',
              url: 'https://example.com/vector',
              source_name: 'Example Journal',
              explanation: 'Related article connected by Vector search.',
              matched_signals: ['Vector search'],
            },
          ],
        },
        { path: 'deeper', label: 'Deeper path', items: [] },
      ],
      empty_message: null,
    });

    renderPage(5);

    expect(await screen.findByText('Learning trail')).toBeInTheDocument();
    expect(screen.getAllByText('Prerequisite concepts').length).toBeGreaterThan(0);
    expect(await screen.findByRole('link', { name: 'Embeddings basics' })).toHaveAttribute(
      'href',
      '/learn/2'
    );
    expect(screen.getByRole('link', { name: 'Vector search checklist' })).toHaveAttribute(
      'href',
      'https://example.com/vector'
    );
    expect(
      screen.getByText('Builds background around Embeddings before revisiting this lesson.')
    ).toBeInTheDocument();
    expect(screen.getByText('Vector search')).toBeInTheDocument();
  });

  it('shows a learning trail empty state', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);

    renderPage(5);

    expect(
      await screen.findByText('No related lessons or articles are available in your corpus yet.')
    ).toBeInTheDocument();
  });

  it('shows a degraded lesson graph state when extraction is unavailable', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      lesson_detail: {
        ...COMPLETE_LESSON.lesson_detail!,
        graph_context: {
          available: false,
          entities: [],
          relationships: [],
          related_article_ids: [],
          related_briefing_ids: [],
        },
      },
    });

    renderPage(5);

    expect(await screen.findByText(/Graph extraction is not available/i)).toBeInTheDocument();
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

  const SLIDE_DECK = {
    slides: Array.from({ length: 6 }, (_, i) => ({
      title: `Slide ${i + 1}`,
      bullets: [`Bullet ${i + 1}.1`, `Bullet ${i + 1}.2`],
    })),
  };

  const INFOGRAPHIC = {
    title: 'Infographic title',
    subtitle: 'Infographic subtitle',
    sections: [
      { heading: 'Context', body: 'Why the lesson matters.' },
      { heading: 'Takeaway', body: 'What to remember next.' },
    ],
    footer: 'Generated from the lesson.',
  };

  it('shows a create-slide-deck button, then the slides once generation succeeds', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonSlideDeck').mockResolvedValue({
      ...COMPLETE_LESSON,
      slide_deck: SLIDE_DECK,
      slide_deck_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    const createButton = screen.getByRole('button', { name: 'Create slide deck' });
    expect(createButton).toBeInTheDocument();

    await userEvent.click(createButton);

    await waitFor(() => {
      expect(api.generateLessonSlideDeck).toHaveBeenCalledWith(5, false);
    });
    expect((await screen.findAllByRole('button', { name: 'Regenerate' })).length).toBeGreaterThan(
      0
    );
    expect(screen.getByText('Slide 1')).toBeInTheDocument();
    expect(screen.getByText('Bullet 1.1')).toBeInTheDocument();
  });

  it('shows a friendly error and keeps the create button when slide deck generation fails', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonSlideDeck').mockRejectedValue(
      new api.HttpError(503, 'AI not configured')
    );

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Create slide deck' }));

    expect(await screen.findByText('AI not configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create slide deck' })).toBeInTheDocument();
  });

  it('shows the failed-slide-deck banner from persisted lesson state', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      slide_deck_status: 'failed',
      slide_deck_error: 'Could not generate slide deck.',
    });

    renderPage(5);

    expect(await screen.findByText('Could not generate slide deck.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
  });

  it('forces regeneration when clicking regenerate on an existing slide deck', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      slide_deck: SLIDE_DECK,
      slide_deck_status: 'complete',
    });
    vi.spyOn(api, 'generateLessonSlideDeck').mockResolvedValue({
      ...COMPLETE_LESSON,
      slide_deck: SLIDE_DECK,
      slide_deck_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

    await waitFor(() => {
      expect(api.generateLessonSlideDeck).toHaveBeenCalledWith(5, true);
    });
  });

  it('shows a create-infographic button, then the artifact once generation succeeds', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonInfographic').mockResolvedValue({
      ...COMPLETE_LESSON,
      infographic: INFOGRAPHIC,
      infographic_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    const createButton = screen.getByRole('button', { name: 'Create infographic' });
    expect(createButton).toBeInTheDocument();

    await userEvent.click(createButton);

    await waitFor(() => {
      expect(api.generateLessonInfographic).toHaveBeenCalledWith(5, false);
    });
    expect(await screen.findByText('Infographic title')).toBeInTheDocument();
    expect(screen.getByText('Infographic subtitle')).toBeInTheDocument();
    expect(screen.getByText('Context')).toBeInTheDocument();
    expect(screen.getByText('Why the lesson matters.')).toBeInTheDocument();
    expect(screen.getByText('Generated from the lesson.')).toBeInTheDocument();
  });

  it('shows a friendly error and keeps the create button when infographic generation fails', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'generateLessonInfographic').mockRejectedValue(
      new api.HttpError(503, 'AI not configured')
    );

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Create infographic' }));

    expect(await screen.findByText('AI not configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create infographic' })).toBeInTheDocument();
  });

  it('shows the failed-infographic banner from persisted lesson state', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      infographic_status: 'failed',
      infographic_error: 'Could not generate infographic.',
    });

    renderPage(5);

    expect(await screen.findByText('Could not generate infographic.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
  });

  it('forces regeneration when clicking regenerate on an existing infographic', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      infographic: INFOGRAPHIC,
      infographic_status: 'complete',
    });
    vi.spyOn(api, 'generateLessonInfographic').mockResolvedValue({
      ...COMPLETE_LESSON,
      infographic: INFOGRAPHIC,
      infographic_status: 'complete',
    });

    renderPage(5);
    await screen.findByText('A careful article');

    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

    await waitFor(() => {
      expect(api.generateLessonInfographic).toHaveBeenCalledWith(5, true);
    });
  });

  it('shows create actions after regenerated artifacts are cleared', async () => {
    vi.spyOn(api, 'fetchLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      podcast_status: null,
      slide_deck: null,
      slide_deck_status: null,
      infographic: null,
      infographic_status: null,
      study_artifacts: null,
    });

    renderPage(5);
    await screen.findByText('A careful article');

    expect(screen.getByRole('button', { name: 'Create podcast' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create slide deck' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create infographic' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Regenerate' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Flashcards' })).not.toBeInTheDocument();
    expect(document.querySelector('audio')).not.toBeInTheDocument();
    expect(screen.queryByText('Slide 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Infographic title')).not.toBeInTheDocument();
  });
});
