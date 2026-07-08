// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── Shared API mock ──────────────────────────────────────────────────────────
// StatsPage / FeedsRunsPage import from '../api'; SettingsPage from '@/api'.
const apiMock = vi.hoisted(() => ({
  fetchArticleCounts: vi.fn(),
  fetchTriageMetrics: vi.fn(),
  fetchIngestedVsHandled: vi.fn(),
  fetchSourceQuality: vi.fn(),
  fetchCategoryMix: vi.fn(),
  fetchIngestRuns: vi.fn(),
  fetchIngestRunSources: vi.fn(),
  recalculateMyRecommendations: vi.fn(),
  fetchAiMemories: vi.fn(),
  createAiMemory: vi.fn(),
  updateAiMemory: vi.fn(),
  deactivateAiMemory: vi.fn(),
  learnAiMemoriesFromReading: vi.fn(),
  downloadUserExport: vi.fn(),
  importUserArchive: vi.fn(),
  deleteOwnAccount: vi.fn(),
}));
vi.mock('../api', () => apiMock);
vi.mock('@/api', () => apiMock);

const authMock = vi.hoisted(() => ({
  user: { id: 1, username: 'testuser', is_admin: false },
  setUser: vi.fn(),
}));
vi.mock('@/contexts/auth', () => ({
  useAuth: () => authMock,
}));

// recharts renders nothing measurable under happy-dom; stub it to plain divs so
// StatsPage's data rows/tables still mount and assert cleanly.
vi.mock('recharts', () => {
  const Pass = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Pass,
    AreaChart: Pass,
    BarChart: Pass,
    LineChart: Pass,
    Area: () => null,
    Bar: () => null,
    Line: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
  };
});

import '@/lib/i18n';
import { StatsPage } from '../pages/StatsPage';
import { SettingsPage } from '../pages/SettingsPage';
import { FeedsRunsPage } from '../pages/FeedsRunsPage';

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  apiMock.fetchAiMemories.mockResolvedValue([]);
});

