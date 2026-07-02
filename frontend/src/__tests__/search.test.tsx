// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SearchPage } from '../pages/SearchPage';
import * as workflowApi from '../api/workflowApi';
import * as api from '../api';
import * as tagsApi from '../api/tagsApi';
import type { WorkflowArticle } from '../lib/workflowTypes';
import type { Source } from '../types';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import type { SearchArticlePage } from '../api/workflowApi';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    slug: 'test-source',
    name: 'Test Source',
    url: 'https://example.com',
    category: 'engineering',
    kind: 'rss',
    priority: 1,
    enabled: 1,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(api, 'fetchSources').mockResolvedValue([]);
  vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([]);
});

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '1',
    title: 'Python Tips Article',
    sourceId: 'python-insider',
    sourceName: 'Python Insider',
    category: 'python',
    url: 'https://example.com/python-tips',
    publishedAt: '2024-01-15T10:00:00Z',
    ingestedAt: '2024-01-15T11:00:00Z',
    reason: 'Relevant to your interests',
    summary: 'Summary of the article.',
    signal: 'high',
    tags: ['python', 'tips'],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function makePage(
  items: WorkflowArticle[],
  overrides: Partial<Omit<SearchArticlePage, 'items'>> = {}
): SearchArticlePage {
  return {
    items,
    total: items.length,
    limit: 100,
    offset: 0,
    hasMore: false,
    ...overrides,
  };
}

function renderSearch(initialSearch = '') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FocusedArticleProvider>
        <MemoryRouter initialEntries={[`/search${initialSearch}`]}>
          <Routes>
            <Route path="/search" element={<SearchPage />} />
            <Route path="/a/:id" element={<div data-testid="reader-page">Reader</div>} />
          </Routes>
        </MemoryRouter>
      </FocusedArticleProvider>
    </QueryClientProvider>
  );
}

// ─── Rendering ───────────────────────────────────────────────────────────────

describe('SearchPage — rendering', () => {
  it('renders the heading and search input', () => {
    renderSearch();
    expect(screen.getByText('Search')).toBeTruthy();
    expect(screen.getByPlaceholderText(/Search titles/)).toBeTruthy();
  });

  it('renders all filter chip groups', () => {
    renderSearch();
    expect(screen.getByText('Starred')).toBeTruthy();
    expect(screen.getByText('Include archived')).toBeTruthy();
    expect(screen.getByText('State')).toBeTruthy();
    expect(screen.getByText('Category')).toBeTruthy();
    expect(screen.getByText('Date')).toBeTruthy();
  });

  it('shows empty state prompt when no query or filters', () => {
    renderSearch();
    expect(screen.getByText('Start searching')).toBeTruthy();
  });
});

// ─── Search flow ─────────────────────────────────────────────────────────────

describe('SearchPage — search flow', () => {
  it('calls searchArticlesFiltered when user types a query', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    renderSearch();

    const input = screen.getByPlaceholderText(/Search titles/);
    await userEvent.type(input, 'python');

    await waitFor(
      () => {
        expect(spy).toHaveBeenCalledWith(expect.objectContaining({ q: 'python' }));
      },
      { timeout: 1000 }
    );
  });

  it('displays results when API returns articles', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(
      makePage([
        makeArticle({ id: '1', title: 'Python Tips Article' }),
        makeArticle({ id: '2', title: 'Async Patterns' }),
      ])
    );

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('Python Tips Article')).toBeTruthy();
      expect(screen.getByText('Async Patterns')).toBeTruthy();
    });
  });

  it('shows result count', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(
      makePage([makeArticle({ id: '1' }), makeArticle({ id: '2', url: 'https://example.com/2' })])
    );

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('2 of 2 results')).toBeTruthy();
    });
  });

  it('shows "No results" when API returns empty array', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    renderSearch('?q=nonexistent');

    await waitFor(() => {
      expect(screen.getByText('No results')).toBeTruthy();
    });
  });

  it('loads more results with the active filters', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered');
    spy
      .mockResolvedValueOnce(
        makePage([makeArticle({ id: '1', title: 'First Page' })], {
          total: 2,
          limit: 1,
          offset: 0,
          hasMore: true,
        })
      )
      .mockResolvedValueOnce(
        makePage([makeArticle({ id: '2', title: 'Second Page' })], {
          total: 2,
          limit: 1,
          offset: 1,
          hasMore: false,
        })
      );

    renderSearch('?q=python&categories=python');

    await waitFor(() => {
      expect(screen.getByText('First Page')).toBeTruthy();
      expect(screen.getByText('1 of 2 results')).toBeTruthy();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Load more' }));

    await waitFor(() => {
      expect(screen.getByText('Second Page')).toBeTruthy();
      expect(screen.getByText('2 of 2 results')).toBeTruthy();
    });
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'python', categories: ['python'], offset: 1 })
    );
  });
});

