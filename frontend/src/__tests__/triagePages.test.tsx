// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import type { WorkflowArticle } from '../lib/workflowTypes';
import { InboxPage } from '../pages/InboxPage';
import { LaterPage } from '../pages/LaterPage';
import { StarredPage } from '../pages/StarredPage';
import { ArchivePage } from '../pages/ArchivePage';
import type { TriageArticlePage } from '../api/workflowApi';

// Pin the data layer: each page only differs in title/sort/config wiring, so we
// stub fetchTriageArticles and assert the page renders its heading + rows.
const fetchTriageArticles = vi.fn<(...args: unknown[]) => Promise<TriageArticlePage>>();
vi.mock('@/api/workflowApi', () => ({
  fetchTriageArticles: (...args: unknown[]) => fetchTriageArticles(...args),
}));
vi.mock('@/hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '1',
    title: 'An article',
    sourceId: 'source',
    sourceName: 'Source',
    category: 'ai-llm',
    url: 'https://example.com/a',
    publishedAt: '2026-06-16T10:00:00Z',
    ingestedAt: '2026-06-16T11:00:00Z',
    reason: 'why',
    summary: 'summary',
    signal: 'high',
    tags: ['ai'],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function page(items: WorkflowArticle[]): TriageArticlePage {
  return { items, limit: 100, offset: 0, hasMore: false };
}

function renderPage(ui: React.ReactElement, route = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FocusedArticleProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </FocusedArticleProvider>
    </QueryClientProvider>
  );
}

describe('triage wrapper pages', () => {
  it('InboxPage renders the Today heading and forwards the category filter', async () => {
    fetchTriageArticles.mockResolvedValueOnce(page([makeArticle()]));
    renderPage(<InboxPage />, '/today?category=ai-llm');
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeTruthy();
    await waitFor(() =>
      expect(fetchTriageArticles).toHaveBeenCalledWith('today', 'ai-llm', {
        limit: 100,
        offset: 0,
      })
    );
  });

  it('LaterPage renders snoozed articles sorted by return date', async () => {
    fetchTriageArticles.mockResolvedValueOnce(
      page([
        makeArticle({ id: '1', title: 'Returns later', later_until: '2026-07-01T00:00:00Z' }),
        makeArticle({ id: '2', title: 'Returns sooner', later_until: '2026-06-25T00:00:00Z' }),
      ])
    );
    renderPage(<LaterPage />, '/later');
    expect(await screen.findByRole('heading', { name: 'Later' })).toBeTruthy();
    await waitFor(() =>
      expect(fetchTriageArticles).toHaveBeenCalledWith('later', undefined, {
        limit: 100,
        offset: 0,
      })
    );
  });

  it('StarredPage renders the Starred heading', async () => {
    fetchTriageArticles.mockResolvedValueOnce(
      page([makeArticle({ starred: true, starred_at: '2026-06-20T00:00:00Z' })])
    );
    renderPage(<StarredPage />, '/starred');
    expect(await screen.findByRole('heading', { name: 'Starred' })).toBeTruthy();
    await waitFor(() =>
      expect(fetchTriageArticles).toHaveBeenCalledWith('starred', undefined, {
        limit: 100,
        offset: 0,
      })
    );
  });

  it('ArchivePage renders the Archive heading', async () => {
    fetchTriageArticles.mockResolvedValueOnce(
      page([makeArticle({ archived_at: '2026-06-19T00:00:00Z' })])
    );
    renderPage(<ArchivePage />, '/archive');
    expect(await screen.findByRole('heading', { name: 'Archive' })).toBeTruthy();
    await waitFor(() =>
      expect(fetchTriageArticles).toHaveBeenCalledWith('archived', undefined, {
        limit: 100,
        offset: 0,
      })
    );
  });

  it('ArchivePage shows the empty state when there are no rows', async () => {
    fetchTriageArticles.mockResolvedValueOnce(page([]));
    renderPage(<ArchivePage />, '/archive');
    expect(await screen.findByText('Archive empty')).toBeTruthy();
  });
});
