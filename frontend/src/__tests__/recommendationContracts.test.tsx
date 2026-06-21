// @vitest-environment happy-dom
//
// Final frontend regression pass for the recommendation epic (issue #227).
//
// The per-feature suites already cover compact labels (recommendationLabel),
// on-demand explanations and reader navigation (articleReader), and keyboard
// triage (keyboard/triage). This file locks the remaining cross-cutting
// contract: re-ranking the Today feed must not disturb the existing row
// affordances — focus highlighting, the reader link, and swipe/tap triage all
// keep working regardless of an article's recommendation metadata.
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ArticleRow } from '../components/article/ArticleRow';
import type { WorkflowArticle } from '../lib/workflowTypes';

const setState = vi.fn();
const toggleStar = vi.fn();

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState, toggleStar, sendLater: vi.fn() }),
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

function renderRow(article: WorkflowArticle, focused?: boolean) {
  return render(
    <MemoryRouter initialEntries={['/today']}>
      <Routes>
        <Route path="/today" element={<ArticleRow article={article} focused={focused} />} />
        <Route path="/a/:id" element={<div data-testid="reader">Reader</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ArticleRow — row focus survives ranking', () => {
  it('marks the focused row for keyboard navigation', () => {
    renderRow(makeArticle({ recommendationScore: 82 }), true);
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.className).toContain('focus-row');
  });

  it('does not mark unfocused rows', () => {
    renderRow(makeArticle({ recommendationScore: 82 }), false);
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.className).not.toContain('focus-row');
  });

  it('keeps focus highlighting even when the article is unranked', () => {
    renderRow(makeArticle({ recommendationScore: undefined }), true);
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.className).toContain('focus-row');
  });
});

describe('ArticleRow — workflows are independent of recommendation score', () => {
  it.each([
    ['a high score', 95],
    ['a low score', 5],
    ['no score', undefined],
  ])('opens the reader at /a/:id with %s', (_label, recommendationScore) => {
    renderRow(makeArticle({ recommendationScore }));
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.getAttribute('href')).toBe('/a/42');
  });

  it('fires the done action on swipe-right regardless of ranking', () => {
    setState.mockClear();
    renderRow(makeArticle({ recommendationScore: 3 }));
    const link = screen.getByRole('link', { name: /readable article/i });
    const touchTarget = link.parentElement!;
    fireEvent.touchStart(touchTarget, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(touchTarget, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(touchTarget);
    expect(setState).toHaveBeenCalledWith(expect.objectContaining({ id: '42' }), 'done', 'Read');
  });
});

describe('Today feed — reader navigation follows the ranked order', () => {
  it('renders rows in the order given by ranking, each opening its own article', () => {
    // The feed hands ArticleRow its articles already sorted by recommendation
    // score; rendering in that order must keep every reader link intact so the
    // user can open exactly the article they tapped after a re-rank.
    const ranked: WorkflowArticle[] = [
      makeArticle({ id: '1', title: 'Top ranked', recommendationScore: 96 }),
      makeArticle({ id: '2', title: 'Middle ranked', recommendationScore: 50 }),
      makeArticle({ id: '3', title: 'Low ranked', recommendationScore: 2 }),
    ];
    render(
      <MemoryRouter initialEntries={['/today']}>
        <Routes>
          <Route
            path="/today"
            element={
              <ul data-testid="feed">
                {ranked.map((article) => (
                  <li key={article.id}>
                    <ArticleRow article={article} />
                  </li>
                ))}
              </ul>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    const feed = screen.getByTestId('feed');
    const links = within(feed).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/a/1', '/a/2', '/a/3']);
    expect(links.map((l) => within(l).getByRole('heading').textContent)).toEqual([
      'Top ranked',
      'Middle ranked',
      'Low ranked',
    ]);
  });
});
