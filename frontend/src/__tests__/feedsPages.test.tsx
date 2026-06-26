// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import type { Source } from '../types';

// ── Shared API mock ──────────────────────────────────────────────────────────
// SourcesPage imports from '@/api', SchedulerPage from '../api'; both resolve to
// the same module, so one mock factory covers both import specifiers.
const apiMock = vi.hoisted(() => ({
  fetchSources: vi.fn(),
  updateSourceEnabled: vi.fn(),
  fetchSchedulerStatus: vi.fn(),
  setSchedulerInterval: vi.fn(),
  pauseScheduler: vi.fn(),
  resumeScheduler: vi.fn(),
  ingestNow: vi.fn(),
}));
vi.mock('@/api', () => apiMock);
vi.mock('../api', () => apiMock);
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(() => 'id'),
  }),
}));

import { FeedsPage } from '../pages/FeedsPage';
import { FeedsLogsPage } from '../pages/FeedsLogsPage';
import { SourcesPage } from '../pages/SourcesPage';
import { SchedulerPage } from '../pages/SchedulerPage';

function withProviders(ui: ReactElement, route = '/') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(ui, { wrapper });
}

function source(overrides: Partial<Source> = {}): Source {
  return {
    slug: 'acme',
    name: 'Acme News',
    url: 'https://acme.test',
    category: 'tech',
    kind: 'rss_feed',
    enabled: 1,
    priority: 1,
    last_checked_at: new Date().toISOString(),
    last_success_at: new Date().toISOString(),
    last_error: null,
    last_fetched_count: 10,
    last_inserted_count: 3,
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

// ── FeedsPage (pure layout) ──────────────────────────────────────────────────

describe('FeedsPage', () => {
  it('renders the tab navigation and child outlet', () => {
    withProviders(
      <Routes>
        <Route path="/feeds" element={<FeedsPage />}>
          <Route index element={<div>child content</div>} />
        </Route>
      </Routes>,
      '/feeds'
    );
    expect(screen.getByRole('heading', { name: 'Feeds' })).toBeTruthy();
    expect(screen.getByText('Sources')).toBeTruthy();
    expect(screen.getByText('Schedule')).toBeTruthy();
    expect(screen.getByText('child content')).toBeTruthy();
  });
});

// ── SourcesPage ──────────────────────────────────────────────────────────────

describe('SourcesPage', () => {
  it('shows a loading skeleton before data resolves', () => {
    apiMock.fetchSources.mockReturnValue(new Promise(vi.fn()));
    const { container } = withProviders(<SourcesPage />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders source rows with health badges', async () => {
    apiMock.fetchSources.mockResolvedValue([
      source({ slug: 'a', name: 'Healthy' }),
      source({ slug: 'b', name: 'Broken', last_error: 'boom' }),
      source({
        slug: 'c',
        name: 'Stale',
        last_error: null,
        last_success_at: null,
        last_checked_at: null,
      }),
    ]);
    withProviders(<SourcesPage />);
    expect(await screen.findAllByText('Healthy')).toHaveLength(2); // desktop + mobile
    expect(screen.getAllByText('error').length).toBeGreaterThan(0);
    expect(screen.getAllByText('stale').length).toBeGreaterThan(0);
  });

  it('toggles a source via the switch', async () => {
    apiMock.fetchSources.mockResolvedValue([source({ enabled: 1 })]);
    apiMock.updateSourceEnabled.mockResolvedValue(source({ enabled: 0 }));
    withProviders(<SourcesPage />);
    const toggles = await screen.findAllByRole('switch');
    fireEvent.click(toggles[0]);
    await waitFor(() => expect(apiMock.updateSourceEnabled).toHaveBeenCalledWith('acme', false));
  });
});

// ── SchedulerPage ────────────────────────────────────────────────────────────

describe('SchedulerPage', () => {
  const running = {
    interval_minutes: 30,
    paused: false,
    next_run_at: new Date(Date.now() + 60_000).toISOString(),
  };

  it('renders running status and interval', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    withProviders(<SchedulerPage />);
    expect(await screen.findByText('▶ Running')).toBeTruthy();
    expect(screen.getByText('30 minutes')).toBeTruthy();
  });

  it('sets an interval preset', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.setSchedulerInterval.mockResolvedValue({ interval_minutes: 60, next_run_at: null });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('1h'));
    await waitFor(() => expect(apiMock.setSchedulerInterval).toHaveBeenCalledWith(60));
  });

  it('pauses a running scheduler', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.pauseScheduler.mockResolvedValue({ paused: true });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('⏸ Pause'));
    await waitFor(() => expect(apiMock.pauseScheduler).toHaveBeenCalled());
  });

  it('shows external scheduler state without mutable interval controls', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue({
      ...running,
      interval_ingest_enabled: false,
      ingest_authority: 'external',
      next_run_at: null,
    });
    withProviders(<SchedulerPage />);

    expect(await screen.findByText('External schedule')).toBeTruthy();
    expect(screen.getByText('External CronJob')).toBeTruthy();
    fireEvent.click(screen.getByText('⏸ Pause'));
    fireEvent.click(screen.getByText('1h'));
    expect(apiMock.pauseScheduler).not.toHaveBeenCalled();
    expect(apiMock.setSchedulerInterval).not.toHaveBeenCalled();
  });

  it('resumes a paused scheduler', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue({ ...running, paused: true });
    apiMock.resumeScheduler.mockResolvedValue({ paused: false, next_run_at: null });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('▶ Resume'));
    await waitFor(() => expect(apiMock.resumeScheduler).toHaveBeenCalled());
  });

  it('triggers an on-demand ingest', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.ingestNow.mockResolvedValue({ inserted: 2, results: {} });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('↻ Fetch now'));
    await waitFor(() => expect(apiMock.ingestNow).toHaveBeenCalled());
  });

  it('saves a valid custom interval and rejects an invalid one', async () => {
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.setSchedulerInterval.mockResolvedValue({ interval_minutes: 45, next_run_at: null });
    withProviders(<SchedulerPage />);
    const input = await screen.findByLabelText('Custom interval in minutes');

    // invalid → no API call
    fireEvent.change(input, { target: { value: '0' } });
    fireEvent.click(screen.getByText('Save'));
    expect(apiMock.setSchedulerInterval).not.toHaveBeenCalled();

    // valid → API call
    fireEvent.change(input, { target: { value: '45' } });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(apiMock.setSchedulerInterval).toHaveBeenCalledWith(45));
  });
});

