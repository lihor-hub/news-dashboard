// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { toast } from 'sonner';
import type { WorkflowArticle } from '../lib/workflowTypes';
import * as workflowApi from '../api/workflowApi';
import { useTriageMutations, ARTICLES_KEY } from '../hooks/useTriageMutations';
import { trackFeature } from '../lib/analytics';

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

vi.mock('../lib/analytics', () => ({
  trackFeature: vi.fn(),
}));

let patchArticleStatePromise: Promise<unknown> = Promise.resolve({});

vi.mock('../api/workflowApi', async (importOriginal) => {
  const actual = await importOriginal<typeof workflowApi>();
  return {
    ...actual,
    patchArticleState: vi.fn(() => patchArticleStatePromise),
    patchArticleStar: vi.fn().mockResolvedValue({}),
    patchArticleLater: vi.fn().mockResolvedValue({}),
  };
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '42',
    title: 'Test article',
    sourceId: 'test-source',
    sourceName: 'Test Source',
    category: 'ai',
    url: 'https://example.com/42',
    publishedAt: '2024-01-01T10:00:00Z',
    ingestedAt: '2024-01-01T11:00:00Z',
    reason: 'Relevant',
    summary: 'A summary',
    signal: 'high',
    tags: [],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const article = makeArticle();
  queryClient.setQueryData([ARTICLES_KEY, { state: 'today' }], [article]);
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper: Wrapper, queryClient };
}

interface ToastAction {
  label: string;
  onClick: () => void;
}
interface ToastOpts {
  id?: string;
  action?: ToastAction;
}

/** Extract the Undo onClick from the last toast call. */
function capturedUndo(): () => void {
  const mockFn = vi.mocked(toast);
  const lastArgs = mockFn.mock.lastCall as unknown as [string, ToastOpts?] | undefined;
  if (!lastArgs?.[1]?.action?.onClick) throw new Error('No undo handler in last toast call');
  return lastArgs[1].action.onClick;
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useTriageMutations — undo calls the API to revert server state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    patchArticleStatePromise = Promise.resolve({});
  });

  it('setState undo calls patchArticleState with original state', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today', starred: false });

    act(() => {
      result.current.setState(article, 'done', 'Marked as read');
    });

    act(() => {
      capturedUndo()();
    });

    expect(workflowApi.patchArticleState).toHaveBeenCalledWith('42', 'today', false);
  });

  it('setState undo passes original starred flag', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today', starred: true });

    act(() => {
      result.current.setState(article, 'done', 'Marked as read');
    });

    act(() => {
      capturedUndo()();
    });

    expect(workflowApi.patchArticleState).toHaveBeenCalledWith('42', 'today', true);
  });

  it('toggleStar undo calls patchArticleStar with original starred value', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ starred: false });

    act(() => {
      result.current.toggleStar(article);
    });

    act(() => {
      capturedUndo()();
    });

    expect(workflowApi.patchArticleStar).toHaveBeenCalledWith('42', false);
  });

  it('emits feature events for triage actions so the analytics panel is populated', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });

    act(() => {
      result.current.setState(makeArticle(), 'done', 'Marked as read');
    });
    expect(trackFeature).toHaveBeenCalledWith('triage_done');

    act(() => {
      result.current.toggleStar(makeArticle({ starred: false }));
    });
    expect(trackFeature).toHaveBeenCalledWith('star');

    act(() => {
      result.current.sendLater(makeArticle(), 1);
    });
    expect(trackFeature).toHaveBeenCalledWith('snooze');
  });

  it('sendLater undo calls patchArticleState with original state', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today', starred: false });

    act(() => {
      result.current.sendLater(article, 1);
    });

    act(() => {
      capturedUndo()();
    });

    expect(workflowApi.patchArticleState).toHaveBeenCalledWith('42', 'today', false);
  });

  it('setState shows toast with Undo action label', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle();

    act(() => {
      result.current.setState(article, 'skipped', 'Skipped');
    });

    const lastArgs = vi.mocked(toast).mock.lastCall as unknown as [string, ToastOpts?] | undefined;
    expect(lastArgs?.[0]).toBe('Skipped');
    expect(lastArgs?.[1]?.action?.label).toBe('Undo');
  });

  it('every action toast carries the shared triage id so rapid actions replace the previous toast', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle();

    // Three rapid actions in sequence — each should carry the same id.
    act(() => {
      result.current.setState(article, 'done', 'Marked as read');
    });
    const afterDone = vi.mocked(toast).mock.lastCall as unknown as [string, ToastOpts?] | undefined;
    expect(afterDone?.[1]?.id).toBe('triage');

    act(() => {
      result.current.toggleStar(article);
    });
    const afterStar = vi.mocked(toast).mock.lastCall as unknown as [string, ToastOpts?] | undefined;
    expect(afterStar?.[1]?.id).toBe('triage');

    act(() => {
      result.current.sendLater(article, 1);
    });
    const afterLater = vi.mocked(toast).mock.lastCall as unknown as
      | [string, ToastOpts?]
      | undefined;
    expect(afterLater?.[1]?.id).toBe('triage');
  });

  it('setState blocks skipping a starred article', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ starred: true });

    act(() => {
      result.current.setState(article, 'skipped', 'Skipped');
    });

    expect(vi.mocked(toast).error).toHaveBeenCalledWith("Starred articles can't be skipped", {
      id: 'triage',
    });
    expect(workflowApi.patchArticleState).not.toHaveBeenCalled();
  });

  it('removes moved articles from state-filtered query caches before the API resolves', () => {
    patchArticleStatePromise = new Promise((resolve) => {
      void resolve;
    });
    const { wrapper, queryClient } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today' });
    queryClient.setQueryData([ARTICLES_KEY, 'today'], [article]);

    act(() => {
      result.current.setState(article, 'done', 'Marked as read');
    });

    expect(queryClient.getQueryData([ARTICLES_KEY, 'today'])).toEqual([]);
  });
});

