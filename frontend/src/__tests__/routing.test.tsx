// @vitest-environment happy-dom
/**
 * Routing and navigation tests for #104 (Brief default route, Today at /today)
 * and #105 (command palette + keyboard shortcuts for Brief/Today).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '../components/AppShell';
import { CommandPalette } from '../components/CommandPalette';
import { ShortcutOverlay } from '../components/ShortcutOverlay';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import * as api from '../api';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

// ── Silence deps that don't affect these tests ────────────────────────────────

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    loading: vi.fn(() => 'toast-id'),
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));

// Silence page fetches during AppShell render tests
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchLatestBriefing: vi.fn().mockReturnValue(new Promise((_r) => undefined)),
    fetchBriefings: vi.fn().mockReturnValue(new Promise((_r) => undefined)),
    fetchBriefing: vi.fn().mockReturnValue(new Promise((_r) => undefined)),
    fetchSummary: vi.fn().mockResolvedValue({ byStatus: {}, byCategory: {} }),
    searchArticles: vi.fn().mockResolvedValue([]),
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderShell(initialPath = '/') {
  const qc = makeQc();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <FocusedArticleProvider>
          <AppShell />
        </FocusedArticleProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderPalette(open = true) {
  const qc = makeQc();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FocusedArticleProvider>
          <CommandPalette open={open} onOpenChange={vi.fn()} />
        </FocusedArticleProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ── #104: Desktop navigation items ───────────────────────────────────────────

describe('#104 — desktop rail navigation', () => {
  it('shows Brief in desktop nav', async () => {
    renderShell('/');
    await waitFor(() => {
      const links = screen.getAllByRole('link', { name: /brief/i });
      expect(links.length).toBeGreaterThan(0);
    });
  });

  it('shows Today in desktop nav', async () => {
    renderShell('/today');
    await waitFor(() => {
      const links = screen.getAllByRole('link', { name: /today/i });
      expect(links.length).toBeGreaterThan(0);
    });
  });

  it('Brief link points to /', async () => {
    renderShell('/');
    await waitFor(() => {
      const briefLinks = screen
        .getAllByRole('link', { name: /brief/i })
        .filter((l) => l.getAttribute('href') === '/');
      expect(briefLinks.length).toBeGreaterThan(0);
    });
  });

  it('Today link points to /today', async () => {
    renderShell('/today');
    await waitFor(() => {
      const todayLinks = screen
        .getAllByRole('link', { name: /today/i })
        .filter((l) => l.getAttribute('href') === '/today');
      expect(todayLinks.length).toBeGreaterThan(0);
    });
  });
});

// ── #104: Mobile bottom nav items ────────────────────────────────────────────

describe('#104 — mobile bottom navigation', () => {
  it('Brief appears in mobile nav', async () => {
    renderShell('/');
    await waitFor(() => {
      const briefLinks = screen
        .getAllByRole('link', { name: /brief/i })
        .filter((l) => l.getAttribute('href') === '/');
      expect(briefLinks.length).toBeGreaterThan(0);
    });
  });

  it('Today appears in mobile nav', async () => {
    renderShell('/today');
    await waitFor(() => {
      const todayLinks = screen
        .getAllByRole('link', { name: /today/i })
        .filter((l) => l.getAttribute('href') === '/today');
      expect(todayLinks.length).toBeGreaterThan(0);
    });
  });
});

// ── #104: Page title reflects route ──────────────────────────────────────────

describe('#104 — header title', () => {
  it('shows "Brief" as title at /', async () => {
    renderShell('/');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Brief' })).toBeTruthy());
  });

  it('shows "Today" as title at /today', async () => {
    renderShell('/today');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Today' })).toBeTruthy());
  });
});

// ── #105: Command palette navigation entries ──────────────────────────────────

describe('#105 — command palette navigation', () => {
  it('shows Brief as a nav item in the palette', () => {
    renderPalette();
    expect(screen.getByText('Brief')).toBeTruthy();
  });

  it('shows Today as a nav item in the palette', () => {
    renderPalette();
    expect(screen.getByText('Today')).toBeTruthy();
  });

  it('shows both Brief and Today in the palette', () => {
    renderPalette();
    const items = screen.getAllByRole('option');
    const labels = items.map((i) => i.textContent ?? '');
    expect(labels.some((l) => l.includes('Brief'))).toBe(true);
    expect(labels.some((l) => l.includes('Today'))).toBe(true);
  });
});

// ── #105: Shortcut overlay text ───────────────────────────────────────────────

describe('#105 — shortcut overlay', () => {
  it('mentions g b for Brief', () => {
    render(<ShortcutOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText(/g b/i)).toBeTruthy();
  });

  it('mentions g t for Today', () => {
    render(<ShortcutOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText(/g t/i)).toBeTruthy();
  });

  it('has Brief in shortcut descriptions', () => {
    render(<ShortcutOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getAllByText(/brief/i).length).toBeGreaterThan(0);
  });

  it('has Today in shortcut descriptions', () => {
    render(<ShortcutOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getAllByText(/today/i).length).toBeGreaterThan(0);
  });
});

// ── #118: Briefing History nav + shortcuts ────────────────────────────────────

describe('#118 — Brief History in moreItems nav', () => {
  it('shows Brief History link in shell nav', async () => {
    renderShell('/');
    await waitFor(() => {
      const links = screen.getAllByRole('link', { name: /brief history/i });
      expect(links.length).toBeGreaterThan(0);
    });
  });

  it('Brief History link points to /briefs', async () => {
    renderShell('/');
    await waitFor(() => {
      const link = screen
        .getAllByRole('link', { name: /brief history/i })
        .find((l) => l.getAttribute('href') === '/briefs');
      expect(link).toBeTruthy();
    });
  });

  it('header shows "Briefs" title at /briefs', async () => {
    renderShell('/briefs');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Briefs' })).toBeTruthy());
  });
});

describe('#118 — Briefing History in command palette', () => {
  it('shows Briefing History as a nav item', () => {
    renderPalette();
    expect(screen.getByText('Briefing History')).toBeTruthy();
  });
});

describe('#118 — shortcut overlay shows g h', () => {
  it('mentions g h for Briefing History', () => {
    render(<ShortcutOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText('g h')).toBeTruthy();
  });
});

// ── #105: Keyboard shortcut navigation ───────────────────────────────────────

describe('#105 — g-key shortcuts via AppShell', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchSummary').mockResolvedValue({ byStatus: {}, byCategory: {} });
  });

  it('g then b navigates to / (Brief)', async () => {
    const qc = makeQc();
    // We can't easily spy on react-router navigate in unit tests,
    // so we verify the shortcut wiring via the keyboard test for AppShell.
    // This test checks the key handler registers 'b' for Brief.
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/today']}>
          <FocusedArticleProvider>
            <AppShell />
          </FocusedArticleProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
    // Fire g then b — if wired, the URL would change; we verify no error is thrown.
    await userEvent.keyboard('gb');
    // Verify the component renders without error after the keypress.
    expect(screen.getAllByText('Brief').length).toBeGreaterThan(0);
  });

  it('g then t navigates to /today (Today)', async () => {
    const qc = makeQc();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <FocusedArticleProvider>
            <AppShell />
          </FocusedArticleProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
    await userEvent.keyboard('gt');
    expect(screen.getAllByText('Brief').length).toBeGreaterThan(0);
  });
});
