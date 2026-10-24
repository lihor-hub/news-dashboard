// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ArticleRow } from '../components/article/ArticleRow';
import type { WorkflowArticle } from '../lib/workflowTypes';

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));
vi.mock('react-i18next', async () => {
  const english = (await import('../locales/en/translation.json')).default as Record<
    string,
    unknown
  >;
  const lookupKey = (key: string) =>
    key
      .split('.')
      .reduce<unknown>(
        (node, part) => (node as Record<string, unknown> | undefined)?.[part],
        english
      );
  const t = (key: string, options?: Record<string, unknown>) => {
    const singular = options?.count === 1 ? lookupKey(`${key}_one`) : undefined;
    const value =
      typeof singular === 'string'
        ? singular
        : key
            .split('.')
            .reduce<unknown>(
              (node, part) => (node as Record<string, unknown> | undefined)?.[part],
              english
            );
    if (typeof value !== 'string') return key;
    return value.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ''));
  };
  return { useTranslation: () => ({ t }) };
});

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
  it('shows a "+N sources" meta chip naming duplicate sources', () => {
    renderRow(makeArticle({ alsoFrom: ['The Verge', 'Ars Technica'] }));
    const chip = screen.getByTestId('also-covered-by');
    expect(chip.textContent).toBe('+2 sources');
    expect(chip.getAttribute('title')).toBe('Also covered by The Verge, Ars Technica');
    expect(chip.getAttribute('aria-label')).toBe('Also covered by The Verge, Ars Technica');
  });

  it('renders nothing when also_from is absent', () => {
    renderRow(makeArticle({ alsoFrom: undefined }));
    expect(screen.queryByTestId('also-covered-by')).toBeNull();
  });

  it('renders nothing when also_from is an empty array', () => {
    renderRow(makeArticle({ alsoFrom: [] }));
    expect(screen.queryByTestId('also-covered-by')).toBeNull();
  });

  it('shows all names with no "+more" suffix at exactly 3 duplicates', () => {
    renderRow(makeArticle({ alsoFrom: ['Source A', 'Source B', 'Source C'] }));
    expect(screen.getByTestId('also-covered-by').getAttribute('title')).toBe(
      'Also covered by Source A, Source B, Source C'
    );
  });

  it('collapses more than 3 duplicate sources to "+N more"', () => {
    renderRow(
      makeArticle({ alsoFrom: ['Source A', 'Source B', 'Source C', 'Source D', 'Source E'] })
    );
    const chip = screen.getByTestId('also-covered-by');
    expect(chip.textContent).toBe('+5 sources');
    expect(chip.getAttribute('title')).toBe(
      'Also covered by Source A, Source B, Source C, +2 more'
    );
  });

  it('keeps rendering the row normally alongside the existing metadata', () => {
    renderRow(makeArticle({ alsoFrom: ['The Verge'], recommendationScore: 82 }));
    expect(screen.getByText('Readable article')).toBeTruthy();
    expect(screen.getByTestId('recommendation-label')).toBeTruthy();
    expect(screen.getByTestId('also-covered-by').textContent).toBe('+1 source');
  });
});

describe('ArticleRow — high-priority sources', () => {
  it('renders an accessible urgent treatment for a high-priority source', () => {
    renderRow(makeArticle({ highPriority: true }));

    const row = screen.getByRole('link', { name: /high priority.*readable article/i });
    expect(row.className).toContain('border-s');
    expect(screen.getByText('High priority')).toBeTruthy();
  });

  it('does not render urgent treatment for a normal source', () => {
    renderRow(makeArticle({ highPriority: false }));

    expect(screen.queryByText('High priority')).toBeNull();
  });
});

describe('ArticleRow — modernized layout', () => {
  it('leads with a deterministic source-initial avatar tile using chart tokens', () => {
    const { unmount } = renderRow(makeArticle({ sourceName: 'ars technica' }));
    const avatar = screen.getByTestId('source-avatar');
    expect(avatar.textContent).toBe('A');
    expect(avatar.getAttribute('aria-hidden')).toBe('true');
    const style = avatar.getAttribute('style') ?? '';
    expect(style).toMatch(/var\(--color-chart-[1-5]\)/);
    unmount();

    renderRow(makeArticle({ sourceName: 'ars technica' }));
    expect(screen.getByTestId('source-avatar').getAttribute('style')).toBe(style);
  });

  it('renders the label as a soft pill and a slim match bar sized to the score', () => {
    renderRow(makeArticle({ recommendationScore: 83.4 }));
    const label = screen.getByTestId('recommendation-label');
    expect(label.className).toContain('rounded-full');
    const bar = screen.getByTestId('recommendation-match-bar');
    expect(bar.getAttribute('aria-hidden')).toBe('true');
    const fill = bar.firstElementChild as HTMLElement;
    expect(fill.style.width).toBe('83%');
    expect(screen.getByTestId('recommendation-score').textContent).toBe('83%');
  });

  it('omits the match bar for unranked articles', () => {
    renderRow(makeArticle({ recommendationScore: undefined }));
    expect(screen.queryByTestId('recommendation-match-bar')).toBeNull();
  });

  it('uses a 16px semibold title and a ≥48px tap height', () => {
    renderRow(makeArticle());
    const title = screen.getByRole('heading', { name: 'Readable article' });
    expect(title.className).toContain('text-base');
    expect(title.className).toContain('font-semibold');
    expect(screen.getByRole('link', { name: /readable article/i }).className).toContain('min-h-12');
  });

  it('keeps meta text at 12px or larger', () => {
    renderRow(makeArticle({ detectedLang: 'de', originalTitle: 'Lesbarer Artikel' }));
    const link = screen.getByRole('link', { name: /readable article/i });
    expect(link.innerHTML).not.toMatch(/text-\[(9|10|11)px\]/);
  });

  it('makes the explanation trigger a 44px tap target that toggles the tooltip', () => {
    renderRow(makeArticle({ recommendationScore: 80, recommendationExplanation: 'Matches AI' }));
    const trigger = screen.getByTestId('recommendation-explanation-trigger');
    expect(trigger.className).toContain('size-11');
    fireEvent.click(trigger);
    expect(screen.getByTestId('recommendation-explanation-tooltip').textContent).toBe('Matches AI');
  });

  it('labels the swipe reveal with the matching triage action', () => {
    renderRow(makeArticle());
    const link = screen.getByRole('link', { name: /readable article/i });
    fireEvent.touchStart(link, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(link, { touches: [{ clientX: 60, clientY: 0 }] });
    expect(screen.getByText('Done')).toBeTruthy();
    fireEvent.touchMove(link, { touches: [{ clientX: -60, clientY: 0 }] });
    expect(screen.getByText('Skip')).toBeTruthy();
  });
});
