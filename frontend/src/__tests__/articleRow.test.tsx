// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ArticleRow } from '../components/article/ArticleRow';
import type { WorkflowArticle } from '../lib/workflowTypes';

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => (key === 'priorityFeeds.highPriority' ? 'High priority' : key),
  }),
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

function renderRow(article: WorkflowArticle) {
  return render(
    <MemoryRouter initialEntries={['/today']}>
      <Routes>
        <Route path="/today" element={<ArticleRow article={article} />} />
        <Route path="/a/:id" element={<div data-testid="reader">Reader</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ArticleRow — also covered by duplicate sources (#929)', () => {
  it('shows an "Also covered by" line naming duplicate sources', () => {
    renderRow(makeArticle({ alsoFrom: ['The Verge', 'Ars Technica'] }));
    expect(screen.getByText('Also covered by The Verge, Ars Technica')).toBeTruthy();
  });

  it('renders nothing when also_from is absent', () => {
    renderRow(makeArticle({ alsoFrom: undefined }));
    expect(screen.queryByText(/Also covered by/)).toBeNull();
  });

  it('renders nothing when also_from is an empty array', () => {
    renderRow(makeArticle({ alsoFrom: [] }));
    expect(screen.queryByText(/Also covered by/)).toBeNull();
  });

  it('shows all names with no "+more" suffix at exactly 3 duplicates', () => {
    renderRow(makeArticle({ alsoFrom: ['Source A', 'Source B', 'Source C'] }));
    expect(screen.getByText('Also covered by Source A, Source B, Source C')).toBeTruthy();
    expect(screen.queryByText(/more/)).toBeNull();
  });

  it('collapses more than 3 duplicate sources to "+N more"', () => {
    renderRow(
      makeArticle({ alsoFrom: ['Source A', 'Source B', 'Source C', 'Source D', 'Source E'] })
    );
    expect(screen.getByText('Also covered by Source A, Source B, Source C, +2 more')).toBeTruthy();
  });

  it('keeps rendering the row normally alongside the existing metadata', () => {
    renderRow(makeArticle({ alsoFrom: ['The Verge'], recommendationScore: 82 }));
    expect(screen.getByText('Readable article')).toBeTruthy();
    expect(screen.getByTestId('recommendation-label')).toBeTruthy();
    expect(screen.getByText('Also covered by The Verge')).toBeTruthy();
  });
});

describe('ArticleRow — high-priority sources', () => {
  it('renders an accessible urgent treatment for a high-priority source', () => {
    renderRow(makeArticle({ highPriority: true }));

    const row = screen.getByRole('link', { name: /high priority.*readable article/i });
    expect(row.className).toContain('border-l');
    expect(screen.getByText('High priority')).toBeTruthy();
  });

  it('does not render urgent treatment for a normal source', () => {
    renderRow(makeArticle({ highPriority: false }));

    expect(screen.queryByText('High priority')).toBeNull();
  });
});
