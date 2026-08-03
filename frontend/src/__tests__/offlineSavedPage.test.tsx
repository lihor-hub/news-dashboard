// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { OfflineSavedPage } from '../pages/OfflineSavedPage';
import { saveOfflineArticle } from '../lib/offline';

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, 'caches', {
    configurable: true,
    value: {
      open: vi.fn().mockResolvedValue({
        add: vi.fn().mockResolvedValue(undefined),
        delete: vi.fn().mockResolvedValue(true),
      }),
    },
  });
});

describe('OfflineSavedPage', () => {
  it('shows saved offline articles with article links', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Cached article',
      source: 'Example Feed',
      url: 'https://example.com/cached',
    });

    render(
      <MemoryRouter>
        <OfflineSavedPage />
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: 'Cached article' });
    expect(link.getAttribute('href')).toBe('/a/42');
    expect(screen.getByText('Example Feed')).toBeTruthy();
  });

  it('removes saved articles from the list', async () => {
    await saveOfflineArticle({
      id: 42,
      title: 'Cached article',
      source: 'Example Feed',
      url: 'https://example.com/cached',
    });

    render(
      <MemoryRouter>
        <OfflineSavedPage />
      </MemoryRouter>
    );

    await userEvent.click(screen.getByRole('button', { name: 'Remove Cached article' }));

    await waitFor(() => expect(screen.queryByText('Cached article')).toBeNull());
    expect(screen.getByText('No offline articles')).toBeTruthy();
  });
});
