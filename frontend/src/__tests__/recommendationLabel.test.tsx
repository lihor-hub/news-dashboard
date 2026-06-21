// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ArticleRow } from '../components/article/ArticleRow';
import {
  recommendationLabel,
  recommendationExplanation,
  RECOMMENDATION_LABEL_TEXT,
} from '../lib/recommendation';
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

describe('recommendationLabel — score bands', () => {
  it('maps high scores to Recommended', () => {
    expect(recommendationLabel(95)).toBe('recommended');
    expect(recommendationLabel(70)).toBe('recommended');
  });

  it('maps mid scores to Relevant', () => {
    expect(recommendationLabel(69.9)).toBe('relevant');
    expect(recommendationLabel(45)).toBe('relevant');
  });

  it('maps low scores to Low signal', () => {
    expect(recommendationLabel(44.9)).toBe('low');
    expect(recommendationLabel(0)).toBe('low');
  });

  it('returns null for missing or invalid scores', () => {
    expect(recommendationLabel(undefined)).toBeNull();
    expect(recommendationLabel(null)).toBeNull();
    expect(recommendationLabel(NaN)).toBeNull();
  });
});

describe('ArticleRow — compact recommendation labels', () => {
  it('renders the recommendation label when a score is present', () => {
    renderRow(makeArticle({ recommendationScore: 82 }));
    const label = screen.getByTestId('recommendation-label');
    expect(label.textContent).toBe(RECOMMENDATION_LABEL_TEXT.recommended);
    expect(label.getAttribute('data-source')).toBe('recommendation');
    expect(label.className).toContain('text-signal-high');
  });

  it('renders the Relevant band for mid scores', () => {
    renderRow(makeArticle({ recommendationScore: 50 }));
    const label = screen.getByTestId('recommendation-label');
    expect(label.textContent).toBe('Relevant');
    expect(label.className).toContain('text-signal-mid');
  });

  it('falls back to the importance signal label when no score is present', () => {
    renderRow(makeArticle({ recommendationScore: undefined, signal: 'high' }));
    const label = screen.getByTestId('recommendation-label');
    expect(label.textContent).toBe('High signal');
    expect(label.getAttribute('data-source')).toBe('signal');
    expect(label.className).toContain('text-signal-high');
  });
});

describe('ArticleRow — existing workflows keep working', () => {
  it('keeps the article link for keyboard/tap opening', () => {
    renderRow(makeArticle({ recommendationScore: 82 }));
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.getAttribute('href')).toBe('/a/42');
  });

  it('fires the done action on swipe-right (mobile-friendly row interaction)', () => {
    setState.mockClear();
    renderRow(makeArticle({ recommendationScore: 50 }));
    const link = screen.getByRole('link', { name: /readable article/i });
    const touchTarget = link.parentElement!;
    fireEvent.touchStart(touchTarget, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(touchTarget, { touches: [{ clientX: 100, clientY: 0 }] });
    fireEvent.touchEnd(touchTarget);
    expect(setState).toHaveBeenCalledWith(expect.objectContaining({ id: '42' }), 'done', 'Read');
  });
});

describe('recommendationExplanation — concise factor reasons', () => {
  it('names each factor that meaningfully lifted the score', () => {
    const { reasons, fallback } = recommendationExplanation({
      score: 85,
      signals: {
        affinity_adjustment: 8,
        semantic_adjustment: 12,
        freshness_adjustment: 3,
        novelty_adjustment: 4,
      },
    });
    expect(fallback).toBe(false);
    expect(reasons).toEqual([
      'Matches sources and topics you engage with',
      'Similar to articles you’ve starred or read',
      'Fresh and timely right now',
      'Brings something new to your feed',
    ]);
  });

  it('omits factors that did not contribute', () => {
    const { reasons } = recommendationExplanation({
      score: 60,
      signals: {
        affinity_adjustment: 0,
        semantic_adjustment: 9,
        freshness_adjustment: 0.2,
        novelty_adjustment: -1,
      },
    });
    expect(reasons).toEqual(['Similar to articles you’ve starred or read']);
  });

  it('falls back to a useful reason when a score exists but no factor stands out', () => {
    const { reasons, fallback } = recommendationExplanation({
      score: 48,
      signals: { affinity_adjustment: 0, semantic_adjustment: 0 },
    });
    expect(fallback).toBe(true);
    expect(reasons).toEqual(['Ranked by overall relevance and importance for you']);
  });

  it('explains unranked articles rather than rendering an empty list', () => {
    const { reasons, fallback } = recommendationExplanation({});
    expect(fallback).toBe(true);
    expect(reasons).toEqual(['Not personalized yet — shown based on general importance']);
    expect(reasons.length).toBeGreaterThan(0);
  });
});
