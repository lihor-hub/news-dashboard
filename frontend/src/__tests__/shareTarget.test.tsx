// @vitest-environment happy-dom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import * as readingListApi from '../api/readingListApi';
import { ShareTargetPage } from '../pages/ShareTargetPage';

const testRoutes = [
  { path: '/share-target', element: <ShareTargetPage /> },
  { path: '/a/:id', element: <div>Reader</div> },
  { path: '/reading-list', element: <div>Reading list</div> },
];

function renderPage(initialEntry: string) {
  const router = createMemoryRouter(testRoutes, { initialEntries: [initialEntry] });
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
  return router;
}

describe('ShareTargetPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('saves the shared URL as an article and navigates to the reader', async () => {
    vi.spyOn(api, 'saveSharedUrl').mockResolvedValue({ id: 42 } as never);
    const router = renderPage(
      '/share-target?title=Post&text=Note&url=https%3A%2F%2Fexample.com%2Fpost'
    );

    await userEvent.click(await screen.findByRole('button', { name: /save as article/i }));

    await waitFor(() =>
      expect(api.saveSharedUrl).toHaveBeenCalledWith({
        url: 'https://example.com/post',
        title: 'Post',
        text: 'Note',
      })
    );
    await waitFor(() => expect(router.state.location.pathname).toBe('/a/42'));
  });

  it('saves the shared URL to the reading list and navigates there', async () => {
    const addSpy = vi
      .spyOn(readingListApi, 'addReadingListItem')
      .mockResolvedValue({ id: 7 } as never);
    const router = renderPage('/share-target?url=https%3A%2F%2Fexample.com%2Fvideo');

    await userEvent.click(await screen.findByRole('button', { name: /save to reading list/i }));

    await waitFor(() => expect(addSpy).toHaveBeenCalledWith('https://example.com/video'));
    await waitFor(() => expect(router.state.location.pathname).toBe('/reading-list'));
  });

  it('shows a graceful error when the share payload has no URL', async () => {
    const saveSpy = vi.spyOn(api, 'saveSharedUrl');
    renderPage('/share-target?text=just+words');

    expect(await screen.findByText('Could not save link')).toBeTruthy();
    expect(saveSpy).not.toHaveBeenCalled();
  });
});
