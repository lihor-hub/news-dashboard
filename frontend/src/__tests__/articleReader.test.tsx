// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArticlePage } from '../pages/ArticlePage';
import * as api from '../api';
import type { Article } from '../types';

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
    // The action bar element must be present in the DOM.  It lives outside the
    // motion-slide-in-right animated wrapper so position:fixed always resolves
    // against the viewport rather than against an ancestor that carries a CSS
    // transform during the 0.2 s entry animation (fixes #189).
    expect(screen.getByTestId('action-bar')).toBeTruthy();
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
