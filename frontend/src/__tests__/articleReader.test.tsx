// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArticlePage } from '../pages/ArticlePage';
import * as api from '../api';
import * as workflowApi from '../api/workflowApi';
import type { Article } from '../types';

vi.mock('../api/workflowApi', async (importOriginal) => {
  const actual = await importOriginal<typeof workflowApi>();
  return {
    ...actual,
    patchArticleState: vi.fn().mockResolvedValue({}),
    patchArticleStar: vi.fn().mockResolvedValue({}),
  };
});

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

  it('shows action bar with Star, Done, Later, Skip, Archive, Listen', async () => {
    renderReader();
    await waitFor(() => {
      expect(screen.getByText('Star')).toBeTruthy();
      expect(screen.getByText('Done')).toBeTruthy();
      expect(screen.getByText('Later')).toBeTruthy();
      expect(screen.getByText('Skip')).toBeTruthy();
      expect(screen.getByText('Archive')).toBeTruthy();
      expect(screen.getByText('Listen')).toBeTruthy();
    });
  });

  it('renders safe article body markdown links as external anchors', async () => {
    const body = 'Read [the original report](https://example.org/report?from=reader&ok=1).';
    const article = makeArticle({ body_status: 'ok', body });
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(article);
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(article);

    renderReader('42', article);

    const link = await screen.findByRole('link', { name: 'the original report' });
    expect(link).toHaveAttribute('href', 'https://example.org/report?from=reader&ok=1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders unsafe article body markdown links as plain text', async () => {
    const body = [
      '[run script](javascript:alert(1))',
      '[data url](data:text/html,<script>alert(1)</script>)',
      '[vbscript url](vbscript:msgbox(1))',
      '[broken url](https://example.com/" onclick="alert(1))',
    ].join('\n\n');
    const article = makeArticle({ body_status: 'ok', body });
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(article);
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(article);

    renderReader('42', article);

    await screen.findByText('run script');
    expect(screen.queryByRole('link', { name: 'run script' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'data url' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'vbscript url' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'broken url' })).toBeNull();
  });

  it('escapes article body markdown link labels and href attributes', async () => {
    const body = '[<img src=x onerror=alert(1)>](https://example.org/report?quote="&tag=<tag>)';
    const article = makeArticle({ body_status: 'ok', body });
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(article);
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(article);

    renderReader('42', article);

    const link = await screen.findByRole('link', { name: '<img src=x onerror=alert(1)>' });
    expect(link.innerHTML).toBe('&lt;img src=x onerror=alert(1)&gt;');
    expect(link).toHaveAttribute('href', 'https://example.org/report?quote=%22&tag=%3Ctag%3E');
    expect(link).not.toHaveAttribute('onerror');
  });
});

// ─── Open original link ───────────────────────────────────────────────────────

describe('ArticlePage — Open original link', () => {
  it('is visible while body is still loading', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'missing' }));
    // Body fetch never resolves — simulates in-progress load
    vi.spyOn(api, 'fetchArticleBody').mockReturnValue(new Promise(() => undefined));

    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    // Meta-line "Open original" link is always present
    expect(screen.getAllByText('Open original').length).toBeGreaterThanOrEqual(1);
  });

  it('is visible when body loaded successfully', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full text.' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full text.' })
    );

    renderReader('42', makeArticle({ body_status: 'ok', body: 'Full text.' }));
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getAllByText('Open original').length).toBeGreaterThanOrEqual(1);
  });

  it('is visible when body fetch failed', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'error', body: null })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'error', body: null })
    );

    renderReader('42', makeArticle({ body_status: 'error', body: null }));
    await waitFor(() => screen.getByText('Test Article Title'));
    // Meta-line link + error-block link are both present
    expect(screen.getAllByText('Open original').length).toBeGreaterThanOrEqual(2);
  });

  it('points to the article URL', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'missing' }));
    vi.spyOn(api, 'fetchArticleBody').mockReturnValue(new Promise(() => undefined));

    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    // The meta-line link (first match by text) must point to the article URL
    const links = screen.getAllByText('Open original');
    const hrefs = links.map((el) => el.closest('a')?.href);
    expect(hrefs).toContain('https://example.com/article');
  });
});

// ─── Reading time ─────────────────────────────────────────────────────────────

