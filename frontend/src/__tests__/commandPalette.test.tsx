// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import { CommandPalette } from '../components/CommandPalette';
import * as api from '../api';
import type { Article } from '../types';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    loading: vi.fn(() => 'toast-id'),
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));

function makeArticle(overrides: Partial<Article> = {}): Article {
  return {
    id: 42,
    url: 'https://example.com/article',
    title: 'Search result article',
    source_name: 'Source',
    category: 'ai-llm',
    kind: 'rss',
    published_at: '2026-06-16T10:00:00Z',
    discovered_at: '2026-06-16T11:00:00Z',
    status: 'new',
    importance_score: 0.9,
    summary: 'Summary text.',
    reason: 'Why this matters.',
    tags: '["ai"]',
    ...overrides,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPalette() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/search']}>
        <FocusedArticleProvider>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <LocationProbe />
                  <CommandPalette open={true} onOpenChange={vi.fn()} />
                </>
              }
            />
          </Routes>
        </FocusedArticleProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CommandPalette article search', () => {
  it('opens article results inside the reader route instead of a new tab', async () => {
    vi.spyOn(api, 'searchArticles').mockResolvedValue([makeArticle()]);
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    renderPalette();

    await userEvent.type(screen.getByPlaceholderText(/jump to a view/i), 'search result');
    await waitFor(() => expect(screen.getByText('Search result article')).toBeTruthy());

    await userEvent.click(screen.getByText('Search result article'));

    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/a/42'));
    expect(openSpy).not.toHaveBeenCalled();
  });
});
