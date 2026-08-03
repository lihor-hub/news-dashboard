// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation } from 'react-router';
import * as api from '../api';
import * as analytics from '../lib/analytics';
import i18n from '../lib/i18n';
import { useOnboardingWizard } from '../hooks/useOnboardingWizard';
import { OnboardingWizard } from '../components/OnboardingWizard';

// ── helpers ────────────────────────────────────────────────────────────────────

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  return <output aria-label="current route">{useLocation().pathname}</output>;
}

const MOCK_INTERESTS = [
  { id: 'tech', label: 'Technology', description: 'Software and hardware news' },
  { id: 'science', label: 'Science', description: 'Research and discoveries' },
  { id: 'finance', label: 'Finance', description: 'Markets and economics' },
];

const MOCK_RECOMMENDATIONS = [
  {
    slug: 'hn',
    name: 'Hacker News',
    category: 'tech',
    kind: 'rss_feed',
    url: 'https://news.ycombinator.com/rss',
    matched_interests: ['tech'],
    reason: 'Top source for tech discussion',
    recommended: true,
    enabled: 0,
    priority: 1,
  },
  {
    slug: 'arxiv',
    name: 'arXiv',
    category: 'science',
    kind: 'rss_feed',
    url: 'https://arxiv.org/rss',
    matched_interests: ['science'],
    reason: 'Primary preprint server for research',
    recommended: true,
    enabled: 0,
    priority: 1,
  },
];

beforeEach(async () => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
  );
  sessionStorage.clear();
  await i18n.changeLanguage('en');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

// ── useOnboardingWizard ───────────────────────────────────────────────────────

describe('useOnboardingWizard', () => {
  it('opens when the backend indicates onboarding is not completed', async () => {
    vi.spyOn(api, 'fetchOnboardingStatus').mockResolvedValue({ completed: false });
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.open).toBe(true));
  });

  it('stays closed when onboarding is already completed', async () => {
    vi.spyOn(api, 'fetchOnboardingStatus').mockResolvedValue({ completed: true });
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.open).toBe(false);
  });

  it('stays closed when dismissed for current session (skip)', async () => {
    vi.spyOn(api, 'fetchOnboardingStatus').mockResolvedValue({ completed: false });
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.open).toBe(true));
    act(() => result.current.skip());
    expect(result.current.open).toBe(false);
    expect(sessionStorage.getItem('onboarding-skipped')).toBe('1');
  });

  it('stays closed for the session after skip even if backend says incomplete', async () => {
    sessionStorage.setItem('onboarding-skipped', '1');
    vi.spyOn(api, 'fetchOnboardingStatus').mockResolvedValue({ completed: false });
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.open).toBe(false);
  });

  it('stays closed on fetch error (non-critical)', async () => {
    vi.spyOn(api, 'fetchOnboardingStatus').mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.open).toBe(false);
  });

  it('exposes openWizard to manually trigger the wizard', async () => {
    vi.spyOn(api, 'fetchOnboardingStatus').mockResolvedValue({ completed: true });
    const { result } = renderHook(() => useOnboardingWizard(), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.open).toBe(false);
    act(() => result.current.openWizard());
    expect(result.current.open).toBe(true);
  });
});

// ── OnboardingWizard component ────────────────────────────────────────────────