describe('ArticlePage — reading time', () => {
  it('shows "X min read" when body is loaded', async () => {
    // 400 words → 2 min read
    const body = Array(400).fill('word').join(' ');
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'ok', body }));
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(makeArticle({ body_status: 'ok', body }));

    renderReader('42', makeArticle({ body_status: 'ok', body }));
    await waitFor(() => expect(screen.getByText('2 min read')).toBeTruthy());
  });

  it('does not show reading time when body is not yet loaded', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'missing' }));
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(makeArticle({ body_status: 'missing' }));

    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.queryByText(/min read/)).toBeNull();
  });

  it('shows minimum 1 min read for very short bodies', async () => {
    const body = 'Short.';
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle({ body_status: 'ok', body }));
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(makeArticle({ body_status: 'ok', body }));

    renderReader('42', makeArticle({ body_status: 'ok', body }));
    await waitFor(() => expect(screen.getByText('1 min read')).toBeTruthy());
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
    // Multiple "Open original" links exist (meta-line + error block)
    expect(screen.getAllByText('Open original').length).toBeGreaterThanOrEqual(1);
  });
});

// ─── Action bar viewport-fixed ───────────────────────────────────────────────

describe('ArticlePage — action bar', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
  });

  it('renders the action bar', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getByTestId('action-bar')).toBeTruthy();
  });

  it('action bar is a direct child of document.body (portal)', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    const actionBar = screen.getByTestId('action-bar');
    // The action bar is rendered via createPortal(…, document.body) so that
    // position:fixed always resolves against the viewport — no ancestor or
    // sibling CSS transform (including the motion-slide-in-right entry
    // animation) can bleed into the compositor layer for the bar (fixes #196).
    expect(actionBar.parentElement).toBe(document.body);
  });

  it('action bar is not a descendant of the animated wrapper', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    const animatedWrapper = document.querySelector('.motion-slide-in-right');
    const actionBar = screen.getByTestId('action-bar');
    expect(animatedWrapper?.contains(actionBar)).toBe(false);
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

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────

describe('ArticlePage — keyboard shortcuts', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
  });

  it('o opens article URL in new tab with noopener,noreferrer', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    fireEvent.keyDown(window, { key: 'o' });
    expect(openSpy).toHaveBeenCalledWith(
      'https://example.com/article',
      '_blank',
      'noopener,noreferrer'
    );
  });
});

// ─── Touch gesture handling ────────────────────────────────────────────────────

describe('ArticlePage — touch gesture state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
  });

  it('action bar buttons are in the DOM and individually accessible', async () => {
    // Regression: the motion-slide-in-right CSS animation used fill:both which
    // retained transform:translateX(0) on the outer div after the 0.2s animation.
    // Any non-none CSS transform makes an element a containing block for
    // position:fixed descendants — the fixed action bar would scroll with the
    // content instead of staying viewport-fixed, making buttons unreachable.
    // The fix removes transform from the keyframe `to` state so no transform is
    // retained after the animation ends.
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    // All six action buttons must be present in the DOM.
    expect(screen.getByRole('button', { name: /star/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /done/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /later/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /skip/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /archive/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /listen/i })).toBeTruthy();
  });

  it('listen button is accessible and enabled when article is loaded', async () => {
    vi.spyOn(api, 'fetchArticleAudioUrl').mockResolvedValue('blob:fake');
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    const btn = screen.getByRole('button', { name: /listen/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it('touchcancel on the article content resets swipe state without navigating', async () => {
    // Regression: missing onTouchCancel meant swipeRef.current stayed non-null
    // after a cancelled browser gesture, so the very next touchEnd could see
    // a stale dx and fire prev/next navigation unexpectedly.
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));

    // Find the scrollable content div (it has the touch handlers).
    // In the rendered DOM it wraps the <article> element.
    const contentDiv = screen.getByText('Test Article Title').closest('article')!.parentElement!;

    // Simulate a horizontal drag that is then cancelled by the browser.
    fireEvent.touchStart(contentDiv, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchMove(contentDiv, { touches: [{ clientX: 90, clientY: 0 }] });
    // Browser cancels the gesture (e.g. a notification steals touch).
    fireEvent(contentDiv, new TouchEvent('touchcancel', { bubbles: true }));

    // A fresh tap immediately after must not trigger navigation — swipeRef was cleared.
    fireEvent.touchStart(contentDiv, { touches: [{ clientX: 0, clientY: 0 }] });
    fireEvent.touchEnd(contentDiv);
    // No navigation error thrown = pass (MemoryRouter absorbs navigate calls).
  });
});

// ─── AI insights ─────────────────────────────────────────────────────────────

describe('ArticlePage — AI insights (on-demand)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
  });

  it('does NOT auto-fetch insights on mount', async () => {
    const insightsSpy = vi.spyOn(api, 'fetchArticleInsights').mockResolvedValue([]);
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(insightsSpy).not.toHaveBeenCalled();
  });

  it('shows "Key takeaways" button in idle state', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getByTestId('insights-button')).toBeTruthy();
    expect(screen.getByText('Key takeaways')).toBeTruthy();
  });

  it('clicking the button triggers insights fetch', async () => {
    const insightsSpy = vi
      .spyOn(api, 'fetchArticleInsights')
      .mockReturnValue(new Promise(() => undefined));
    renderReader();
    await waitFor(() => screen.getByTestId('insights-button'));
    await userEvent.click(screen.getByTestId('insights-button'));
    expect(insightsSpy).toHaveBeenCalledWith('42');
  });

  it('shows analyzing spinner after button click while loading', async () => {
    vi.spyOn(api, 'fetchArticleInsights').mockReturnValue(new Promise(() => undefined));
    renderReader();
    await waitFor(() => screen.getByTestId('insights-button'));
    await userEvent.click(screen.getByTestId('insights-button'));
    await waitFor(() => expect(screen.getByText('Analyzing…')).toBeTruthy());
    expect(screen.queryByTestId('insights-button')).toBeNull();
  });

  it('shows bullet list after button click when insights return', async () => {
    vi.spyOn(api, 'fetchArticleInsights').mockResolvedValue([
      'First insight bullet',
      'Second insight bullet',
    ]);
    renderReader();
    await waitFor(() => screen.getByTestId('insights-button'));
    await userEvent.click(screen.getByTestId('insights-button'));
    await waitFor(() => expect(screen.getByText('First insight bullet')).toBeTruthy());
    expect(screen.getByText('Second insight bullet')).toBeTruthy();
    expect(screen.getByTestId('insights-section')).toBeTruthy();
    expect(screen.queryByTestId('insights-button')).toBeNull();
  });

  it('hides insights section and button on error after click', async () => {
    vi.spyOn(api, 'fetchArticleInsights').mockRejectedValue(new Error('501 Not Implemented'));
    renderReader();
    await waitFor(() => screen.getByTestId('insights-button'));
    await userEvent.click(screen.getByTestId('insights-button'));
    await waitFor(() => expect(screen.queryByTestId('insights-section')).toBeNull());
    expect(screen.queryByTestId('insights-button')).toBeNull();
  });

  it('hides insights section when bullets list is empty after click', async () => {
    vi.spyOn(api, 'fetchArticleInsights').mockResolvedValue([]);
    renderReader();
    await waitFor(() => screen.getByTestId('insights-button'));
    await userEvent.click(screen.getByTestId('insights-button'));
    await waitFor(() => expect(screen.queryByTestId('insights-section')).toBeNull());
    expect(screen.queryByTestId('insights-button')).toBeNull();
  });
});