// ─── Filter chips ─────────────────────────────────────────────────────────────

describe('SearchPage — filter chips', () => {
  it('Starred chip toggles starred_only in API call', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    renderSearch('?q=test');

    await waitFor(() => expect(spy).toHaveBeenCalled());
    spy.mockClear();

    const starredChip = screen.getByRole('button', { name: 'Starred' });
    await userEvent.click(starredChip);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ starredOnly: true }));
    });
  });

  it('Include archived chip toggles includeArchived in API call', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    renderSearch('?q=test');

    await waitFor(() => expect(spy).toHaveBeenCalled());
    spy.mockClear();

    const archivedChip = screen.getByRole('button', { name: 'Include archived' });
    await userEvent.click(archivedChip);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ includeArchived: true }));
    });
  });
});

// ─── Navigation to reader ────────────────────────────────────────────────────

describe('SearchPage — reader navigation', () => {
  it('navigates to reader when article row is clicked', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(
      makePage([makeArticle({ id: '42', title: 'Clickable Article' })])
    );

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('Clickable Article')).toBeTruthy();
    });

    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toContain('/a/42');
  });
});

// ─── Source filter ────────────────────────────────────────────────────────────

describe('SearchPage — source filter', () => {
  it('renders Source filter group when sources are available', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([
      makeSource({ slug: 'hn', name: 'Hacker News' }),
      makeSource({ slug: 'openai-blog', name: 'OpenAI Blog' }),
    ]);

    renderSearch();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Source/i })).toBeTruthy();
    });
  });

  it('does not render Source filter group when no sources available', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([]);
    renderSearch();

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /^Source/i })).toBeNull();
    });
  });

  it('shows source names in dropdown when Source button is clicked', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([
      makeSource({ slug: 'hn', name: 'Hacker News' }),
      makeSource({ slug: 'openai-blog', name: 'OpenAI Blog' }),
    ]);

    renderSearch();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Source/i })).toBeTruthy();
    });

    await userEvent.click(screen.getByRole('button', { name: /^Source/i }));

    expect(screen.getByText('Hacker News')).toBeTruthy();
    expect(screen.getByText('OpenAI Blog')).toBeTruthy();
  });

  it('passes selected sources to searchArticlesFiltered', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    vi.spyOn(api, 'fetchSources').mockResolvedValue([
      makeSource({ slug: 'hn', name: 'Hacker News' }),
    ]);

    renderSearch('?q=test&sources=hn');

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ sources: ['hn'] }));
    });
  });

  it('preselects sources from URL params', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([
      makeSource({ slug: 'hn', name: 'Hacker News' }),
      makeSource({ slug: 'openai-blog', name: 'OpenAI Blog' }),
    ]);

    renderSearch('?q=test&sources=hn');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Source · 1/i })).toBeTruthy();
    });
  });
});

describe('SearchPage — tag filter', () => {
  it('renders Tag filter group when tags are available', async () => {
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([
      { id: 1, user_id: 1, name: 'rust', color: null, created_at: '2026-01-01T00:00:00Z' },
    ]);

    renderSearch();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Tag/i })).toBeTruthy();
    });
  });

  it('selecting a tag filters results by tag_id', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue(makePage([]));
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([
      { id: 3, user_id: 1, name: 'rust', color: null, created_at: '2026-01-01T00:00:00Z' },
    ]);

    renderSearch('?q=test');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Tag/i })).toBeTruthy();
    });
    await userEvent.click(screen.getByRole('button', { name: /^Tag/i }));
    await userEvent.click(screen.getByText('rust'));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ tagId: 3 }));
    });
  });

  it('preselects a tag from URL params', async () => {
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([
      { id: 3, user_id: 1, name: 'rust', color: null, created_at: '2026-01-01T00:00:00Z' },
    ]);

    renderSearch('?q=test&tag=3');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Tag · rust/i })).toBeTruthy();
    });
  });
});
