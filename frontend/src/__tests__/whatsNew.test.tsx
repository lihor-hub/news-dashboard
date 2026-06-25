// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor, render, screen, fireEvent } from '@testing-library/react';
import { useWhatsNew } from '../hooks/useWhatsNew';
import { WhatsNewDialog } from '../components/WhatsNewDialog';

const STORAGE_KEY = 'lastSeenVersion';

const MOCK_RESPONSE = {
  version: '1.15.3',
  entries: [
    { version: '1.15.3', items: ['Show relevance score', 'Invalidate cache'] },
    { version: '1.15.2', items: ['Fix HuggingFace snippets'] },
  ],
};

function mockFetch(payload: unknown) {
  return vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) })
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

// ── useWhatsNew ──────────────────────────────────────────────────────────────

describe('useWhatsNew', () => {
  it('opens when version differs from lastSeenVersion', async () => {
    vi.stubGlobal('fetch', mockFetch(MOCK_RESPONSE));
    localStorage.setItem(STORAGE_KEY, '1.15.2');
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.open).toBe(true));
    expect(result.current.version).toBe('1.15.3');
    expect(result.current.items).toEqual(['Show relevance score', 'Invalidate cache']);
  });

  it('stays closed when version matches lastSeenVersion', async () => {
    vi.stubGlobal('fetch', mockFetch(MOCK_RESPONSE));
    localStorage.setItem(STORAGE_KEY, '1.15.3');
    const { result } = renderHook(() => useWhatsNew());
    // give the hook time to resolve; open must stay false
    await waitFor(() => expect(result.current.version).toBe(''));
    expect(result.current.open).toBe(false);
  });

  it('opens with empty items when current version has no changelog entry', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({ version: '9.9.9', entries: [{ version: '1.0.0', items: ['old'] }] })
    );
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.open).toBe(true));
    expect(result.current.items).toEqual([]);
  });

  it('opens when no lastSeenVersion is stored', async () => {
    vi.stubGlobal('fetch', mockFetch({ version: 'unknown', entries: [] }));
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.open).toBe(true));
  });

  it('dismiss saves version to localStorage and closes', async () => {
    vi.stubGlobal('fetch', mockFetch(MOCK_RESPONSE));
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.open).toBe(true));
    act(() => result.current.dismiss());
    expect(result.current.open).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('1.15.3');
  });

  it('stays closed on fetch error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network')))
    );
    const { result } = renderHook(() => useWhatsNew());
    // let the rejected promise settle; open must stay false
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.open).toBe(false);
  });
});

// ── WhatsNewDialog ───────────────────────────────────────────────────────────

describe('WhatsNewDialog', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      }
    );
  });

  function makeState(overrides?: Partial<ReturnType<typeof useWhatsNew>>) {
    return {
      open: true,
      version: '1.15.3',
      items: ['Show relevance score', 'Invalidate cache'],
      dismiss: vi.fn(),
      ...overrides,
    };
  }

  it('renders version and items when open', () => {
    render(<WhatsNewDialog state={makeState()} />);
    expect(screen.getByText("What's new in v1.15.3")).toBeTruthy();
    expect(screen.getByText('Show relevance score')).toBeTruthy();
    expect(screen.getByText('Invalidate cache')).toBeTruthy();
  });

  it('calls dismiss when Got it is clicked', () => {
    const dismiss = vi.fn();
    render(<WhatsNewDialog state={makeState({ dismiss })} />);
    fireEvent.click(screen.getByRole('button', { name: /got it/i }));
    expect(dismiss).toHaveBeenCalledOnce();
  });

  it('renders nothing when open is false', () => {
    render(<WhatsNewDialog state={makeState({ open: false })} />);
    expect(screen.queryByText("What's new in v1.15.3")).toBeNull();
  });
});