function renderPage(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

// ── StatsPage ────────────────────────────────────────────────────────────────

describe('StatsPage', () => {
  const counts = { new: 1, saved: 2, read: 3, skipped: 4, archived: 5 };
  const triage = {
    articles_this_week: 12,
    handled_rate: 80,
    avg_triage_hours: 2,
    save_rate: 25,
  };

  function resolveAll() {
    apiMock.fetchArticleCounts.mockResolvedValue(counts);
    apiMock.fetchTriageMetrics.mockResolvedValue(triage);
    apiMock.fetchIngestedVsHandled.mockResolvedValue([
      { day: '2026-06-01', ingested: 10, handled: 4 },
    ]);
    apiMock.fetchSourceQuality.mockResolvedValue([
      {
        source_name: 'Acme',
        total: 42,
        skip_rate: 10,
        save_rate: 20,
        handle_rate: 55.5,
        error_rate: 3,
      },
    ]);
    apiMock.fetchCategoryMix.mockResolvedValue([{ day: '2026-06-01', 'ai-llm': 5 }]);
  }

  it('shows a loading placeholder before data resolves', () => {
    apiMock.fetchArticleCounts.mockReturnValue(new Promise(vi.fn()));
    apiMock.fetchTriageMetrics.mockReturnValue(new Promise(vi.fn()));
    apiMock.fetchIngestedVsHandled.mockReturnValue(new Promise(vi.fn()));
    apiMock.fetchSourceQuality.mockReturnValue(new Promise(vi.fn()));
    apiMock.fetchCategoryMix.mockReturnValue(new Promise(vi.fn()));
    renderPage(<StatsPage />);
    expect(screen.getByRole('heading', { name: 'Stats' })).toBeTruthy();
    expect(screen.getByText('Loading…')).toBeTruthy();
  });

  it('renders counts, metrics, and source quality once loaded', async () => {
    resolveAll();
    renderPage(<StatsPage />);
    // total = 1+2+3+4+5 = 15
    await waitFor(() => expect(screen.getByText('15')).toBeTruthy());
    expect(screen.getByText('80%')).toBeTruthy(); // handled rate
    expect(screen.getByText('25% save rate')).toBeTruthy();
    expect(screen.getByText('Acme')).toBeTruthy();
    expect(screen.getByText('55.5%')).toBeTruthy(); // handle_rate.toFixed(1)
    expect(screen.getByText('Category mix over time')).toBeTruthy();
  });

  it('surfaces an error message when a fetch fails', async () => {
    apiMock.fetchArticleCounts.mockRejectedValue(new Error('boom'));
    apiMock.fetchTriageMetrics.mockResolvedValue(triage);
    apiMock.fetchIngestedVsHandled.mockResolvedValue([]);
    apiMock.fetchSourceQuality.mockResolvedValue([]);
    apiMock.fetchCategoryMix.mockResolvedValue([]);
    renderPage(<StatsPage />);
    await waitFor(() => expect(screen.getByText('boom')).toBeTruthy());
    expect(screen.getByText('No data yet')).toBeTruthy();
  });
});

// ── SettingsPage ─────────────────────────────────────────────────────────────

describe('SettingsPage', () => {
  beforeEach(() => {
    // useUpdateCheck.check() runs on the web "Check version" button, not on mount.
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ version: '1.0.0' }),
        })
      )
    );
  });

  it('renders theme options and toggles the active theme', () => {
    renderPage(<SettingsPage />);
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeTruthy();
    expect(screen.getByText('Light')).toBeTruthy();
    expect(screen.getByText('Dark')).toBeTruthy();
    fireEvent.click(screen.getByText('Dark'));
    expect(localStorage.getItem('nd_theme') ?? localStorage.getItem('theme')).toBeDefined();
  });

  it('recalculates recommendations and reports the scored count', async () => {
    apiMock.recalculateMyRecommendations.mockResolvedValue({ scored: 3 });
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Refresh recommendations'));
    await waitFor(() => expect(screen.getByText(/Personalized 3 articles/)).toBeTruthy());
  });

  it('invalidates article caches after recalculation so stale scores are not shown', async () => {
    apiMock.recalculateMyRecommendations.mockResolvedValue({ scored: 2 });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <SettingsPage />
        </QueryClientProvider>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('Refresh recommendations'));
    await waitFor(() => expect(screen.getByText(/Personalized 2 articles/)).toBeTruthy());
    // Both the article list and per-article caches must be purged so recommendation
    // scores are re-fetched from the backend on the next view.
    const calledKeys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(calledKeys.some((k) => Array.isArray(k) && k.includes('articles'))).toBe(true);
    expect(calledKeys.some((k) => Array.isArray(k) && k[0] === 'article' && k.length === 1)).toBe(
      true
    );
  });

  it('reports when there is nothing to personalize', async () => {
    apiMock.recalculateMyRecommendations.mockResolvedValue({ scored: 0 });
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Refresh recommendations'));
    await waitFor(() => expect(screen.getByText(/Nothing to personalize yet/)).toBeTruthy());
  });

  it('shows an error when recalculation fails', async () => {
    apiMock.recalculateMyRecommendations.mockRejectedValue(new Error('nope'));
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Refresh recommendations'));
    await waitFor(() => expect(screen.getByText(/Couldn't refresh recommendations/)).toBeTruthy());
  });

  it('lets users create, edit, learn, and deactivate AI memories', async () => {
    apiMock.fetchAiMemories.mockResolvedValue([
      {
        id: 1,
        memory_type: 'preference',
        content: 'prioritize agent infrastructure',
        source: 'explicit',
        confidence: 1,
        active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]);
    apiMock.createAiMemory.mockResolvedValue({
      id: 2,
      memory_type: 'preference',
      content: 'avoid model-release marketing',
      source: 'explicit',
      confidence: 1,
      active: true,
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    });
    apiMock.updateAiMemory.mockResolvedValue({
      id: 1,
      memory_type: 'preference',
      content: 'prioritize agent infrastructure and evals',
      source: 'explicit',
      confidence: 1,
      active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-03T00:00:00Z',
    });
    apiMock.learnAiMemoriesFromReading.mockResolvedValue([
      {
        id: 3,
        memory_type: 'interest',
        content: 'Recent reading suggests sustained interest in ai coverage.',
        source: 'reading_dna',
        confidence: 0.65,
        active: true,
        created_at: '2026-01-04T00:00:00Z',
        updated_at: '2026-01-04T00:00:00Z',
      },
    ]);
    apiMock.deactivateAiMemory.mockResolvedValue({
      id: 2,
      memory_type: 'preference',
      content: 'avoid model-release marketing',
      source: 'explicit',
      confidence: 1,
      active: false,
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-05T00:00:00Z',
    });

    renderPage(<SettingsPage />);
    await waitFor(() => expect(screen.getByText('prioritize agent infrastructure')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('New AI memory'), {
      target: { value: 'avoid model-release marketing' },
    });
    fireEvent.click(screen.getByText('Add'));
    await waitFor(() =>
      expect(apiMock.createAiMemory).toHaveBeenCalledWith('avoid model-release marketing')
    );
    expect(screen.getByText('avoid model-release marketing')).toBeTruthy();

    fireEvent.click(screen.getAllByLabelText('Edit AI memory')[0]);
    fireEvent.change(screen.getByLabelText('AI memory content'), {
      target: { value: 'prioritize agent infrastructure and evals' },
    });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() =>
      expect(screen.getByText('prioritize agent infrastructure and evals')).toBeTruthy()
    );

    fireEvent.click(screen.getByText('Learn from recent reading'));
    await waitFor(() =>
      expect(
        screen.getByText('Recent reading suggests sustained interest in ai coverage.')
      ).toBeTruthy()
    );

    fireEvent.click(screen.getAllByLabelText('Deactivate AI memory')[1]);
    await waitFor(() => expect(screen.queryByText('avoid model-release marketing')).toBeNull());
  });

  it('shows the export download button', () => {
    renderPage(<SettingsPage />);
    expect(screen.getByText('Download archive')).toBeTruthy();
  });

  it('calls downloadUserExport and shows success message', async () => {
    apiMock.downloadUserExport.mockResolvedValue(undefined);
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Download archive'));
    await waitFor(() => expect(screen.getByText('Archive downloaded.')).toBeTruthy());
    expect(apiMock.downloadUserExport).toHaveBeenCalledOnce();
  });

  it('shows an error message when export fails', async () => {
    apiMock.downloadUserExport.mockRejectedValue(new Error('network error'));
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Download archive'));
    await waitFor(() => expect(screen.getByText('network error')).toBeTruthy());
  });

  it('shows the restore archive button', () => {
    renderPage(<SettingsPage />);
    expect(screen.getByText('Restore archive')).toBeTruthy();
  });

  it('restores an archive and shows the per-section counts', async () => {
    apiMock.importUserArchive.mockResolvedValue({
      articles: { added: 2, updated: 1, skipped: 0 },
      briefings: { added: 1, updated: 0, skipped: 0 },
      ai_memories: { added: 0, updated: 1, skipped: 0 },
      ai_memory_events: { added: 3, skipped: 0 },
    });
    renderPage(<SettingsPage />);

    const file = new File(['{"schema_version":2}'], 'archive.json', {
      type: 'application/json',
    });
    fireEvent.change(screen.getByLabelText('Restore archive'), { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText(/Articles: 2 added/)).toBeTruthy());
    expect(apiMock.importUserArchive).toHaveBeenCalledWith(file);
  });

  it('shows an error message when archive import fails', async () => {
    apiMock.importUserArchive.mockRejectedValue(new Error('unsupported schema_version'));
    renderPage(<SettingsPage />);

    const file = new File(['not json'], 'archive.json', { type: 'application/json' });
    fireEvent.change(screen.getByLabelText('Restore archive'), { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText('unsupported schema_version')).toBeTruthy());
  });

  it('requires typing the exact username before deletion is enabled', () => {
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Delete my account'));
    const button = screen.getByRole<HTMLButtonElement>('button', {
      name: /Permanently delete account/,
    });
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'wrong' } });
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'testuser' } });
    expect(button.disabled).toBe(false);
  });

  it('deletes the account and clears the session on confirmation', async () => {
    apiMock.deleteOwnAccount.mockResolvedValue(undefined);
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'testuser' } });
    fireEvent.click(screen.getByText('Permanently delete account'));
    await waitFor(() => expect(apiMock.deleteOwnAccount).toHaveBeenCalledWith('testuser'));
    expect(authMock.setUser).toHaveBeenCalledWith(null);
  });

  it('shows an error message when account deletion fails', async () => {
    apiMock.deleteOwnAccount.mockRejectedValue(new Error('cannot delete last admin'));
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'testuser' } });
    fireEvent.click(screen.getByText('Permanently delete account'));
    await waitFor(() => expect(screen.getByText('cannot delete last admin')).toBeTruthy());
  });

  it('cancels the delete confirmation flow', () => {
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'testuser' } });
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByLabelText(/Type/)).toBeNull();
    expect(screen.getByText('Delete my account')).toBeTruthy();
  });
});

