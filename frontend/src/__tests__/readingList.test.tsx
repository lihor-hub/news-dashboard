// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
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