describe('useTriageMutations — surfaces backend error details in error toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    patchArticleStatePromise = Promise.resolve({});
  });

  it('setState shows backend error detail and reverted message on API failure', async () => {
    patchArticleStatePromise = Promise.reject(
      new Error("transition 'later' → 'skipped' is not allowed")
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'later', starred: false });

    await act(async () => {
      result.current.setState(article, 'skipped', 'Skipped');
      await patchArticleStatePromise.catch(() => undefined);
    });

    await waitFor(() => {
      expect(vi.mocked(toast).error).toHaveBeenCalledWith(
        "Action failed — transition 'later' → 'skipped' is not allowed. Changes reverted.",
        { id: 'triage' }
      );
    });
  });

  it('setState falls back to generic message when error has no detail', async () => {
    patchArticleStatePromise = Promise.reject(new Error(''));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today', starred: false });

    await act(async () => {
      result.current.setState(article, 'done', 'Marked as read');
      await patchArticleStatePromise.catch(() => undefined);
    });

    await waitFor(() => {
      expect(vi.mocked(toast).error).toHaveBeenCalledWith('Action failed — changes reverted', {
        id: 'triage',
      });
    });
  });

  it('setState restores cache after error with backend detail message', async () => {
    patchArticleStatePromise = Promise.reject(new Error('some backend error'));
    const { wrapper, queryClient } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today' });
    queryClient.setQueryData([ARTICLES_KEY, 'today'], [article]);

    await act(async () => {
      result.current.setState(article, 'done', 'Marked as read');
      await patchArticleStatePromise.catch(() => undefined);
    });

    await waitFor(() => {
      const cached = queryClient.getQueryData<WorkflowArticle[]>([ARTICLES_KEY, 'today']);
      expect(cached?.some((a) => a.id === article.id)).toBe(true);
    });
  });

  it('starMutation surfaces backend error detail', async () => {
    vi.mocked(workflowApi.patchArticleStar).mockRejectedValueOnce(
      new Error('star update rejected by server')
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ starred: false });

    await act(async () => {
      result.current.toggleStar(article);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(vi.mocked(toast).error).toHaveBeenCalledWith(
        'Action failed — star update rejected by server. Changes reverted.',
        { id: 'triage' }
      );
    });
  });

  it('sendLaterMutation surfaces backend error detail', async () => {
    vi.mocked(workflowApi.patchArticleLater).mockRejectedValueOnce(
      new Error('snooze window not allowed')
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today' });

    await act(async () => {
      result.current.sendLater(article, 1);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(vi.mocked(toast).error).toHaveBeenCalledWith(
        'Action failed — snooze window not allowed. Changes reverted.',
        { id: 'triage' }
      );
    });
  });
});

describe('useTriageMutations — settles caches without a full article refetch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    patchArticleStatePromise = Promise.resolve({});
  });

  it('marks article lists stale without refetching and refreshes summary counts', async () => {
    const { wrapper, queryClient } = makeWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ state: 'today' });

    await act(async () => {
      result.current.setState(article, 'done', 'Marked as read');
      await patchArticleStatePromise;
    });

    // Article lists are marked stale but NOT refetched (refetchType: 'none'),
    // so a triage click never triggers a full list round-trip to the backend.
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: [ARTICLES_KEY],
        refetchType: 'none',
      });
    });
    // Summary counts aren't derivable from the cache, so they still refetch.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['summary'] });
    // No invalidation ever forces an immediate article-list refetch.
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: [ARTICLES_KEY] });
  });
});
