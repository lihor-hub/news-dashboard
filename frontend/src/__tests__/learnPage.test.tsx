// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LearnPage } from '../pages/LearnPage';
import { HttpError, createLessonFromLink, fetchLesson } from '../api';
import * as api from '../api';

const { translationSpy } = vi.hoisted(() => ({
  translationSpy: vi.fn((key: string) => {
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
    };
    return translations[key] ?? key;
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

const COMPLETE_LESSON = {
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
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T10:01:00Z',
} as const;

const PENDING_LESSON = {
  ...COMPLETE_LESSON,
  id: 8,
  title: null,
  source_name: null,
  author: null,
  published_at: null,
  source_content: null,
  generation_status: 'pending',
} as const;

const FAILED_LESSON = {
  ...COMPLETE_LESSON,
  id: 9,
  title: null,
  source_name: null,
  author: null,
  published_at: null,
  source_content: null,
  generation_status: 'failed',
  generation_error: 'Could not extract readable article content.',
} as const;

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
      body: JSON.stringify({ url: 'https://example.com/article' }),
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
    expect(screen.getByText(/Example Journal/i)).toBeInTheDocument();
    expect(screen.getByText(/Jane Example/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open original article/i })).toHaveAttribute(
      'href',
      'https://example.com/article'
    );
    expect(screen.getByText(/A compact but useful article body preview\./i)).toBeInTheDocument();
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
});
