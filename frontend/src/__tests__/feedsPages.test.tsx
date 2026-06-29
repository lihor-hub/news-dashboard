// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactElement, type ReactNode } from 'react';
import type { Source, User } from '../types';
import { AuthProvider, useAuth } from '../contexts/auth';

// ── Shared API mock ──────────────────────────────────────────────────────────
// SourcesPage imports from '@/api', SchedulerPage from '../api'; both resolve to
// the same module, so one mock factory covers both import specifiers.
const apiMock = vi.hoisted(() => ({
  fetchSources: vi.fn(),
  fetchSourceCleanupSuggestions: vi.fn(),
  updateSourceEnabled: vi.fn(),
  applySourceCleanup: vi.fn(),
  createSource: vi.fn(),
  deleteSource: vi.fn(),
  fetchSchedulerStatus: vi.fn(),
  setSchedulerInterval: vi.fn(),
  pauseScheduler: vi.fn(),
  resumeScheduler: vi.fn(),
  ingestNow: vi.fn(),
  fetchOnboardingInterests: vi.fn().mockResolvedValue([]),
  fetchOnboardingSourceRecommendations: vi.fn().mockResolvedValue([]),
  fetchOnboardingStatus: vi.fn().mockResolvedValue({ completed: true }),
  saveOnboardingInterests: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('@/api', () => apiMock);
vi.mock('../api', () => apiMock);
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(() => 'id'),
  }),
}));

import { FeedsPage } from '../pages/FeedsPage';
import { FeedsLogsPage } from '../pages/FeedsLogsPage';
import { SourcesPage } from '../pages/SourcesPage';
import { SchedulerPage } from '../pages/SchedulerPage';

function SetUser({ user, children }: { user: User | null; children: ReactNode }) {
  const { setUser } = useAuth();
  useEffect(() => setUser(user), [user, setUser]);
  return <>{children}</>;
}

