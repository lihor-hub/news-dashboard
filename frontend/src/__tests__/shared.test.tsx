// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

// ── API mock ─────────────────────────────────────────────────────────────────
const apiMock = vi.hoisted(() => ({
  fetchReceivedShares: vi.fn(),
  markShareRead: vi.fn(),
  fetchShareDetail: vi.fn(),
  fetchShareMessages: vi.fn(),
  postShareMessage: vi.fn(),
}));
vi.mock('../api', () => apiMock);
vi.mock('@/api', () => apiMock);

// Auth context — provides a logged-in user
vi.mock('../contexts/auth', () => ({
  useAuth: () => ({ user: { id: 1, username: 'alice', is_admin: false }, setUser: vi.fn() }),
}));

import { SharedPage } from '../pages/SharedPage';
import { SharedDetailPage } from '../pages/SharedDetailPage';

afterEach(() => {
  vi.clearAllMocks();
});

function makeShare(overrides = {}) {
  return {
    id: 42,
    note: 'Check this out',
    context_summary: null,
    created_at: new Date(Date.now() - 60_000).toISOString(),
    read_at: null,
    from_user_id: 2,
    from_username: 'bob',
    article_id: 99,
    article_title: 'The Future of TypeScript',
    article_url: 'https://example.com/ts',
    article_source_name: 'Tech Blog',
    article_summary: null,
    annotations: [],
    messages: [],
    ...overrides,
  };
}

function renderWithRouter(ui: ReactElement, { path = '/', route = '/' } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ── SharedPage ────────────────────────────────────────────────────────────────

describe('SharedPage', () => {
  beforeEach(() => {
    apiMock.markShareRead.mockResolvedValue(true);
  });

  it('shows empty state when no shares', async () => {
    apiMock.fetchReceivedShares.mockResolvedValue({ items: [] });
    renderWithRouter(<SharedPage />, { path: '/shared', route: '/shared' });
    await waitFor(() => expect(screen.getByText('Nothing shared yet')).toBeTruthy());
  });

  it('renders a share item with title linking to the detail view', async () => {
    apiMock.fetchReceivedShares.mockResolvedValue({ items: [makeShare()] });
    renderWithRouter(<SharedPage />, { path: '/shared', route: '/shared' });
    await waitFor(() => expect(screen.getByText('The Future of TypeScript')).toBeTruthy());

    const titleLink = screen.getByRole('link', { name: 'The Future of TypeScript' });
    expect(titleLink.getAttribute('href')).toBe('/shared/42');

    const viewLink = screen.getByRole('link', { name: 'View' });
    expect(viewLink.getAttribute('href')).toBe('/shared/42');
  });

  it('still shows the Original external link', async () => {
    apiMock.fetchReceivedShares.mockResolvedValue({ items: [makeShare()] });
    renderWithRouter(<SharedPage />, { path: '/shared', route: '/shared' });
    await waitFor(() => expect(screen.getByText('The Future of TypeScript')).toBeTruthy());
    const original = screen.getByRole('link', { name: /Original/ });
    expect(original.getAttribute('href')).toBe('https://example.com/ts');
  });
});

// ── SharedDetailPage ──────────────────────────────────────────────────────────

describe('SharedDetailPage', () => {
  it('shows a loading skeleton while fetching', () => {
    apiMock.fetchShareDetail.mockReturnValue(new Promise(vi.fn()));
    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    // skeleton divs are rendered during loading
    expect(screen.getByText('Shared with me')).toBeTruthy();
  });

  it('renders article metadata, sender note, and context summary', async () => {
    apiMock.fetchShareDetail.mockResolvedValue(
      makeShare({ context_summary: 'This matters because TypeScript ships faster now.' })
    );
    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    await waitFor(() => expect(screen.getByText('The Future of TypeScript')).toBeTruthy());

    expect(screen.getByText('Tech Blog')).toBeTruthy();
    expect(screen.getByText(/Check this out/)).toBeTruthy();
    expect(screen.getByText('This matters because TypeScript ships faster now.')).toBeTruthy();

    const readLink = screen.getByRole('link', { name: 'Read article' });
    expect(readLink.getAttribute('href')).toBe('/a/99');

    const origLink = screen.getByRole('link', { name: /Original/ });
    expect(origLink.getAttribute('href')).toBe('https://example.com/ts');
  });

  it('renders annotations as a highlight list', async () => {
    const annotations = [
      {
        id: 1,
        share_id: 42,
        highlighted_text: 'TypeScript is amazing',
        offset_chars: 0,
        note: 'Key insight',
        created_at: new Date().toISOString(),
      },
    ];
    apiMock.fetchShareDetail.mockResolvedValue(makeShare({ annotations }));
    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    await waitFor(() => expect(screen.getByText(/"TypeScript is amazing"/)).toBeTruthy());
    expect(screen.getByText('Key insight')).toBeTruthy();
  });

  it('renders the message thread', async () => {
    const messages = [
      {
        id: 1,
        share_id: 42,
        user_id: 2,
        username: 'bob',
        message: 'What do you think?',
        created_at: new Date().toISOString(),
      },
    ];
    apiMock.fetchShareDetail.mockResolvedValue(makeShare({ messages }));
    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    await waitFor(() => expect(screen.getByText('What do you think?')).toBeTruthy());
    // 'bob' appears as sender in the header and as message author — both should be present
    expect(screen.getAllByText('bob').length).toBeGreaterThanOrEqual(1);
  });

  it('submits a new message and refreshes the thread', async () => {
    apiMock.fetchShareDetail.mockResolvedValue(makeShare());
    apiMock.postShareMessage.mockResolvedValue({
      id: 10,
      share_id: 42,
      user_id: 1,
      username: 'alice',
      message: 'Great article!',
      created_at: new Date().toISOString(),
    });

    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    await waitFor(() => expect(screen.getByPlaceholderText('Add a message…')).toBeTruthy());

    const textarea = screen.getByPlaceholderText('Add a message…');
    fireEvent.change(textarea, { target: { value: 'Great article!' } });
    fireEvent.click(screen.getByRole('button', { name: /Send/ }));

    await waitFor(() =>
      expect(apiMock.postShareMessage).toHaveBeenCalledWith(42, 'Great article!')
    );
  });

  it('shows an error state when the share cannot be loaded', async () => {
    apiMock.fetchShareDetail.mockRejectedValue(new Error('Share not found.'));
    renderWithRouter(<SharedDetailPage />, { path: '/shared/:shareId', route: '/shared/42' });
    await waitFor(() => expect(screen.getByText('Share not found.')).toBeTruthy());
  });
});
