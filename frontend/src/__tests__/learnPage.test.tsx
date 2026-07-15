// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LearnPage } from '../pages/LearnPage';
import { HttpError, createLessonFromLink, fetchLesson } from '../api';
import type { Lesson } from '../api';
import * as api from '../api';

const { translationSpy } = vi.hoisted(() => ({
  translationSpy: vi.fn((key: string, options?: Record<string, string | number>) => {
    const translations: Record<string, string> = {
      'learn.title': 'Learn',
      'learn.description': 'Turn one article into a compact lesson you can review inside Radar.',
      'learn.form.url_label': 'Article URL',
      'learn.form.url_placeholder': 'https://example.com/article',
      'learn.form.submit': 'Generate lesson',
      'learn.form.submitting': 'Generating lesson...',
      'learn.empty': 'Paste a link to generate a lesson summary from a readable article.',
      'learn.status.pending': 'Generating lesson...',
      'learn.status.complete': 'Lesson generated',
      'learn.status.failed': 'Lesson generation failed',
      'learn.link.open_original': 'Open original article',
      'learn.refresh_error': 'Failed to refresh lesson',
      'learn.request_error': 'Lesson generation failed',
      'learn.detail.gist': 'Gist Translated',
      'learn.detail.explanation': 'Explanation Translated',
      'learn.detail.why_it_matters': 'Why It Matters Translated',
      'learn.detail.key_claims': 'Key Claims Translated',
      'learn.detail.prerequisite_concepts': 'Prerequisite Concepts Translated',
      'learn.detail.who_should_read': 'Who Should Read Translated',
      'learn.detail.questions_to_keep_in_mind': 'Questions to Keep in Mind Translated',
      'learn.detail.citations': 'Citations Translated',
      'learn.controls.depth_label': 'Explanation depth',
      'learn.controls.persona_label': 'Learning persona',
      'learn.controls.depth.tiny': 'Tiny',
      'learn.controls.depth.normal': 'Normal',
      'learn.controls.depth.deep': 'Deep',
      'learn.controls.depth.expert': 'Expert',
      'learn.controls.persona.developer': 'Developer',
      'learn.controls.persona.product_builder': 'Product builder',
      'learn.controls.persona.new_to_ai': 'New to AI',
      'learn.controls.persona.preparing_talk': 'Preparing a talk',
      'learn.controls.regenerate': 'Regenerate lesson',
      'learn.controls.regenerating': 'Regenerating...',
      'learn.controls.regenerate_error': 'Failed to regenerate lesson',
      'learn.controls.active_summary': 'Generated for {{persona}} at {{depth}} depth',
      'learn.controls.history_summary': '{{count}} prior generations saved',
    };
    const template = translations[key] ?? key;
    if (!options) return template;
    return Object.entries(options).reduce(
      (result, [name, value]) => result.replaceAll(`{{${name}}}`, String(value)),
      template
    );
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translationSpy,
    i18n: {
      changeLanguage: () => Promise.resolve(),
    },
  }),
}));

vi.spyOn(console, 'error').mockImplementation(() => undefined);

const COMPLETE_LESSON: Lesson = {
  id: 7,
  user_id: 1,
  original_url: 'https://example.com/article',
  normalized_url: 'https://example.com/article',
  title: 'A careful article',
  source_name: 'Example Journal',
  author: 'Jane Example',
  published_at: '2026-07-08T10:00:00Z',
  source_content: 'A compact but useful article body preview.',
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
    explanation:
      'It walks through how the author chose a small set of high-signal sources and why that improves review quality.',
    key_claims: [
      'A short reading stack can outperform a broad feed when the goal is comprehension.',
      'Editorial filtering reduces noise and makes follow-up questions sharper.',
    ],
    prerequisite_concepts: ['Signal-to-noise ratio', 'Editorial curation'],
    why_it_matters:
      'Knowing when to skim versus study helps the reader spend attention where it compounds.',
    read_worthiness: {
      verdict: 'study',
      rationale: 'It introduces a repeatable framework for deciding how deeply to read a piece.',
    },
    who_should_read: ['People building reading workflows', 'Editors evaluating article quality'],
    questions_to_keep_in_mind: [
      'What filtering rule is being applied?',
      'Which audience is this lesson aiming at?',
    ],
    citations: [
      {
        label: 'Filtering principle',
        snippet: 'Choose fewer, higher-signal sources when the goal is durable understanding.',
        source: 'Example Journal',
      },
    ],
  },
  study_artifacts: {
    comprehension_questions: [
      {
        question: 'What is the primary topic of the text?',
        expected_answer: 'Paragraph one.',
      },
    ],
    flashcards: [
      {
        concept: 'Core Claim',
        claim: 'Paragraph one.',
      },
    ],
    quiz: [
      {
        question: 'Which of the following best summarizes the main point of the source?',
        options: [
          'Paragraph one.',
          'A completely unrelated fact.',
          'An incorrect assertion.',
          'A generic fallback.',
        ],
        correct_index: 0,
        explanation: 'The source content explicitly states the core claim.',
      },
    ],
  },
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T10:01:00Z',
};

