// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { DragEndEvent } from '@dnd-kit/core';
import { ReadingListPage } from '../pages/ReadingListPage';
import * as readingListApi from '../api/readingListApi';
import type { ReadingListItem } from '../api/readingListApi';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

let capturedOnDragEnd: ((event: DragEndEvent) => void) | undefined;

vi.mock('@dnd-kit/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@dnd-kit/core')>();
  return {
    ...actual,
    DndContext: ({
      children,
      onDragEnd,
    }: {
      children: ReactNode;
      onDragEnd: (event: DragEndEvent) => void;
    }) => {
      capturedOnDragEnd = onDragEnd;
      return children;
    },
  };
});

function makeItem(overrides: Partial<ReadingListItem> = {}): ReadingListItem {
  return {
    id: 1,
    user_id: 1,
    url: 'https://example.com/post',
    normalized_url: 'https://example.com/post',
    title: 'Great post',
    description: 'A very insightful post.',
    image_url: null,
    site_name: 'Example Blog',
    kind: 'article',
    fetch_status: 'ok',
    fetch_error: null,
    fetched_at: '2026-07-03T10:00:00Z',
    summary: null,
    summary_status: 'pending',
    status: 'unread',
    priority: 1,
    note: null,
    created_at: '2026-07-03T09:00:00Z',
    done_at: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReadingListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ReadingListPage', () => {
  it('renders fetched items with their metadata', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Great post')).toBeTruthy();
    });
    expect(screen.getByText('Example Blog')).toBeTruthy();
    expect(screen.getByText('A very insightful post.')).toBeTruthy();
  });

  it('shows a retryable load error instead of the empty state', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockRejectedValue(new Error('offline'));

    renderPage();

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText('Could not load reading list')).toBeTruthy();
    expect(screen.queryByText('Your reading list is empty')).toBeNull();
  });

  it('sends search and type filters to the reading list API', async () => {
    const fetchSpy = vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);

    renderPage();
    await screen.findByText('Great post');

    await userEvent.type(screen.getByPlaceholderText(/search saved links/i), 'video');
    await userEvent.selectOptions(screen.getByLabelText(/filter by type/i), 'video');

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith({
        status: 'unread',
        q: 'video',
        kind: 'video',
      });
    });
  });

  it('clears search and type filters without a page reload', async () => {
    const fetchSpy = vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);

    renderPage();
    await screen.findByText('Great post');

    await userEvent.type(screen.getByPlaceholderText(/search saved links/i), 'briefing');
    await userEvent.selectOptions(screen.getByLabelText(/filter by type/i), 'article');
    await userEvent.click(screen.getByRole('button', { name: /clear filters/i }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith({
        status: 'unread',
        q: '',
        kind: undefined,
      });
    });
  });

  it('shows a no-matches empty state for active filters', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([]);

    renderPage();
    await screen.findByText('Your reading list is empty');
    await userEvent.type(screen.getByPlaceholderText(/search saved links/i), 'missing');

    expect(await screen.findByText('No matching saved links')).toBeTruthy();
    expect(screen.getByText(/clear search or type filters/i)).toBeTruthy();
  });

  it('reveals the AI summary when the toggle is clicked', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ summary: 'A concise take on the post.', summary_status: 'ok' }),
    ]);

    renderPage();
    const toggle = await screen.findByRole('button', { name: /ai summary/i });
    expect(screen.queryByText('A concise take on the post.')).toBeNull();

    await userEvent.click(toggle);
    expect(screen.getByText('A concise take on the post.')).toBeTruthy();
  });

  it('does not show an AI summary toggle when no summary is available', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem({ summary: null })]);

    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Great post')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: /ai summary/i })).toBeNull();
  });

  it('shows a pending placeholder while metadata is being fetched', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ title: null, description: null, site_name: null, fetch_status: 'pending' }),
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('https://example.com/post')).toBeTruthy();
    });
    expect(screen.getByText(/fetching preview/i)).toBeTruthy();
  });

  it('adds a pasted link', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([]);
    const addSpy = vi
      .spyOn(readingListApi, 'addReadingListItem')
      .mockResolvedValue(makeItem({ fetch_status: 'pending' }));

    renderPage();
    const input = await screen.findByPlaceholderText(/paste a link/i);
    await userEvent.type(input, 'https://example.com/post');
    await userEvent.click(screen.getByRole('button', { name: /add/i }));

    await waitFor(() => {
      expect(addSpy).toHaveBeenCalledWith('https://example.com/post');
    });
  });

  it('marks an item as done', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);
    const updateSpy = vi
      .spyOn(readingListApi, 'updateReadingListItem')
      .mockResolvedValue(makeItem({ status: 'done' }));

    renderPage();
    await screen.findByText('Great post');
    await userEvent.click(screen.getByRole('button', { name: 'Mark as done' }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(1, { status: 'done' });
    });
  });

  it('reorders items with the move-down control', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ id: 1, title: 'First' }),
      makeItem({ id: 2, title: 'Second', priority: 2 }),
    ]);
    const reorderSpy = vi.spyOn(readingListApi, 'reorderReadingList').mockResolvedValue([]);

    renderPage();
    await screen.findByText('First');
    const [moveFirstDown] = screen.getAllByRole('button', { name: 'Move down' });
    await userEvent.click(moveFirstDown);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith([2, 1]);
    });
  });

  it('renders a drag handle for each item to support drag-and-drop reordering', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ id: 1, title: 'First' }),
      makeItem({ id: 2, title: 'Second', priority: 2 }),
    ]);

    renderPage();
    await screen.findByText('First');

    expect(screen.getAllByRole('button', { name: 'Drag to reorder' })).toHaveLength(2);
  });

  it('reorders items when a drag-and-drop gesture completes', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ id: 1, title: 'First' }),
      makeItem({ id: 2, title: 'Second', priority: 2 }),
    ]);
    const reorderSpy = vi.spyOn(readingListApi, 'reorderReadingList').mockResolvedValue([]);

    renderPage();
    await screen.findByText('First');

    expect(capturedOnDragEnd).toBeDefined();
    capturedOnDragEnd?.({
      active: { id: 1 },
      over: { id: 2 },
    } as DragEndEvent);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith([2, 1]);
    });
  });

  it('deletes an item', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);
    const deleteSpy = vi.spyOn(readingListApi, 'deleteReadingListItem').mockResolvedValue();

    renderPage();
    await screen.findByText('Great post');
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(1);
    });
  });

  it('switches to the archived filter and fetches archived items', async () => {
    const fetchSpy = vi
      .spyOn(readingListApi, 'fetchReadingList')
      .mockResolvedValue([makeItem({ status: 'archived' })]);

    renderPage();
    await screen.findByText('Great post');

    await userEvent.click(screen.getByRole('button', { name: 'archived' }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith({
        status: 'archived',
        q: '',
        kind: undefined,
      });
    });
  });

  it('shows an empty state tailored to the archived filter', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([]);

    renderPage();
    await screen.findByText('Your reading list is empty');
    await userEvent.click(screen.getByRole('button', { name: 'archived' }));

    expect(await screen.findByText('Nothing archived yet')).toBeTruthy();
  });

  it('archives an unread item', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([makeItem()]);
    const updateSpy = vi
      .spyOn(readingListApi, 'updateReadingListItem')
      .mockResolvedValue(makeItem({ status: 'archived' }));

    renderPage();
    await screen.findByText('Great post');
    await userEvent.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(1, { status: 'archived' });
    });
  });

  it('restores an archived item to unread', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ status: 'archived' }),
    ]);
    const updateSpy = vi
      .spyOn(readingListApi, 'updateReadingListItem')
      .mockResolvedValue(makeItem({ status: 'unread' }));

    renderPage();
    await screen.findByText('Great post');
    await userEvent.click(screen.getByRole('button', { name: 'Restore to unread' }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(1, { status: 'unread' });
    });
  });

  it('does not show an archive button for already-archived items', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([
      makeItem({ status: 'archived' }),
    ]);

    renderPage();
    await screen.findByText('Great post');

    expect(screen.queryByRole('button', { name: 'Archive' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Mark as done' })).toBeNull();
  });

  it('imports a Pocket export and shows the added/skipped/failed summary', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([]);
    const importSpy = vi
      .spyOn(readingListApi, 'importReadingList')
      .mockResolvedValue({ added: 2, skipped: 1, failed: 0 });

    renderPage();
    const file = new File(['title,url\nA,https://example.com/a\n'], 'pocket.csv', {
      type: 'text/csv',
    });
    const input = screen.getByLabelText(/import reading list export/i);
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(importSpy).toHaveBeenCalledWith(file, 'pocket');
    });
    expect(await screen.findByText(/2 added/)).toBeTruthy();
  });

  it('shows an error message when import fails', async () => {
    vi.spyOn(readingListApi, 'fetchReadingList').mockResolvedValue([]);
    vi.spyOn(readingListApi, 'importReadingList').mockRejectedValue(new Error('bad file'));

    renderPage();
    const file = new File(['not json'], 'omnivore.json', { type: 'application/json' });
    const input = screen.getByLabelText(/import reading list export/i);
    await userEvent.upload(input, file);

    expect(await screen.findByText(/import failed: bad file/i)).toBeTruthy();
  });
});