describe('OnboardingWizard', () => {
  function makeProps(overrides?: Partial<Parameters<typeof OnboardingWizard>[0]>) {
    return {
      open: true,
      onClose: vi.fn(),
      ...overrides,
    };
  }

  it('renders step 1 interest selection when open', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    expect(screen.getByText('Science')).toBeTruthy();
    expect(screen.getByText('Finance')).toBeTruthy();
  });

  it('does not render when open is false', () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ open: false })} />
      </Wrapper>
    );
    expect(screen.queryByText('Technology')).toBeNull();
  });

  it('calls onClose (without saving) when Skip for now is clicked', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    const saveInterests = vi.spyOn(api, 'saveOnboardingInterests');
    const onClose = vi.fn();
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /skip for now/i }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(saveInterests).not.toHaveBeenCalled();
  });

  it('moves to step 2 (recommendations) when Next is clicked with selected interests', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    // Select the "Technology" interest
    fireEvent.click(screen.getByText('Technology'));
    // Click Next
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    expect(screen.getByText('Top source for tech discussion')).toBeTruthy();
  });

  it('shows recommendation reasons on step 2', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Top source for tech discussion')).toBeTruthy());
  });

  it('saves preferences and advances to the AI research workflow when Apply is clicked', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    const save = vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    // Click Apply
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(
      await screen.findByRole('heading', { name: /your ai research desk is ready/i })
    ).toBeTruthy();
    expect(screen.getByText(/your ai research desk for technical news/i)).toBeTruthy();
    expect(screen.getByText('Find what matters')).toBeTruthy();
    expect(screen.getByText('Understand why')).toBeTruthy();
    expect(screen.getByText('Remember it')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('tracks the workflow impression without invoking an AI endpoint', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const createBriefing = vi.spyOn(api, 'createBriefing');
    const trackFeature = vi.spyOn(analytics, 'trackFeature');

    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByText('Find what matters')).toBeTruthy();
    expect(trackFeature).toHaveBeenCalledWith('onboarding_ai_workflow_impression');
    expect(createBriefing).not.toHaveBeenCalled();
  });

  it.each([
    ['Explore Today', '/today', 'onboarding_ai_workflow_today'],
    ['Open your first briefing', '/brief', 'onboarding_ai_workflow_brief'],
  ])('navigates with the %s action and tracks it', async (label, route, event) => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const createBriefing = vi.spyOn(api, 'createBriefing');
    const trackFeature = vi.spyOn(analytics, 'trackFeature');
    const onClose = vi.fn();

    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
        <LocationProbe />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));
    await screen.findByText('Find what matters');
    fireEvent.click(screen.getByRole('button', { name: label }));

    expect(screen.getByLabelText('current route').textContent).toBe(route);
    expect(trackFeature).toHaveBeenCalledWith(event);
    expect(createBriefing).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('explains AI configuration and keeps a non-AI path available', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);

    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByText(/openai-compatible configuration/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Explore Today' })).toBeTruthy();
  });

  it('does not call save on Apply when no interests are selected', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue([]);
    const save = vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    // Don't select any interest, still click next (button may be disabled, let's check)
    const nextBtn = screen.getByRole('button', { name: /next/i });
    expect(nextBtn.hasAttribute('disabled')).toBe(true);
    expect(save).not.toHaveBeenCalled();
  });

  it('shows loading skeleton while interests are fetching', () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockReturnValue(new Promise(() => undefined));
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps()} />
      </Wrapper>
    );
    // Loading state should be visible
    expect(screen.getByTestId('onboarding-loading')).toBeTruthy();
  });

  it('preselects recommended sources after recommendation data loads on step 2', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    const save = vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    // Apply without manually selecting — recommended sources should already be selected
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));
    await waitFor(() => expect(save).toHaveBeenCalled());
    const payload = save.mock.calls[0][0];
    // Both recommended sources should be in the enabled list
    expect(payload.enabled_source_slugs).toContain('hn');
    expect(payload.enabled_source_slugs).toContain('arxiv');
    expect(payload.disabled_source_slugs).toEqual([]);
  });

  it('sends unselected recommendations as disabled_source_slugs on Apply', async () => {
    vi.spyOn(api, 'fetchOnboardingInterests').mockResolvedValue(MOCK_INTERESTS);
    vi.spyOn(api, 'fetchOnboardingSourceRecommendations').mockResolvedValue(MOCK_RECOMMENDATIONS);
    const save = vi.spyOn(api, 'saveOnboardingInterests').mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <Wrapper>
        <OnboardingWizard {...makeProps({ onClose })} />
      </Wrapper>
    );
    await waitFor(() => expect(screen.getByText('Technology')).toBeTruthy());
    fireEvent.click(screen.getByText('Technology'));
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('Hacker News')).toBeTruthy());
    // Deselect arXiv, leaving only Hacker News selected
    fireEvent.click(screen.getByText('arXiv'));
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));
    await waitFor(() => expect(save).toHaveBeenCalled());
    const payload = save.mock.calls[0][0];
    expect(payload.enabled_source_slugs).toEqual(['hn']);
    expect(payload.disabled_source_slugs).toEqual(['arxiv']);
  });
});

// ── API functions ─────────────────────────────────────────────────────────────

describe('onboarding API functions', () => {
  function stubFetch(body: unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) }))
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('fetchOnboardingStatus calls /api/onboarding/status', async () => {
    stubFetch({ completed: false });
    const result = await api.fetchOnboardingStatus();
    expect(result).toEqual({ completed: false });
  });

  it('fetchOnboardingInterests calls /api/onboarding/interests', async () => {
    stubFetch([{ id: 'tech', label: 'Technology', description: 'desc' }]);
    const result = await api.fetchOnboardingInterests();
    expect(result).toEqual([{ id: 'tech', label: 'Technology', description: 'desc' }]);
  });

  it('fetchOnboardingSourceRecommendations POSTs interests to /api/onboarding/recommendations', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(MOCK_RECOMMENDATIONS),
        });
      })
    );
    await api.fetchOnboardingSourceRecommendations(['tech', 'science']);
    expect(calls[0].url).toBe('/api/onboarding/recommendations');
    expect(calls[0].init?.method).toBe('POST');
    const body = JSON.parse(calls[0].init?.body as string) as { interest_ids: string[] };
    expect(body.interest_ids).toEqual(['tech', 'science']);
  });

  it('saveOnboardingInterests POSTs to /api/onboarding/interests', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      })
    );
    await api.saveOnboardingInterests({
      interests: ['tech'],
      enabled_source_slugs: ['hn'],
      disabled_source_slugs: ['arxiv'],
    });
    expect(calls[0].url).toBe('/api/onboarding/interests');
    expect(calls[0].init?.method).toBe('POST');
    const body = JSON.parse(calls[0].init?.body as string) as {
      interests: string[];
      enabled_source_slugs: string[];
      disabled_source_slugs: string[];
    };
    expect(body.interests).toEqual(['tech']);
    expect(body.enabled_source_slugs).toEqual(['hn']);
    expect(body.disabled_source_slugs).toEqual(['arxiv']);
  });
});
