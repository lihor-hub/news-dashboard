// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { ListenQueueProvider, useListenQueue } from '../contexts/listenQueue';
import * as api from '../api';
import * as workflowApi from '../api/workflowApi';
import type { WorkflowArticle } from '../lib/workflowTypes';

type Listener = (...args: unknown[]) => void;

class FakeAudio {
  src = '';
  currentTime = 0;
  duration = 0;
  paused = true;
  listeners = new Map<string, Set<Listener>>();

  addEventListener(event: string, cb: Listener) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event)!.add(cb);
  }

  removeEventListener(event: string, cb: Listener) {
    this.listeners.get(event)?.delete(cb);
  }

  dispatch(event: string) {
    this.listeners.get(event)?.forEach((cb) => cb());
  }

  play() {
    this.paused = false;
    this.dispatch('play');
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
    this.dispatch('pause');
  }

  removeAttribute() {
    this.src = '';
  }
}

let lastAudio: FakeAudio;

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '1',
    title: 'An article',
    sourceId: 'source',
    sourceName: 'Source',
    category: 'ai-llm',
    url: 'https://example.com/a',
    publishedAt: '2026-06-16T10:00:00Z',
    ingestedAt: '2026-06-16T11:00:00Z',
    reason: 'why',
    summary: 'summary',
    signal: 'high',
    tags: [],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  return <ListenQueueProvider>{children}</ListenQueueProvider>;
}

beforeEach(() => {
  vi.stubGlobal(
    'Audio',
    vi.fn().mockImplementation(function AudioMock() {
      lastAudio = new FakeAudio();
      return lastAudio;
    })
  );
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:fake'),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(api, 'fetchArticleAudioUrl').mockImplementation((id) =>
    Promise.resolve(`blob:fake-${id}`)
  );
  vi.spyOn(workflowApi, 'patchArticleState').mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ListenQueueProvider', () => {
  it('builds a queue from a feed and starts playback on the first item', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [
      makeArticle({ id: '1', title: 'First' }),
      makeArticle({ id: '2', title: 'Second' }),
    ];

    act(() => {
      result.current.start(articles);
    });

    await waitFor(() => expect(result.current.current?.id).toBe('1'));
    expect(result.current.queue).toHaveLength(2);
    await waitFor(() => expect(result.current.isPlaying).toBe(true));
    expect(lastAudio.src).toBe('blob:fake-1');
  });

  it('auto-advances to the next article when the current one ends', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' }), makeArticle({ id: '2' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      lastAudio.dispatch('ended');
    });

    await waitFor(() => expect(result.current.current?.id).toBe('2'));
    expect(result.current.currentIndex).toBe(1);
  });

  it('stops the queue when the last article ends', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      lastAudio.dispatch('ended');
    });

    await waitFor(() => expect(result.current.current).toBeNull());
  });

  it('marks the article done on finish when markDoneOnFinish is enabled', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' }), makeArticle({ id: '2' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      lastAudio.dispatch('ended');
    });

    await waitFor(() =>
      expect(workflowApi.patchArticleState).toHaveBeenCalledWith('1', 'done', false)
    );
  });

  it('skip forward and back move the active item', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' }), makeArticle({ id: '2' }), makeArticle({ id: '3' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      result.current.next();
    });
    await waitFor(() => expect(result.current.current?.id).toBe('2'));

    act(() => {
      result.current.prev();
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));
  });

  it('seek updates currentTime on the underlying audio element', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      result.current.seek(42);
    });

    expect(lastAudio.currentTime).toBe(42);
    expect(result.current.currentTime).toBe(42);
  });

  it('stop clears the queue and playback state', async () => {
    const { result } = renderHook(() => useListenQueue(), { wrapper });
    const articles = [makeArticle({ id: '1' })];

    act(() => {
      result.current.start(articles);
    });
    await waitFor(() => expect(result.current.current?.id).toBe('1'));

    act(() => {
      result.current.stop();
    });

    expect(result.current.queue).toHaveLength(0);
    expect(result.current.current).toBeNull();
    expect(result.current.isPlaying).toBe(false);
  });
});