// ── FeedsRunsPage ────────────────────────────────────────────────────────────

describe('FeedsRunsPage', () => {
  function run(overrides = {}) {
    return {
      id: 1,
      started_at: '2026-06-01T00:00:00Z',
      duration_ms: 1500,
      sources_run: 4,
      total_new: 7,
      total_errors: 0,
      ...overrides,
    };
  }

  it('shows the empty state when there are no runs', async () => {
    apiMock.fetchIngestRuns.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      has_more: false,
    });
    renderPage(<FeedsRunsPage />);
    await waitFor(() => expect(screen.getByText('No ingest runs recorded yet.')).toBeTruthy());
  });

  it('renders a run row and highlights errors', async () => {
    apiMock.fetchIngestRuns.mockResolvedValue({
      items: [run({ total_errors: 2 })],
      total: 1,
      page: 1,
      has_more: false,
    });
    renderPage(<FeedsRunsPage />);
    await waitFor(() => expect(screen.getByText('7')).toBeTruthy());
    expect(screen.getByText('2')).toBeTruthy(); // error count
    expect(screen.getByText('1–1 of 1')).toBeTruthy();
  });

  it('expands a run to load the per-source breakdown', async () => {
    apiMock.fetchIngestRuns.mockResolvedValue({
      items: [run()],
      total: 1,
      page: 1,
      has_more: false,
    });
    apiMock.fetchIngestRunSources.mockResolvedValue([
      {
        id: 11,
        source_name: 'Acme Feed',
        articles_found: 9,
        articles_new: 3,
        duplicates: 6,
        error_message: null,
        duration_ms: 800,
      },
    ]);
    renderPage(<FeedsRunsPage />);
    const toggle = await screen.findByRole('button', { name: /Expand run 1/ });
    fireEvent.click(toggle);
    await waitFor(() => expect(screen.getByText('Acme Feed')).toBeTruthy());
    expect(screen.getByText('800ms')).toBeTruthy();
    expect(apiMock.fetchIngestRunSources).toHaveBeenCalledWith(1);
  });

  it('surfaces an error when run loading fails', async () => {
    apiMock.fetchIngestRuns.mockRejectedValue(new Error('load failed'));
    renderPage(<FeedsRunsPage />);
    await waitFor(() => expect(screen.getByText('load failed')).toBeTruthy());
  });
});