function withProviders(ui: ReactElement, route = '/', user: User | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <SetUser user={user}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </SetUser>
      </AuthProvider>
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

const adminUser: User = { id: 1, username: 'admin', is_admin: true };
const regularUser: User = { id: 2, username: 'user', is_admin: false };

// ── FeedsPage (pure layout) ──────────────────────────────────────────────────

describe('FeedsPage', () => {
  it('renders the tab navigation and child outlet', () => {
    withProviders(
      <Routes>
        <Route path="/feeds" element={<FeedsPage />}>
          <Route index element={<div>child content</div>} />
        </Route>
      </Routes>,
      '/feeds',
      adminUser
    );
    expect(screen.getByRole('heading', { name: 'Feeds' })).toBeTruthy();
    expect(screen.getByText('Sources')).toBeTruthy();
    expect(screen.getByText('Schedule')).toBeTruthy();
    expect(screen.getByText('child content')).toBeTruthy();
  });

  it('shows all tabs to admin users', () => {
    withProviders(
      <Routes>
        <Route path="/feeds" element={<FeedsPage />}>
          <Route index element={<div>child content</div>} />
        </Route>
      </Routes>,
      '/feeds',
      adminUser
    );
    expect(screen.getByText('Sources')).toBeTruthy();
    expect(screen.getByText('Schedule')).toBeTruthy();
    expect(screen.getByText('Runs')).toBeTruthy();
    expect(screen.getByText('Logs')).toBeTruthy();
  });

  it('hides Schedule, Runs, and Logs tabs from non-admin users', () => {
    withProviders(
      <Routes>
        <Route path="/feeds" element={<FeedsPage />}>
          <Route index element={<div>child content</div>} />
        </Route>
      </Routes>,
      '/feeds',
      regularUser
    );
    expect(screen.getByText('Sources')).toBeTruthy();
    expect(screen.queryByText('Schedule')).toBeNull();
    expect(screen.queryByText('Runs')).toBeNull();
    expect(screen.queryByText('Logs')).toBeNull();
  });
});

// ── SourcesPage ──────────────────────────────────────────────────────────────

describe('SourcesPage', () => {
  beforeEach(() => {
    apiMock.fetchSourceCleanupSuggestions.mockResolvedValue([]);
  });

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

  it('opens the Add source dialog when "Add source" is clicked', async () => {
    apiMock.fetchSources.mockResolvedValue([source()]);
    withProviders(<SourcesPage />, '/', regularUser);
    await screen.findAllByText('Acme News');
    fireEvent.click(screen.getByRole('button', { name: /add source/i }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(screen.getByLabelText(/name/i)).toBeTruthy();
    expect(screen.getByLabelText(/feed url/i)).toBeTruthy();
  });

  it('calls createSource with form data and closes dialog on success', async () => {
    const newSource = source({ slug: 'my-blog', name: 'My Blog', owner_user_id: 2 });
    apiMock.fetchSources.mockResolvedValue([source()]);
    apiMock.createSource.mockResolvedValue(newSource);
    withProviders(<SourcesPage />, '/', regularUser);
    await screen.findAllByText('Acme News');

    fireEvent.click(screen.getByRole('button', { name: /add source/i }));
    await screen.findByRole('dialog');

    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: 'My Blog' } });
    fireEvent.change(screen.getByLabelText(/feed url/i), {
      target: { value: 'https://myblog.com/feed' },
    });

    // Re-mock to include the new source after creation
    apiMock.fetchSources.mockResolvedValue([source(), newSource]);
    fireEvent.click(screen.getByRole('button', { name: /^add source$/i }));

    await waitFor(() =>
      expect(apiMock.createSource).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'My Blog', url: 'https://myblog.com/feed' })
      )
    );
  });

  it('shows error message when createSource fails', async () => {
    apiMock.fetchSources.mockResolvedValue([source()]);
    apiMock.createSource.mockRejectedValue(new Error('slug already exists'));
    withProviders(<SourcesPage />, '/', regularUser);
    await screen.findAllByText('Acme News');

    fireEvent.click(screen.getByRole('button', { name: /add source/i }));
    await screen.findByRole('dialog');

    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: 'My Blog' } });
    fireEvent.change(screen.getByLabelText(/feed url/i), {
      target: { value: 'https://myblog.com/feed' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^add source$/i }));

    await waitFor(() => expect(screen.getByText('slug already exists')).toBeTruthy());
  });

  it('shows delete button for sources owned by current user', async () => {
    apiMock.fetchSources.mockResolvedValue([
      source({ slug: 'global', name: 'Global News', owner_user_id: null }),
      source({ slug: 'mine', name: 'My Blog', owner_user_id: regularUser.id }),
    ]);
    withProviders(<SourcesPage />, '/', regularUser);
    await screen.findAllByText('Global News');

    const deleteButtons = screen.getAllByRole('button', { name: /delete my blog/i });
    expect(deleteButtons.length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /delete global news/i })).toBeNull();
  });

  it('calls deleteSource when delete button is clicked', async () => {
    apiMock.fetchSources.mockResolvedValue([
      source({ slug: 'mine', name: 'My Blog', owner_user_id: regularUser.id }),
    ]);
    apiMock.deleteSource.mockResolvedValue({ status: 'deleted' });
    withProviders(<SourcesPage />, '/', regularUser);
    await screen.findAllByText('My Blog');

    const [deleteBtn] = screen.getAllByRole('button', { name: /delete my blog/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => expect(apiMock.deleteSource).toHaveBeenCalledWith('mine'));
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
    apiMock.ingestNow.mockResolvedValue({
      inserted: 2,
      results: {},
      run_id: 1,
      total_errors: 0,
      failed_sources: [],
    });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('↻ Fetch now'));
    await waitFor(() => expect(apiMock.ingestNow).toHaveBeenCalled());
  });

  it('shows success toast when all sources succeed', async () => {
    const { toast } = await import('sonner');
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.ingestNow.mockResolvedValue({
      inserted: 3,
      results: { feed: 3 },
      run_id: 1,
      total_errors: 0,
      failed_sources: [],
    });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('↻ Fetch now'));
    await waitFor(() =>
      expect(
        (toast as unknown as { success: ReturnType<typeof vi.fn> }).success
      ).toHaveBeenCalledWith(expect.stringContaining('3 new articles'), expect.anything())
    );
  });

  it('shows warning toast when some sources fail', async () => {
    const { toast } = await import('sonner');
    apiMock.fetchSchedulerStatus.mockResolvedValue(running);
    apiMock.ingestNow.mockResolvedValue({
      inserted: 2,
      results: { ok: 2, bad: -1 },
      run_id: 42,
      total_errors: 1,
      failed_sources: ['bad'],
    });
    withProviders(<SchedulerPage />);
    fireEvent.click(await screen.findByText('↻ Fetch now'));
    await waitFor(() =>
      expect(
        (toast as unknown as { warning: ReturnType<typeof vi.fn> }).warning
      ).toHaveBeenCalledWith(expect.stringContaining('1 source failed'), expect.anything())
    );
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
