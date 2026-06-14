// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BriefingsHistoryPage } from '../pages/BriefingsHistoryPage';
import { BriefingDetailPage } from '../pages/BriefingDetailPage';
import * as api from '../api';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const COMPLETE_BRIEFING = {
  id: 7,
  created_at: '2026-06-13T12:00:00+00:00',
  scope: 'since_last_briefing',
  since_at: '2026-06-12T12:00:00+00:00',
  until_at: '2026-06-13T12:00:00+00:00',
  status: 'complete' as const,
  title: 'AI Safety Takes Center Stage',
  summary: 'Anthropic and OpenAI both made waves today.',
  content: {
    sections: [
      {
        title: 'Safety Research',
        body: 'New frameworks published.',
        citations: [1],
      },
    ],
    worth_opening: [],
  },
  model: 'gpt-4o-mini',
  error: null,
  articles: [
    {
      id: 1,
      title: 'Anthropic Safety Paper',
      url: 'https://example.com/1',
      source_name: 'Anthropic Blog',
      category: 'ai',
      section_index: 0,
      citation_index: 0,
    },
  ],
};

const FAILED_BRIEFING = {
  ...COMPLETE_BRIEFING,
  id: 8,
  status: 'failed' as const,
  title: '',
  summary: '',
  content: null,
  error: 'AI returned invalid JSON',
  articles: [],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderHistory() {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={['/briefs']}>
        <BriefingsHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderDetail(id: string) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[`/briefs/${id}`]}>
        <Routes>
          <Route path="/briefs/:id" element={<BriefingDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ── BriefingsHistoryPage ──────────────────────────────────────────────────────

describe('BriefingsHistoryPage — loading state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefings').mockReturnValue(new Promise((_r) => undefined));
  });

  it('renders without crashing while loading', () => {
    const { container } = renderHistory();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('shows the page heading', () => {
    renderHistory();
    expect(screen.getByText('Briefing History')).toBeTruthy();
  });
});

describe('BriefingsHistoryPage — empty state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefings').mockResolvedValue({ items: [] });
  });

  it('shows empty message when no briefings', async () => {
    renderHistory();
    await waitFor(() => expect(screen.getByText('No briefings yet')).toBeTruthy());
  });

  it('links to Brief page from empty state', async () => {
    renderHistory();
    await waitFor(() => {
      const link = screen.getByRole('link', { name: 'Brief' });
      expect(link).toBeTruthy();
      expect(link.getAttribute('href')).toBe('/');
    });
  });
});

describe('BriefingsHistoryPage — list state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefings').mockResolvedValue({
      items: [COMPLETE_BRIEFING, FAILED_BRIEFING],
    });
  });

  it('renders briefing title', async () => {
    renderHistory();
    await waitFor(() => expect(screen.getByText('AI Safety Takes Center Stage')).toBeTruthy());
  });

  it('renders a link to the briefing detail', async () => {
    renderHistory();
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /AI Safety Takes Center Stage/i });
      expect(link.getAttribute('href')).toBe('/briefs/7');
    });
  });

  it('shows failed badge for failed briefing', async () => {
    renderHistory();
    await waitFor(() => expect(screen.getByText('Failed')).toBeTruthy());
  });

  it('shows failed briefing error message', async () => {
    renderHistory();
    await waitFor(() => expect(screen.getByText(/AI returned invalid JSON/i)).toBeTruthy());
  });

  it('renders multiple rows', async () => {
    renderHistory();
    await waitFor(() => {
      const links = screen.getAllByRole('link');
      // Each briefing row is a link; at least 2 briefing rows
      const briefingLinks = links.filter((l) => l.getAttribute('href')?.startsWith('/briefs/'));
      expect(briefingLinks.length).toBe(2);
    });
  });
});

// ── BriefingDetailPage ────────────────────────────────────────────────────────

describe('BriefingDetailPage — loading state', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefing').mockReturnValue(new Promise((_r) => undefined));
  });

  it('shows skeleton while loading', () => {
    const { container } = renderDetail('7');
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('shows back link while loading', () => {
    renderDetail('7');
    const link = screen.getByRole('link', { name: /briefing history/i });
    expect(link.getAttribute('href')).toBe('/briefs');
  });
});

describe('BriefingDetailPage — complete briefing', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefing').mockResolvedValue(COMPLETE_BRIEFING);
  });

  it('renders briefing title', async () => {
    renderDetail('7');
    await waitFor(() => expect(screen.getByText('AI Safety Takes Center Stage')).toBeTruthy());
  });

  it('renders briefing summary', async () => {
    renderDetail('7');
    await waitFor(() =>
      expect(screen.getByText('Anthropic and OpenAI both made waves today.')).toBeTruthy()
    );
  });

  it('renders section heading', async () => {
    renderDetail('7');
    await waitFor(() => expect(screen.getByText('Safety Research')).toBeTruthy());
  });

  it('renders back link to /briefs', () => {
    renderDetail('7');
    const link = screen.getByRole('link', { name: /briefing history/i });
    expect(link.getAttribute('href')).toBe('/briefs');
  });

  it('does not show a Refresh button (read-only view)', async () => {
    renderDetail('7');
    await waitFor(() => expect(screen.getByText('AI Safety Takes Center Stage')).toBeTruthy());
    expect(screen.queryByRole('button', { name: /refresh|generate/i })).toBeNull();
  });
});

describe('BriefingDetailPage — failed briefing', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefing').mockResolvedValue(FAILED_BRIEFING);
  });

  it('shows failed state message', async () => {
    renderDetail('8');
    await waitFor(() => expect(screen.getByText('This briefing failed')).toBeTruthy());
  });

  it('shows the error message', async () => {
    renderDetail('8');
    await waitFor(() => expect(screen.getByText(/AI returned invalid JSON/i)).toBeTruthy());
  });
});

describe('BriefingDetailPage — error / not found', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchBriefing').mockRejectedValue(new Error('404 Not Found'));
  });

  it('shows not found message', async () => {
    renderDetail('999');
    await waitFor(() => expect(screen.getByText('Briefing not found')).toBeTruthy());
  });

  it('shows back link even in error state', async () => {
    renderDetail('999');
    await waitFor(() => {
      const links = screen.getAllByRole('link', { name: /briefing history/i });
      expect(links.length).toBeGreaterThan(0);
    });
  });
});

describe('BriefingDetailPage — invalid ID', () => {
  it('shows invalid ID message for non-numeric ID', () => {
    renderDetail('not-a-number');
    expect(screen.getByText('Invalid briefing ID.')).toBeTruthy();
  });
});
