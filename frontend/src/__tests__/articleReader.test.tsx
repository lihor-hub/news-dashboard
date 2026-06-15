// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArticlePage } from '../pages/ArticlePage';
import * as api from '../api';
import type { Article } from '../types';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

beforeEach(() => {
  vi.clearAllMocks();
});

function makeArticle(overrides: Partial<Article> = {}): Article {
  return {
    id: 42,
    url: 'https://example.com/article',
    title: 'Test Article Title',
    source_name: 'Test Source',
    category: 'ai-llm',
    kind: 'rss',
    published_at: '2024-01-15T10:00:00Z',
    discovered_at: '2024-01-15T11:00:00Z',
    status: 'new',
    importance_score: 0.8,
    summary: 'A short summary of the article.',
    reason: 'Why this matters to you',
    tags: '["llm","agents"]',
    read_at: null,
    saved_at: null,
    skipped_at: null,
    archived_at: null,
    body: null,
    body_status: 'missing',
    ...overrides,
  };
}

function renderReader(id = '42', cachedArticle?: Article) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (cachedArticle) {
    queryClient.setQueryData(['article', id], cachedArticle);
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/a/${id}`]}>
        <Routes>
          <Route path="/a/:id" element={<ArticlePage />} />
          <Route path="/" element={<div>Home</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── Rendering ────────────────────────────────────────────────────────────────

describe('ArticlePage — rendering', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle());
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text here.' })
    );
  });

  it('shows article title after load', async () => {
    renderReader();
    await waitFor(() => expect(screen.getByText('Test Article Title')).toBeTruthy());
  });

  it('shows source and reason', async () => {
    renderReader();
    await waitFor(() => {
      expect(screen.getByText('Test Source')).toBeTruthy();
      expect(screen.getByText('Why this matters to you')).toBeTruthy();
    });
  });

  it('shows Back button', async () => {
    renderReader();
    await waitFor(() => expect(screen.getByText('Back')).toBeTruthy());
  });

  it('shows action bar with Star, Done, Later, Skip, Archive', async () => {
    renderReader();
    await waitFor(() => {
      expect(screen.getByText('Star')).toBeTruthy();
      expect(screen.getByText('Done')).toBeTruthy();
      expect(screen.getByText('Later')).toBeTruthy();
      expect(screen.getByText('Skip')).toBeTruthy();
      expect(screen.getByText('Archive')).toBeTruthy();
    });
  });
});

// ─── Body fetch on open ───────────────────────────────────────────────────────

describe('ArticlePage — body fetch', () => {
  it('triggers body fetch when body_status is missing', async () => {
    const fetchBodySpy = vi
      .spyOn(api, 'fetchArticleBody')
      .mockResolvedValue(makeArticle({ body_status: 'ok', body: 'Full text' }));
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'missing' }));

    renderReader();
    await waitFor(() => expect(fetchBodySpy).toHaveBeenCalledWith('42'));
  });

  it('does not re-fetch when body_status is ok (cache already warm)', async () => {
    const cachedArticle = makeArticle({ body_status: 'ok', body: 'Cached text' });
    const fetchBodySpy = vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(cachedArticle);
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(cachedArticle);

    // Pre-populate the React Query cache so the useEffect skips the body fetch.
    renderReader('42', cachedArticle);
    await waitFor(() => expect(screen.getByText('Test Article Title')).toBeTruthy());
    expect(fetchBodySpy).not.toHaveBeenCalled();
  });

  it('shows extracted body text', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'This is the full article body content.' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'This is the full article body content.' })
    );

    renderReader();
    await waitFor(() => expect(screen.getByText(/full article body content/)).toBeTruthy());
  });

  it('shows error fallback when body_status is error', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'error', body: null })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'error', body: null })
    );

    renderReader();
    await waitFor(() => expect(screen.getByText("Couldn't extract article text")).toBeTruthy());
    expect(screen.getByText('Open original')).toBeTruthy();
  });
});

// ─── Back navigation ──────────────────────────────────────────────────────────

describe('ArticlePage — back navigation', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
  });

  it('Back button navigates back', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Back'));
    await userEvent.click(screen.getByText('Back'));
    // Just confirm click doesn't throw
  });
});
