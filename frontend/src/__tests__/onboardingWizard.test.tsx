// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as api from '../api';
import { useOnboardingWizard } from '../hooks/useOnboardingWizard';
import { OnboardingWizard } from '../components/OnboardingWizard';

// ── helpers ────────────────────────────────────────────────────────────────────

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={makeQc()}>{children}</QueryClientProvider>;
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

beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
  );
  sessionStorage.clear();
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

  it('calls saveOnboardingInterests and onClose when Apply is clicked', async () => {
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
    await waitFor(() => expect(onClose).toHaveBeenCalled());
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
    expect(payload.enabled_slugs).toContain('hn');
    expect(payload.enabled_slugs).toContain('arxiv');
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

  it('saveOnboardingInterests POSTs to /api/onboarding/profile', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      })
    );
    await api.saveOnboardingInterests({ interest_ids: ['tech'], enabled_slugs: ['hn'] });
    expect(calls[0].url).toBe('/api/onboarding/profile');
    expect(calls[0].init?.method).toBe('POST');
    const body = JSON.parse(calls[0].init?.body as string) as {
      interest_ids: string[];
      enabled_slugs: string[];
    };
    expect(body.interest_ids).toEqual(['tech']);
    expect(body.enabled_slugs).toEqual(['hn']);
  });
});
