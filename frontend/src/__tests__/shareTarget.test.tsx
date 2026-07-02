// @vitest-environment happy-dom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import { ShareTargetPage } from '../pages/ShareTargetPage';

const testRoutes = [
  { path: '/share-target', element: <ShareTargetPage /> },
  { path: '/a/:id', element: <div>Reader</div> },
];

describe('ShareTargetPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('saves the shared URL and navigates to the article reader', async () => {
    vi.spyOn(api, 'saveSharedUrl').mockResolvedValue({ id: 42 } as never);
    const router = createMemoryRouter(testRoutes, {
      initialEntries: ['/share-target?title=Post&text=Note&url=https%3A%2F%2Fexample.com%2Fpost'],
    });
    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    await waitFor(() =>
      expect(api.saveSharedUrl).toHaveBeenCalledWith({
        url: 'https://example.com/post',
        title: 'Post',
        text: 'Note',
      })
    );
    await waitFor(() => expect(router.state.location.pathname).toBe('/a/42'));
  });

  it('shows a graceful error when the share payload has no URL', async () => {
    const saveSpy = vi.spyOn(api, 'saveSharedUrl');
    const router = createMemoryRouter(testRoutes, {
      initialEntries: ['/share-target?text=just+words'],
    });
    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    expect(await screen.findByText('Could not save link')).toBeTruthy();
    expect(saveSpy).not.toHaveBeenCalled();
  });
});
