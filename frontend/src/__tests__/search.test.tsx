// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SearchPage } from '../pages/SearchPage';
import * as workflowApi from '../api/workflowApi';
import type { WorkflowArticle } from '../lib/workflowTypes';
import { FocusedArticleProvider } from '../contexts/focusedArticle';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

beforeEach(() => {
  vi.clearAllMocks();
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
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([]);
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
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([
      makeArticle({ id: '1', title: 'Python Tips Article' }),
      makeArticle({ id: '2', title: 'Async Patterns' }),
    ]);

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('Python Tips Article')).toBeTruthy();
      expect(screen.getByText('Async Patterns')).toBeTruthy();
    });
  });

  it('shows result count', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([
      makeArticle({ id: '1' }),
      makeArticle({ id: '2', url: 'https://example.com/2' }),
    ]);

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('2 results')).toBeTruthy();
    });
  });

  it('shows "No results" when API returns empty array', async () => {
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([]);
    renderSearch('?q=nonexistent');

    await waitFor(() => {
      expect(screen.getByText('No results')).toBeTruthy();
    });
  });
});

// ─── Filter chips ─────────────────────────────────────────────────────────────

describe('SearchPage — filter chips', () => {
  it('Starred chip toggles starred_only in API call', async () => {
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([]);
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
    const spy = vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([]);
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
    vi.spyOn(workflowApi, 'searchArticlesFiltered').mockResolvedValue([
      makeArticle({ id: '42', title: 'Clickable Article' }),
    ]);

    renderSearch('?q=python');

    await waitFor(() => {
      expect(screen.getByText('Clickable Article')).toBeTruthy();
    });

    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toContain('/a/42');
  });
});