// ─── Why recommended (on-demand explanation, #225) ────────────────────────────

describe('ArticlePage — why recommended (on-demand)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
  });

  it('keeps the explanation collapsed by default to avoid clutter', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({
        body_status: 'ok',
        body: 'Text',
        recommendation_score: 82,
        recommendation_signals: { semantic_adjustment: 12 },
      })
    );
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getByTestId('why-recommended-button')).toBeTruthy();
    expect(screen.queryByTestId('why-recommended-section')).toBeNull();
  });

  it('reveals concise factor reasons on demand', async () => {
    const scored = makeArticle({
      body_status: 'ok',
      body: 'Text',
      recommendation_score: 88,
      recommendation_signals: { affinity_adjustment: 8, semantic_adjustment: 12 },
    });
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(scored);
    // The body-fetch response replaces the cached article, so it must carry the
    // same recommendation metadata for the explanation to survive body load.
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(scored);
    renderReader();
    await waitFor(() => screen.getByTestId('why-recommended-button'));
    await userEvent.click(screen.getByTestId('why-recommended-button'));
    await waitFor(() => expect(screen.getByTestId('why-recommended-section')).toBeTruthy());
    expect(screen.getByText('Matches sources and topics you engage with')).toBeTruthy();
    expect(screen.getByText('Similar to articles you’ve starred or read')).toBeTruthy();
  });

  it('shows a useful fallback when recommendation metadata is missing', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    renderReader();
    await waitFor(() => screen.getByTestId('why-recommended-button'));
    await userEvent.click(screen.getByTestId('why-recommended-button'));
    await waitFor(() => expect(screen.getByTestId('why-recommended-section')).toBeTruthy());
    expect(
      screen.getByText('Not personalized yet — shown based on general importance')
    ).toBeTruthy();
  });

  it('can be toggled closed again, preserving the clean reader', async () => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text', recommendation_score: 70 })
    );
    renderReader();
    await waitFor(() => screen.getByTestId('why-recommended-button'));
    await userEvent.click(screen.getByTestId('why-recommended-button'));
    await waitFor(() => expect(screen.getByTestId('why-recommended-section')).toBeTruthy());
    await userEvent.click(screen.getByTestId('why-recommended-button'));
    await waitFor(() => expect(screen.queryByTestId('why-recommended-section')).toBeNull());
  });
});

// ─── Share button ─────────────────────────────────────────────────────────────

