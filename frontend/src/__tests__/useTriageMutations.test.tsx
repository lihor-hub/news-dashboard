// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { toast } from 'sonner';
import type { WorkflowArticle } from '../lib/workflowTypes';
import * as workflowApi from '../api/workflowApi';
import { useTriageMutations, ARTICLES_KEY } from '../hooks/useTriageMutations';

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  }),
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

  it('setState blocks skipping a starred article', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTriageMutations(), { wrapper });
    const article = makeArticle({ starred: true });

    act(() => {
      result.current.setState(article, 'skipped', 'Skipped');
    });

    expect(vi.mocked(toast).error).toHaveBeenCalledWith("Starred articles can't be skipped");
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
