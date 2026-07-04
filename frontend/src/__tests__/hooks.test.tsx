// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { useIsMobile } from '../hooks/use-mobile';
import { useTheme } from '../hooks/useTheme';
import { useArticleAudio } from '../hooks/useArticleAudio';
import * as api from '../api';

// ── matchMedia harness ──────────────────────────────────────────────────────
// happy-dom ships a minimal matchMedia; we replace it with a controllable mock
// so we can drive change events deterministically.

type Listener = () => void;

function installMatchMedia(matches: boolean) {
  const listeners = new Set<Listener>();
  const mql = {
    matches,
    media: '',
    addEventListener: (_: string, cb: Listener) => listeners.add(cb),
    removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
    dispatch: () => listeners.forEach((cb) => cb()),
  };
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mql)
  );
  return mql;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── useIsMobile ─────────────────────────────────────────────────────────────

describe('useIsMobile', () => {
  it('reports true below the mobile breakpoint', async () => {
    installMatchMedia(true);
    vi.stubGlobal('innerWidth', 500);
    const { result } = renderHook(() => useIsMobile());
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('reports false at desktop width', async () => {
    installMatchMedia(false);
    vi.stubGlobal('innerWidth', 1200);
    const { result } = renderHook(() => useIsMobile());
    await waitFor(() => expect(result.current).toBe(false));
  });

  it('re-evaluates when the media query fires a change', async () => {
    const mql = installMatchMedia(false);
    vi.stubGlobal('innerWidth', 1200);
    const { result } = renderHook(() => useIsMobile());
    await waitFor(() => expect(result.current).toBe(false));

    vi.stubGlobal('innerWidth', 400);
    act(() => mql.dispatch());
    await waitFor(() => expect(result.current).toBe(true));
  });
});

// ── useTheme ────────────────────────────────────────────────────────────────

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('initialises from stored preference', () => {
    installMatchMedia(false);
    localStorage.setItem('theme', 'dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
  });

  it('setTheme persists and applies the new theme', () => {
    installMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme('light'));
    expect(result.current.theme).toBe('light');
    expect(localStorage.getItem('theme')).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('re-applies system theme when OS preference changes', () => {
    const mql = installMatchMedia(true);
    localStorage.setItem('theme', 'system');
    renderHook(() => useTheme());
    act(() => mql.dispatch());
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});

// ── useArticleAudio ─────────────────────────────────────────────────────────

describe('useArticleAudio', () => {
  function wrapper({ children }: { children: React.ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }

  it('starts in idle state', () => {
    const { result } = renderHook(() => useArticleAudio('42'), { wrapper });
    expect(result.current.audioState).toBe('idle');
  });

  it('revokes the object URL on unmount', async () => {
    vi.spyOn(api, 'fetchArticleAudioUrl').mockResolvedValue('blob:mock-url');
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.stubGlobal(
      'Audio',
      vi.fn(function MockAudio(this: { play: () => void; pause: () => void }) {
        this.play = vi.fn();
        this.pause = vi.fn();
      })
    );

    const { result, unmount } = renderHook(() => useArticleAudio('42'), { wrapper });
    act(() => result.current.handleListen());
    await waitFor(() => expect(result.current.audioState).toBe('playing'));

    unmount();
    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-url');
  });
});
