// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BriefPage } from '../pages/BriefPage';
import * as api from '../api';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const ARTICLE_CITED = {
  id: 42,
  title: 'Claude 4 Released',
  url: 'https://example.com/claude-4',
  source_name: 'Anthropic Blog',
  category: 'ai',
  section_index: 0,
  citation_index: 0,
  importance_score: 90,
};

const ARTICLE_WORTH = {
  id: 99,
  title: 'Another Article',
  url: 'https://example.com/other',
  source_name: 'Tech News',
  category: 'tech',
  section_index: null,
  citation_index: null,
  importance_score: 50,
};

const COMPLETE_BRIEFING = {
  id: 1,
  created_at: '2026-06-13T12:00:00+00:00',
  scope: 'since_last_briefing',
  since_at: '2026-06-12T12:00:00+00:00',
  until_at: '2026-06-13T12:00:00+00:00',
  status: 'complete' as const,
  title: 'AI Frameworks Tighten Production Workflows',
  summary: "A summary of today's top AI news.",
  content: {
    sections: [
      {
        title: 'Agent frameworks',
        body: 'LangGraph and related updates shape production AI.',
        citations: [42],
      },
    ],
    worth_opening: [99],
  },
  model: 'gpt-4o-mini',
  error: null,
  articles: [ARTICLE_CITED, ARTICLE_WORTH],
};

const FAILED_BRIEFING = {
  ...COMPLETE_BRIEFING,
  id: 2,
  status: 'failed' as const,
  title: '',
  summary: '',
  content: null,
  error: 'AI returned invalid JSON',
  articles: [],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderBriefPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/brief']}>
        <BriefPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('BriefPage — loading state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockReturnValue(new Promise((_res) => undefined));
  });

  it('renders skeleton while loading', () => {
    renderBriefPage();
    // Skeleton elements are present (animate-pulse divs)
    const { container } = renderBriefPage();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });
});

describe('BriefPage — empty state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue({ status: 'empty' });
  });

  it('shows no-briefing-yet message', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('No briefing yet')).toBeTruthy());
  });

  it('shows Generate briefing button', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
  });

  it('shows Review Today feed button', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /review today feed/i })).toBeTruthy()
    );
  });
});

describe('BriefPage — latest briefing', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue(COMPLETE_BRIEFING);
  });

  it('renders the briefing title', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByText('AI Frameworks Tighten Production Workflows')).toBeTruthy()
    );
  });

  it('renders the executive summary', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText("A summary of today's top AI news.")).toBeTruthy());
  });

  it('renders section title and body', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Agent frameworks')).toBeTruthy());
    expect(screen.getByText('LangGraph and related updates shape production AI.')).toBeTruthy();
  });

  it('renders citation chip for cited article', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Claude 4 Released')).toBeTruthy());
  });

  it('renders "Also worth a look" section', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Also worth a look')).toBeTruthy());
    expect(screen.getByText('Another Article')).toBeTruthy();
  });

  it('orders worth-opening articles by the briefing content contract', async () => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue({
      ...COMPLETE_BRIEFING,
      content: {
        ...COMPLETE_BRIEFING.content,
        worth_opening: [99, 77],
      },
      articles: [
        { ...ARTICLE_CITED, id: 77, title: 'Second Worth Opening', section_index: null },
        ARTICLE_WORTH,
      ],
    });

    renderBriefPage();

    await waitFor(() => expect(screen.getByText('Also worth a look')).toBeTruthy());
    const worthLinks = screen
      .getAllByRole('link')
      .filter(
        (link) => link.getAttribute('href') === '/a/99' || link.getAttribute('href') === '/a/77'
      );

    expect(worthLinks.map((link) => link.textContent)).toEqual([
      'Another ArticleTech News',
      'Second Worth OpeningAnthropic Blog',
    ]);
  });

  it('shows Refresh button', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate new briefing/i })).toBeTruthy()
    );
  });
});

describe('BriefPage — citation navigation', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue(COMPLETE_BRIEFING);
  });

  it('citation chip links to /a/:id', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Claude 4 Released')).toBeTruthy());
    const link = screen.getByText('Claude 4 Released').closest('a');
    expect(link).toBeTruthy();
    expect(link?.getAttribute('href')).toBe('/a/42');
  });

  it('worth-opening article links to /a/:id', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Another Article')).toBeTruthy());
    const link = screen.getByText('Another Article').closest('a');
    expect(link).toBeTruthy();
    expect(link?.getAttribute('href')).toBe('/a/99');
  });
});

describe('BriefPage — generating state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue({ status: 'empty' });
    vi.spyOn(api, 'createBriefing').mockReturnValue(new Promise((_res) => undefined));
  });

  it('disables generate button while generating', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
    const btn = screen.getByRole<HTMLButtonElement>('button', { name: /generate briefing/i });
    await userEvent.click(btn);
    await waitFor(() => {
      const updatedBtn = screen.getByRole<HTMLButtonElement>('button', { name: /generating/i });
      expect(updatedBtn.disabled).toBe(true);
    });
  });
});

describe('BriefPage — AI not configured error', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue({ status: 'empty' });
    vi.spyOn(api, 'createBriefing').mockRejectedValue(new Error('503 Service Unavailable'));
  });

  it('shows AI not configured message', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole('button', { name: /generate briefing/i }));
    await waitFor(() => expect(screen.getByText('AI not configured')).toBeTruthy());
  });

  it('shows the Today feed path', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole('button', { name: /generate briefing/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /review today feed/i })).toBeTruthy()
    );
  });
});

describe('BriefPage — generation failed error', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue({ status: 'empty' });
    vi.spyOn(api, 'createBriefing').mockRejectedValue(new Error('500 Internal Server Error'));
  });

  it('shows generation failed message', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole('button', { name: /generate briefing/i }));
    await waitFor(() => expect(screen.getByText('Generation failed')).toBeTruthy());
  });

  it('shows Retry button', async () => {
    renderBriefPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate briefing/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole('button', { name: /generate briefing/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy());
  });
});

describe('BriefPage — failed briefing state (last save failed)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchLatestBriefing').mockResolvedValue(FAILED_BRIEFING);
  });

  it('shows last briefing failed message', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('Last briefing failed')).toBeTruthy());
  });

  it('shows the error detail', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByText('AI returned invalid JSON')).toBeTruthy());
  });

  it('shows Retry and Review Today feed buttons', async () => {
    renderBriefPage();
    await waitFor(() => expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy());
    expect(screen.getByRole('button', { name: /review today feed/i })).toBeTruthy();
  });
});