const PENDING_LESSON: Lesson = {
  ...COMPLETE_LESSON,
  id: 8,
  title: null,
  source_name: null,
  author: null,
  published_at: null,
  source_content: null,
  generation_status: 'pending',
  lesson_detail: null,
};

const FAILED_LESSON: Lesson = {
  ...COMPLETE_LESSON,
  id: 9,
  title: null,
  source_name: null,
  author: null,
  published_at: null,
  source_content: null,
  generation_status: 'failed',
  generation_error: 'Could not extract readable article content.',
  lesson_detail: null,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/learn']}>
        <LearnPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('learn API client', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('posts a URL to create a lesson', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify(COMPLETE_LESSON), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await createLessonFromLink('https://example.com/article');

    expect(result).toEqual(COMPLETE_LESSON);
    expect(global.fetch).toHaveBeenCalledWith('/api/learn/lessons', {
      body: JSON.stringify({
        url: 'https://example.com/article',
        depth: 'normal',
        persona: 'developer',
      }),
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
  });

  it('posts depth and persona controls when regenerating a lesson', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify(COMPLETE_LESSON), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await api.regenerateLesson(7, 'deep', 'new_to_ai');

    expect(result).toEqual(COMPLETE_LESSON);
    expect(global.fetch).toHaveBeenCalledWith('/api/learn/lessons/7/regenerate', {
      body: JSON.stringify({ depth: 'deep', persona: 'new_to_ai' }),
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
  });

  it('fetches a lesson by id', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify(COMPLETE_LESSON), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await fetchLesson(7);

    expect(result).toEqual(COMPLETE_LESSON);
    expect(global.fetch).toHaveBeenCalledWith('/api/learn/lessons/7', {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
  });
});

describe('LearnPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    translationSpy.mockClear();
    vi.spyOn(api, 'fetchLessonGenerations').mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('creates a lesson from a link and shows the completed lesson', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(COMPLETE_LESSON);

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/lesson generated/i);
    expect(screen.getByText(/A careful article/i)).toBeInTheDocument();
    expect(screen.getByText(/Example Journal/i, { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText(/Jane Example/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open original article/i })).toHaveAttribute(
      'href',
      'https://example.com/article'
    );
    expect(screen.getByText(/A compact but useful article body preview\./i)).toBeInTheDocument();
    expect(screen.getByText(/Study/i, { selector: 'div' })).toBeInTheDocument();
    expect(
      screen.getByText(
        /It introduces a repeatable framework for deciding how deeply to read a piece\./i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /The article argues that strong source selection matters more than raw volume\./i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /It walks through how the author chose a small set of high-signal sources and why that improves review quality\./i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /A short reading stack can outperform a broad feed when the goal is comprehension\./i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Editorial filtering reduces noise and makes follow-up questions sharper\./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Signal-to-noise ratio/i)).toBeInTheDocument();
    expect(screen.getByText(/Editorial curation/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Knowing when to skim versus study helps the reader spend attention where it compounds\./i
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/People building reading workflows/i)).toBeInTheDocument();
    expect(screen.getByText(/Editors evaluating article quality/i)).toBeInTheDocument();
    expect(screen.getByText(/What filtering rule is being applied\?/i)).toBeInTheDocument();
    expect(screen.getByText(/Which audience is this lesson aiming at\?/i)).toBeInTheDocument();
    expect(screen.getByText(/Filtering principle/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Choose fewer, higher-signal sources when the goal is durable understanding\./i
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/Example Journal/i, { selector: 'div' })).toBeInTheDocument();
    expect(screen.getByText('Gist Translated')).toBeInTheDocument();
    expect(screen.getByText('Explanation Translated')).toBeInTheDocument();
    expect(screen.getByText('Why It Matters Translated')).toBeInTheDocument();
    expect(screen.getByText('Key Claims Translated')).toBeInTheDocument();
    expect(screen.getByText('Prerequisite Concepts Translated')).toBeInTheDocument();
    expect(screen.getByText('Who Should Read Translated')).toBeInTheDocument();
    expect(screen.getByText('Questions to Keep in Mind Translated')).toBeInTheDocument();
    expect(screen.getByText('Citations Translated')).toBeInTheDocument();

    expect(translationSpy).toHaveBeenCalledWith('learn.title');
    expect(translationSpy).toHaveBeenCalledWith('learn.description');
    expect(translationSpy).toHaveBeenCalledWith('learn.form.url_label');
    expect(translationSpy).toHaveBeenCalledWith('learn.form.url_placeholder');
    expect(translationSpy).toHaveBeenCalledWith('learn.form.submit');
    expect(translationSpy).toHaveBeenCalledWith('learn.status.complete');
    expect(translationSpy).toHaveBeenCalledWith('learn.link.open_original');
  });

  it('shows the backend failure message when generation fails', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(FAILED_LESSON);

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/lesson generation failed/i);
    expect(screen.getByText(/could not extract readable article content\./i)).toBeInTheDocument();
    expect(translationSpy).toHaveBeenCalledWith('learn.status.failed');
  });

  it('shows the request error when lesson creation throws', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockRejectedValue(new HttpError(400, 'unsafe url'));

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'file:///etc/passwd');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/unsafe url/i);
    expect(screen.queryByText(/lesson generated/i)).toBeNull();
  });

  it('uses the localized fallback when lesson creation throws a non-error value', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockRejectedValue('no structured error');

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/lesson generation failed/i);
    expect(translationSpy).toHaveBeenCalledWith('learn.request_error');
  });

  it('shows a pending lesson and polls until it completes', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(PENDING_LESSON);
    const fetchSpy = vi.spyOn(api, 'fetchLesson').mockResolvedValue(COMPLETE_LESSON);

    renderPage();
    fireEvent.change(screen.getByLabelText(/article url/i), {
      target: { value: 'https://example.com/article' },
    });
    fireEvent.click(screen.getByRole('button', { name: /generate lesson/i }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getAllByText(/generating lesson\.\.\./i).length).toBeGreaterThan(0);
    expect(translationSpy).toHaveBeenCalledWith('learn.status.pending');
    expect(screen.getByRole('link', { name: /open original article/i })).toHaveAttribute(
      'href',
      'https://example.com/article'
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(fetchSpy).toHaveBeenCalledWith(8);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText(/lesson generated/i)).toBeInTheDocument();
    expect(screen.getByText(/A careful article/i)).toBeInTheDocument();
  });

  it('keeps polling after one refresh failure and later shows the completed lesson', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(PENDING_LESSON);
    const fetchSpy = vi
      .spyOn(api, 'fetchLesson')
      .mockRejectedValueOnce(new Error('temporary refresh failure'))
      .mockResolvedValueOnce(COMPLETE_LESSON);

    renderPage();
    fireEvent.change(screen.getByLabelText(/article url/i), {
      target: { value: 'https://example.com/article' },
    });
    fireEvent.click(screen.getByRole('button', { name: /generate lesson/i }));

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText(/temporary refresh failure/i)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(/lesson generated/i)).toBeInTheDocument();
    expect(screen.getByText(/A careful article/i)).toBeInTheDocument();
  });

  it('renders study artifacts and handles tab switches/reveal/quiz actions', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(COMPLETE_LESSON);

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/lesson generated/i);

    // Verify Comprehension tab is active by default
    expect(screen.getByText(/Q1: What is the primary topic of the text\?/i)).toBeInTheDocument();
    expect(screen.queryByText(/Paragraph one\./i)).toBeNull(); // answer hidden by default

    // Click show answer
    await user.click(screen.getByRole('button', { name: /show answer/i }));
    expect(screen.getByText(/Paragraph one\./i)).toBeInTheDocument();

    // Click hide answer
    await user.click(screen.getByRole('button', { name: /hide answer/i }));
    expect(screen.queryByText(/Paragraph one\./i)).toBeNull();

    // Switch to Flashcards tab
    await user.click(screen.getByRole('button', { name: /flashcards/i }));
    expect(screen.getByText(/Core Claim/i)).toBeInTheDocument();
    expect(screen.getByText(/Click to flip and reveal details\.\.\./i)).toBeInTheDocument();

    // Click to flip
    await user.click(screen.getByText(/Core Claim/i));
    expect(screen.getByText(/Paragraph one\./i)).toBeInTheDocument();

    // Switch to Quiz tab
    await user.click(screen.getByRole('button', { name: /quiz/i }));
    expect(
      screen.getByText(
        /Question 1: Which of the following best summarizes the main point of the source\?/i
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/A completely unrelated fact\./i)).toBeInTheDocument();

    // Submit answer
    await user.click(screen.getByText(/Paragraph one\./i));
    await user.click(screen.getByRole('button', { name: /submit answer/i }));
    expect(
      screen.getByText(/The source content explicitly states the core claim\./i)
    ).toBeInTheDocument();
  });

  it('sends the selected depth and persona when generating a lesson', async () => {
    const createSpy = vi
      .spyOn(api, 'createLessonFromLink')
      .mockResolvedValue({ ...COMPLETE_LESSON, depth: 'deep', persona: 'new_to_ai' });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.selectOptions(screen.getByLabelText(/explanation depth/i), 'deep');
    await user.selectOptions(screen.getByLabelText(/learning persona/i), 'new_to_ai');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));

    await screen.findByText(/lesson generated/i);
    expect(createSpy).toHaveBeenCalledWith('https://example.com/article', 'deep', 'new_to_ai');
    expect(screen.getByText(/generated for new to ai at deep depth/i)).toBeInTheDocument();
  });

  it('regenerates a lesson with the currently selected controls', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(COMPLETE_LESSON);
    const regenerateSpy = vi.spyOn(api, 'regenerateLesson').mockResolvedValue({
      ...COMPLETE_LESSON,
      depth: 'tiny',
      persona: 'preparing_talk',
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));
    await screen.findByText(/lesson generated/i);

    await user.selectOptions(screen.getByLabelText(/explanation depth/i), 'tiny');
    await user.selectOptions(screen.getByLabelText(/learning persona/i), 'preparing_talk');
    await user.click(screen.getByRole('button', { name: /regenerate lesson/i }));

    await screen.findByText(/generated for preparing a talk at tiny depth/i);
    expect(regenerateSpy).toHaveBeenCalledWith(COMPLETE_LESSON.id, 'tiny', 'preparing_talk');
  });

  it('shows an error when regeneration fails', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'regenerateLesson').mockRejectedValue(new HttpError(500, 'server exploded'));

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));
    await screen.findByText(/lesson generated/i);

    await user.click(screen.getByRole('button', { name: /regenerate lesson/i }));

    await screen.findByText(/server exploded/i);
  });

  it('shows a history summary once a lesson has more than one saved generation', async () => {
    vi.spyOn(api, 'createLessonFromLink').mockResolvedValue(COMPLETE_LESSON);
    vi.spyOn(api, 'fetchLessonGenerations').mockResolvedValue([
      { ...COMPLETE_LESSON, id: 1, lesson_id: 7, generation_status: 'complete' },
      { ...COMPLETE_LESSON, id: 2, lesson_id: 7, generation_status: 'complete' },
    ]);

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/article url/i), 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: /generate lesson/i }));
    await screen.findByText(/lesson generated/i);

    await screen.findByText(/2 prior generations saved/i);
  });
});