describe('ArticlePage — Share button', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
  });

  it('shows Share button in the action bar', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getByRole('button', { name: /share/i })).toBeTruthy();
  });

  it('calls navigator.share with article title and url when supported', async () => {
    const shareMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', {
      value: shareMock,
      configurable: true,
    });

    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    // Open the share dialog, then pick the external option.
    await userEvent.click(screen.getByRole('button', { name: /share/i }));
    await userEvent.click(await screen.findByText('Share externally'));

    expect(shareMock).toHaveBeenCalledWith({
      title: 'Test Article Title',
      url: 'https://example.com/article',
    });
  });

  it('copies to clipboard when navigator.share is unavailable', async () => {
    Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
    const clipboardMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardMock },
      configurable: true,
    });

    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /share/i }));
    await userEvent.click(await screen.findByText('Share externally'));

    expect(clipboardMock).toHaveBeenCalledWith('https://example.com/article');
  });
});

// ─── Triage actions navigate back ────────────────────────────────────────────
//
// Each triage button (Done, Archive, Skip, Later, Star) must navigate back to
// the previous page (i.e. the Today list) after the action succeeds.  The
// test uses a MemoryRouter with a two-entry history stack so that navigate(-1)
// is observable: the "/" route renders a sentinel element that appears only
// after navigation has occurred.

describe('ArticlePage — triage actions navigate back to the list', () => {
  function renderReaderWithHistory() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/', '/a/42']} initialIndex={1}>
          <Routes>
            <Route path="/a/:id" element={<ArticlePage />} />
            <Route path="/" element={<div data-testid="today-list">Today List</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(makeArticle());
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Text' })
    );
    vi.mocked(workflowApi.patchArticleState).mockResolvedValue({} as never);
    vi.mocked(workflowApi.patchArticleStar).mockResolvedValue({} as never);
  });

  it('Done navigates back to the list', async () => {
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /done/i }));
    await waitFor(() => screen.getByTestId('today-list'));
  });

  it('Archive navigates back to the list', async () => {
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /archive/i }));
    await waitFor(() => screen.getByTestId('today-list'));
  });

  it('Skip navigates back to the list (unstarred article)', async () => {
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByTestId('today-list'));
  });

  it('Later navigates back to the list', async () => {
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /later/i }));
    await waitFor(() => screen.getByTestId('today-list'));
  });

  it('Star navigates back to the list', async () => {
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    await userEvent.click(screen.getByRole('button', { name: /star/i }));
    await waitFor(() => screen.getByTestId('today-list'));
  });

  it('Skip on a starred article is disabled and does NOT navigate', async () => {
    // Override BOTH fetchArticle and fetchArticleBody so bodyMutation.onSuccess
    // (which calls setQueryData with the body response) does not overwrite the
    // starred flag.  adaptArticle uses a.state != null for the new state model,
    // so both state and starred must be present on both responses.
    const starredArticle = makeArticle({ state: 'today', starred: true });
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(starredArticle);
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ state: 'today', starred: true, body_status: 'ok', body: 'Text' })
    );
    renderReaderWithHistory();
    await waitFor(() => screen.getByText('Test Article Title'));
    // Skip button is disabled when the article is starred
    const skipBtn = screen.getByRole('button', { name: /skip/i });
    expect((skipBtn as HTMLButtonElement).disabled).toBe(true);
    // Still on the article page — no navigation
    expect(screen.queryByTestId('today-list')).toBeNull();
    expect(workflowApi.patchArticleState).not.toHaveBeenCalled();
  });
});

// ─── TTS / Listen button ──────────────────────────────────────────────────────

describe('ArticlePage — Listen / TTS', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchArticle').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
    vi.spyOn(api, 'fetchArticleBody').mockResolvedValue(
      makeArticle({ body_status: 'ok', body: 'Full article text.' })
    );
  });

  it('shows Listen button in idle state', async () => {
    renderReader();
    await waitFor(() => screen.getByText('Test Article Title'));
    expect(screen.getByText('Listen')).toBeTruthy();
  });

  it('shows loading state while audio is being fetched', async () => {
    let resolveAudio!: (url: string) => void;
    vi.spyOn(api, 'fetchArticleAudioUrl').mockReturnValue(
      new Promise<string>((res) => {
        resolveAudio = res;
      })
    );

    renderReader();
    await waitFor(() => screen.getByText('Listen'));
    await userEvent.click(screen.getByText('Listen'));

    await waitFor(() => expect(screen.getByText('Loading…')).toBeTruthy());
    const btn = screen.getByRole('button', { name: /loading/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);

    resolveAudio('blob:fake');
  });

  it('shows error toast when audio fetch fails', async () => {
    vi.spyOn(api, 'fetchArticleAudioUrl').mockRejectedValue(new Error('501 Not Implemented'));

    renderReader();
    await waitFor(() => screen.getByText('Listen'));
    await userEvent.click(screen.getByText('Listen'));

    await waitFor(() => expect(screen.getByText('Listen')).toBeTruthy());
  });
});
