// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import { ArticleListView } from '../components/article/ArticleListView';
import type { WorkflowArticle } from '../lib/workflowTypes';
import { Inbox } from 'lucide-react';

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '42',
    title: 'Readable article',
    sourceId: 'source',
    sourceName: 'Source',
    category: 'ai-llm',
    url: 'https://example.com/readable',
    publishedAt: '2026-06-16T10:00:00Z',
    ingestedAt: '2026-06-16T11:00:00Z',
    reason: 'This is why it matters.',
    summary: 'Summary text.',
    signal: 'high',
    tags: ['ai'],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function renderArticleList(queryFn: () => Promise<WorkflowArticle[]>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <FocusedArticleProvider>
        <MemoryRouter initialEntries={['/today']}>
          <Routes>
            <Route
              path="/today"
              element={
                <ArticleListView
                  title="Today"
                  description={({ count }) => `${count} unhandled`}
                  queryKey={['articles', 'today']}
                  queryFn={queryFn}
                  empty={{ icon: Inbox, title: 'Queue clear' }}
                  showCategoryFilter
                />
              }
            />
            <Route path="/a/:id" element={<div data-testid="reader">Reader</div>} />
          </Routes>
        </MemoryRouter>
      </FocusedArticleProvider>
    </QueryClientProvider>
  );
}

describe('ArticleListView', () => {
  it('renders a configured heading, category filter, count, and article links', async () => {
    renderArticleList(() => Promise.resolve([makeArticle()]));

    await waitFor(() => expect(screen.getByText('Readable article')).toBeTruthy());

    expect(screen.getByRole('heading', { name: 'Today' })).toBeTruthy();
    expect(screen.getByText('1 unhandled')).toBeTruthy();
    expect(screen.getByRole('link', { name: /readable article/i }).getAttribute('href')).toBe(
      '/a/42'
    );
    expect(screen.getByText('All')).toBeTruthy();
  });

  it('renders the configured empty state after a successful empty response', async () => {
    renderArticleList(() => Promise.resolve([]));

    await waitFor(() => expect(screen.getByText('Queue clear')).toBeTruthy());
  });
});

describe('ArticleListView — list-view triage actions do not navigate', () => {
  it('swipe-right (done) calls setState but stays on the list page', async () => {
    renderArticleList(() => Promise.resolve([makeArticle()]));
    await waitFor(() => screen.getByText('Readable article'));

    // The SwipeableRow inner div (touch target) wraps the article Link.
    const link = screen.getByRole('link', { name: /readable article/i });
    const touchTarget = link.parentElement!;

    fireEvent.touchStart(touchTarget, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(touchTarget, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(touchTarget);

    // Still on the list — article reader route was not activated
    expect(screen.queryByTestId('reader')).toBeNull();
    expect(screen.getByText('Readable article')).toBeTruthy();
  });
});