// ── FeedsLogsPage (SSE) ──────────────────────────────────────────────────────

describe('FeedsLogsPage', () => {
  type Handler = (e: unknown) => void;

  const holder: { current: FakeEventSource } = { current: null as never };

  class FakeEventSource {
    handlers: Record<string, Handler> = {};
    onopen: Handler | null = null;
    onerror: Handler | null = null;
    close = vi.fn();
    addEventListener = (type: string, cb: Handler) => {
      this.handlers[type] = cb;
    };
    constructor() {
      holder.current = this;
    }
  }

  beforeEach(() => {
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('shows live status and appends streamed lines', async () => {
    render(<FeedsLogsPage />);
    expect(screen.getByText('Connecting…')).toBeTruthy();

    holder.current.onopen?.(null);
    await waitFor(() => expect(screen.getByText('Live')).toBeTruthy());

    holder.current.handlers.line?.({ data: 'hello' });
    await waitFor(() => expect(screen.getByText(/hello/)).toBeTruthy());

    holder.current.handlers.reset?.(null);
    await waitFor(() => expect(screen.getByText('Waiting for ingest output…')).toBeTruthy());

    holder.current.onerror?.(null);
    await waitFor(() => expect(screen.getByText('Connecting…')).toBeTruthy());
  });
});
